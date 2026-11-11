#!/usr/bin/env python3
"""Quarto post-render hook: print the styled HTML exactly as the portfolio PDFs.

The QMD sources own all content and formatting. This hook adds no CSS or layout
changes. Requires Chrome/Chromium and websocket-client (included with JupyterLab).
Set CHROME_PATH if the browser is not installed in a standard location.
"""

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from urllib.request import ProxyHandler, build_opener

import websocket

ROOT = Path(__file__).resolve().parents[1]
REPORTS = {ROOT / "report" / f"{name}.html" for name in ("report", "showcase")}


def find_chrome():
    candidates = [
        os.environ.get("CHROME_PATH"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        str(Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe"),
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    ]
    for path in candidates:
        if path and Path(path).is_file():
            return path
    raise RuntimeError("Install Chrome/Chromium or set CHROME_PATH to its executable")


class DevTools:
    def __init__(self, url):
        self.connection = websocket.create_connection(url, timeout=45, suppress_origin=True)
        self.sequence = 0

    def call(self, method, **params):
        self.sequence += 1
        self.connection.send(json.dumps({"id": self.sequence, "method": method, "params": params}))
        while True:
            message = json.loads(self.connection.recv())
            if message.get("id") == self.sequence:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})


def export_pdf(chrome, source, destination):
    with tempfile.TemporaryDirectory(prefix="thin-film-portfolio-") as temporary:
        temp = Path(temporary)
        with (temp / "chrome.log").open("w") as log:
            process = subprocess.Popen(
                [chrome, "--headless", "--disable-gpu", "--disable-extensions",
                 "--disable-background-networking", "--remote-debugging-port=0",
                 "--remote-debugging-address=127.0.0.1", f"--user-data-dir={temp}", "about:blank"],
                stdout=log, stderr=log,
            )
            client = None
            try:
                deadline = time.monotonic() + 20
                active_port = temp / "DevToolsActivePort"
                while not active_port.exists():
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("Chrome did not start: " + (temp / "chrome.log").read_text()[-1500:])
                    time.sleep(0.1)
                port = int(active_port.read_text().splitlines()[0])
                opener = build_opener(ProxyHandler({}))
                with opener.open(f"http://127.0.0.1:{port}/json/list", timeout=10) as response:
                    page = next(page for page in json.load(response) if page["type"] == "page")
                client = DevTools(page["webSocketDebuggerUrl"])
                client.call("Page.enable")
                client.call("Page.navigate", url=source.resolve().as_uri())
                client.call("Emulation.setEmulatedMedia", media="print")
                ready = client.call(
                    "Runtime.evaluate",
                    expression="""(async () => {
                      if (document.readyState !== 'complete') {
                        await new Promise(resolve => addEventListener('load', resolve, {once: true}));
                      }
                      await document.fonts.ready;
                      if (window.MathJax?.startup?.promise) await window.MathJax.startup.promise;
                      await Promise.all([...document.images].map(image => image.decode().catch(() => {})));
                      return [...document.images].filter(image => !image.naturalWidth).length;
                    })()""",
                    awaitPromise=True,
                    returnByValue=True,
                )
                if ready.get("exceptionDetails") or ready.get("result", {}).get("value") != 0:
                    raise RuntimeError(f"Page resources did not finish loading: {ready}")
                # US Letter and Chrome's default 1 cm margins match soccer_xg's PDF.
                result = client.call(
                    "Page.printToPDF", printBackground=True, displayHeaderFooter=False,
                    paperWidth=8.5, paperHeight=11,
                )
                data = base64.b64decode(result["data"])
                if len(data) < 10000 or not data.startswith(b"%PDF-"):
                    raise RuntimeError(f"Invalid PDF exported for {source.name}")
                pending = destination.with_suffix(".pdf.tmp")
                pending.write_bytes(data)
                pending.replace(destination)
                print(f"Created {destination.relative_to(ROOT) if destination.is_relative_to(ROOT) else destination}")
            finally:
                if client:
                    client.connection.close()
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main():
    outputs = os.environ.get("QUARTO_PROJECT_OUTPUT_FILES", "").splitlines()
    sources = sorted({(ROOT / name).resolve() for name in outputs} & REPORTS)
    if not sources:
        return
    chrome = find_chrome()
    for source in sources:
        export_pdf(chrome, source, source.with_suffix(".pdf"))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Render both QMD sources to native research PDFs and companion HTML.

Requires Quarto and a TeX distribution (install with `quarto install tinytex`).
Pass --quarto /path/to/quarto to use a CLI that is not on PATH.
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quarto", default=shutil.which("quarto"), help="Quarto executable")
    args = parser.parse_args()
    if not args.quarto:
        parser.error("Quarto is required; install it from https://quarto.org/docs/get-started/")
    env = os.environ.copy()
    env["QUARTO_PYTHON"] = sys.executable
    subprocess.run(
        [args.quarto, "render", "--to", "all", "--execute-daemon", "0"],
        cwd=ROOT,
        env=env,
        check=True,
    )


if __name__ == "__main__":
    main()

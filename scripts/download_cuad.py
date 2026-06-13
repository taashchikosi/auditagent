"""Fetch the full CUAD corpus (510 contracts, CC BY 4.0) from GitHub.

The repo ships a real 20-contract test-split SAMPLE so `make eval` runs with
zero download. This pulls the FULL corpus for a complete eval (`make eval-full`).

    python scripts/download_cuad.py            # clone + report
    python scripts/download_cuad.py --extract  # clone, unzip, write test json

Source: The Atticus Project — CUAD v1, CC BY 4.0.
  https://github.com/TheAtticusProject/cuad
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = "https://github.com/TheAtticusProject/cuad.git"
DEST = Path(__file__).resolve().parent.parent / "data" / "cuad"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true", help="unzip + write test json")
    args = ap.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)
    clone_dir = DEST / "_cuad_repo"
    if not clone_dir.exists():
        print(f"Cloning {REPO} (shallow) ...")
        subprocess.run(
            ["git", "clone", "--depth", "1", REPO, str(clone_dir)], check=True
        )
    else:
        print("Repo already cloned.")

    if not args.extract:
        print(f"Done. data.zip is at {clone_dir / 'data.zip'}. Re-run with --extract.")
        return 0

    print("Extracting data.zip ...")
    with zipfile.ZipFile(clone_dir / "data.zip") as z:
        z.extractall(DEST / "_extracted")
    test_src = DEST / "_extracted" / "test.json"
    out = DEST / "CUADv1_test.json"
    out.write_text(test_src.read_text(encoding="utf-8"))
    n = len(json.loads(out.read_text())["data"])
    print(f"Wrote {out} ({n} held-out test contracts).")
    print("Now run:  python -m auditagent.eval --full data/cuad/CUADv1_test.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

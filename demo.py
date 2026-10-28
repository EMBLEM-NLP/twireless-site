#!/usr/bin/env python3
"""Build the GitHub Pages demo of every design into docs/.

    python3 demo.py

Design 1 goes to docs/ (https://emblem-nlp.github.io/twireless-site/) and each design in
designs/ to docs/<id>/ (for example .../twireless-site/design-2/). Every page gets the preview
banner with links to the same page in the other designs, and shared links get a preview image.
The client's questionnaire web app goes to docs/questionnaire/ (.../twireless-site/questionnaire/).
Needs only the Python standard library: 3.8+ for the designs, 3.10+ for the questionnaire.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = "https://emblem-nlp.github.io"
BASE = "/twireless-site/"


def designs():
    found = [("design-1", "Design 1")]
    for cfg in sorted((ROOT / "designs").glob("*/design.json")):
        d = json.loads(cfg.read_text(encoding="utf-8"))
        found.append((d["id"], d["label"]))
    return found


def main():
    ds = designs()
    paths = {i: BASE if i == "design-1" else f"{BASE}{i}/" for i, _ in ds}
    switch = ";".join(f"{label}={paths[i]}={i}" for i, label in ds)
    for i, _ in ds:  # design 1 first: its build replaces docs/, the others go inside it
        out = ROOT / "docs" if i == "design-1" else ROOT / "docs" / i
        cmd = [sys.executable, str(ROOT / "build.py"), "--demo", "--base-path", paths[i], "--switch", switch,
               "--public-url", SITE + paths[i].rstrip("/"), "--out", str(out)]
        if i != "design-1":
            cmd += ["--design", i]
        subprocess.run(cmd, check=True)
    # The questions for the client, as a page the client can open on a phone. Last, because building design 1 replaces docs/.
    quest = f"{BASE}questionnaire/"
    subprocess.run([sys.executable, str(ROOT / "ops" / "questionnaire" / "build_questionnaire.py"), "app",
                    "--app-out", str(ROOT / "docs" / "questionnaire" / "index.html"), "--url", SITE + quest], check=True)
    for i, _ in ds:
        print(f"{i}: {SITE}{paths[i]}")
    print(f"questionnaire: {SITE}{quest}")


if __name__ == "__main__":
    main()

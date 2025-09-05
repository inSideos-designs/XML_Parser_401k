#!/usr/bin/env python3
"""
Standalone-friendly runner for XML Prompt Filler.

Designed to be packaged as a Windows .exe via PyInstaller (--onefile).

It avoids spawning a Python subprocess and instead imports the
processing module and invokes its main() with redirected stdin/stdout.

Outputs are written to the current working directory so the .exe can be
launched from anywhere and leave results next to where it's run.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from pathlib import Path


# Default input directory (same convention as other tools)
SOURCE_DIR = Path.home() / 'Desktop' / 'Test Folder'

# Output targets go to the current working directory
OUTPUT_DIR = Path.cwd()
OUTPUT_JSON = OUTPUT_DIR / 'output.json'
OUTPUT_CSV = OUTPUT_DIR / 'output.csv'


def build_payload(source_dir: Path) -> dict:
    if not source_dir.exists():
        raise SystemExit(f"Source directory not found: {source_dir}")
    xml_files = sorted([p for p in source_dir.iterdir() if p.suffix.lower() == '.xml'])
    if not xml_files:
        raise SystemExit(f"No .xml files found in: {source_dir}")
    payload = {"xmlFiles": []}
    for p in xml_files:
        try:
            content = p.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            content = p.read_text(errors='ignore')
        payload["xmlFiles"].append({"name": p.name, "content": content})
    return payload


def process_payload_via_module(payload: dict) -> dict:
    # Import here so PyInstaller sees the dependency
    from server import process_local as pl  # type: ignore

    # Redirect stdin/stdout to interact with pl.main()
    orig_stdin = sys.stdin
    orig_stdout = sys.stdout
    try:
        sys.stdin = io.StringIO(json.dumps(payload))
        buf = io.StringIO()
        sys.stdout = buf
        rc = pl.main()
        sys.stdout.flush()
        out_text = buf.getvalue()
    finally:
        sys.stdin = orig_stdin
        sys.stdout = orig_stdout

    if rc != 0:
        # Try parse JSON for structured error
        try:
            data = json.loads(out_text)
        except Exception:
            data = None
        if isinstance(data, dict) and 'error' in data:
            raise SystemExit(f"Processor error: {data['error']}")
        raise SystemExit(f"Processor failed with exit code {rc}. Output was:\n{out_text}")

    try:
        return json.loads(out_text)
    except json.JSONDecodeError as e:
        raise SystemExit(f"Processor returned non-JSON output.\n{e}\nOutput was:\n{out_text}")


def write_csv(result: dict, csv_path: Path) -> None:
    file_names = list(result.get('fileNames') or [])
    rows = list(result.get('rows') or [])
    with csv_path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['PROMPT'] + file_names)
        for r in rows:
            prompt = r.get('promptText', '')
            values = r.get('values', {})
            w.writerow([prompt] + [values.get(name, '') for name in file_names])


def main() -> int:
    print(f"Preparing payload from: {SOURCE_DIR}")
    payload = build_payload(SOURCE_DIR)
    print(f"Found {len(payload['xmlFiles'])} XML files. Running processor…")
    data = process_payload_via_module(payload)

    OUTPUT_JSON.write_text(json.dumps(data, indent=2))
    write_csv(data, OUTPUT_CSV)
    print(f"Success: wrote {OUTPUT_JSON} and {OUTPUT_CSV}")

    # Auto-open CSV where supported
    try:
        if sys.platform == 'darwin':
            import subprocess
            subprocess.run(['open', str(OUTPUT_CSV)], check=False)
        elif sys.platform.startswith('win'):
            os.startfile(str(OUTPUT_CSV))  # type: ignore[attr-defined]
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())


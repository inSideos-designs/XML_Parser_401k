#!/usr/bin/env python3
"""
One-click runner for XML Prompt Filler.

What it does:
- Reads all .xml files from a source directory (default: ~/Desktop/Test Folder)
- Pipes them to server/process_local.py
- Saves the resulting JSON to output.json in this folder
- Optionally opens the output file on macOS

Adjust SOURCE_DIR below if needed.
"""

from __future__ import annotations

import json
import os
import sys
import subprocess
from pathlib import Path

# Configure the default XML source directory (matches existing scripts)
SOURCE_DIR = Path.home() / 'Desktop' / 'Test Folder'

ROOT = Path(__file__).resolve().parent
PROCESSOR = ROOT / 'server' / 'process_local.py'
OUTPUT_JSON = ROOT / 'output.json'
OUTPUT_CSV = ROOT / 'output.csv'


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


def run_processor(payload: dict) -> dict:
    if not PROCESSOR.exists():
        raise SystemExit(f"Processor not found: {PROCESSOR}")
    try:
        completed = subprocess.run(
            [sys.executable, str(PROCESSOR)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=str(ROOT),
        )
    except FileNotFoundError:
        # Fallback to python3 on PATH
        completed = subprocess.run(
            ['python3', str(PROCESSOR)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=str(ROOT),
        )

    stdout = completed.stdout or ''
    stderr = completed.stderr or ''

    if completed.returncode != 0:
        # Try to parse error JSON if any, else surface stderr
        try:
            data = json.loads(stdout)
        except Exception:
            data = None
        if data and isinstance(data, dict) and 'error' in data:
            raise SystemExit(f"Processor error: {data['error']}\n{stderr}")
        else:
            raise SystemExit(f"Processor failed with exit code {completed.returncode}.\nSTDERR:\n{stderr}\nSTDOUT:\n{stdout}")

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise SystemExit(f"Processor returned non-JSON output.\n{e}\nOutput was:\n{stdout}")


def main() -> int:
    print("Preparing payload from:", SOURCE_DIR)
    payload = build_payload(SOURCE_DIR)
    print(f"Found {len(payload['xmlFiles'])} XML files. Running processor…")
    data = run_processor(payload)
    # Always keep JSON for debugging/transforms
    OUTPUT_JSON.write_text(json.dumps(data, indent=2))
    # Also emit CSV for spreadsheet workflows
    try:
        file_names = data.get('fileNames') or []
        rows = data.get('rows') or []
        import csv
        with OUTPUT_CSV.open('w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['PROMPT'] + list(file_names))
            for r in rows:
                prompt = r.get('promptText', '')
                values = r.get('values', {})
                writer.writerow([prompt] + [values.get(name, '') for name in file_names])
    except Exception as e:
        print(f"Warning: failed to write CSV: {e}", file=sys.stderr)
    print(f"Success: wrote {OUTPUT_JSON} and {OUTPUT_CSV}")
    # On macOS, try to open the result for convenience
    if sys.platform == 'darwin':
        try:
            subprocess.run(['open', str(OUTPUT_CSV)], check=False)
        except Exception:
            pass
    elif sys.platform.startswith('win'):
        try:
            os.startfile(str(OUTPUT_CSV))  # type: ignore[attr-defined]
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

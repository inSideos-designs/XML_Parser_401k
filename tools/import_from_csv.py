#!/usr/bin/env python3
"""
Import Map CSV and Data Points CSV into the local user store so the
XML Prompt Filler can run fully offline without Excel.

Writes to: ~/.xml-prompt-filler/{defaultMap.json, optionsByPrompt.json}

Usage:
  python3 tools/import_from_csv.py \
    --map-csv /path/to/Map.csv \
    --datapoints-csv /path/to/PlanExpress.csv \
    [--store-dir ~/.xml-prompt-filler]

CSV formats expected:
  - Map CSV columns: Prompt, Proposed LinkName (Quick optional)
  - Data Points CSV columns: PROMPT, Options Allowed
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List, Optional


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    # Drop BOM if present
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin1", errors="ignore")


def parse_map_csv(path: Path) -> List[Dict[str, str]]:
    text = _read_text(path)
    reader = csv.DictReader(text.splitlines())
    # normalize headers for matching
    def get_row_val(row: Dict[str, str], *candidates: str) -> str:
        for k in row.keys():
            for cand in candidates:
                if k.strip().lower() == cand.strip().lower():
                    return str(row.get(k) or '').strip()
        return ''
    out: List[Dict[str, str]] = []
    for row in reader:
        prompt = get_row_val(row, 'Prompt')
        linknames = get_row_val(row, 'Proposed LinkName', 'Proposed Linkname', 'LinkNames', 'Linknames')
        quick = get_row_val(row, 'Quick', 'Quick Text')
        if not prompt:
            continue
        out.append({'prompt': prompt, 'linknames': linknames, 'quick': quick})
    if not out:
        raise SystemExit(f"No rows parsed from map CSV: {path}")
    return out


def parse_options_csv(path: Path) -> Dict[str, str]:
    text = _read_text(path)
    reader = csv.DictReader(text.splitlines())
    fieldnames = [fn.strip() for fn in (reader.fieldnames or [])]
    def key_for(names: List[str]) -> Optional[str]:
        for want in names:
            for fn in fieldnames:
                if fn.lower() == want.lower():
                    return fn
        return None
    k_prompt = key_for(['PROMPT', 'Prompt'])
    k_options = key_for(['Options Allowed', 'Options'])
    if not k_prompt or not k_options:
        raise SystemExit('Data Points CSV missing required columns: PROMPT and Options Allowed')
    out: Dict[str, str] = {}
    for row in reader:
        p = str(row.get(k_prompt) or '').strip()
        if not p:
            continue
        oa = str(row.get(k_options) or '').strip()
        out[p] = oa
    if not out:
        raise SystemExit(f"No rows parsed from data points CSV: {path}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description='Import Map/Data Points CSV into local user store for XML Prompt Filler')
    ap.add_argument('--map-csv', required=True, type=Path, help='Path to Map CSV (Prompt, Proposed LinkName, Quick optional)')
    ap.add_argument('--datapoints-csv', required=True, type=Path, help='Path to Data Points CSV (PROMPT, Options Allowed)')
    ap.add_argument('--store-dir', type=Path, default=Path.home() / '.xml-prompt-filler', help='Destination directory (default: ~/.xml-prompt-filler)')
    args = ap.parse_args()

    if not args.map_csv.exists():
        raise SystemExit(f"Map CSV not found: {args.map_csv}")
    if not args.datapoints_csv.exists():
        raise SystemExit(f"Data Points CSV not found: {args.datapoints_csv}")

    entries = parse_map_csv(args.map_csv)
    options = parse_options_csv(args.datapoints_csv)

    args.store_dir.mkdir(parents=True, exist_ok=True)
    (args.store_dir / 'defaultMap.json').write_text(json.dumps(entries, indent=2))
    (args.store_dir / 'optionsByPrompt.json').write_text(json.dumps(options, indent=2))
    print('Imported successfully:')
    print('  Map entries  :', len(entries))
    print('  Options items:', len(options))
    print('Saved to      :', args.store_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())


#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import runpy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT_CSV = ROOT / 'output_wave2_template.csv'


def normalize_text(s: str) -> str:
    import re
    return re.sub(r'\s+', ' ', (s or '').strip()).lower()


def build_payload(src: Path) -> dict:
    return {
        'xmlFiles': [
            {'name': p.name, 'content': p.read_text(errors='ignore')}
            for p in sorted(src.glob('*.xml'))
        ]
    }


def run_processor(payload: dict) -> dict:
    from server import process_local as pl  # type: ignore
    orig_stdin, orig_stdout = sys.stdin, sys.stdout
    try:
        sys.stdin = io.StringIO(json.dumps(payload))
        buf = io.StringIO()
        sys.stdout = buf
        rc = pl.main()
        sys.stdout.flush()
        out = buf.getvalue()
    finally:
        sys.stdin, sys.stdout = orig_stdin, orig_stdout
    if rc != 0:
        raise SystemExit(f'processor failed with code {rc}: {out}')
    return json.loads(out)


def employer_name_from_xml(xml_text: str) -> str | None:
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return None
    for field in ('1stAdoptERName', 'EmployerNameA', 'ProjectName', 'PlanNameA'):
        el = root.find(f".//PlanData[@FieldName='{field}']")
        if el is not None and (el.text or '').strip():
            return (el.text or '').strip()
    return None


def norm(s: str) -> str:
    import re
    return re.sub(r'[^a-z0-9]+', '', (s or '').lower())


def map_header_to_xml(header: list[str], payload: dict) -> dict[int, str]:
    # Return: column_index -> xml_file_name
    mapping: dict[int, str] = {}
    # Columns after Options Allowed (index 5 onwards)
    for col_idx, cell in enumerate(header[5:], start=5):
        display = (cell or '').split(' [', 1)[0].strip()
        target_key = norm(display)
        # Find xml with matching employer display name
        for item in payload.get('xmlFiles', []):
            disp = employer_name_from_xml(item.get('content', '')) or ''
            if norm(disp) == target_key:
                mapping[col_idx] = item.get('name', '')
                break
    return mapping


def read_verified_from_csv(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    with path.open(newline='') as f:
        for r in csv.reader(f):
            rows.append(r)
    return rows


def read_verified_from_xlsx_with_helpers(xlsx: Path, sheet: str, helpers: Path) -> list[list[str]]:
    mod = runpy.run_path(str(helpers))
    read_xlsx_named_sheet_rows = mod['read_xlsx_named_sheet_rows']
    return read_xlsx_named_sheet_rows(xlsx, sheet)


def default_xml_dir() -> Path:
    for c in [ROOT / 'samples', ROOT / 'input', Path.cwd()]:
        try:
            if c.exists() and any(p.suffix.lower() == '.xml' for p in c.iterdir()):
                return c
        except Exception:
            continue
    return ROOT


def main() -> int:
    ap = argparse.ArgumentParser(description='Export aligned CSV to the verified template header')
    ap.add_argument('--verified-csv', type=str, default=None, help='Verified CSV template to align against')
    ap.add_argument('--verified-xlsx', type=str, default=None, help='Verified XLSX template (requires --helpers to read)')
    ap.add_argument('--verified-sheet', type=str, default='Plan Express Data Points', help='Sheet name in XLSX (default: Plan Express Data Points)')
    ap.add_argument('--helpers', type=str, default=None, help='Path to a Python file exporting read_xlsx_named_sheet_rows and normalize_text')
    ap.add_argument('--xml-dir', type=str, default=None, help='Directory containing .xml files (default: autodetect samples/input/cwd)')
    ap.add_argument('--out', type=str, default=str(OUTPUT_CSV), help='Output CSV path')
    args = ap.parse_args()

    # Load verified rows
    verified_rows: list[list[str]]
    if args.verified_csv:
        verified_rows = read_verified_from_csv(Path(args.verified_csv).expanduser())
        normalize = normalize_text
    elif args.verified_xlsx and args.helpers:
        verified_rows = read_verified_from_xlsx_with_helpers(Path(args.verified_xlsx).expanduser(), args.verified_sheet, Path(args.helpers).expanduser())
        mod = runpy.run_path(str(Path(args.helpers).expanduser()))
        normalize = mod['normalize_text']
    else:
        raise SystemExit('Provide either --verified-csv or both --verified-xlsx and --helpers')

    header = verified_rows[0]

    # Build payload from XML dir (default to autodetect or verified file directory)
    if args.xml_dir:
        xml_dir = Path(args.xml_dir).expanduser()
    else:
        # if using a verified file, try its folder first
        xml_dir = default_xml_dir()
    payload = build_payload(xml_dir)
    result = run_processor(payload)

    # Build prompt lookup
    value_by_prompt: dict[str, dict[str, str]] = {}
    for r in result.get('rows', []):
        value_by_prompt[normalize(r.get('promptText', ''))] = r.get('values', {})

    # Map header columns to xml filenames
    col_to_xml = map_header_to_xml(header, payload)

    out_path = Path(args.out).expanduser()
    with out_path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in verified_rows[1:]:
            # Pad row to header length
            out = list(r) + [''] * max(0, len(header) - len(r))
            prompt_norm = normalize(r[2] if len(r) > 2 else '')
            values = value_by_prompt.get(prompt_norm, {})
            for col_idx, xml_name in col_to_xml.items():
                out[col_idx] = values.get(xml_name, '')
            w.writerow(out)
    print(f'Wrote {out_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

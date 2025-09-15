#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_ALIGNED = ROOT / 'output_wave2_template.csv'
DEFAULT_DIFF = ROOT / 'wave2_mismatches.csv'


def normalize_text(s: str) -> str:
    import re
    return re.sub(r'\s+', ' ', (s or '').strip()).lower()


def read_verified_from_csv(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    with path.open(newline='') as f:
        for r in csv.reader(f):
            rows.append(r)
    return rows


def read_verified_from_xlsx_with_helpers(xlsx: Path, sheet: str, helpers: Path) -> tuple[list[list[str]], callable]:
    mod = runpy.run_path(str(helpers))
    read_xlsx_named_sheet_rows = mod['read_xlsx_named_sheet_rows']
    rows = read_xlsx_named_sheet_rows(xlsx, sheet)
    norm = mod.get('normalize_text', normalize_text)
    return rows, norm


def read_aligned_csv(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    with path.open() as f:
        for r in csv.reader(f):
            rows.append(r)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description='Diff aligned CSV against a verified template')
    ap.add_argument('--aligned-csv', type=str, default=str(DEFAULT_ALIGNED), help='Aligned CSV (output from export script)')
    ap.add_argument('--verified-csv', type=str, default=None, help='Verified CSV template to compare against')
    ap.add_argument('--verified-xlsx', type=str, default=None, help='Verified XLSX template (requires --helpers)')
    ap.add_argument('--verified-sheet', type=str, default='Plan Express Data Points', help='Sheet name in XLSX (default: Plan Express Data Points)')
    ap.add_argument('--helpers', type=str, default=None, help='Path to Python file exporting read_xlsx_named_sheet_rows and normalize_text')
    ap.add_argument('--out', type=str, default=str(DEFAULT_DIFF), help='Output CSV for mismatches')
    args = ap.parse_args()

    aligned = read_aligned_csv(Path(args.aligned_csv).expanduser())
    if not aligned:
        raise SystemExit(f'Missing aligned CSV: {args.aligned_csv}')
    header = aligned[0]

    # Load verified and normalization
    if args.verified_csv:
        verified = read_verified_from_csv(Path(args.verified_csv).expanduser())
        norm = normalize_text
    elif args.verified_xlsx and args.helpers:
        verified, norm = read_verified_from_xlsx_with_helpers(Path(args.verified_xlsx).expanduser(), args.verified_sheet, Path(args.helpers).expanduser())
    else:
        raise SystemExit('Provide either --verified-csv or both --verified-xlsx and --helpers')

    # Sanity: verified header should match first 5 and company labels
    comp_cols = list(range(5, len(header)-1)) if header[-1].strip().lower() == 'comments' else list(range(5, len(header)))
    mismatches: list[list[str]] = []
    # Build a map from normalized prompt to verified row index
    v_map = {norm(r[2] if len(r) > 2 else ''): r for r in verified[1:]}
    for a in aligned[1:]:
        key = norm(a[2] if len(a) > 2 else '')
        vrow = v_map.get(key)
        if not vrow:
            continue
        for i in comp_cols:
            exp = (vrow[i] if i < len(vrow) else '').strip()
            act = (a[i] if i < len(a) else '').strip()
            # Only record mismatch where verified has a value (so we don't flag blanks)
            if exp and exp != act:
                mismatches.append([
                    a[0] if len(a) > 0 else '',
                    a[1] if len(a) > 1 else '',
                    a[2] if len(a) > 2 else '',
                    header[i],
                    exp,
                    act,
                ])

    out_path = Path(args.out).expanduser()
    with out_path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Page', 'Seq', 'PROMPT', 'Company Column', 'Expected', 'Actual'])
        w.writerows(mismatches)
    print(f'Wrote {out_path} with {len(mismatches)} mismatches')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

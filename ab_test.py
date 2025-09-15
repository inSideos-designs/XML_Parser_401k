#!/usr/bin/env python3
from __future__ import annotations

"""
AB test harness for XML Prompt Filler reliability.

What it does:
- Loads verified workbook structure and corresponding XML files from the
  same directory used by existing export scripts.
- Runs the processor twice (Variant A and Variant B), each as a Python module
  with a `main()` compatible with server/process_local.py.
- Aligns each variant's output to the verified template header (company columns),
  producing two CSVs: output_wave2_template_A.csv and output_wave2_template_B.csv.
- Computes mismatches vs. the verified workbook for each variant, and writes
  wave2_mismatches_A.csv and wave2_mismatches_B.csv with counts in the console.
- Compares A vs B cell-by-cell and writes wave2_ab_diff.csv with differences.

Usage examples:
- Default (A and B both use server.process_local):
    python ab_test.py
- Specify a different B variant (e.g., server.process_local_b):
    python ab_test.py --variant-b server.process_local_b
"""

import argparse
import csv
import io
import json
import runpy
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import importlib
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent

# Outputs (relative to project root)
OUT_A = ROOT / 'output_A.csv'
OUT_B = ROOT / 'output_B.csv'
MISMATCHES_A = ROOT / 'mismatches_A.csv'
MISMATCHES_B = ROOT / 'mismatches_B.csv'
AB_DIFF = ROOT / 'ab_diff.csv'


def normalize_text(s: str) -> str:
    import re
    return re.sub(r'\s+', ' ', (s or '').strip()).lower()


def read_verified_csv(p: Path) -> List[List[str]]:
    rows: List[List[str]] = []
    with p.open(newline='') as f:
        for r in csv.reader(f):
            rows.append(r)
    return rows


def build_payload(src: Path) -> dict:
    return {
        'xmlFiles': [
            {'name': p.name, 'content': p.read_text(errors='ignore')}
            for p in sorted(src.glob('*.xml'))
        ]
    }


def run_processor_module(module_path: str, payload: dict) -> dict:
    mod = importlib.import_module(module_path)
    # Emulate server/process_local main() contract via stdin/stdout
    orig_stdin, orig_stdout = sys.stdin, sys.stdout
    try:
        sys.stdin = io.StringIO(json.dumps(payload))
        buf = io.StringIO()
        sys.stdout = buf
        rc = mod.main()
        sys.stdout.flush()
        out = buf.getvalue()
    finally:
        sys.stdin, sys.stdout = orig_stdin, orig_stdout
    if rc != 0:
        # Try to parse error JSON
        try:
            data = json.loads(out)
        except Exception:
            data = None
        if isinstance(data, dict) and 'error' in data:
            raise SystemExit(f'{module_path} error: {data["error"]}')
        raise SystemExit(f'{module_path} failed with code {rc}: {out}')
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise SystemExit(f'{module_path} returned non-JSON: {e}\nOutput was:\n{out}')


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


def map_header_to_xml(header: List[str], payload: dict) -> Dict[int, str]:
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


@dataclass
class VariantResult:
    header: List[str]
    rows: List[List[str]]
    mismatches: int


def align_to_verified(module_path: str, verified_rows: List[List[str]], payload: dict) -> VariantResult:
    # Build prompt lookup from processor output
    result = run_processor_module(module_path, payload)
    value_by_prompt: dict[str, dict[str, str]] = {}
    for r in result.get('rows', []):
        value_by_prompt[normalize_text(r.get('promptText', ''))] = r.get('values', {})

    header = list(verified_rows[0])
    # If the verified header only contains PROMPT/Options, produce an A/B-only layout:
    # We still align using payload file names as columns to keep consistency.
    col_to_xml = map_header_to_xml(header if len(header) > 5 else [''] * 5 + ['PROMPT'] * 1 + [p['name'] for p in payload.get('xmlFiles', [])], payload)
    if len(header) <= 2:
        header = ['Page', 'Seq', 'PROMPT'] + [item.get('name', '') for item in payload.get('xmlFiles', [])]

    out_rows: List[List[str]] = []
    for r in verified_rows[1:]:
        # Pad row to header length
        out = list(r) + [''] * max(0, len(header) - len(r))
        prompt_norm = normalize_text(r[2] if len(r) > 2 else (r[0] if r else ''))
        values = value_by_prompt.get(prompt_norm, {})
        for col_idx, xml_name in col_to_xml.items():
            out[col_idx] = values.get(xml_name, '')
        out_rows.append(out)

    # Count mismatches vs. verified only when verified has more than just prompt/option columns
    mismatches = 0
    if len(verified_rows[0]) > 5:
        comments = (header[-1].strip().lower() == 'comments')
        last_idx = len(header) - (1 if comments else 0)
        for vr, ar in zip(verified_rows[1:], out_rows):
            for i in range(5, last_idx):
                exp = (vr[i] if i < len(vr) else '').strip()
                act = (ar[i] if i < len(ar) else '').strip()
                if exp and exp != act:
                    mismatches += 1

    return VariantResult(header=header, rows=out_rows, mismatches=mismatches)


def write_csv(path: Path, header: List[str], rows: List[List[str]]):
    with path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def write_mismatches_csv(path: Path, header: List[str], verified_rows: List[List[str]], aligned_rows: List[List[str]]):
    comments = (header[-1].strip().lower() == 'comments')
    last_idx = len(header) - (1 if comments else 0)
    with path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Page', 'Seq', 'PROMPT', 'Company Column', 'Expected', 'Actual'])
        for vr, ar in zip(verified_rows[1:], aligned_rows):
            for i in range(5, last_idx):
                exp = (vr[i] if i < len(vr) else '').strip()
                act = (ar[i] if i < len(ar) else '').strip()
                if exp and exp != act:
                    w.writerow([
                        vr[0] if len(vr) > 0 else '',
                        vr[1] if len(vr) > 1 else '',
                        vr[2] if len(vr) > 2 else '',
                        header[i],
                        exp,
                        act,
                    ])


def write_ab_diff_csv(path: Path, header: List[str], rows_a: List[List[str]], rows_b: List[List[str]]):
    # Only compare overlapping rows length
    count = min(len(rows_a), len(rows_b))
    comments = (header[-1].strip().lower() == 'comments')
    last_idx = len(header) - (1 if comments else 0)
    with path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Row', 'Page', 'Seq', 'PROMPT', 'Company Column', 'A', 'B'])
        for idx in range(count):
            ra = rows_a[idx]
            rb = rows_b[idx]
            for i in range(5, last_idx):
                a = (ra[i] if i < len(ra) else '').strip()
                b = (rb[i] if i < len(rb) else '').strip()
                if a != b:
                    w.writerow([
                        idx + 2,  # Excel-like row num (header + 1)
                        ra[0] if len(ra) > 0 else '',
                        ra[1] if len(ra) > 1 else '',
                        ra[2] if len(ra) > 2 else '',
                        header[i],
                        a,
                        b,
                    ])


def main() -> int:
    ap = argparse.ArgumentParser(description='A/B test harness for XML Prompt Filler')
    ap.add_argument('--variant-a', default='server.process_local', help='Python module path for Variant A (default: server.process_local)')
    ap.add_argument('--variant-b', default='server.process_local', help='Python module path for Variant B (default: server.process_local)')
    ap.add_argument('--xml-dir', default=None, help='Directory of XML files (default: autodetect samples/input/cwd)')
    ap.add_argument('--verified-csv', default=None, help='Optional CSV template with expected values to compare against')
    args = ap.parse_args()

    # Build payload using robust defaults
    def pick_xml_dir() -> Path:
        candidates = [ROOT / 'samples', ROOT / 'input', Path.cwd()]
        if args.xml_dir:
            return Path(args.xml_dir).expanduser()
        for c in candidates:
            try:
                if c.exists() and any(p.suffix.lower() == '.xml' for p in c.iterdir()):
                    return c
            except Exception:
                continue
        return ROOT

    xml_dir = pick_xml_dir()
    payload = build_payload(xml_dir)

    # Determine verified rows, if provided
    verified_rows: List[List[str]]
    if args.verified_csv:
        vpath = Path(args.verified_csv).expanduser()
        if not vpath.exists():
            raise SystemExit(f'verified CSV not found: {vpath}')
        verified_rows = read_verified_csv(vpath)
    else:
        # Fallback minimal template from PlanExpress prompts if present, else from processor output
        plan_csv = ROOT / 'PlanExpress.csv'
        if plan_csv.exists():
            verified_rows = read_verified_csv(plan_csv)
            # Ensure at least 3 columns to hold Page/Seq/PROMPT shape
            if verified_rows and (len(verified_rows[0]) < 3):
                verified_rows[0] = ['PROMPT']
                verified_rows = [['', '', r[0]] for r in verified_rows]
                verified_rows.insert(0, ['Page', 'Seq', 'PROMPT'])
        else:
            # Derive from Variant A prompt list later; initialize minimal header
            verified_rows = [['Page', 'Seq', 'PROMPT']]

    print(f'Running Variant A: {args.variant_a}')
    var_a = align_to_verified(args.variant_a, verified_rows, payload)
    write_csv(OUT_A, var_a.header, var_a.rows)
    if len(verified_rows[0]) > 5:
        write_mismatches_csv(MISMATCHES_A, var_a.header, verified_rows, var_a.rows)
        print(f'Variant A mismatches vs verified: {var_a.mismatches} -> {MISMATCHES_A.name}')
    else:
        print('Variant A: verified comparisons skipped (no verified dataset provided)')

    print(f'Running Variant B: {args.variant_b}')
    var_b = align_to_verified(args.variant_b, verified_rows, payload)
    write_csv(OUT_B, var_b.header, var_b.rows)
    if len(verified_rows[0]) > 5:
        write_mismatches_csv(MISMATCHES_B, var_b.header, verified_rows, var_b.rows)
        print(f'Variant B mismatches vs verified: {var_b.mismatches} -> {MISMATCHES_B.name}')
    else:
        print('Variant B: verified comparisons skipped (no verified dataset provided)')

    # A/B diff between variants
    write_ab_diff_csv(AB_DIFF, var_a.header, var_a.rows, var_b.rows)
    # Count AB diffs quickly
    ab_diffs = 0
    comments = (var_a.header[-1].strip().lower() == 'comments') if var_a.header else False
    last_idx = len(var_a.header) - (1 if comments else 0) if var_a.header else 0
    for ra, rb in zip(var_a.rows, var_b.rows):
        for i in range(5 if last_idx >= 6 else 3, last_idx):
            if (ra[i] if i < len(ra) else '').strip() != (rb[i] if i < len(rb) else '').strip():
                ab_diffs += 1
    print(f'A vs B differing cells: {ab_diffs} -> {AB_DIFF.name}')

    print('Done. Outputs:')
    print(f'  {OUT_A}')
    print(f'  {OUT_B}')
    if len(verified_rows[0]) > 5:
        print(f'  {MISMATCHES_A}')
        print(f'  {MISMATCHES_B}')
    print(f'  {AB_DIFF}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

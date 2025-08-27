#!/usr/bin/env python3
import json
import runpy
from pathlib import Path

def main() -> int:
    mod = runpy.run_path(str(Path.home() / 'Desktop' / 'Test Folder' / 'fill_plan_data.py'))
    read_xlsx_named_sheet_rows = mod['read_xlsx_named_sheet_rows']

    datapoints_path = Path.home() / 'Desktop' / 'Test Folder' / 'TPA Data Points_PE_Module_FeeUI - Wave 1 (1).xlsx'
    if not datapoints_path.exists():
        print(json.dumps({ 'error': f'Data Points workbook not found: {datapoints_path}' }))
        return 404

    rows = read_xlsx_named_sheet_rows(datapoints_path, 'Plan Express Data Points')
    if not rows:
        print(json.dumps({ 'error': 'No rows read from Data Points sheet' }))
        return 500

    header = [ (h or '').strip() for h in rows[0] ]
    # Find PROMPT (fuzzy) and Options Allowed
    try:
        i_prompt = header.index('PROMPT')
    except ValueError:
        i_prompt = next((i for i,h in enumerate(header) if 'PROMPT' in (h or '')), -1)
    try:
        i_options = header.index('Options Allowed')
    except ValueError:
        i_options = -1

    if i_prompt < 0 or i_options < 0:
        print(json.dumps({ 'error': 'Required columns not found (PROMPT, Options Allowed)' }))
        return 400

    out = {}
    for r in rows[1:]:
        p = (r[i_prompt] if i_prompt < len(r) else '') or ''
        p = str(p).strip()
        if not p:
            continue
        oa = (r[i_options] if i_options < len(r) else '') or ''
        out[p] = str(oa).strip()

    print(json.dumps(out))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())


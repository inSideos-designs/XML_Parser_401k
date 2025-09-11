#!/usr/bin/env python3
import json
import runpy
from pathlib import Path


def _load_user_options_json() -> dict | None:
    p = Path.home() / '.xml-prompt-filler' / 'optionsByPrompt.json'
    try:
        if p.exists():
            data = json.loads(p.read_text())
            if isinstance(data, dict):
                return {str(k): str(v or '') for k, v in data.items()}
            if isinstance(data, list):
                out = {}
                for item in data:
                    if isinstance(item, dict) and 'key' in item:
                        out[str(item.get('key') or '')] = str(item.get('value') or '')
                return out
    except Exception:
        pass
    return None


def _load_packaged_options_json() -> dict | None:
    here = Path(__file__).resolve().parent
    json_path = here.parent / 'maps' / 'optionsByPrompt.json'
    try:
        if json_path.exists():
            data = json.loads(json_path.read_text())
            # Accept either an object mapping or a list of {key, value}
            if isinstance(data, dict):
                return {str(k): str(v or '') for k, v in data.items()}
            if isinstance(data, list):
                out = {}
                for item in data:
                    if isinstance(item, dict) and 'key' in item:
                        out[str(item.get('key') or '')] = str(item.get('value') or '')
                return out
    except Exception:
        pass
    return None


def main() -> int:
    # Prefer user-imported JSON, then packaged JSON
    packed = _load_user_options_json() or _load_packaged_options_json()
    if packed is not None:
        print(json.dumps(packed))
        return 0

    # Fallback to Excel via user's Working Logic helper
    mod = runpy.run_path(str(Path.home() / 'Desktop' / 'Test Folder' / 'fill_plan_data.py'))
    read_xlsx_named_sheet_rows = mod['read_xlsx_named_sheet_rows']

    datapoints_path = Path.home() / 'Desktop' / 'Test Folder' / 'TPA Data Points_PE_Module_FeeUI - Wave 1 (1).xlsx'
    if not datapoints_path.exists():
        print(json.dumps({'error': f'Data Points workbook not found: {datapoints_path}'}))
        return 404

    rows = read_xlsx_named_sheet_rows(datapoints_path, 'Plan Express Data Points')
    if not rows:
        print(json.dumps({'error': 'No rows read from Data Points sheet'}))
        return 500

    header = [(h or '').strip() for h in rows[0]]
    # Find PROMPT (fuzzy) and Options Allowed
    try:
        i_prompt = header.index('PROMPT')
    except ValueError:
        i_prompt = next((i for i, h in enumerate(header) if 'PROMPT' in (h or '')), -1)
    try:
        i_options = header.index('Options Allowed')
    except ValueError:
        i_options = -1

    if i_prompt < 0 or i_options < 0:
        print(json.dumps({'error': 'Required columns not found (PROMPT, Options Allowed)'}))
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

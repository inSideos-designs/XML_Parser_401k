#!/usr/bin/env python3
import json
import runpy
from pathlib import Path

def main() -> int:
    # Load parser utilities from the user's Test Folder
    mod = runpy.run_path(str(Path.home() / 'Desktop' / 'Test Folder' / 'fill_plan_data.py'))
    parse_map_workbook = mod['parse_map_workbook']

    map_path = Path.home() / 'Desktop' / 'Test Folder' / 'Map Updated 8152025.xlsx'
    if not map_path.exists():
        print(json.dumps({ 'error': f'Map workbook not found: {map_path}' }))
        return 404

    mapping = parse_map_workbook(map_path)
    out = []
    for prompt, entry in mapping.items():
        out.append({
            'prompt': prompt,
            'linknames': entry.get('linknames', ''),
            'quick': entry.get('quick', '')
        })
    print(json.dumps(out))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())


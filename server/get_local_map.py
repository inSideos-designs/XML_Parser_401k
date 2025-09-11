#!/usr/bin/env python3
import json
import runpy
from pathlib import Path


def _load_user_map_json() -> list | None:
    """Try to read the user's imported JSON map from ~/.xml-prompt-filler."""
    json_path = Path.home() / '.xml-prompt-filler' / 'defaultMap.json'
    try:
        if json_path.exists():
            data = json.loads(json_path.read_text())
            if isinstance(data, list):
                return [
                    {
                        'prompt': str(item.get('prompt', '')),
                        'linknames': str(item.get('linknames', '')),
                        'quick': str(item.get('quick', '')),
                    }
                    for item in data if isinstance(item, dict)
                ]
    except Exception:
        pass
    return None


def _load_packaged_map_json() -> list | None:
    """Try to read the bundled JSON map first."""
    here = Path(__file__).resolve().parent
    json_path = here.parent / 'maps' / 'defaultMap.json'
    try:
        if json_path.exists():
            data = json.loads(json_path.read_text())
            # Expecting a list of {prompt, linknames, quick}
            if isinstance(data, list):
                # Basic shape check
                return [
                    {
                        'prompt': str(item.get('prompt', '')),
                        'linknames': str(item.get('linknames', '')),
                        'quick': str(item.get('quick', '')),
                    }
                    for item in data
                    if isinstance(item, dict)
                ]
    except Exception:
        pass
    return None


def main() -> int:
    # Prefer user-imported JSON, then packaged JSON
    data = _load_user_map_json()
    if data is None:
        data = _load_packaged_map_json()
    if data is not None:
        print(json.dumps(data))
        return 0

    # Fallback to Excel via user's Working Logic helper
    mod = runpy.run_path(str(Path.home() / 'Desktop' / 'Test Folder' / 'fill_plan_data.py'))
    parse_map_workbook = mod['parse_map_workbook']

    map_path = Path.home() / 'Desktop' / 'Test Folder' / 'Map Updated 8152025.xlsx'
    if not map_path.exists():
        print(json.dumps({'error': f'Map workbook not found: {map_path}'}))
        return 404

    mapping = parse_map_workbook(map_path)
    out = []
    for prompt, entry in mapping.items():
        out.append({
            'prompt': prompt,
            'linknames': entry.get('linknames', ''),
            'quick': entry.get('quick', ''),
        })
    print(json.dumps(out))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

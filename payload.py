import argparse
import json
import os
from pathlib import Path


def default_source_dir() -> Path:
    here = Path(__file__).resolve().parent
    for c in [here / 'samples', here / 'input', Path.cwd()]:
        try:
            if c.exists() and any(p.suffix.lower() == '.xml' for p in c.iterdir()):
                return c
        except Exception:
            continue
    return here


def build_payload(src: Path) -> dict:
    payload = {"xmlFiles": []}
    for p in sorted(src.glob('*.xml')):
        try:
            content = p.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            content = p.read_text(errors='ignore')
        payload["xmlFiles"].append({"name": p.name, "content": content})
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description='Build JSON payload from a directory of XML files')
    ap.add_argument('--source', '-s', type=str, default=None, help='Directory containing .xml files (default: autodetect samples/input/cwd)')
    args = ap.parse_args()
    src = Path(args.source).expanduser() if args.source else default_source_dir()
    if not src.exists():
        raise SystemExit(f'Source directory not found: {src}')
    data = build_payload(src)
    print(json.dumps(data))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

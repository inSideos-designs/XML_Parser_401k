#!/bin/bash
# Double-clickable macOS launcher for the XML Prompt Filler

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi

"$PY" "$DIR/run_xml_prompt_filler.py"

read -r -p "\nDone. Press Enter to close…" _


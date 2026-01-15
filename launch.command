#!/bin/bash
cd "$(dirname "$0")"
echo "Starting Plan Express Batch Filler GUI..."
python3 -c "import flask" 2>/dev/null || pip3 install flask
(sleep 2 && open http://localhost:5001) &
python3 app.py

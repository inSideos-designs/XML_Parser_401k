#!/bin/bash
# Double-clickable macOS launcher for the XML Prompt Filler GUI (Vite dev server)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is required. Please install Node 18+ from nodejs.org or via nvm."
  read -r -p "Press Enter to close…" _
  exit 1
fi

# Start dev server
echo "Starting dev server…"
open "http://localhost:5173" >/dev/null 2>&1 || true

# If node_modules missing, ask the user to install.
if [ ! -d node_modules ]; then
  echo "node_modules not found. Attempting 'npm install'…"
  npm install || { echo "npm install failed. Please run it manually."; read -r -p "Press Enter to close…" _; exit 1; }
fi

npm run dev


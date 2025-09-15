## XML Prompt Filler

Local‑first tool to batch‑extract plan provisioning answers from Empower XMLs into a clean table. It maps human prompts to XML linknames, applies smart heuristics (Yes/No normalization, options matching, related text), and outputs CSV/JSON for audit and review. Runs fully offline using a local config store (or the packaged defaults) — no runtime Excel dependency.

## Features
- Offline: Uses a local config store at `~/.xml-prompt-filler/` or bundled JSON in `maps/`.
- Batch: Process many XMLs at once into a consolidated table.
- Smart mapping: Linkname resolution, related-text extraction, Y/N normalization, options matching.
- Flexible I/O: XML in; CSV/JSON out. Optional CSV uploads for mapping and options.
- UI + CLI: React/Vite frontend and a one‑click Python CLI.

## Prerequisites
- Node.js 18+
- Python 3.x on PATH

## Run the GUI (Quick Start)
```
cd Desktop/xml-prompt-filler
npm install
npm run dev
```
Open the printed URL (usually http://localhost:5173) and:
- Step 1: Upload XML files.
- Step 2: Leave “Auto-load local config (no uploads)” enabled to use your local config (or packaged defaults). Toggle off to upload Map/Data Points CSVs instead.
- Step 3: Click Process, then download the CSV.

## One‑Time Import (recommended)
Import your Map and Data Points once so any machine can run offline without Excel.

1) Export your Excel sheets to CSV:
- Map CSV headers: `Prompt`, `Proposed LinkName` (optional `Quick`)
- Data Points CSV headers: `PROMPT`, `Options Allowed`

2) Run the import CLI:
```
python3 tools/import_from_csv.py \
  --map-csv /path/to/Map.csv \
  --datapoints-csv /path/to/PlanExpress.csv
```

This writes two files to `~/.xml-prompt-filler/`:
- `defaultMap.json` — list of `{ prompt, linknames, quick }`
- `optionsByPrompt.json` — mapping `{ PROMPT: "Options Allowed" }`

The app automatically prefers the user store over packaged defaults. Refresh the GUI after import.

Optional server import endpoints (if you run `python3 server/app.py`):
- POST `/admin/import-csv` with `multipart/form-data` fields `map_csv` and `datapoints_csv`.
- POST `/admin/import-json` with body `{ map: [...], options: {...} }`.

## CLI (Batch, no UI)
- Run locally with autodetect (uses `samples/`, then `input/`, else current directory if it has XMLs):
```
python3 run_xml_prompt_filler.py
```
- Or specify an XML folder explicitly:
```
python3 run_xml_prompt_filler.py --source /path/to/xmls
```
Outputs: `output.csv` and `output.json` in the project folder.

### A/B Reliability Test
Run two processor variants on the same XMLs and diff results:
```
python3 ab_test.py --xml-dir /path/to/xmls \
  [--variant-b server.process_local_b] \
  [--verified-csv /path/to/verified.csv]
```
Outputs: `output_A.csv`, `output_B.csv`, `ab_diff.csv` (and `mismatches_*.csv` if `--verified-csv` supplied).

### Align To Verified Template
Create an aligned CSV using a verified template (CSV preferred; XLSX supported with helpers):
```
python3 export_wave2_to_template_csv_v2.py \
  --verified-csv /path/to/verified.csv \
  --xml-dir /path/to/xmls \
  --out output_wave2_template.csv
```
Or, if you must use XLSX, provide a helpers module that exposes
`read_xlsx_named_sheet_rows` and `normalize_text`:
```
python3 export_wave2_to_template_csv_v2.py \
  --verified-xlsx /path/to/verified.xlsx \
  --verified-sheet "Plan Express Data Points" \
  --helpers /path/to/fill_plan_data.py \
  --xml-dir /path/to/xmls
```

### Diff Against Verified
Compare an aligned CSV to a verified dataset:
```
python3 diff_wave2_vs_verified.py \
  --aligned-csv output_wave2_template.csv \
  --verified-csv /path/to/verified.csv \
  --out wave2_mismatches.csv
```
Or using XLSX + helpers as above with `--verified-xlsx` and `--helpers`.

## Configuration Sources
Load order used by the GUI and CLI:
1) User store: `~/.xml-prompt-filler/{defaultMap.json, optionsByPrompt.json}`
2) Packaged defaults: `maps/defaultMap.json`, `maps/optionsByPrompt.json`

## Notable Files
- `maps/defaultMap.json` — Prompt → LinkNames (+ Quick)
- `maps/optionsByPrompt.json` — PROMPT → Options Allowed
- `server/logic.py` — XML parsing + mapping heuristics
- `server/process_local.py` — Offline processor used by the CLI
- `server/app.py` — Flask API (processing + admin import)
- `tools/import_from_csv.py` — One‑time CSV → JSON importer
- `App.tsx` — React UI (auto‑load, processing, download)

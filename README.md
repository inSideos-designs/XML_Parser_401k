# Run and deploy your APP 

This contains everything you need to run your app locally.

## Run Locally

**Prerequisites:**  Node.js


1. Install dependencies:
   `npm install`
2. Run the app:
   `npm run dev`

This version uses a local XML extraction service. The Prompt CSV must contain columns `Prompt` and `Proposed LinkName`. The `Proposed LinkName` is used to match XML LinkName/PlanData fields.

## Advanced (Python Working Logic)

For parity with your prior "good" results, run the local Python backend and enable Advanced mode in the UI.

- Start backend (Flask):
  - `cd Desktop/ai-xml-prompt-filler/server`
  - `python3 -m pip install -r requirements.txt`
  - `python3 app.py` (listens on `http://127.0.0.1:8787`)
  - Reuses `fill_plan_data.py` from `~/Desktop/Working Logic` (fallback: `~/Desktop/Test Folder`).

- In the UI (Step 2):
  - Toggle "Advanced (use local Python Working Logic)"
  - Upload your Map workbook (`Map Updated 8152025.xlsx` or CSV)
  - Upload your Data Points workbook (`TPA Data Points_PE_Module_FeeUI - Wave 1 (1).xlsx`)
  - Process: the UI will send XMLs + workbooks to the backend and render the filled table.

Notes:
- The backend adds CORS headers for the dev UI.
- If your Working Logic lives elsewhere, update `server/server.py` to point to it.

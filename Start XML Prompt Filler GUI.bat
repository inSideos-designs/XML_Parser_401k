@echo off
setlocal
REM Double-clickable Windows launcher for the XML Prompt Filler GUI (Vite dev server)

cd /d "%~dp0"

where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
  echo Node.js (v18+) is required. Install from https://nodejs.org/
  pause
  exit /b 1
)

REM Open the app URL in default browser
start "" "http://localhost:5173"

if not exist node_modules (
  echo node_modules not found. Running 'npm install'...
  call npm install
  if %ERRORLEVEL% neq 0 (
    echo npm install failed. Please run it manually in this folder.
    pause
    exit /b 1
  )
)

call npm run dev
echo.
pause


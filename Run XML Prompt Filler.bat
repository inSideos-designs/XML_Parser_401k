@echo off
setlocal
REM Double-clickable Windows launcher for the XML Prompt Filler

cd /d "%~dp0"

REM Choose Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
  where py >nul 2>nul
  if %ERRORLEVEL% neq 0 (
    echo Python 3 is required. Please install from https://www.python.org/downloads/
    pause
    exit /b 1
  )
  set "PY=py -3"
) else (
  set "PY=python"
)

%PY% "%CD%\run_xml_prompt_filler.py"
if %ERRORLEVEL% neq 0 (
  echo.
  echo Run failed. See messages above.
)
echo.
pause


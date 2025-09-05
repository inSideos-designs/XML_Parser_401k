@echo off
setlocal
REM Build a standalone Windows .exe for XML Prompt Filler using PyInstaller.

cd /d "%~dp0"

REM Prefer the Python launcher if present
set "PYCMD=python"
where python >nul 2>nul || set "PYCMD=py -3"

echo.
echo === Ensuring PyInstaller is available ===
%PYCMD% -m pip install --upgrade pip pyinstaller
if %ERRORLEVEL% neq 0 (
  echo Failed to install PyInstaller. Check your network or Python installation.
  pause
  exit /b 1
)

echo.
echo === Building onefile executable ===
%PYCMD% -m PyInstaller --onefile --name XMLPromptFiller run_xml_prompt_filler_standalone.py
if %ERRORLEVEL% neq 0 (
  echo Build failed.
  pause
  exit /b 1
)

echo.
echo Build complete. Find the exe at: %CD%\dist\XMLPromptFiller.exe
echo You can move it anywhere. It writes output.json and output.csv to the folder it runs in.
echo.
pause


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

set "XML_DIR="
if not "%~1"=="" (
  set "XML_DIR=%~1"
) else (
  if exist "%CD%\input\*.xml" (
    set "XML_DIR=%CD%\input"
  ) else if exist "%CD%\samples\*.xml" (
    set "XML_DIR=%CD%\samples"
  ) else (
    set "XML_DIR=%CD%"
  )
)

echo Using XML directory: %XML_DIR%
%PY% "%CD%\run_xml_prompt_filler.py" --source "%XML_DIR%"
if %ERRORLEVEL% neq 0 (
  echo.
  echo Run failed. See messages above.
)
echo.
pause

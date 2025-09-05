XML Prompt Filler — Windows EXE Build Guide
==========================================

What this builds
----------------
- A single-file Windows executable: dist\XMLPromptFiller.exe
- No Python required on the target machine.
- Outputs are written to the current folder: output.csv and output.json

Prereqs
-------
- Windows with internet access
- Python 3 installed (only on the build machine)

How to build
------------
1) Double-click: Build XML Prompt Filler EXE.bat
   - The script installs PyInstaller if needed and builds a one-file exe
2) Find the exe at: dist\XMLPromptFiller.exe

How to run the EXE
------------------
1) Place XML files in: %USERPROFILE%\Desktop\Test Folder
   (or modify SOURCE_DIR inside the exe’s companion script if you rebuild)
2) Double-click XMLPromptFiller.exe
3) It writes output.csv and output.json in the same folder you launch it from
   and opens output.csv automatically.

Notes
-----
- The tool uses your local mapping/data-point logic found at:
  %USERPROFILE%\Desktop\Test Folder\fill_plan_data.py
  along with the Map/DataPoints workbooks in the same folder.
  The logic is pure-stdlib and requires no external Python packages.
- If you move the EXE to a different machine, copy the Test Folder too.
- To change the XML source directory, edit SOURCE_DIR in
  run_xml_prompt_filler_standalone.py and rebuild.


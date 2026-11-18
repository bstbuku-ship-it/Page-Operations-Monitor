@echo off
rem First step before publishing: sync this package's browser-extension/
rem into the repo's main branch, so the cloud build embeds the new
rem connector. Run this FIRST, then double-click publish.bat.
rem Keep sync_connector.py in the SAME folder as this file.
rem All output is also shown in this window.
rem NOTE: this file is intentionally pure ASCII so cmd never misreads it.
cd /d "%~dp0"
if not exist "%~dp0sync_connector.py" (
  echo [ERROR] sync_connector.py not found in %~dp0
  echo Put sync_connector.py and 1-sync-connector.bat in the SAME folder, then double-click 1-sync-connector.bat.
  pause
  exit /b 1
)
if not exist "%~dp0browser-extension\manifest.json" (
  echo [ERROR] browser-extension\manifest.json not found in %~dp0
  echo Use the full release package, then double-click 1-sync-connector.bat again.
  pause
  exit /b 1
)
echo Step 1 of 2: sync browser-extension to the repo main branch.
echo After this finishes, double-click publish.bat for step 2.
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3 with "Add to PATH", then retry.
    pause
    exit /b 1
  )
  py "%~dp0sync_connector.py" %*
) else (
  python "%~dp0sync_connector.py" %*
)
echo.
echo [exit code %errorlevel%] Done when the script prints the completion lines above.
echo Next: double-click publish.bat.
pause

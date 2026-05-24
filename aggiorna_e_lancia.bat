@echo off
REM Doppio click su questo file = aggiorna il codice dal git e rilancia lo
REM script. Niente da imparare: 1 click e basta.
cd /d "%~dp0"
echo === Aggiorno il codice dal server git ===
git pull origin main
if errorlevel 1 (
    echo.
    echo PROBLEMA col git pull. Premi un tasto per chiudere.
    pause
    exit /b 1
)
echo.
echo === Lancio lo scraper ===
python run.py
echo.
echo === Finito. Apri output\eventi.html nel browser e fai Ctrl+F5 ===
pause

@echo off
REM ==========================================================
REM  preparer_hors_ligne.bat
REM
REM  A lancer UNE SEULE FOIS, avec Internet, sur le PC qui
REM  servira a fabriquer CompilateurOffline.exe. Telecharge
REM  PyInstaller (et ses dependances) dans vendor\.
REM ==========================================================

cd /d "%~dp0\.."

echo [1/2] Verification de Python...
python --version
if errorlevel 1 (
    echo ERREUR: Python n'est pas installe ou pas dans le PATH.
    pause
    exit /b 1
)

echo.
echo [2/2] Telechargement de PyInstaller dans vendor\ (necessite Internet)...
python -m pip install --upgrade pip
python -m pip download -r requirements.txt -d vendor

if errorlevel 1 (
    echo ERREUR lors du telechargement.
    pause
    exit /b 1
)

echo.
echo Termine. Vous pouvez maintenant lancer installer\build.bat,
echo y compris plus tard sur un PC sans Internet (copiez tout le
echo dossier, y compris vendor\).
pause


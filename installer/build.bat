@echo off
REM ==========================================================
REM  build.bat — Compile CompilateurOffline.exe
REM
REM  Particularite : on inclut PyInstaller LUI-MEME a l'interieur
REM  de l'executable produit (--collect-all PyInstaller), pour
REM  que CompilateurOffline.exe puisse ensuite compiler d'autres
REM  scripts Python SANS avoir besoin d'un Python installe a cote,
REM  ni d'Internet.
REM ==========================================================

cd /d "%~dp0\.."

echo [1/3] Verification de Python...
python --version
if errorlevel 1 (
    echo ERREUR: Python n'est pas installe ou pas dans le PATH.
    pause
    exit /b 1
)

echo.
echo [2/3] Installation de PyInstaller...
python -m pip install --upgrade pip >nul

if exist "vendor\" (
    echo Dossier vendor\ detecte -^> installation HORS LIGNE.
    python -m pip install --no-index --find-links=vendor -r requirements.txt
) else (
    echo Aucun vendor\ trouve -^> installation EN LIGNE ^(Internet requis^).
    echo ^(Pour eviter Internet la prochaine fois : lancez d'abord
    echo   installer\preparer_hors_ligne.bat une fois.^)
    python -m pip install -r requirements.txt
)
if errorlevel 1 (
    echo ERREUR lors de l'installation.
    pause
    exit /b 1
)

echo.
echo [3/3] Compilation de CompilateurOffline.exe (avec PyInstaller integre)...
python -m PyInstaller --noconfirm --windowed --name CompilateurOffline ^
    --collect-all PyInstaller ^
    main.py

if errorlevel 1 (
    echo ERREUR pendant la compilation.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Termine ! dist\CompilateurOffline\CompilateurOffline.exe
echo
echo  Ce dossier complet (pas seulement le .exe) peut maintenant
echo  etre copie sur N'IMPORTE QUEL PC WINDOWS, meme sans Python
echo  installe et sans Internet. Double-cliquez sur
echo  CompilateurOffline.exe pour ouvrir l'interface, choisissez
echo  un script .py (par exemple votemgr\main.py) et cliquez
echo  "Compiler".
echo
echo  IMPORTANT : testez-le d'abord sur une machine hors-ligne
echo  avant de compter dessus le jour J (voir README.md, section
echo  "Limites a connaitre").
echo ============================================================
pause

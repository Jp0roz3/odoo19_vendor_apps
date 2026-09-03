@echo off
chcp 65001 >nul
title Instalar Inicio Automatico - VenPOS Fiscal Agent
echo =======================================================
echo   Configurando Inicio Automatico en Windows (Segundo Plano)
echo =======================================================

set SCRIPT_DIR=%~dp0
set VBS_TARGET=%SCRIPT_DIR%iniciar_agente_silencioso.vbs
set STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%STARTUP_FOLDER%\VenPOS_Fiscal_Agent.lnk'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%VBS_TARGET%\"'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.WindowStyle = 7; $s.Save(); Write-Host '[OK] Acceso directo creado en la carpeta de Inicio de Windows.'"

echo.
echo =======================================================
echo   LISTO: A partir de ahora, cada vez que encienda la PC
echo   de la caja, el Agente Fiscal arrancara en segundo plano
echo   de forma 100%% INVISIBLE sin abrir ninguna ventana.
echo =======================================================
echo.
pause

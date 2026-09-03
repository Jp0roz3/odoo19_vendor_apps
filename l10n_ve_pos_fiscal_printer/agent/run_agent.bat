@echo off
title VenPOS Fiscal Agent - Bixolon SRP-812
echo =======================================================
echo   Iniciando Agente Fiscal VenPOS para Odoo 19
echo =======================================================
echo.
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta instalado o no se encuentra en el PATH.
    echo Por favor instale Python 3.8 o superior desde python.org
    pause
    exit /b
)

pip install -r requirements.txt --quiet

echo Iniciando servicio en http://127.0.0.1:9069 ...
python fiscal_agent.py --port 9069
pause

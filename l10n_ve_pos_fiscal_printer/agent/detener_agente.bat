@echo off
chcp 65001 >nul
title Detener VenPOS Fiscal Agent
echo =======================================================
echo   Deteniendo VenPOS Fiscal Agent en segundo plano...
echo =======================================================

powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*fiscal_agent.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host '[OK] Proceso detenido: ' $_.ProcessId }"

powershell -NoProfile -Command "Start-Sleep -Milliseconds 500"

@echo off
title NDX Quant Strategy Dashboard
cd /d "%~dp0"
echo ============================================================
echo Starting NDX Strategy Web Dashboard...
echo Dashboard will automatically open in your default browser.
echo ============================================================
python web_dashboard.py
pause

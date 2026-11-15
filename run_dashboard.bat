@echo off
title ABP Nadia Photo Mailer Dashboard
cd /d "%~dp0"
echo Starting Dashboard on http://localhost:5000 ...
start "" http://localhost:5000
python dashboard.py
pause

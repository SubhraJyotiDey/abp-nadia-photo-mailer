@echo off
cd /d "%~dp0"
python main.py >> mailer_log.txt 2>&1

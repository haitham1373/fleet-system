@echo off
cd /d "%~dp0"
echo Starting Fleet Management System...
python -m streamlit run app.py
if errorlevel 1 (
    echo.
    echo Failed to start the application.
    pause
)

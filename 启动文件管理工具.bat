@echo off
chcp 65001 >nul
title FileFinder
cd /d "%~dp0"

rem v2.2 needs customtkinter, which is installed in Python 3.11.
rem So prefer the py launcher pinned to 3.11 instead of a bare "python"
rem (bare python may resolve to the Microsoft Store 3.10, which lacks customtkinter).
where py >nul 2>nul
if %errorlevel%==0 (
    py -3.11 file_manager.py
) else (
    python file_manager.py
)

if errorlevel 1 (
    echo.
    echo Start failed! If the error says "No module named 'customtkinter'", run:
    echo   py -3.11 -m pip install customtkinter
    pause
)

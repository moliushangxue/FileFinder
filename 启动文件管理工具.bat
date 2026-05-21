@echo off
chcp 65001 >nul
title FileFinder
cd /d "%~dp0"
python file_manager.py
if errorlevel 1 (
    echo.
    echo Start failed! Please install Python.
    pause
)

@echo off
chcp 65001 >nul
title FileFinder
echo 正在启动 FileFinder...
python "%~dp0file_manager.py"
if errorlevel 1 (
    echo.
    echo 启动失败！请确保已安装 Python。
    pause
)

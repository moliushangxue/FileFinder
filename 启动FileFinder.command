#!/bin/bash
# ══════════════════════════════════════════════════════════════════
#  FileFinder - macOS 启动脚本
#
#  首次使用（只需执行一次）：
#      chmod +x 启动FileFinder.command
#  之后双击本文件即可启动。
#  若双击没反应，也可以直接在终端里运行：
#      bash 启动FileFinder.command
#
#  脚本做三件事：
#    1. 切到脚本所在目录 —— 双击运行时的工作目录不是项目目录，
#       不切的话会找不到 file_manager.py
#    2. 挑一个「自带 tkinter」的 Python 3 —— 这是 macOS 上最容易踩的坑：
#       系统自带的 python3（由 Xcode 命令行工具提供）不包含 tkinter，
#       直接拿它跑会以 ModuleNotFoundError 失败。
#       所以这里逐个探测「能不能 import tkinter」，而不是无脑用 python3。
#    3. 缺 customtkinter 时自动安装，然后启动程序
# ══════════════════════════════════════════════════════════════════

cd "$(dirname "$0")" || exit 1

PY=""

# 候选解释器按「最可能装好 Tk 的」排在前面；官方安装包自带 Tk，优先级最高
for cand in \
    python3 \
    python3.13 python3.12 python3.11 \
    /usr/local/bin/python3 \
    /opt/homebrew/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/*/bin/python3
do
    # 只有能成功 import tkinter 的解释器才算数（失败会返回非 0，自动跳过）
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import tkinter" >/dev/null 2>&1; then
        PY="$cand"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "没有找到带 tkinter 的 Python 3。"
    echo
    echo "macOS 系统自带的 python3（Xcode 命令行工具提供）不包含 tkinter，"
    echo "请安装官方版 Python 3.11 或更高：https://www.python.org/downloads/macos/"
    echo "官方安装包自带 Tk，装完直接双击本文件即可，无需额外配置。"
    echo
    read -r -p "按回车键关闭窗口..."
    exit 1
fi

echo "使用解释器：$PY"

if ! "$PY" -c "import customtkinter" >/dev/null 2>&1; then
    echo "首次运行，正在安装依赖 customtkinter ..."
    if ! "$PY" -m pip install --user customtkinter; then
        echo
        echo "依赖安装失败，请手动执行："
        echo "    $PY -m pip install customtkinter"
        read -r -p "按回车键关闭窗口..."
        exit 1
    fi
fi

"$PY" file_manager.py
status=$?

# 程序异常退出时停一下，否则窗口一闪而过看不到报错
if [ $status -ne 0 ]; then
    echo
    echo "程序已退出，状态码 $status"
    read -r -p "按回车键关闭窗口..."
fi

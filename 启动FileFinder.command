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
#    2. 挑一个「自带 tkinter」的 Python 3 —— 不能假设 python3 一定带 tkinter：
#       同样是 macOS，来源不同的解释器差别很大（Xcode 命令行工具提供的那份
#       有些版本缺 Tcl/Tk；Homebrew 的 Python 要额外装 python-tk 才有）。
#       所以这里逐个探测「能不能 import tkinter」，而不是无脑用 python3。
#    3. 在项目目录里建一个虚拟环境 .venv，依赖装进它里面，再用它启动程序
# ══════════════════════════════════════════════════════════════════

# ── 为什么是 .venv，而不是 pip install --user ─────────────────────
#  Homebrew 的 Python 遵守 PEP 668：直接用 pip 往解释器里装包会被拦下来
#  （报 externally-managed-environment），目的是不让第三方包装坏 brew 自己
#  的依赖。加 --break-system-packages 能硬闯，但可能把 brew 环境弄坏，
#  所以这里不走那条路。
#
#  虚拟环境是官方指定的正规出口，本质是「在项目目录里新开一份独立的依赖
#  目录」：不往系统目录写、不往 /opt/homebrew 写、不需要 sudo，删掉 .venv
#  就等于卸载干净。.venv 已在 .gitignore 里，不会被提交。
# ══════════════════════════════════════════════════════════════════

cd "$(dirname "$0")" || exit 1

VENV_DIR="$PWD/.venv"
VENV_PY="$VENV_DIR/bin/python"

# ── 1. 找一个带 tkinter 的 Python 3 ───────────────────────────────
#  候选按「最可能装好 Tk 的」排序；官方安装包自带 Tk，优先级最高
PY=""
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
    echo "macOS 上不同来源的 python3 差别很大，有的不含 tkinter。"
    echo "最省事的办法是装官方版 Python 3.11 或更高："
    echo "    https://www.python.org/downloads/macos/"
    echo "官方安装包自带 Tk，装完直接双击本文件即可，无需额外配置。"
    echo
    read -r -p "按回车键关闭窗口..."
    exit 1
fi

echo "使用解释器：$PY"

# ── 2. 确保 .venv 存在 ────────────────────────────────────────────
#  只在第一次运行时创建；之后每次启动复用同一个环境，不会重复安装
if [ ! -x "$VENV_PY" ]; then
    echo "首次运行，正在创建虚拟环境 .venv ..."
    if ! "$PY" -m venv "$VENV_DIR"; then
        echo
        echo "创建虚拟环境失败。常见原因：这个 Python 缺 ensurepip（venv 依赖它）。"
        echo "换官方版 Python 3.11+ 重来一次通常就好了。"
        read -r -p "按回车键关闭窗口..."
        exit 1
    fi
fi

# 虚拟环境会继承基础解释器的 Tk。万一没继承到，在这里就报出来，
# 比等程序启动后闪退、连报错都看不见要好
if ! "$VENV_PY" -c "import tkinter" >/dev/null 2>&1; then
    echo
    echo ".venv 里的 Python 用不了 tkinter，界面起不来。"
    echo "多半是基础解释器 $PY 的 Tcl/Tk 没装好，换官方版 Python 重来一次。"
    read -r -p "按回车键关闭窗口..."
    exit 1
fi

# ── 3. 装依赖（只装进 .venv）──────────────────────────────────────
#  用「能不能 import 到」当判据，而不是记一个「装过了」的标记文件 ——
#  依赖是不是真的可用，只有解释器自己说了算
if ! "$VENV_PY" -c "import customtkinter" >/dev/null 2>&1; then
    echo "首次运行，正在把依赖装进 .venv（只影响本项目，不动系统环境）..."
    if ! "$VENV_PY" -m pip install --disable-pip-version-check customtkinter; then
        echo
        echo "依赖安装失败。可手动重试："
        echo "    $VENV_PY -m pip install customtkinter"
        echo "若卡在下载，换国内镜像："
        echo "    $VENV_PY -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple customtkinter"
        read -r -p "按回车键关闭窗口..."
        exit 1
    fi
fi

"$VENV_PY" file_manager.py
status=$?

# 程序异常退出时停一下，否则窗口一闪而过看不到报错
if [ $status -ne 0 ]; then
    echo
    echo "程序已退出，状态码 $status"
    read -r -p "按回车键关闭窗口..."
fi

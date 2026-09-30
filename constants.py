#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FileFinder - 全局常量与公共工具函数

这个文件存放整个项目共享的"固定值"和"工具函数"。
把常量集中在一个地方的好处是：改一个地方，全项目都生效，不用到处找。
"""

import json   # 配置文件读写
import os     # 文件路径操作
import re     # 正则表达式支持
import sys    # 平台判断（配置目录位置）

# ─── 文本文件预览的最大字节数 ───
# 超过这个大小的文本文件，预览时只显示前面一部分，避免加载太慢
PREVIEW_MAX_BYTES = 100 * 1024  # 100 KB

# ─── 可预览的文本扩展名 ───
# 这是一个"集合"（set），用花括号 {} 定义。
# 集合查找速度极快（O(1)），适合做"某个扩展名在不在里面"的判断。
# 只要文件扩展名在这个集合里，就当作文本文件来预览。
TEXT_PREVIEW_EXTS = {
    '.txt', '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.htm', '.css',
    '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
    '.md', '.rst', '.csv', '.tsv', '.log', '.sh', '.bash', '.zsh', '.bat',
    '.cmd', '.ps1', '.c', '.cpp', '.h', '.hpp', '.java', '.kt', '.go',
    '.rs', '.rb', '.php', '.sql', '.r', '.m', '.swift', '.dart', '.lua',
    '.pl', '.pm', '.hs', '.ex', '.exs', '.erl', '.clj', '.lisp', '.el',
    '.vim', '.env', '.gitignore', '.dockerignore', '.makefile', '.cmake',
    '.rtf', '.properties', '.gradle', '.dockerfile', '.editorconfig',
}

# ─── 文件冲突类型描述（冲突检测和对话框共用，避免到处硬编码字符串） ───
CONFLICT_TARGET_EXISTS = "目标文件夹中已存在同名文件"
CONFLICT_SOURCE_DUP = "选中的源文件之间存在同名"


# ─── 全局字体（按平台选择各系统自带的字体） ───
# 为什么不能写死一个名字：tkinter 在字体族不存在时不会报错，而是「静默回退」到
# 默认字体——界面能开，但观感整个跑偏，且很难排查。
# 所以三个平台各用自己系统里一定有的那套：
#   Windows  微软雅黑 / Consolas
#   macOS    苹方 PingFang SC / Menlo
#   Linux    DejaVu Sans / DejaVu Sans Mono（绝大多数发行版自带）
if sys.platform == "win32":
    _FONT_UI, _FONT_MONO_FAMILY = "Microsoft YaHei UI", "Consolas"
elif sys.platform == "darwin":
    _FONT_UI, _FONT_MONO_FAMILY = "PingFang SC", "Menlo"
else:
    _FONT_UI, _FONT_MONO_FAMILY = "DejaVu Sans", "DejaVu Sans Mono"


# ─── UI 配色与字体（浅色现代风 + 蓝色点缀） ───
# 集中定义的好处：想换主题色只改这里，全界面生效
class UI:
    BG = "#f1f5f9"            # 窗口底色：很浅的蓝灰（slate-100）
    CARD = "#ffffff"          # 卡片底色：纯白
    ACCENT = "#2563eb"        # 点缀色：蓝（blue-600）
    ACCENT_HOVER = "#1d4ed8"  # 按钮悬停：更深的蓝（blue-700）
    ACCENT_LIGHT = "#eff6ff"  # 浅蓝底（blue-50），用于标题条等
    TEXT = "#0f172a"          # 主文字：近黑（slate-900）
    TEXT_DIM = "#64748b"      # 次要文字：灰蓝（slate-500）
    BORDER = "#e2e8f0"        # 边框：浅灰（slate-200）
    DANGER = "#dc2626"        # 危险操作：红（覆盖按钮）
    DANGER_HOVER = "#b91c1c"

    FONT = _FONT_UI                  # 全局字体：按平台选择（见上方 _FONT_UI 的说明）
    FONT_MONO = _FONT_MONO_FAMILY    # 等宽字体：预览代码/日志用



# ─── 常用文件类型（筛选快捷键用） ───
# 点击界面上的"常用类型"按钮时，只有这些扩展名会被勾选
COMMON_TYPES = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp',        # 图片
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',  # 文档
    '.txt', '.csv',                                   # 文本
    '.mp3', '.mp4', '.avi', '.mkv',                  # 音视频
    '.zip', '.rar', '.7z',                            # 压缩包
}


def fmt_size(size):
    """把字节数格式化成人类可读的大小，例如 1048576 → '1.0 MB'

    原理：不断除以 1024，直到数值 < 1024，同时更换单位。
    1024 B → 1.0 KB → ... → 1.0 GB → 1.0 TB
    """
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024:
            return f"{size:.1f} {unit}"  # :.1f 表示保留1位小数
        size /= 1024
    return f"{size:.1f} TB"


def compile_regex_patterns(keywords):
    """将关键词列表编译为正则表达式对象列表

    参数:
        keywords: 关键词列表

    返回:
        编译后的正则表达式对象列表

    异常:
        如果某个关键词不是有效的正则表达式，抛出 ValueError
    """
    patterns = []
    for kw in keywords:
        try:
            patterns.append(re.compile(kw, re.IGNORECASE))
        except re.error as e:
            raise ValueError(f"关键词 '{kw}' 不是有效的正则表达式：{str(e)}")
    return patterns


def match_file(filename, keywords, selected_extensions, regex_patterns=None):
    """检查文件是否同时满足关键词和扩展名两个筛选条件

    参数:
        filename:            文件名（不含路径），如 "photo.jpg"
        keywords:            关键词列表，文件名包含任一关键词即匹配
        selected_extensions: 选中的扩展名集合，文件扩展名在其中即匹配
        regex_patterns:      预编译的正则表达式列表（可选），如果提供则使用正则匹配

    返回:
        True = 匹配（应该出现在结果中）；False = 不匹配
    """
    _, ext = os.path.splitext(filename)  # 分离扩展名，如 ".jpg"
    ext = ext.lower()                     # 统一转小写

    # 条件1：扩展名筛选（如果有选中的扩展名，文件扩展名必须在其中）
    if selected_extensions and ext not in selected_extensions:
        return False

    # 条件2：关键词筛选
    if keywords:
        if regex_patterns:
            # 正则表达式模式：文件名必须匹配至少一个正则表达式
            if not any(pattern.search(filename) for pattern in regex_patterns):
                return False
        else:
            # 普通模式：文件名必须包含至少一个关键词
            name_lower = filename.lower()
            # any() 表示"只要有一个满足条件就返回 True"
            if not any(kw.lower() in name_lower for kw in keywords):
                return False

    return True


# ─── 启动提示配置（"不再提示"标记持久化） ───
# 存到用户配置目录而不是程序目录：打包成 exe 后程序目录可能没有写权限

def get_config_dir():
    """返回应用配置目录（跨平台）

    Windows: %LOCALAPPDATA%\\FileFinder（无 LOCALAPPDATA 时退回用户主目录）
    macOS:   ~/Library/Application Support/FileFinder
    Linux:   $XDG_CONFIG_HOME/FileFinder 或 ~/.config/FileFinder
    """
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or home
    elif sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    return os.path.join(base, "FileFinder")


def should_show_disclaimer():
    """是否需要显示启动风险提示弹窗

    返回 False 的条件：配置文件里已有 "disclaimer_agreed": true
    （用户之前勾选过"不再提示"并点了确定）
    """
    cfg = os.path.join(get_config_dir(), "config.json")
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            return not json.load(f).get("disclaimer_agreed", False)
    except (OSError, ValueError):
        return True   # 读不到配置 = 从未同意过，需要弹窗


def save_disclaimer_agreed():
    """记录用户勾选"不再提示"，以后启动不再弹提示"""
    config_dir = get_config_dir()
    os.makedirs(config_dir, exist_ok=True)
    cfg = os.path.join(config_dir, "config.json")
    data = {}
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    data["disclaimer_agreed"] = True
    with open(cfg, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

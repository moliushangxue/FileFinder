#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FileFinder - 文件预览 Mixin（混入类）

Mixin 是一种设计模式：把"某一类功能"单独写在另一个类里，
然后通过"多继承"把它混入主类中，让主类自动拥有这些方法。

这样做的好处是：主类不会太臃肿，每个文件只负责一件事。

这个 Mixin 提供文件预览功能：
  - 文本文件：直接显示内容
  - docx/xlsx/pptx：解压后解析 XML 提取文本
  - 图片/音视频/压缩包/PDF：显示元信息（不支持内容预览）

需要宿主类（主类）提供以下属性：
  self.preview_info_var  — tkinter.StringVar，显示文件元信息
  self.preview_text      — tkinter.scrolledtext.ScrolledText，显示预览内容
"""

import os
import datetime
import zipfile
import xml.etree.ElementTree as ET

import tkinter as tk
from tkinter import scrolledtext

# 从 constants.py 导入预览所需常量和工具函数
from constants import PREVIEW_MAX_BYTES, TEXT_PREVIEW_EXTS, _fmt_size


class PreviewMixin:
    """文件预览功能混入类

    用多继承混入主类：class FileManagerApp(PreviewMixin, ClipboardMixin):
    这样 FileManagerApp 就自动拥有了预览和剪贴板的所有方法。
    """

    # ════════════════════════════════════════════════════════════
    #  清空预览区域
    # ════════════════════════════════════════════════════════════

    def _clear_preview(self):
        """清空右侧预览面板，恢复到初始状态"""
        self.preview_info_var.set("选择文件以预览")       # 顶部元信息
        self.preview_text.config(state=tk.NORMAL)           # 打开编辑权限（才能清空）
        self.preview_text.delete("1.0", tk.END)           # 删除所有内容（"1.0"=第1行第0列）
        self.preview_text.config(state=tk.DISABLED)         # 关闭编辑权限（只读）

    # ════════════════════════════════════════════════════════════
    #  预览入口：根据文件类型分发到不同方法
    # ════════════════════════════════════════════════════════════

    def _preview_file(self, file_path):
        """预览文件的主入口，根据扩展名决定用哪种方式预览

        参数:
            file_path: 要预览的文件的完整路径
        """
        if not os.path.exists(file_path):
            self.preview_info_var.set("文件不存在")
            return

        # ── 获取文件元信息 ──
        stat = os.stat(file_path)                          # 获取文件状态（大小、修改时间等）
        size = stat.st_size                                # 文件大小（字节）
        # 把时间戳（秒数）转换成可读格式，如 "2026-05-21 23:28:00"
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        _, ext = os.path.splitext(file_path)              # 分离文件名和扩展名，ext 含"."
        ext = ext.lower()                                  # 统一转小写，方便匹配

        # 顶部显示的基本信息（文件名、大小、修改时间、路径）
        info_lines = [
            f"📄 {os.path.basename(file_path)}",
            f"大小: {_fmt_size(size)}　　修改时间: {mtime}",
            f"路径: {file_path}",
        ]

        # 打开预览文本框，准备写入内容
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)

        # ── 根据扩展名分发到不同的预览方法 ──
        if ext in TEXT_PREVIEW_EXTS or size == 0:
            # 文本文件（在 TEXT_PREVIEW_EXTS 里）或空文件 → 直接读内容
            self._preview_text_file(file_path, info_lines, size)
        elif ext == '.docx':
            # Word 文档 → 解压 docx，解析 word/document.xml
            self._preview_docx(file_path, info_lines)
        elif ext in {'.xlsx', '.xlsm'}:
            # Excel 文档 → 解压，解析所有 sheet XML
            self._preview_office_xml(file_path, info_lines, "xl/worksheets/sheet", "xlsx")
        elif ext in {'.pptx'}:
            # PPT 文档 → 解压，解析所有幻灯片 XML
            self._preview_office_xml(file_path, info_lines, "ppt/slides/slide", "pptx")
        elif ext in {'.doc', '.xls', '.ppt'}:
            # 旧版 Office 格式（二进制格式，不是 ZIP）→ 无法解析
            info_lines.append("\n[旧版 Office 格式（.doc/.xls/.ppt）— 二进制格式，无法直接预览文本]")
            info_lines.append("提示：可转换为 .docx/.xlsx/.pptx 后预览")
            self.preview_info_var.set("\n".join(info_lines))
        elif ext in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.webp', '.svg'}:
            info_lines.append("\n[图片文件 — 无法在文本预览中显示]")
            self.preview_info_var.set("\n".join(info_lines))
        elif ext in {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma'}:
            info_lines.append("\n[音频文件]")
            self.preview_info_var.set("\n".join(info_lines))
        elif ext in {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv'}:
            info_lines.append("\n[视频文件]")
            self.preview_info_var.set("\n".join(info_lines))
        elif ext in {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'}:
            info_lines.append("\n[压缩文件]")
            self.preview_info_var.set("\n".join(info_lines))
        elif ext in {'.pdf'}:
            info_lines.append("\n[PDF 文件]")
            self.preview_info_var.set("\n".join(info_lines))
        else:
            # 未知类型，尝试当作文本文件打开（force=False：失败时不报错，只显示提示）
            self._preview_text_file(file_path, info_lines, size, force=False)

        # 关闭文本框编辑权限
        self.preview_text.config(state=tk.DISABLED)

    # ════════════════════════════════════════════════════════════
    #  文本文件预览
    # ════════════════════════════════════════════════════════════

    def _preview_text_file(self, file_path, info_lines, size, force=True):
        """尝试以文本方式读取并预览文件内容

        参数:
            file_path:  文件路径
            info_lines: 顶部元信息列表（会追加更多信息）
            size:       文件大小（字节）
            force:      True=强制预览（失败报错）；False=失败只显示提示
        """
        try:
            if size > PREVIEW_MAX_BYTES:
                # 文件太大：只读前面一部分，避免界面卡死
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read(PREVIEW_MAX_BYTES)
                info_lines.append(f"\n[文件较大，仅显示前 {PREVIEW_MAX_BYTES // 1024} KB]")
                self.preview_text.insert(tk.END, content)
                self.preview_text.insert(tk.END, "\n\n... (内容已截断)")
            elif size == 0:
                # 空文件
                info_lines.append("\n[空文件]")
            else:
                # 正常大小：读取全部内容
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                self.preview_text.insert(tk.END, content)
        except Exception as e:
            if force:
                # force=True：确实想预览，但失败了 → 显示错误
                info_lines.append(f"\n[读取失败: {e}]")
            else:
                # force=False：不确定是不是文本文件 → 只提示无法预览
                info_lines.append("\n[二进制文件，无法预览]")

        # 把元信息更新到顶部
        self.preview_info_var.set("\n".join(info_lines))

    # ════════════════════════════════════════════════════════════
    #  Office 文件预览：docx（本质是 ZIP 包里的 XML）
    # ════════════════════════════════════════════════════════════

    def _preview_docx(self, file_path, info_lines):
        """预览 .docx 文件内容

        .docx 本质上是一个 ZIP 压缩包，里面包含 word/document.xml，
        这个 XML 里用 <w:t> 标签存放所有文本片段，
        用 <w:p> 标签表示段落（段落之间应该换行）。

        步骤：
        1. 用 zipfile 打开 docx（当成 ZIP 读）
        2. 找到 word/document.xml，用 ET.parse() 解析成 XML 树
        3. 遍历所有 <w:p>（段落），把段落里所有 <w:t> 的文本拼起来
        4. 把所有段落用换行符连接，显示到预览框
        """
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                # 检查必要文件是否存在
                if 'word/document.xml' not in z.namelist():
                    info_lines.append("\n[无法解析 docx 结构]")
                    self.preview_info_var.set("\n".join(info_lines))
                    return

                # 打开 word/document.xml，解析 XML
                with z.open('word/document.xml') as f:
                    tree = ET.parse(f)

            # ── 提取段落文本 ──
            # 遍历 XML 里所有 <w:p>（段落）标签
            paragraphs = []
            # {http://...} 是 XML 命名空间，必须写完整才能匹配
            p_elems = tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p')
            for p in p_elems:
                p_texts = []
                # 遍历这个段落里所有 <w:t>（文本片段）
                for t in p.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
                    if t.text:
                        p_texts.append(t.text)
                # 只保留有内容的段落
                if p_texts:
                    paragraphs.append(''.join(p_texts))

            # 把段落拼接起来显示
            if paragraphs:
                content = '\n'.join(paragraphs)
                if len(content) > PREVIEW_MAX_BYTES:
                    content = content[:PREVIEW_MAX_BYTES] + "\n\n... (内容已截断)"
                self.preview_text.insert(tk.END, content)
            else:
                info_lines.append("\n[文档内容为空或无纯文本]")

        except zipfile.BadZipFile:
            # 文件不是有效的 ZIP（docx 本质是 ZIP）
            info_lines.append("\n[文件损坏或不是有效的 docx 格式]")
        except Exception as e:
            info_lines.append(f"\n[解析失败: {e}]")

        self.preview_info_var.set("\n".join(info_lines))

    # ════════════════════════════════════════════════════════════
    #  Office 文件预览：xlsx / pptx（共用逻辑）
    # ════════════════════════════════════════════════════════════

    def _preview_office_xml(self, file_path, info_lines, content_prefix, office_type):
        """预览 Office Open XML 格式（xlsx/pptx）的文本内容

        参数:
            file_path:     文件路径
            info_lines:    顶部元信息列表
            content_prefix: ZIP 包里 XML 文件的前缀
                            xlsx → "xl/worksheets/sheet"（sheet1.xml, sheet2.xml...）
                            pptx → "ppt/slides/slide"（slide1.xml, slide2.xml...）
            office_type:    显示用名称（"xlsx" 或 "pptx"）

        原理和 _preview_docx 类似：打开 ZIP → 找 XML → 提取所有文本节点
        """
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                # 找出 ZIP 包里所有匹配的 XML 文件
                # 例如 xlsx 里会有 xl/worksheets/sheet1.xml, sheet2.xml...
                target_files = [n for n in z.namelist() if n.startswith(content_prefix)]

                if not target_files:
                    info_lines.append(f"\n[无法解析 {office_type} 结构]")
                    self.preview_info_var.set("\n".join(info_lines))
                    return

                # 遍历每个 XML 文件，提取文本
                all_text = []
                for xml_name in sorted(target_files):
                    with z.open(xml_name) as f:
                        tree = ET.parse(f)

                    # 遍历 XML 里所有有文本的节点
                    for elem in tree.iter():
                        if elem.text and elem.text.strip():
                            all_text.append(elem.text.strip())

                # 显示提取到的文本
                if all_text:
                    content = '\n'.join(all_text)
                    if len(content) > PREVIEW_MAX_BYTES:
                        content = content[:PREVIEW_MAX_BYTES] + "\n\n... (内容已截断)"
                    self.preview_text.insert(tk.END, content)
                else:
                    info_lines.append(f"\n[{office_type} 文件无可提取的文本]")

        except zipfile.BadZipFile:
            info_lines.append("\n[文件损坏或格式不正确]")
        except Exception as e:
            info_lines.append(f"\n[解析失败: {e}]")

        self.preview_info_var.set("\n".join(info_lines))

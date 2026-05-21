#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件管理工具 - 批量文件筛选和操作工具
支持按文件名关键词搜索、按文件类型筛选，并提供复制/剪切/移动功能
v2.0 - 新增：递归搜索子文件夹、文件预览、文件冲突处理
"""

import os
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
import platform
import datetime


# ─── 文本文件预览的最大字节数 ───
PREVIEW_MAX_BYTES = 100 * 1024  # 100 KB
# ─── 可预览的文本扩展名 ───
TEXT_PREVIEW_EXTS = {
    '.txt', '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.htm', '.css',
    '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
    '.md', '.rst', '.csv', '.tsv', '.log', '.sh', '.bash', '.zsh', '.bat',
    '.cmd', '.ps1', '.c', '.cpp', '.h', '.hpp', '.java', '.kt', '.go',
    '.rs', '.rb', '.php', '.sql', '.r', '.m', '.swift', '.dart', '.lua',
    '.pl', '.pm', '.hs', '.ex', '.exs', '.erl', '.clj', '.lisp', '.el',
    '.vim', '.env', '.gitignore', '.dockerignore', '.makefile', '.cmake',
}


class ConflictDialog(tk.Toplevel):
    """文件冲突处理对话框"""

    def __init__(self, parent, conflicts):
        """
        conflicts: list of (filename, src_path, dest_path, conflict_type)
        """
        super().__init__(parent)
        self.title("文件冲突")
        self.geometry("620x450")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.conflicts = conflicts
        self.result = {}  # {filename: "skip" | "overwrite" | "rename"}
        self._apply_all = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # 居中
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        # 统计冲突类型
        target_conflicts = sum(1 for _, _, _, ct in self.conflicts if "目标" in ct)
        source_conflicts = sum(1 for _, _, _, ct in self.conflicts if "源文件" in ct)
        
        summary_parts = []
        if target_conflicts:
            summary_parts.append(f"{target_conflicts} 个与目标文件夹冲突")
        if source_conflicts:
            summary_parts.append(f"{source_conflicts} 个源文件之间同名冲突")
        
        ttk.Label(
            self, text=f"发现文件冲突（{'，'.join(summary_parts)}），请选择处理方式：",
            padding=10, wraplength=580
        ).pack(fill=tk.X)

        # 冲突文件列表
        list_frame = ttk.Frame(self, padding=(10, 0))
        list_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(list_frame, height=10, yscrollcommand=scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)

        for fname, src, dest, conflict_type in self.conflicts:
            src_size = os.path.getsize(src) if os.path.exists(src) else 0
            # 显示冲突类型 + 大小信息
            if "源文件" in conflict_type:
                self.listbox.insert(
                    tk.END,
                    f"⚠ {fname}  — {conflict_type}（大小: {self._fmt_size(src_size)}）"
                )
            else:
                dest_size = os.path.getsize(dest) if os.path.exists(dest) else 0
                self.listbox.insert(
                    tk.END,
                    f"⚠ {fname}  — {conflict_type}（源: {self._fmt_size(src_size)} → 目标: {self._fmt_size(dest_size)}）"
                )

        # 按钮区域
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="全部覆盖", command=lambda: self._apply_all_action("overwrite")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="全部重命名", command=lambda: self._apply_all_action("rename")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="全部跳过", command=lambda: self._apply_all_action("skip")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="取消", command=self._on_cancel).pack(side=tk.RIGHT, padx=4)

    @staticmethod
    def _fmt_size(size):
        for unit in ('B', 'KB', 'MB', 'GB'):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def _apply_all_action(self, action):
        self._apply_all = action
        for fname, _, _, _ in self.conflicts:
            self.result[fname] = action
        self.destroy()

    def _on_cancel(self):
        self.result = None  # 用户取消
        self.destroy()


class FileManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FileFinder v2.0")
        self.root.geometry("1100x750")

        # 变量初始化
        self.folder_path = tk.StringVar()
        self.target_folder = tk.StringVar()
        self.file_extensions = []  # 选中的文件扩展名
        self.all_extensions = set()  # 所有检测到的扩展名
        self.found_files = []  # 找到的文件列表
        self.selected_files = []  # 用户选中的文件
        self.recursive_var = tk.BooleanVar(value=False)  # 递归搜索

        # 创建界面
        self.create_widgets()

        # 绑定列表选择事件 → 更新预览
        self.file_listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

    def create_widgets(self):
        """创建GUI组件"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)  # 文件列表+预览区域可伸缩

        # ── 1. 文件夹选择区域 ──
        folder_frame = ttk.LabelFrame(main_frame, text="源文件夹", padding="10")
        folder_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        folder_frame.columnconfigure(1, weight=1)

        ttk.Label(folder_frame, text="路径:").grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Entry(folder_frame, textvariable=self.folder_path, width=50).grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=5
        )
        ttk.Button(folder_frame, text="浏览...", command=self.browse_folder).grid(
            row=0, column=2, padx=5
        )
        # 递归搜索复选框
        ttk.Checkbutton(
            folder_frame, text="递归搜索子文件夹", variable=self.recursive_var
        ).grid(row=0, column=3, padx=10)

        # ── 2. 搜索和筛选区域 ──
        search_frame = ttk.LabelFrame(main_frame, text="搜索和筛选", padding="10")
        search_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        search_frame.columnconfigure(0, weight=1)

        # 关键词输入框
        keyword_frame = ttk.Frame(search_frame)
        keyword_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        keyword_frame.columnconfigure(1, weight=1)

        ttk.Label(keyword_frame, text="关键词(每行一个):").grid(row=0, column=0, sticky=tk.W, padx=5)

        text_frame = ttk.Frame(keyword_frame)
        text_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        self.keyword_text = tk.Text(text_frame, height=3, width=60)
        scrollbar_keyword = ttk.Scrollbar(text_frame, command=self.keyword_text.yview)
        self.keyword_text.configure(yscrollcommand=scrollbar_keyword.set)
        self.keyword_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        scrollbar_keyword.pack(side=tk.RIGHT, fill=tk.Y)

        # 扫描按钮和清空按钮
        btn_col_frame = ttk.Frame(keyword_frame)
        btn_col_frame.grid(row=1, column=2, padx=5, sticky=tk.N)
        ttk.Button(btn_col_frame, text="扫描文件", command=self.scan_files).pack(pady=(0, 3))
        ttk.Button(btn_col_frame, text="清空关键词", command=self.clear_keywords).pack()

        # 文件类型筛选
        ttk.Label(search_frame, text="文件类型筛选:").grid(
            row=1, column=0, sticky=tk.W, padx=5, pady=5
        )
        type_frame = ttk.Frame(search_frame)
        type_frame.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5)

        ttk.Button(type_frame, text="全选", command=self.select_all_types).grid(row=0, column=0, padx=2)
        ttk.Button(type_frame, text="全不选", command=self.deselect_all_types).grid(row=0, column=1, padx=2)
        ttk.Button(type_frame, text="常用类型", command=self.select_common_types).grid(row=0, column=2, padx=2)

        # 扩展名复选框容器（横向滚动）
        self.extension_checkboxes = {}
        checkbox_outer = ttk.Frame(search_frame)
        checkbox_outer.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=3)

        self.checkbox_canvas = tk.Canvas(checkbox_outer, height=28, highlightthickness=0)
        h_scroll = ttk.Scrollbar(checkbox_outer, orient=tk.HORIZONTAL, command=self.checkbox_canvas.xview)
        self.checkbox_canvas.configure(xscrollcommand=h_scroll.set)

        self.checkbox_canvas.pack(side=tk.TOP, fill=tk.X, expand=True)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.checkbox_container = ttk.Frame(self.checkbox_canvas)
        self.checkbox_canvas_window = self.checkbox_canvas.create_window(
            (0, 0), window=self.checkbox_container, anchor=tk.NW
        )
        # 内部框架大小变化时更新滚动区域
        self.checkbox_container.bind("<Configure>", lambda e: self.checkbox_canvas.configure(
            scrollregion=self.checkbox_canvas.bbox("all")
        ))
        # canvas 大小变化时让内部框架跟高度一致
        self.checkbox_canvas.bind("<Configure>", lambda e: self.checkbox_canvas.itemconfig(
            self.checkbox_canvas_window, height=e.height
        ))

        # ── 3. 文件列表 + 预览（左右分栏） ──
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.grid(row=2, column=0, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)

        # 左侧：文件列表
        list_frame = ttk.LabelFrame(paned, text="找到的文件", padding="5")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        paned.add(list_frame, weight=3)

        list_inner = ttk.Frame(list_frame)
        list_inner.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_inner.columnconfigure(0, weight=1)
        list_inner.rowconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(list_inner)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        self.file_listbox = tk.Listbox(
            list_inner, selectmode=tk.MULTIPLE, yscrollcommand=scrollbar.set, height=12
        )
        self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.config(command=self.file_listbox.yview)

        # 选择按钮
        select_btn_frame = ttk.Frame(list_frame)
        select_btn_frame.grid(row=1, column=0, pady=3)
        ttk.Button(select_btn_frame, text="全选", command=self.select_all_files).pack(side=tk.LEFT, padx=3)
        ttk.Button(select_btn_frame, text="全不选", command=self.deselect_all_files).pack(side=tk.LEFT, padx=3)
        ttk.Button(select_btn_frame, text="反选", command=self.invert_selection).pack(side=tk.LEFT, padx=3)

        # 剪贴板按钮
        clipboard_frame = ttk.LabelFrame(list_frame, text="剪贴板操作", padding="3")
        clipboard_frame.grid(row=2, column=0, pady=3, sticky=(tk.W, tk.E))
        ttk.Button(clipboard_frame, text="复制路径到剪贴板", command=self.copy_paths_to_clipboard).pack(side=tk.LEFT, padx=3)
        ttk.Button(clipboard_frame, text="复制文件到剪贴板", command=self.copy_files_to_clipboard).pack(side=tk.LEFT, padx=3)

        # 右侧：文件预览
        preview_frame = ttk.LabelFrame(paned, text="文件预览", padding="5")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(1, weight=1)
        paned.add(preview_frame, weight=2)

        # 预览文件信息
        self.preview_info_var = tk.StringVar(value="选择文件以预览")
        ttk.Label(preview_frame, textvariable=self.preview_info_var, wraplength=350).grid(
            row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 3)
        )

        # 预览内容
        self.preview_text = scrolledtext.ScrolledText(
            preview_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10)
        )
        self.preview_text.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # ── 4. 操作区域 ──
        action_frame = ttk.LabelFrame(main_frame, text="文件操作", padding="10")
        action_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=5)
        action_frame.columnconfigure(1, weight=1)

        ttk.Label(action_frame, text="目标文件夹:").grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Entry(action_frame, textvariable=self.target_folder, width=50).grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=5
        )
        ttk.Button(action_frame, text="浏览...", command=self.browse_target).grid(row=0, column=2, padx=5)

        btn_frame = ttk.Frame(action_frame)
        btn_frame.grid(row=1, column=0, columnspan=3, pady=8)
        ttk.Button(btn_frame, text="复制到目标文件夹", command=lambda: self.perform_action("copy")).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="剪切到目标文件夹", command=lambda: self.perform_action("move")).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="直接移动", command=lambda: self.perform_action("direct_move")).pack(side=tk.LEFT, padx=5)

        # ── 5. 状态栏 ──
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN).grid(
            row=5, column=0, sticky=(tk.W, tk.E), pady=3
        )

    # ════════════════════════════════════════════════════════════
    #  文件夹浏览
    # ════════════════════════════════════════════════════════════

    def browse_folder(self):
        folder = filedialog.askdirectory(title="选择源文件夹")
        if folder:
            self.folder_path.set(folder)
            self.status_var.set(f"已选择文件夹: {folder}")

    def browse_target(self):
        folder = filedialog.askdirectory(title="选择目标文件夹")
        if folder:
            self.target_folder.set(folder)
            self.status_var.set(f"已选择目标文件夹: {folder}")

    # ════════════════════════════════════════════════════════════
    #  扫描文件（支持递归）
    # ════════════════════════════════════════════════════════════

    def clear_keywords(self):
        """清空关键词输入框"""
        self.keyword_text.delete("1.0", tk.END)

    def scan_files(self):
        source_folder = self.folder_path.get()

        if not source_folder:
            messagebox.showwarning("警告", "请先选择源文件夹！")
            return

        if not os.path.exists(source_folder):
            messagebox.showerror("错误", "源文件夹不存在！")
            return

        # 获取搜索关键词列表
        keyword_text = self.keyword_text.get("1.0", tk.END).strip()
        keywords = [kw.strip() for kw in keyword_text.split('\n') if kw.strip()] if keyword_text else []

        # 获取选中的文件扩展名
        selected_extensions = [
            ext for ext, var in self.extension_checkboxes.items() if var.get()
        ]

        recursive = self.recursive_var.get()

        # 扫描文件
        self.found_files = []
        try:
            if recursive:
                # 递归遍历
                for dirpath, dirnames, filenames in os.walk(source_folder):
                    for fname in filenames:
                        full_path = os.path.join(dirpath, fname)
                        if self._match_file(fname, keywords, selected_extensions):
                            self.found_files.append(full_path)
            else:
                # 仅当前目录
                for item in os.listdir(source_folder):
                    full_path = os.path.join(source_folder, item)
                    if not os.path.isfile(full_path):
                        continue
                    if self._match_file(item, keywords, selected_extensions):
                        self.found_files.append(full_path)

            # 更新文件列表显示
            self.update_file_list()

            # 收集所有扩展名（首次扫描时）
            if not self.all_extensions:
                self.collect_extensions(source_folder, recursive)

            self.status_var.set(f"找到 {len(self.found_files)} 个文件" + ("（递归）" if recursive else ""))

        except Exception as e:
            messagebox.showerror("错误", f"扫描文件时出错: {str(e)}")

    def _match_file(self, filename, keywords, selected_extensions):
        """检查文件是否匹配关键词和扩展名筛选"""
        _, ext = os.path.splitext(filename)
        ext = ext.lower()

        if selected_extensions and ext not in selected_extensions:
            return False

        if keywords:
            name_lower = filename.lower()
            if not any(kw.lower() in name_lower for kw in keywords):
                return False

        return True

    def collect_extensions(self, folder, recursive=False):
        """收集文件夹中所有的文件扩展名"""
        self.all_extensions.clear()
        if recursive:
            for dirpath, _, filenames in os.walk(folder):
                for fname in filenames:
                    _, ext = os.path.splitext(fname)
                    ext = ext.lower()
                    if ext:
                        self.all_extensions.add(ext)
        else:
            for item in os.listdir(folder):
                full_path = os.path.join(folder, item)
                if os.path.isfile(full_path):
                    _, ext = os.path.splitext(item)
                    ext = ext.lower()
                    if ext:
                        self.all_extensions.add(ext)

        self.create_extension_checkboxes()

    def create_extension_checkboxes(self):
        """创建扩展名复选框（横向排列）"""
        for widget in self.checkbox_container.winfo_children():
            widget.destroy()
        self.extension_checkboxes.clear()

        sorted_extensions = sorted(self.all_extensions)

        for ext in sorted_extensions:
            var = tk.BooleanVar(value=True)
            cb = ttk.Checkbutton(self.checkbox_container, text=ext, variable=var)
            cb.pack(side=tk.LEFT, padx=4, pady=2)
            self.extension_checkboxes[ext] = var

    # ════════════════════════════════════════════════════════════
    #  文件类型筛选
    # ════════════════════════════════════════════════════════════

    def select_all_types(self):
        for var in self.extension_checkboxes.values():
            var.set(True)

    def deselect_all_types(self):
        for var in self.extension_checkboxes.values():
            var.set(False)

    def select_common_types(self):
        common_types = {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.txt', '.csv',
            '.mp3', '.mp4', '.avi', '.mkv',
            '.zip', '.rar', '.7z',
        }
        for ext, var in self.extension_checkboxes.items():
            var.set(ext in common_types)

    # ════════════════════════════════════════════════════════════
    #  文件列表操作
    # ════════════════════════════════════════════════════════════

    def update_file_list(self):
        self.file_listbox.delete(0, tk.END)
        # 清空预览
        self._clear_preview()
        for file_path in self.found_files:
            # 递归模式下显示相对路径
            source = self.folder_path.get()
            try:
                display = os.path.relpath(file_path, source)
            except ValueError:
                display = os.path.basename(file_path)
            self.file_listbox.insert(tk.END, display)

    def select_all_files(self):
        self.file_listbox.select_set(0, tk.END)

    def deselect_all_files(self):
        self.file_listbox.select_clear(0, tk.END)

    def invert_selection(self):
        current_selection = set(self.file_listbox.curselection())
        total = self.file_listbox.size()
        self.file_listbox.select_clear(0, tk.END)
        for i in range(total):
            if i not in current_selection:
                self.file_listbox.select_set(i)

    # ════════════════════════════════════════════════════════════
    #  文件预览
    # ════════════════════════════════════════════════════════════

    def _on_listbox_select(self, event=None):
        """列表选中时触发预览"""
        sel = self.file_listbox.curselection()
        if not sel:
            self._clear_preview()
            return
        idx = sel[0]
        if idx < len(self.found_files):
            self._preview_file(self.found_files[idx])

    def _clear_preview(self):
        self.preview_info_var.set("选择文件以预览")
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.config(state=tk.DISABLED)

    def _preview_file(self, file_path):
        """预览文件内容或元信息"""
        if not os.path.exists(file_path):
            self.preview_info_var.set("文件不存在")
            return

        # 基本信息
        stat = os.stat(file_path)
        size = stat.st_size
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()

        info_lines = [
            f"📄 {os.path.basename(file_path)}",
            f"大小: {self._fmt_size(size)}　　修改时间: {mtime}",
            f"路径: {file_path}",
        ]

        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)

        # 判断是否可预览
        if ext in TEXT_PREVIEW_EXTS or size == 0:
            self._preview_text_file(file_path, info_lines, size)
        elif ext == '.docx':
            self._preview_docx(file_path, info_lines)
        elif ext in {'.xlsx', '.xlsm'}:
            self._preview_office_xml(file_path, info_lines, "xl/worksheets/sheet", "xlsx")
        elif ext in {'.pptx'}:
            self._preview_office_xml(file_path, info_lines, "ppt/slides/slide", "pptx")
        elif ext in {'.doc', '.xls', '.ppt'}:
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
            # 尝试作为文本读取
            self._preview_text_file(file_path, info_lines, size, force=False)

        self.preview_text.config(state=tk.DISABLED)

    def _preview_text_file(self, file_path, info_lines, size, force=True):
        """尝试预览文本文件内容"""
        try:
            if size > PREVIEW_MAX_BYTES:
                # 只读前面部分
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read(PREVIEW_MAX_BYTES)
                info_lines.append(f"\n[文件较大，仅显示前 {PREVIEW_MAX_BYTES // 1024} KB]")
                self.preview_text.insert(tk.END, content)
                self.preview_text.insert(tk.END, "\n\n... (内容已截断)")
            elif size == 0:
                info_lines.append("\n[空文件]")
            else:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                self.preview_text.insert(tk.END, content)
        except Exception as e:
            if force:
                info_lines.append(f"\n[读取失败: {e}]")
            else:
                info_lines.append(f"\n[二进制文件，无法预览]")

        self.preview_info_var.set("\n".join(info_lines))

    def _preview_docx(self, file_path, info_lines):
        """预览 .docx 文件内容（从 word/document.xml 提取纯文本）"""
        import zipfile
        import xml.etree.ElementTree as ET

        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                if 'word/document.xml' not in z.namelist():
                    info_lines.append("\n[无法解析 docx 结构]")
                    self.preview_info_var.set("\n".join(info_lines))
                    return

                with z.open('word/document.xml') as f:
                    tree = ET.parse(f)

            # 提取所有 <w:t> 标签的文本
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            texts = []
            for t_elem in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
                if t_elem.text:
                    texts.append(t_elem.text)

            # 提取段落结构（<w:p> 之间加换行）
            paragraphs = []
            p_elems = tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p')
            for p in p_elems:
                p_texts = []
                for t in p.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
                    if t.text:
                        p_texts.append(t.text)
                if p_texts:
                    paragraphs.append(''.join(p_texts))

            if paragraphs:
                content = '\n'.join(paragraphs)
                if len(content) > PREVIEW_MAX_BYTES:
                    content = content[:PREVIEW_MAX_BYTES] + "\n\n... (内容已截断)"
                self.preview_text.insert(tk.END, content)
            else:
                info_lines.append("\n[文档内容为空或无纯文本]")

        except zipfile.BadZipFile:
            info_lines.append("\n[文件损坏或不是有效的 docx 格式]")
        except Exception as e:
            info_lines.append(f"\n[解析失败: {e}]")

        self.preview_info_var.set("\n".join(info_lines))

    def _preview_office_xml(self, file_path, info_lines, content_prefix, office_type):
        """预览 Office Open XML 格式（xlsx/pptx）的文本内容"""
        import zipfile
        import xml.etree.ElementTree as ET

        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                # 找到所有匹配的 XML 文件（如 xl/worksheets/sheet1.xml）
                target_files = [n for n in z.namelist() if n.startswith(content_prefix)]

                if not target_files:
                    info_lines.append(f"\n[无法解析 {office_type} 结构]")
                    self.preview_info_var.set("\n".join(info_lines))
                    return

                all_text = []
                for xml_name in sorted(target_files):
                    with z.open(xml_name) as f:
                        tree = ET.parse(f)

                    # 提取所有文本节点
                    for elem in tree.iter():
                        if elem.text and elem.text.strip():
                            all_text.append(elem.text.strip())

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

    @staticmethod
    def _fmt_size(size):
        for unit in ('B', 'KB', 'MB', 'GB'):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    # ════════════════════════════════════════════════════════════
    #  剪贴板操作
    # ════════════════════════════════════════════════════════════

    def copy_paths_to_clipboard(self):
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要复制路径的文件！")
            return

        selected_files = [self.found_files[i] for i in selected_indices]
        paths_text = '\n'.join(selected_files)

        self.root.clipboard_clear()
        self.root.clipboard_append(paths_text)
        self.root.update()

        self.status_var.set(f"已复制 {len(selected_files)} 个文件路径到剪贴板")
        messagebox.showinfo("成功", f"已复制 {len(selected_files)} 个文件路径到剪贴板！\n\n可以直接在其他地方粘贴使用。")

    def copy_files_to_clipboard(self):
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要复制的文件！")
            return

        selected_files = [self.found_files[i] for i in selected_indices]

        try:
            system = platform.system()
            if system == "Windows":
                self._copy_files_windows(selected_files)
            elif system == "Darwin":
                self._copy_files_macos(selected_files)
            else:
                self._copy_files_linux(selected_files)

            self.status_var.set(f"已复制 {len(selected_files)} 个文件到剪贴板")
            messagebox.showinfo(
                "成功",
                f"已复制 {len(selected_files)} 个文件到剪贴板！\n\n"
                f"现在可以在其他文件夹中按 Ctrl+V (Mac: Cmd+V) 粘贴文件。"
            )
        except Exception as e:
            messagebox.showerror("错误", f"复制文件到剪贴板失败：{str(e)}")

    def _copy_files_windows(self, files):
        import subprocess
        file_paths = ", ".join([f'"{f}"' for f in files])
        powershell_script = f"Set-Clipboard -Path {file_paths}"
        result = subprocess.run(["powershell", "-Command", powershell_script], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"PowerShell执行失败: {result.stderr}")

    def _copy_files_macos(self, files):
        import subprocess
        posix_files = ", ".join([f'POSIX file "{f}"' for f in files])
        script = f'''
        tell application "Finder"
            set theFiles to {{{posix_files}}}
            set the clipboard to theFiles
        end tell
        '''
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

    def _copy_files_linux(self, files):
        import subprocess
        try:
            file_uris = "\n".join([f"file://{f}" for f in files])
            proc = subprocess.Popen(
                ['xclip', '-selection', 'clipboard', '-t', 'text/uri-list'],
                stdin=subprocess.PIPE
            )
            proc.communicate(input=file_uris.encode())
            if proc.returncode != 0:
                raise RuntimeError("xclip执行失败")
        except FileNotFoundError:
            raise RuntimeError("需要安装xclip工具（sudo apt-get install xclip）")

    # ════════════════════════════════════════════════════════════
    #  文件操作（带冲突处理）
    # ════════════════════════════════════════════════════════════

    def perform_action(self, action):
        target_folder = self.target_folder.get()

        if not target_folder:
            messagebox.showwarning("警告", "请先选择目标文件夹！")
            return

        if not os.path.exists(target_folder):
            messagebox.showerror("错误", "目标文件夹不存在！")
            return

        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要操作的文件！")
            return

        selected_files = [self.found_files[i] for i in selected_indices]

        action_names = {"copy": "复制", "move": "剪切", "direct_move": "直接移动"}

        # ── 检测冲突（含源文件之间的同名冲突） ──
        # 第一轮：找出与目标文件夹已有文件的冲突
        # 第二轮：源文件之间同名的也算冲突
        from collections import defaultdict
        basename_groups = defaultdict(list)  # fname → [(src_path, dest_path), ...]

        for src_path in selected_files:
            fname = os.path.basename(src_path)
            dest_path = os.path.join(target_folder, fname)
            basename_groups[fname].append((src_path, dest_path))

        conflicts = []       # 需要用户决策的: (fname, src_path, dest_path, conflict_type)
        no_conflict = []     # 无冲突的: (fname, src_path, dest_path)

        for fname, items in basename_groups.items():
            dest_path = items[0][1]  # 共享同一个目标路径
            target_exists = os.path.exists(dest_path)

            if target_exists or len(items) > 1:
                # 有冲突：目标已存在 或 源文件之间同名
                for src_path, _ in items:
                    if target_exists:
                        conflict_type = "目标文件夹中已存在同名文件"
                    else:
                        conflict_type = "选中的源文件之间存在同名"
                    conflicts.append((fname, src_path, dest_path, conflict_type))
            else:
                # 无冲突
                no_conflict.append((fname, items[0][0], dest_path))

        # 处理冲突
        conflict_map = {}  # src_path → "skip" | "overwrite" | "rename"
        if conflicts:
            dlg = ConflictDialog(self.root, conflicts)
            self.root.wait_window(dlg)
            if dlg.result is None:
                self.status_var.set("操作已取消")
                return
            # dlg.result 是 {fname: decision}，但同名源文件可能有多个
            # 需要按 src_path 精确映射
            for fname, src_path, dest_path, _ in conflicts:
                conflict_map[src_path] = dlg.result.get(fname, "skip")

        # 确认操作
        total = len(selected_files)
        confirm = messagebox.askyesno(
            "确认操作",
            f"确定要{action_names[action]} {total} 个文件到:\n{target_folder} 吗？"
        )
        if not confirm:
            return

        # 执行操作 — 跟踪已占用的目标路径，防止同名源文件互相覆盖
        used_dest_paths = set()
        success_count = 0
        error_count = 0
        skip_count = 0

        # 先处理无冲突的，再处理有冲突的
        all_items = [(f, s, d) for f, s, d, _ in conflicts] + no_conflict
        # 去重（no_conflict 的 fname 不在 conflicts 里，不会重复）
        seen = set()
        ordered = []
        for fname, src_path, dest_path in all_items:
            if src_path not in seen:
                seen.add(src_path)
                ordered.append((fname, src_path, dest_path))

        for fname, src_path, dest_path in ordered:
            # 检查是否有冲突决策
            if src_path in conflict_map:
                decision = conflict_map[src_path]
                if decision == "skip":
                    skip_count += 1
                    continue
                elif decision == "rename":
                    dest_path = self._unique_dest(dest_path, used_dest_paths)
                # "overwrite" → 直接用原 dest_path

            # 无冲突文件也要检查：如果多个源文件同名，后续的会撞上前面已占用的路径
            elif dest_path in used_dest_paths:
                # 源文件之间同名但没被标记为冲突（理论上不会走到这里，防御性处理）
                dest_path = self._unique_dest(dest_path, used_dest_paths)

            try:
                if action == "copy":
                    shutil.copy2(src_path, dest_path)
                elif action in ["move", "direct_move"]:
                    shutil.move(src_path, dest_path)
                used_dest_paths.add(dest_path)
                success_count += 1
            except Exception as e:
                error_count += 1
                print(f"处理文件失败 {fname}: {str(e)}")

        # 显示结果
        result_parts = [f"操作完成！\n成功: {success_count} 个文件"]
        if skip_count > 0:
            result_parts.append(f"跳过: {skip_count} 个文件")
        if error_count > 0:
            result_parts.append(f"失败: {error_count} 个文件")
        result_msg = "\n".join(result_parts)

        messagebox.showinfo("结果", result_msg)
        self.status_var.set(result_msg.replace("\n", ", "))

        if action in ["move", "direct_move"]:
            self.scan_files()

    @staticmethod
    def _unique_dest(dest_path, used_paths=None):
        """生成不冲突的文件名，如 file(1).txt, file(2).txt ...
        
        Args:
            dest_path: 原始目标路径
            used_paths: 已被占用的目标路径集合（可选），同时检查磁盘和集合
        """
        if used_paths is None:
            used_paths = set()
        
        base, ext = os.path.splitext(dest_path)
        counter = 1
        while os.path.exists(dest_path) or dest_path in used_paths:
            dest_path = f"{base}({counter}){ext}"
            counter += 1
        return dest_path


def main():
    root = tk.Tk()
    app = FileManagerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FileFinder 主程序 - 批量文件筛选和操作工具

功能概览：
  1. 选择源文件夹，扫描里面的文件
  2. 按关键词（文件名）和扩展名（文件类型）筛选文件
  3. 支持递归搜索子文件夹
  4. 预览文件内容（文本/Office/图片等）
  5. 把选中的文件复制、剪切或移动到目标文件夹
  6. 处理同名文件冲突（覆盖/重命名/跳过）

架构说明：
  - FileManagerApp 是主类，继承自 PreviewMixin + ClipboardMixin
  - PreviewMixin（preview_mixin.py）：文件预览功能
  - ClipboardMixin（clipboard_mixin.py）：剪贴板操作功能
  - ConflictDialog（conflict_dialog.py）：冲突处理弹窗
  - constants.py：全局常量和工具函数

v2.0 - 新增：递归搜索子文件夹、文件预览、文件冲突处理
"""

import os
import shutil                                     # 文件操作（复制、移动）
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading                                  # 多线程，让扫描不卡 UI
import traceback                                  # 获取完整的错误堆栈信息
from collections import defaultdict               # 带默认值的字典


class ToolTip:
    """鼠标悬浮提示：鼠标放在控件上时，弹出一段解释文字

    tkinter 没有自带的 Tooltip，所以手写一个简单的。
    原理：监听鼠标进入/离开事件，进入时创建一个小窗口显示文字，离开时销毁。
    """

    def __init__(self, widget, text):
        """参数:
            widget: 要绑定提示的控件（如按钮、复选框等）
            text:   提示文字
        """
        self.widget = widget
        self.text = text
        self.tip_window = None   # 提示窗口对象（None 表示当前没显示）

        # 绑定鼠标事件
        widget.bind('<Enter>', self._show)    # 鼠标进入控件 → 显示提示
        widget.bind('<Leave>', self._hide)    # 鼠标离开控件 → 隐藏提示

    def _show(self, event=None):
        """显示提示窗口"""
        if self.tip_window:
            return  # 已经在显示了，不用重复创建

        # 计算提示窗口的位置：在控件下方偏右一点
        x = self.widget.winfo_rootx() + 20   # 控件左边缘 + 20像素
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5  # 控件底部 + 5像素

        # 创建一个无边框的顶层小窗口
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)          # 去掉窗口边框和标题栏
        tw.wm_geometry(f"+{x}+{y}")           # 设置位置
        tw.attributes('-topmost', True)        # 始终在最前面

        # 在小窗口里放一个 Label 显示文字
        label = tk.Label(
            tw, text=self.text,
            justify=tk.LEFT,                   # 文字左对齐
            background="#ffffe0",              # 淡黄色背景（经典提示框颜色）
            relief=tk.SOLID,                   # 实线边框
            borderwidth=1,
            font=("Microsoft YaHei", 9),       # 微软雅黑 9号字
            padx=8, pady=4                     # 文字周围留 8x4 像素空白
        )
        label.pack()

    def _hide(self, event=None):
        """隐藏提示窗口"""
        if self.tip_window:
            self.tip_window.destroy()  # 销毁窗口
            self.tip_window = None

# 导入项目的其他模块
from constants import (
    COMMON_TYPES, compile_regex_patterns, match_file,
    CONFLICT_TARGET_EXISTS, CONFLICT_SOURCE_DUP,
)
from conflict_dialog import ConflictDialog        # 冲突处理对话框
from preview_mixin import PreviewMixin            # 文件预览功能
from clipboard_mixin import ClipboardMixin        # 剪贴板功能


class FileManagerApp(PreviewMixin, ClipboardMixin):
    """主应用类

    多继承说明：
    class FileManagerApp(PreviewMixin, ClipboardMixin):
    表示 FileManagerApp 同时拥有 PreviewMixin 和 ClipboardMixin 的所有方法。
    这是 Python 的"混入"（Mixin）模式，用来把不同功能分散到不同文件中。
    """

    def __init__(self, root):
        """初始化主应用

        参数:
            root: tkinter.Tk() 根窗口对象
        """
        self.root = root
        self.root.title("FileFinder v2.1")
        self.root.geometry("1100x750")

        # ── 界面变量 ──
        # StringVar 是 tkinter 的"可追踪变量"，和界面控件绑定后，
        #修改变量值会自动更新界面，反之亦然。
        self.folder_path = tk.StringVar()              # 源文件夹路径
        self.target_folder = tk.StringVar()            # 目标文件夹路径
        self.all_extensions = set()                     # 扫描到的所有扩展名（集合）
        self.found_files = []                           # 扫描到的完整文件路径列表
        self._scan_generation = 0                       # 扫描代际标记：防止过期线程覆盖新结果
        self.recursive_var = tk.BooleanVar(value=False) # 是否递归搜索（默认不递归）
        self.regex_var = tk.BooleanVar(value=False)     # 是否使用正则表达式搜索（默认不使用）

        # 创建界面上的所有控件
        self.create_widgets()

        # 绑定事件：当用户在文件列表里点击/选择不同文件时，触发预览
        self.file_listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

    # ════════════════════════════════════════════════════════════
    #  创建界面
    # ════════════════════════════════════════════════════════════

    def create_widgets(self):
        """创建所有 GUI 组件（按钮、输入框、列表等）

        界面从上到下分 5 个区域：
          1. 源文件夹选择区
          2. 搜索和筛选区（关键词 + 扩展名）
          3. 文件列表 + 预览（左右分栏）
          4. 文件操作区（复制/剪切/移动按钮）
          5. 状态栏
        """
        # 主框架：所有控件都放在这个框架里，padding="10" 表示四周留10像素
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        # sticky 表示控件"粘"在网格的哪些边上：
        #   tk.W=左, tk.E=右, tk.N=上, tk.S=下
        # 四个都写 = 控件会拉伸填满整个格子

        # 让主框架随窗口大小自动缩放
        self.root.columnconfigure(0, weight=1)   # weight=1 表示这一列会自动拉伸
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)     # 第3行（文件列表+预览）可伸缩

        # ── 区域 1：源文件夹选择 ──
        # LabelFrame 是带标题的分组框
        folder_frame = ttk.LabelFrame(main_frame, text="源文件夹", padding="10")
        folder_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        folder_frame.columnconfigure(1, weight=1) # 输入框所在列可伸缩

        ttk.Label(folder_frame, text="路径:").grid(row=0, column=0, sticky=tk.W, padx=5)
        # Entry 是文本输入框，textvariable 绑定到 self.folder_path
        # 用户在输入框里改文字 = self.folder_path 自动更新，反过来也一样
        ttk.Entry(folder_frame, textvariable=self.folder_path, width=50).grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=5
        )
        ttk.Button(folder_frame, text="浏览...", command=self.browse_folder).grid(
            row=0, column=2, padx=5
        )
        # Checkbutton 是复选框，variable 绑定到 self.recursive_var
        ttk.Checkbutton(
            folder_frame, text="递归搜索子文件夹", variable=self.recursive_var
        ).grid(row=0, column=3, padx=10)
        regex_cb = ttk.Checkbutton(
            folder_frame, text="正则表达式", variable=self.regex_var
        )
        regex_cb.grid(row=0, column=4, padx=10)
        # 鼠标悬浮提示：用通俗语言解释正则表达式是什么
        ToolTip(regex_cb, "正则表达式：一种高级搜索方式，可以写更灵活的匹配规则。\n"
                        "比如输入 \'\\d{4}\' 可以匹配4位数字，输入 \'jpg|png\' 可以同时匹配两种格式。\n"
                        "如果你不了解正则表达式，保持不勾选即可，用普通关键词搜索就行。")

        # ── 区域 2：搜索和筛选 ──
        search_frame = ttk.LabelFrame(main_frame, text="搜索和筛选", padding="10")
        search_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        search_frame.columnconfigure(0, weight=1)

        # 关键词输入框（多行文本框 + 滚动条）
        keyword_frame = ttk.Frame(search_frame)
        keyword_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        keyword_frame.columnconfigure(1, weight=1)

        ttk.Label(keyword_frame, text="关键词(每行一个):").grid(row=0, column=0, sticky=tk.W, padx=5)

        # Text 是多行文本输入框（和 Entry 不同，Text 支持多行）
        text_frame = ttk.Frame(keyword_frame)
        text_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        self.keyword_text = tk.Text(text_frame, height=3, width=60)
        # 滚动条和文本框联动：滚动条控制文本框，文本框内容变化通知滚动条
        scrollbar_keyword = ttk.Scrollbar(text_frame, command=self.keyword_text.yview)
        self.keyword_text.configure(yscrollcommand=scrollbar_keyword.set)
        self.keyword_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        scrollbar_keyword.pack(side=tk.RIGHT, fill=tk.Y)

        # 扫描按钮和清空按钮（放在关键词框右侧）
        btn_col_frame = ttk.Frame(keyword_frame)
        btn_col_frame.grid(row=1, column=2, padx=5, sticky=tk.N)
        self.scan_button = ttk.Button(btn_col_frame, text="扫描文件", command=self.scan_files)
        self.scan_button.pack(pady=(0, 3))
        ttk.Button(btn_col_frame, text="清空关键词", command=self.clear_keywords).pack()

        # 文件类型筛选按钮（全选/全不选/常用类型）
        ttk.Label(search_frame, text="文件类型筛选:").grid(
            row=1, column=0, sticky=tk.W, padx=5, pady=5
        )
        type_frame = ttk.Frame(search_frame)
        type_frame.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5)

        ttk.Button(type_frame, text="全选", command=self.select_all_types).grid(row=0, column=0, padx=2)
        ttk.Button(type_frame, text="全不选", command=self.deselect_all_types).grid(row=0, column=1, padx=2)
        ttk.Button(type_frame, text="常用类型", command=self.select_common_types).grid(row=0, column=2, padx=2)

        # 扩展名复选框区域（横向滚动，用 Canvas 实现）
        # 原理：Canvas 里面放一个 Frame，Frame 太宽时 Canvas 可以横向滚动
        self.extension_checkboxes = {}            # {扩展名: BooleanVar} 的字典
        checkbox_outer = ttk.Frame(search_frame)
        checkbox_outer.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=3)

        # Canvas 用来承载扩展名复选框（支持横向滚动）
        self.checkbox_canvas = tk.Canvas(checkbox_outer, height=28, highlightthickness=0)
        h_scroll = ttk.Scrollbar(checkbox_outer, orient=tk.HORIZONTAL, command=self.checkbox_canvas.xview)
        self.checkbox_canvas.configure(xscrollcommand=h_scroll.set)

        self.checkbox_canvas.pack(side=tk.TOP, fill=tk.X, expand=True)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        # 复选框实际放在这个 Frame 里，嵌入 Canvas
        self.checkbox_container = ttk.Frame(self.checkbox_canvas)
        # create_window 把 Frame 画到 Canvas 上
        self.checkbox_canvas_window = self.checkbox_canvas.create_window(
            (0, 0), window=self.checkbox_container, anchor=tk.NW
        )
        # 当内部 Frame 大小变化时，更新 Canvas 的滚动范围
        self.checkbox_container.bind("<Configure>", lambda e: self.checkbox_canvas.configure(
            scrollregion=self.checkbox_canvas.bbox("all")
        ))
        # 当 Canvas 大小变化时，让内部 Frame 高度跟 Canvas 一致
        self.checkbox_canvas.bind("<Configure>", lambda e: self.checkbox_canvas.itemconfig(
            self.checkbox_canvas_window, height=e.height
        ))

        # ── 区域 3：文件列表（左）+ 预览（右），用 PanedWindow 可拖拽调整比例 ──
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.grid(row=2, column=0, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)

        # --- 左侧：文件列表 ---
        list_frame = ttk.LabelFrame(paned, text="找到的文件", padding="5")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        paned.add(list_frame, weight=3)          # weight=3 表示左侧占 3 份宽度

        # Listbox + Scrollbar（文件列表 + 滚动条）
        list_inner = ttk.Frame(list_frame)
        list_inner.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_inner.columnconfigure(0, weight=1)
        list_inner.rowconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(list_inner)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # selectmode=tk.MULTIPLE 允许用户同时选多个文件
        self.file_listbox = tk.Listbox(
            list_inner, selectmode=tk.MULTIPLE, yscrollcommand=scrollbar.set, height=12
        )
        self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.config(command=self.file_listbox.yview)

        # 文件选择按钮（全选/全不选/反选）
        select_btn_frame = ttk.Frame(list_frame)
        select_btn_frame.grid(row=1, column=0, pady=3)
        ttk.Button(select_btn_frame, text="全选", command=self.select_all_files).pack(side=tk.LEFT, padx=3)
        ttk.Button(select_btn_frame, text="全不选", command=self.deselect_all_files).pack(side=tk.LEFT, padx=3)
        ttk.Button(select_btn_frame, text="反选", command=self.invert_selection).pack(side=tk.LEFT, padx=3)

        # 剪贴板操作按钮（这两个方法来自 ClipboardMixin）
        clipboard_frame = ttk.LabelFrame(list_frame, text="剪贴板操作", padding="3")
        clipboard_frame.grid(row=2, column=0, pady=3, sticky=(tk.W, tk.E))
        ttk.Button(clipboard_frame, text="复制路径到剪贴板", command=self.copy_paths_to_clipboard).pack(side=tk.LEFT, padx=3)
        ttk.Button(clipboard_frame, text="复制文件到剪贴板", command=self.copy_files_to_clipboard).pack(side=tk.LEFT, padx=3)

        # --- 右侧：文件预览 ---
        preview_frame = ttk.LabelFrame(paned, text="文件预览", padding="5")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(1, weight=1)
        paned.add(preview_frame, weight=2)       # weight=2 表示右侧占 2 份宽度

        # 预览区顶部：文件元信息（文件名、大小、路径等）
        self.preview_info_var = tk.StringVar(value="选择文件以预览")
        ttk.Label(preview_frame, textvariable=self.preview_info_var, wraplength=350).grid(
            row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 3)
        )

        # 预览区主体：可滚动的文本框，显示文件内容
        # state=tk.DISABLED 表示只读（不能编辑），需要写入时临时设为 NORMAL
        self.preview_text = scrolledtext.ScrolledText(
            preview_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10)
        )
        self.preview_text.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # ── 区域 4：文件操作区 ──
        action_frame = ttk.LabelFrame(main_frame, text="文件操作", padding="10")
        action_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=5)
        action_frame.columnconfigure(1, weight=1)

        ttk.Label(action_frame, text="目标文件夹:").grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Entry(action_frame, textvariable=self.target_folder, width=50).grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=5
        )
        ttk.Button(action_frame, text="浏览...", command=self.browse_target).grid(row=0, column=2, padx=5)

        # 操作按钮：复制/剪切
        btn_frame = ttk.Frame(action_frame)
        btn_frame.grid(row=1, column=0, columnspan=3, pady=8)
        # lambda: self.perform_action("copy") → 点击时调用 perform_action，传入 "copy" 参数
        # 不能直接写 command=self.perform_action("copy")，因为那样会在创建按钮时就执行函数
        ttk.Button(btn_frame, text="复制到目标文件夹", command=lambda: self.perform_action("copy")).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="剪切到目标文件夹", command=lambda: self.perform_action("move")).pack(side=tk.LEFT, padx=5)

        # ── 区域 5：状态栏 ──
        self.status_var = tk.StringVar(value="就绪")
        # relief=tk.SUNKEN 让标签有"凹下去"的视觉效果，像状态栏
        ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN).grid(
            row=5, column=0, sticky=(tk.W, tk.E), pady=3
        )

    # ════════════════════════════════════════════════════════════
    #  文件夹浏览：弹出"选择文件夹"对话框
    # ════════════════════════════════════════════════════════════

    def browse_folder(self):
        """弹出系统自带的"选择文件夹"对话框，选择源文件夹"""
        folder = filedialog.askdirectory(title="选择源文件夹")
        if folder:  # 用户选了文件夹（没点取消）
            self.folder_path.set(folder)
            self.status_var.set(f"已选择文件夹: {folder}")

    def browse_target(self):
        """弹出"选择文件夹"对话框，选择目标文件夹"""
        folder = filedialog.askdirectory(title="选择目标文件夹")
        if folder:
            self.target_folder.set(folder)
            self.status_var.set(f"已选择目标文件夹: {folder}")

    # ════════════════════════════════════════════════════════════
    #  扫描文件（支持递归 + 子线程，不卡 UI）
    # ════════════════════════════════════════════════════════════

    def clear_keywords(self):
        """清空关键词输入框"""
        self.keyword_text.delete("1.0", tk.END)  # "1.0" = 第1行第0列，tk.END = 最后

    def scan_files(self):
        """扫描源文件夹中的文件

        核心流程：
        1. 读取用户输入的关键词和选中的扩展名
        2. 在子线程中遍历文件夹（不卡 UI）
        3. 遍历完成后回到主线程更新界面

        为什么要用子线程？
        os.walk 遍历大文件夹时可能要好几秒，
        如果在主线程（UI线程）执行，界面会卡死无法操作。
        所以把耗时的遍历操作放到子线程，遍历完再用 root.after() 回主线程更新 UI。
        """
        source_folder = self.folder_path.get()

        # 输入验证
        if not source_folder:
            messagebox.showwarning("警告", "请先选择源文件夹！")
            return

        if not os.path.exists(source_folder):
            messagebox.showerror("错误", "源文件夹不存在！")
            return

        # ── 读取筛选条件 ──
        # 获取关键词：从多行文本框里读取，按换行分割，去掉空行和前后空格
        keyword_text = self.keyword_text.get("1.0", tk.END).strip()
        keywords = [kw.strip() for kw in keyword_text.split('\n') if kw.strip()] if keyword_text else []

        # 获取选中的扩展名：遍历 extension_checkboxes 字典，找出被勾选的
        # 用集合（set）存储：match_file 里做 "in" 判断时是 O(1)，比列表快
        selected_extensions = {
            ext for ext, var in self.extension_checkboxes.items() if var.get()
        }

        recursive = self.recursive_var.get()
        use_regex = self.regex_var.get()

        # 如果使用正则表达式，先验证所有关键词是否是有效的正则表达式
        regex_patterns = None
        if use_regex and keywords:
            try:
                regex_patterns = compile_regex_patterns(keywords)
            except ValueError as e:
                messagebox.showerror("正则表达式错误", str(e))
                return

        self.status_var.set("正在扫描文件...")
        self.scan_button.config(state=tk.DISABLED)  # 扫描期间禁用按钮，防止重复点击
        self._scan_generation += 1                  # 代际+1：旧线程的结果会被丢弃
        generation = self._scan_generation

        # ── 子线程：执行耗时的文件遍历 ──
        def _scan_thread():
            found = []              # 存放匹配的文件完整路径
            extensions_found = set()  # 收集所有出现的扩展名（避免主线程重复遍历）
            error_msg = None        # 如果扫描出错，记录错误信息
            try:
                if recursive:
                    # 递归模式：os.walk 会遍历所有子文件夹
                    for dirpath, dirnames, filenames in os.walk(source_folder):
                        for fname in filenames:
                            full_path = os.path.join(dirpath, fname)
                            _, ext = os.path.splitext(fname)
                            ext = ext.lower()
                            if ext:
                                extensions_found.add(ext)
                            if match_file(fname, keywords, selected_extensions, regex_patterns):
                                found.append(full_path)
                else:
                    # 非递归模式：只看源文件夹这一层
                    for item in os.listdir(source_folder):
                        full_path = os.path.join(source_folder, item)
                        if not os.path.isfile(full_path):
                            continue  # 跳过子文件夹，只处理文件
                        _, ext = os.path.splitext(item)
                        ext = ext.lower()
                        if ext:
                            extensions_found.add(ext)
                        if match_file(item, keywords, selected_extensions, regex_patterns):
                            found.append(full_path)
            except Exception as e:
                error_msg = f"{str(e)}\n{traceback.format_exc()}"

            # ── 回到主线程更新 UI ──
            def _update_ui():
                self.scan_button.config(state=tk.NORMAL)  # 恢复扫描按钮
                if generation != self._scan_generation:
                    return  # 已有更新的扫描在进行/完成，丢弃这份过期结果
                if error_msg:
                    messagebox.showerror("错误", f"扫描文件时出错: {error_msg}")
                    self.status_var.set("扫描失败")
                    return

                self.found_files = found              # 保存扫描结果
                self.update_file_list()               # 更新文件列表控件
                self.all_extensions = extensions_found  # 用子线程收集的扩展名（避免主线程再次遍历）
                self.create_extension_checkboxes()     # 在主线程创建复选框控件
                self.status_var.set(f"找到 {len(self.found_files)} 个文件" + ("（递归）" if recursive else ""))

            self.root.after(0, _update_ui)  # 调度到主线程执行

        # 启动子线程（daemon=True 表示主程序退出时自动结束此线程）
        threading.Thread(target=_scan_thread, daemon=True).start()

    def create_extension_checkboxes(self):
        """根据收集到的扩展名，创建横向排列的复选框

        每次调用时：
        1. 删除旧的复选框
        2. 按字母顺序排列扩展名
        3. 为每个扩展名创建一个 Checkbutton，默认全部勾选
        """
        # 销毁旧复选框
        for widget in self.checkbox_container.winfo_children():
            widget.destroy()
        self.extension_checkboxes.clear()

        # 按字母排序（更直观）
        sorted_extensions = sorted(self.all_extensions)

        # 为每个扩展名创建一个复选框
        for ext in sorted_extensions:
            var = tk.BooleanVar(value=True)  # 默认勾选
            cb = ttk.Checkbutton(self.checkbox_container, text=ext, variable=var)
            cb.pack(side=tk.LEFT, padx=4, pady=2)  # 横向排列
            self.extension_checkboxes[ext] = var    # 存入字典，方便后续查询

    # ════════════════════════════════════════════════════════════
    #  文件类型筛选快捷操作
    # ════════════════════════════════════════════════════════════

    def select_all_types(self):
        """全选所有扩展名"""
        for var in self.extension_checkboxes.values():
            var.set(True)

    def deselect_all_types(self):
        """取消选择所有扩展名"""
        for var in self.extension_checkboxes.values():
            var.set(False)

    def select_common_types(self):
        """只选择常用文件类型（图片/文档/音视频/压缩包）"""
        for ext, var in self.extension_checkboxes.items():
            var.set(ext in COMMON_TYPES)  # COMMON_TYPES 定义在 constants.py

    # ════════════════════════════════════════════════════════════
    #  文件列表操作（选择/取消选择）
    # ════════════════════════════════════════════════════════════

    def update_file_list(self):
        """把扫描到的文件显示到文件列表控件中

        递归模式下显示相对路径（如 subfolder/photo.jpg），
        非递归模式只显示文件名。
        """
        self.file_listbox.delete(0, tk.END)   # 清空列表
        self._clear_preview()                   # 清空预览（来自 PreviewMixin）

        source = self.folder_path.get()         # 循环外只取一次，不用每个文件都读变量
        for file_path in self.found_files:
            try:
                # 计算相对于源文件夹的路径，如 "sub/photo.jpg"
                display = os.path.relpath(file_path, source)
            except ValueError:
                # 跨盘符时 relpath 会报 ValueError，退而显示文件名
                display = os.path.basename(file_path)
            self.file_listbox.insert(tk.END, display)

    def select_all_files(self):
        """全选文件列表中的所有文件"""
        self.file_listbox.select_set(0, tk.END)  # 选中从第0行到最后一行

    def deselect_all_files(self):
        """取消选择所有文件"""
        self.file_listbox.select_clear(0, tk.END)

    def invert_selection(self):
        """反选：选中的变未选中，未选中的变选中"""
        current_selection = set(self.file_listbox.curselection())  # 当前选中的行号
        total = self.file_listbox.size()
        self.file_listbox.select_clear(0, tk.END)
        for i in range(total):
            if i not in current_selection:    # 之前没选中的，现在选中
                self.file_listbox.select_set(i)

    # ════════════════════════════════════════════════════════════
    #  文件预览入口（连接 PreviewMixin）
    # ════════════════════════════════════════════════════════════

    def _on_listbox_select(self, event=None):
        """用户在文件列表中选中不同文件时，触发右侧预览

        这个方法是事件处理器，由 <<ListboxSelect>> 事件自动调用。
        """
        sel = self.file_listbox.curselection()  # 获取当前选中的行号
        if not sel:
            self._clear_preview()
            return
        idx = sel[-1]                            # 取最后点击的行（多选时更符合直觉）
        if idx < len(self.found_files):
            self._preview_file(self.found_files[idx])  # _preview_file 来自 PreviewMixin

    # ════════════════════════════════════════════════════════════
    #  文件操作：复制/剪切/移动（带冲突检测）
    # ════════════════════════════════════════════════════════════

    def perform_action(self, action):
        """执行文件操作（复制/剪切）

        整体流程：
        1. 验证输入（目标文件夹、选中的文件）
        2. 检测冲突（目标已有同名文件 / 源文件之间同名）
        3. 弹出冲突对话框让用户选择处理方式
        4. 确认操作
        5. 逐个执行，跟踪结果（成功/跳过/失败）
        6. 显示结果

        参数:
            action: "copy"（复制）、"move"（剪切）
        """
        target_folder = self.target_folder.get()

        # ── 输入验证 ──
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

        # 根据列表选中索引，获取对应的完整文件路径
        selected_files = [self.found_files[i] for i in selected_indices]

        # 操作类型的中文名（显示给用户看）
        action_names = {"copy": "复制", "move": "剪切"}

        # ── 第一步：检测冲突 ──
        # 按文件名分组，找出同名的情况
        # defaultdict(list) 的好处：访问不存在的键时自动创建空列表，不会报错
        basename_groups = defaultdict(list)  # fname → [(src_path, dest_path), ...]

        for src_path in selected_files:
            fname = os.path.basename(src_path)                    # 只取文件名
            dest_path = os.path.join(target_folder, fname)       # 目标路径
            basename_groups[fname].append((src_path, dest_path))

        conflicts = []       # 有冲突的文件: (文件名, 源路径, 目标路径, 冲突类型)
        no_conflict = []     # 无冲突的文件: (文件名, 源路径, 目标路径)

        for fname, items in basename_groups.items():
            dest_path = items[0][1]                # 同名文件共享同一个目标路径
            target_exists = os.path.exists(dest_path)  # 目标文件夹是否已有同名文件

            if target_exists or len(items) > 1:
                # 有冲突：目标已有同名文件，或多个源文件同名
                for src_path, _ in items:
                    if target_exists:
                        conflict_type = CONFLICT_TARGET_EXISTS
                    else:
                        conflict_type = CONFLICT_SOURCE_DUP
                    conflicts.append((fname, src_path, dest_path, conflict_type))
            else:
                # 无冲突
                no_conflict.append((fname, items[0][0], dest_path))

        # ── 第二步：处理冲突（如果有） ──
        conflict_map = {}  # src_path → "skip" / "overwrite" / "rename"
        if conflicts:
            # 弹出冲突对话框
            dlg = ConflictDialog(self.root, conflicts)
            self.root.wait_window(dlg)        # 等待对话框关闭
            if dlg.result is None:            # 用户点了取消
                self.status_var.set("操作已取消")
                return
            # 记录每个源文件的处理决策
            for fname, src_path, dest_path, _ in conflicts:
                conflict_map[src_path] = dlg.result.get(src_path, "skip")

        # ── 第三步：确认操作 ──
        total = len(selected_files)
        confirm = messagebox.askyesno(
            "确认操作",
            f"确定要{action_names[action]} {total} 个文件到:\n{target_folder} 吗？"
        )
        if not confirm:
            return

        # ── 第四步：逐个执行操作 ──
        # used_dest_paths 跟踪"已经被占用的目标路径"，
        # 防止多个同名源文件互相覆盖（比如 A/a.txt 和 B/a.txt 都要放到目标文件夹）
        used_dest_paths = set()
        success_count = 0
        error_count = 0
        skip_count = 0

        # 合并有冲突和无冲突的文件列表，去重
        all_items = [(f, s, d) for f, s, d, _ in conflicts] + no_conflict
        seen = set()
        ordered = []
        for fname, src_path, dest_path in all_items:
            if src_path not in seen:
                seen.add(src_path)
                ordered.append((fname, src_path, dest_path))

        # 逐个文件处理
        failed_files = []  # 记录失败的文件名和原因
        for fname, src_path, dest_path in ordered:
            # 如果这个文件有冲突决策
            if src_path in conflict_map:
                decision = conflict_map[src_path]
                if decision == "skip":
                    skip_count += 1
                    continue                              # 跳过，不处理
                elif decision == "rename":
                    dest_path = self._unique_dest(dest_path, used_dest_paths)  # 重命名
                elif decision == "overwrite" and dest_path in used_dest_paths:
                    # 关键保护：目标路径已被本批次的前一个文件占用
                    # （说明这是"源文件之间同名"的冲突），
                    # 此时再覆盖会把前一个文件的内容冲掉（move 时等于数据丢失），
                    # 所以强制改为重命名。
                    dest_path = self._unique_dest(dest_path, used_dest_paths)

            # 无冲突文件也要检查：前面可能已有同名文件占了目标路径
            elif dest_path in used_dest_paths:
                dest_path = self._unique_dest(dest_path, used_dest_paths)

            # 执行实际的文件操作
            try:
                if action == "copy":
                    shutil.copy2(src_path, dest_path)     # 复制（保留元信息）
                elif action == "move":
                    shutil.move(src_path, dest_path)       # 移动
                used_dest_paths.add(dest_path)             # 记录已占用的目标路径
                success_count += 1
            except Exception as e:
                error_count += 1
                # 记录失败的文件名和原因
                failed_files.append((fname, str(e)))
                # 记录详细错误信息到控制台，方便调试
                error_detail = traceback.format_exc()
                print(f"处理文件失败 {fname}: {str(e)}\n{error_detail}")

        # ── 第五步：显示结果 ──
        result_parts = [f"操作完成！\n成功: {success_count} 个文件"]
        if skip_count > 0:
            result_parts.append(f"跳过: {skip_count} 个文件")
        if error_count > 0:
            result_parts.append(f"失败: {error_count} 个文件")
            # 显示失败文件的详细信息（最多显示5个）
            if failed_files:
                result_parts.append("\n失败详情：")
                for fname, reason in failed_files[:5]:
                    result_parts.append(f"  • {fname}: {reason}")
                if len(failed_files) > 5:
                    result_parts.append(f"  ... 还有 {len(failed_files) - 5} 个文件")
        result_msg = "\n".join(result_parts)

        messagebox.showinfo("结果", result_msg)
        self.status_var.set(result_msg.replace("\n", ", "))

        # 剪切/移动操作后，源文件夹的文件少了，需要重新扫描
        if action == "move":
            self.scan_files()

    @staticmethod
    def _unique_dest(dest_path, used_paths=None):
        """生成不冲突的文件名

        如果目标路径已被占用，自动加编号，如：
          D:\target\file.txt  → D:\target\file(1).txt  → D:\target\file(2).txt

        参数:
            dest_path:  原始目标路径
            used_paths: 已被占用的路径集合（同时检查磁盘文件和这个集合）

        返回:
            一个不冲突的新路径
        """
        if used_paths is None:
            used_paths = set()

        base, ext = os.path.splitext(dest_path)  # 分离 "D:\target\file" 和 ".txt"
        counter = 1
        max_attempts = 10000
        # 循环直到找到一个不存在的路径
        while os.path.exists(dest_path) or dest_path in used_paths:
            if counter > max_attempts:
                raise RuntimeError(
                    f"无法为 '{os.path.basename(dest_path)}' 生成不冲突的文件名"
                    f"（已尝试 {max_attempts} 次）"
                )
            dest_path = f"{base}({counter}){ext}"  # file(1).txt, file(2).txt ...
            counter += 1
        return dest_path


# ════════════════════════════════════════════════════════════
#  程序入口
# ════════════════════════════════════════════════════════════

def main():
    """程序入口：创建主窗口，启动事件循环"""
    root = tk.Tk()                           # 创建 tkinter 主窗口
    app = FileManagerApp(root)               # 创建应用实例（构建界面）
    root.mainloop()                          # 启动事件循环（程序开始响应用户操作）


# 当直接运行这个文件时（python file_manager.py），执行 main()
# 当被其他文件 import 时，不会执行 main()
if __name__ == "__main__":
    main()

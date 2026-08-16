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
  - constants.py：全局常量（含 UI 配色）和工具函数

界面说明（v2.2）：
  - UI 框架从 tkinter.ttk 迁移到 customtkinter（CTk）
  - 风格：浅色现代风 + 蓝色点缀，配色集中在 constants.UI
  - 逻辑层（扫描/筛选/操作/冲突）与 v2.1 完全一致，只换 UI 层

v2.0 - 新增：递归搜索子文件夹、文件预览、文件冲突处理
v2.1 - 修复：覆盖冲突数据丢失、xlsx 预览、扫描并发防护
v2.2 - 界面重做为 customtkinter 浅色现代风
"""

import os
import shutil                                     # 文件操作（复制、移动）
import tkinter as tk
from tkinter import filedialog, messagebox
import threading                                  # 多线程，让扫描不卡 UI
import traceback                                  # 获取完整的错误堆栈信息
from collections import defaultdict               # 带默认值的字典

import customtkinter as ctk                       # 现代化 UI 框架（基于 tkinter）

# 导入项目的其他模块
from constants import (
    UI,
    COMMON_TYPES, compile_regex_patterns, match_file,
    CONFLICT_TARGET_EXISTS, CONFLICT_SOURCE_DUP,
    should_show_disclaimer, save_disclaimer_agreed,
)
from conflict_dialog import ConflictDialog        # 冲突处理对话框
from preview_mixin import PreviewMixin            # 文件预览功能
from clipboard_mixin import ClipboardMixin        # 剪贴板功能
from disclaimer_dialog import DisclaimerDialog    # 启动风险提示弹窗


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

        # 现代风提示框：白底 + 浅灰边框（跟随 constants.UI 配色）
        label = tk.Label(
            tw, text=self.text,
            justify=tk.LEFT,                   # 文字左对齐
            background=UI.CARD,                # 白底
            foreground=UI.TEXT,                # 深色文字
            relief=tk.SOLID,                   # 实线边框
            borderwidth=1,
            highlightbackground=UI.BORDER,
            font=(UI.FONT, 9),
            padx=10, pady=6
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
from pack_dialog import PackDialog                # 打包到 ZIP 对话框


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
        self.root.title("FileFinder v2.2")
        # 自适应屏幕：winfo_screenwidth/height 与 geometry 同为逻辑单位，
        # 直接比较即可。预留 100 像素给任务栏和标题栏，防止窗口超出屏幕底部。
        # （CTk 内部会把逻辑单位乘 DPI 缩放系数转成物理像素，不用我们管）
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        win_w = min(1150, sw - 40)
        win_h = min(780, sh - 100)
        self.root.geometry(f"{win_w}x{win_h}")
        self.root.minsize(min(980, win_w), min(640, win_h))  # 最小尺寸不超过初始尺寸
        self.root.configure(fg_color=UI.BG)       # 窗口底色

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
    #  界面搭建辅助：统一的卡片、标题、按钮样式
    # ════════════════════════════════════════════════════════════

    def _card(self, parent):
        """创建一个"卡片"容器：白底 + 圆角，所有功能区都长在卡片上"""
        return ctk.CTkFrame(
            parent,
            fg_color=UI.CARD,          # 白底
            corner_radius=10,          # 圆角
            border_width=1,
            border_color=UI.BORDER,    # 浅灰描边，让卡片边界更清晰
        )

    def _card_title(self, card, text):
        """卡片左上角的小标题（蓝色、加粗、小字号）"""
        ctk.CTkLabel(
            card, text=text,
            font=(UI.FONT, 12, "bold"),
            text_color=UI.ACCENT,
        ).pack(anchor=tk.W, padx=12, pady=(10, 2))

    def _make_button(self, parent, text, command, style="solid",
                     width=80, height=32):
        """创建统一风格的按钮

        style:
            "solid"   — 实心蓝底白字（主要操作）
            "outline" — 蓝边蓝字白底（次要操作）
            "ghost"   — 灰字透明底（最轻量的操作）
        """
        if style == "solid":
            return ctk.CTkButton(
                parent, text=text, command=command,
                width=width, height=height, font=(UI.FONT, 12),
                fg_color=UI.ACCENT, hover_color=UI.ACCENT_HOVER,
            )
        elif style == "outline":
            return ctk.CTkButton(
                parent, text=text, command=command,
                width=width, height=height, font=(UI.FONT, 12),
                fg_color=UI.CARD, hover_color=UI.ACCENT_LIGHT,
                border_width=1, border_color=UI.ACCENT,
                text_color=UI.ACCENT,
            )
        else:  # ghost
            return ctk.CTkButton(
                parent, text=text, command=command,
                width=width, height=height, font=(UI.FONT, 11),
                fg_color="transparent", hover_color=UI.ACCENT_LIGHT,
                text_color=UI.TEXT_DIM,
            )

    # ════════════════════════════════════════════════════════════
    #  创建界面
    # ════════════════════════════════════════════════════════════

    def create_widgets(self):
        """创建所有 GUI 组件

        界面从上到下分 6 个区域：
          0. 顶部标题栏（应用名 + 一句话说明）
          1. 源文件夹卡片
          2. 搜索和筛选卡片（关键词 + 扩展名）
          3. 文件列表 + 预览（左右分栏，可伸缩）
          4. 文件操作卡片
          5. 底部状态栏
        """
        # 状态栏先创建并 pack（side=BOTTOM）：
        # pack 按调用顺序分配空间，先让状态栏占住底部 28 像素，
        # 主容器再吃掉剩余空间，保证状态栏永远不会被挤出可视区。
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ctk.CTkFrame(
            self.root, height=28, corner_radius=0,
            fg_color=UI.CARD,
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        status_bar.pack_propagate(False)          # 固定高度，不被内容撑开
        ctk.CTkLabel(
            status_bar, textvariable=self.status_var,
            font=(UI.FONT, 11), text_color=UI.TEXT_DIM,
        ).pack(side=tk.LEFT, padx=12)

        # 主容器：占满窗口剩余空间，四周留白 12 像素
        # pack 布局从上到下堆叠；中间列表区用 expand 吃掉剩余空间
        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 8))

        # ── 区域 0：顶部标题栏 ──
        header = ctk.CTkFrame(main, fg_color="transparent")
        header.pack(fill=tk.X, pady=(0, 8))
        ctk.CTkLabel(
            header, text="FileFinder",
            font=(UI.FONT, 20, "bold"), text_color=UI.TEXT,
        ).pack(side=tk.LEFT)
        ctk.CTkLabel(
            header, text="  批量文件筛选与整理工具",
            font=(UI.FONT, 12), text_color=UI.TEXT_DIM,
        ).pack(side=tk.LEFT, pady=(6, 0))

        # ── 区域 1：源文件夹卡片 ──
        folder_card = self._card(main)
        folder_card.pack(fill=tk.X, pady=(0, 8))
        self._card_title(folder_card, "源文件夹")

        folder_row = ctk.CTkFrame(folder_card, fg_color="transparent")
        folder_row.pack(fill=tk.X, padx=12, pady=(0, 8))

        # CTkEntry 是单行输入框，textvariable 绑定到 self.folder_path
        ctk.CTkEntry(
            folder_row, textvariable=self.folder_path,
            placeholder_text="选择或输入要扫描的文件夹路径...",
            font=(UI.FONT, 12), height=34,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self._make_button(folder_row, "浏览...", self.browse_folder).pack(side=tk.LEFT)

        # 复选框行：递归 + 正则（放在第二行，避免第一行太挤）
        opt_row = ctk.CTkFrame(folder_card, fg_color="transparent")
        opt_row.pack(fill=tk.X, padx=12, pady=(0, 10))
        ctk.CTkCheckBox(
            opt_row, text="递归搜索子文件夹", variable=self.recursive_var,
            font=(UI.FONT, 12), fg_color=UI.ACCENT, hover_color=UI.ACCENT_HOVER,
        ).pack(side=tk.LEFT, padx=(0, 16))
        regex_cb = ctk.CTkCheckBox(
            opt_row, text="正则表达式", variable=self.regex_var,
            font=(UI.FONT, 12), fg_color=UI.ACCENT, hover_color=UI.ACCENT_HOVER,
        )
        regex_cb.pack(side=tk.LEFT)
        # 鼠标悬浮提示：用通俗语言解释正则表达式是什么
        ToolTip(regex_cb, "正则表达式：一种高级搜索方式，可以写更灵活的匹配规则。\n"
                        "比如输入 \'\\d{4}\' 可以匹配4位数字，输入 \'jpg|png\' 可以同时匹配两种格式。\n"
                        "如果你不了解正则表达式，保持不勾选即可，用普通关键词搜索就行。")

        # ── 区域 2：搜索和筛选卡片 ──
        search_card = self._card(main)
        search_card.pack(fill=tk.X, pady=(0, 8))
        self._card_title(search_card, "搜索和筛选")

        search_row = ctk.CTkFrame(search_card, fg_color="transparent")
        search_row.pack(fill=tk.X, padx=12, pady=(0, 4))

        # 关键词输入框（CTkTextbox 是多行文本框）
        kw_box = ctk.CTkFrame(search_row, fg_color="transparent")
        kw_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ctk.CTkLabel(
            kw_box, text="关键词（每行一个，留空表示不过滤）",
            font=(UI.FONT, 11), text_color=UI.TEXT_DIM,
        ).pack(anchor=tk.W, pady=(0, 3))
        self.keyword_text = ctk.CTkTextbox(
            kw_box, height=64, font=(UI.FONT, 12),
            border_width=1, border_color=UI.BORDER,
        )
        self.keyword_text.pack(fill=tk.X)

        # 扫描按钮和清空按钮（放在关键词框右侧）
        btn_col = ctk.CTkFrame(search_row, fg_color="transparent")
        btn_col.pack(side=tk.LEFT, anchor=tk.S, pady=(20, 0))
        self.scan_button = ctk.CTkButton(
            btn_col, text="扫描文件", command=self.scan_files,
            font=(UI.FONT, 13, "bold"), height=38, width=110,
            fg_color=UI.ACCENT, hover_color=UI.ACCENT_HOVER,
        )
        self.scan_button.pack(pady=(0, 6))
        self._make_button(btn_col, "清空关键词", self.clear_keywords,
                          style="ghost", width=110).pack()

        # 文件类型筛选按钮（全选/全不选/常用类型）
        type_row = ctk.CTkFrame(search_card, fg_color="transparent")
        type_row.pack(fill=tk.X, padx=12, pady=(2, 0))
        ctk.CTkLabel(
            type_row, text="文件类型筛选:",
            font=(UI.FONT, 11), text_color=UI.TEXT_DIM,
        ).pack(side=tk.LEFT, padx=(0, 8))
        self._make_button(type_row, "全选", self.select_all_types,
                          style="ghost", width=64, height=26).pack(side=tk.LEFT, padx=(0, 4))
        self._make_button(type_row, "全不选", self.deselect_all_types,
                          style="ghost", width=64, height=26).pack(side=tk.LEFT, padx=(0, 4))
        self._make_button(type_row, "常用类型", self.select_common_types,
                          style="ghost", width=76, height=26).pack(side=tk.LEFT)

        # 扩展名复选框区域（横向滚动的 CTkScrollableFrame）
        self.extension_checkboxes = {}            # {扩展名: BooleanVar} 的字典
        self.checkbox_container = ctk.CTkScrollableFrame(
            search_card, orientation="horizontal", height=48,
            fg_color=UI.BG,                       # 与窗口底色一致，形成"凹槽"感
        )
        self.checkbox_container.pack(fill=tk.X, padx=12, pady=(4, 10))

        # ── 区域 3：文件列表（左）+ 预览（右）──
        # CTk 没有 PanedWindow，用 grid 两列实现，左:右 = 3:2
        # 注意：content 先创建但不 pack，等操作卡片（区域4）pack 完再 pack，
        # 保证操作卡片先占住底部空间，content 再吃中间剩余空间。
        content = ctk.CTkFrame(main, fg_color="transparent")
        content.columnconfigure(0, weight=3)      # 左列占 3 份
        content.columnconfigure(1, weight=2)      # 右列占 2 份
        content.rowconfigure(0, weight=1)

        # --- 左侧：文件列表卡片 ---
        list_card = self._card(content)
        list_card.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self._card_title(list_card, "找到的文件")

        # tk.Listbox：CTk 没有列表控件，沿用 tk.Listbox 但手动配色融入风格
        list_inner = ctk.CTkFrame(list_card, fg_color="transparent")
        list_inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))

        scrollbar = ctk.CTkScrollbar(list_inner)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.file_listbox = tk.Listbox(
            list_inner,
            selectmode=tk.MULTIPLE,               # 允许同时选多个文件
            yscrollcommand=scrollbar.set,
            font=(UI.FONT, 11),
            bg=UI.CARD, fg=UI.TEXT,               # 白底深字
            selectbackground=UI.ACCENT,           # 选中行：蓝底
            selectforeground="#ffffff",           # 选中行：白字
            activestyle="none",                   # 去掉选中行的虚线框
            relief=tk.FLAT, highlightthickness=1, # 扁平边框 + 1像素浅灰描边
            highlightbackground=UI.BORDER,
            highlightcolor=UI.BORDER,
        )
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.configure(command=self.file_listbox.yview)

        # 注：全选/全不选/反选 和 剪贴板按钮已移到底部"文件操作"卡片，
        # 保证小窗口时也始终可见（列表卡片底部会被可伸缩区挤出）

        # --- 右侧：文件预览卡片 ---
        preview_card = self._card(content)
        preview_card.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self._card_title(preview_card, "文件预览")

        # 预览区顶部：文件元信息（文件名、大小、路径等）
        self.preview_info_var = tk.StringVar(value="选择文件以预览")
        ctk.CTkLabel(
            preview_card, textvariable=self.preview_info_var,
            font=(UI.FONT, 11), text_color=UI.TEXT_DIM,
            justify=tk.LEFT, anchor=tk.W, wraplength=360,
        ).pack(fill=tk.X, padx=12, pady=(0, 4))

        # 预览区主体：CTkTextbox 只读显示文件内容
        self.preview_text = ctk.CTkTextbox(
            preview_card, wrap="word",
            font=(UI.FONT_MONO, 11),              # 等宽字体看代码/日志更整齐
            border_width=1, border_color=UI.BORDER,
        )
        self.preview_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))
        self.preview_text.configure(state="disabled")  # 只读，写入时临时打开

        # ── 区域 4：文件操作卡片（side=BOTTOM 钉在主容器底部）──
        action_card = self._card(main)
        action_card.pack(fill=tk.X, side=tk.BOTTOM)
        self._card_title(action_card, "文件操作")

        target_row = ctk.CTkFrame(action_card, fg_color="transparent")
        target_row.pack(fill=tk.X, padx=12, pady=(0, 8))
        ctk.CTkEntry(
            target_row, textvariable=self.target_folder,
            placeholder_text="选择目标文件夹...",
            font=(UI.FONT, 12), height=34,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self._make_button(target_row, "浏览...", self.browse_target).pack(side=tk.LEFT)

        # 操作按钮：复制/剪切
        op_row = ctk.CTkFrame(action_card, fg_color="transparent")
        op_row.pack(fill=tk.X, padx=12, pady=(0, 10))
        # lambda: self.perform_action("copy") → 点击时调用 perform_action，传入 "copy" 参数
        # 不能直接写 command=self.perform_action("copy")，因为那样会在创建按钮时就执行函数
        ctk.CTkButton(
            op_row, text="复制到目标文件夹",
            command=lambda: self.perform_action("copy"),
            font=(UI.FONT, 12, "bold"), height=34, width=150,
            fg_color=UI.ACCENT, hover_color=UI.ACCENT_HOVER,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ctk.CTkButton(
            op_row, text="剪切到目标文件夹",
            command=lambda: self.perform_action("move"),
            font=(UI.FONT, 12, "bold"), height=34, width=150,
            fg_color=UI.ACCENT, hover_color=UI.ACCENT_HOVER,
        ).pack(side=tk.LEFT)
        # 打包按钮：与复制/剪切分开（右侧），outline 风格弱化视觉、不抢主操作
        self._make_button(
            op_row, "打包到 ZIP", self.open_pack_dialog,
            style="outline", width=150, height=34,
        ).pack(side=tk.RIGHT)

        # 辅助操作行：全选/全不选/反选（左）+ 剪贴板（右）
        # 放在底部卡片里，任何窗口大小都可见
        aux_row = ctk.CTkFrame(action_card, fg_color="transparent")
        aux_row.pack(fill=tk.X, padx=12, pady=(0, 10))
        self._make_button(aux_row, "全选", self.select_all_files,
                          style="ghost", width=64, height=28).pack(side=tk.LEFT, padx=(0, 4))
        self._make_button(aux_row, "全不选", self.deselect_all_files,
                          style="ghost", width=64, height=28).pack(side=tk.LEFT, padx=(0, 4))
        self._make_button(aux_row, "反选", self.invert_selection,
                          style="ghost", width=64, height=28).pack(side=tk.LEFT)
        # 剪贴板操作按钮（这两个方法来自 ClipboardMixin）
        self._make_button(aux_row, "复制路径到剪贴板", self.copy_paths_to_clipboard,
                          style="outline", height=28).pack(side=tk.RIGHT, padx=(0, 6))
        self._make_button(aux_row, "复制文件到剪贴板", self.copy_files_to_clipboard,
                          style="outline", height=28).pack(side=tk.RIGHT)

        # ── 区域 3 的 content 现在才 pack ──
        # 此时顶部卡片（header/源文件夹/搜索）和底部卡片（操作）都已各就各位，
        # content 用 expand 吃掉中间剩余的全部空间。
        content.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

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
    #  打包到 ZIP
    # ════════════════════════════════════════════════════════════

    def open_pack_dialog(self):
        """打开"打包到 ZIP"对话框

        默认打包内容 = 目标文件夹（保存位置也默认为目标文件夹，
        打开即可直接打包）；未设置目标文件夹则不预填。
        """
        initial = []
        tgt = self.target_folder.get()
        if tgt and os.path.isdir(tgt):
            initial.append(tgt)
        PackDialog(
            self.root,
            initial_paths=initial,
            target_folder=tgt,
        )

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
        self.scan_button.configure(state="disabled")  # 扫描期间禁用按钮，防止重复点击
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
                self.scan_button.configure(state="normal")  # 恢复扫描按钮
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
            cb = ctk.CTkCheckBox(
                self.checkbox_container, text=ext, variable=var,
                font=(UI.FONT, 11),
                fg_color=UI.ACCENT, hover_color=UI.ACCENT_HOVER,
                width=20,                        # 复选框本身小一点，排得更紧凑
            )
            cb.pack(side=tk.LEFT, padx=6, pady=2)  # 横向排列
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
    """程序入口：先展示风险提示，同意后才创建主窗口，启动事件循环"""
    # customtkinter 全局设置：浅色模式 + 蓝色主题
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()                         # 创建 CTk 主窗口（底层仍是 tkinter）

    # 先"透明隐藏"主窗口而不是 withdraw()：customtkinter 的 CTkToplevel
    # 在父窗口 withdrawn 状态下不会渲染，弹窗会因此显示不出来。
    # 用透明度隐藏则不影响子窗口（弹窗）显示。
    try:
        root.attributes("-alpha", 0.0)       # 主窗口隐藏，弹窗正常显示
    except tk.TclError:
        pass                                 # 个别平台不支持透明度，则让主窗口直接显示

    # 首次使用（或未勾选"不再提示"）时弹出风险提示，必须同意才能继续
    if should_show_disclaimer():
        dlg = DisclaimerDialog(root)
        root.wait_window(dlg)                # 模态等待弹窗关闭
        if not dlg.agreed:
            root.destroy()                   # 用户拒绝或直接关窗 → 退出程序
            return
        if dlg.dont_ask_again:
            save_disclaimer_agreed()         # 记录"不再提示"，以后启动不再弹出

    app = FileManagerApp(root)               # 创建应用实例（构建界面）
    root.attributes("-alpha", 1.0)           # 显示主窗口
    root.mainloop()                          # 启动事件循环（程序开始响应用户操作）


# 当直接运行这个文件时（python file_manager.py），执行 main()
# 当被其他文件 import 时，不会执行 main()
if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FileFinder - 关键词浮窗

常驻置顶的小输入窗：在其他软件里翻找文件时，不用切回主窗口就能随手输入
关键词（每行一个），内容与主界面的关键词框实时双向同步。

同步机制说明（与 file_manager.py 里的处理器配合）：
  - 监听底层 tkinter.Text 的 <<Modified>> 虚拟事件——它是文本控件最可靠的
    "内容已改变"信号：键盘输入、Ctrl+V、右键菜单粘贴、程序化 delete/insert
    都会触发
  - 实测确认：<<Modified>> 是"延迟派发"的（insert/delete 返回后事件才进队列），
    所以不能用"执行同步期间打个标志"的方式防循环（标志在事件到达时早已复位）；
    改用"内容比较"：两端文本一致就不复制，任何时序下都能自然收敛
  - tkinter 的 Modified 标志是"只触发一次"的：每次事件后必须重置
    （edit_modified(False)），否则后续修改不再触发事件；重置动作本身会再触发
    一次空事件，用 edit_modified() 的返回值把它过滤掉

架构说明：
  KeywordFloatWindow 只管"显示输入框 + 上报变化"，不直接触碰主窗口的控件；
  两者的镜像同步统一由 FileManagerApp._sync_keywords() 负责，
  避免两个窗口互相引用、逻辑分散。
"""

import tkinter as tk

import customtkinter as ctk

from constants import UI


class KeywordFloatWindow(ctk.CTkToplevel):
    """关键词浮窗（常驻置顶）

    参数:
        parent:    父窗口（主界面）
        on_change: 内容变化回调（无参数）。主窗口收到后自行决定如何镜像同步
        on_close:  窗口关闭回调（无参数，点标题栏 X 时触发）。
                   主窗口收到后复位"关键词浮窗"开关的状态并销毁本窗口
    """

    def __init__(self, parent, on_change, on_close):
        super().__init__(parent)
        self.on_change = on_change
        self.on_close = on_close

        self.title("关键词 - FileFinder")
        self.resizable(True, True)               # 宽高都可拖拽调整
        self.minsize(240, 100)                   # 最小尺寸限制，防止被拖没
        self.attributes("-topmost", True)        # 常驻最前
        self.configure(fg_color=UI.BG)           # 与主窗口一致的底色

        # 关键词输入框：与主窗口同款"每行一个关键词"多行文本框
        self.keyword_text = ctk.CTkTextbox(
            self, height=80, font=(UI.FONT, 12),
            border_width=1, border_color=UI.BORDER,
        )
        self.keyword_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 2))

        ctk.CTkLabel(
            self, text="每行一个关键词，与主窗口实时同步",
            font=(UI.FONT, 10), text_color=UI.TEXT_DIM,
        ).pack(anchor=tk.W, padx=12, pady=(0, 8))

        # 监听内容变化（CTkTextbox.bind 内部会转发到底层 tkinter.Text，
        # 并强制 add=True，不会覆盖控件自身的内部绑定）
        self.keyword_text.bind("<<Modified>>", self._on_modified)

        # 点标题栏 X：交给主窗口处理（复位开关 + 销毁本窗口）
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # 尺寸 + 默认位置（父窗口右缘内侧、标题栏下方）
        self.geometry("360x170")
        self._place_near_parent()

    # ────────────────────────────────────────────────────────────
    #  内部事件
    # ────────────────────────────────────────────────────────────

    def _on_modified(self, event=None):
        """文本框内容变化 → 上报给主窗口统一同步

        edit_modified() 返回"自上次重置以来是否有修改"；重置标志
        （edit_modified(False)）本身也会再触发一次事件，用返回值过滤掉。
        """
        changed = self.keyword_text.edit_modified()
        self.keyword_text.edit_modified(False)
        if not changed:
            return                               # 这是重置标志触发的空事件
        self.on_change()

    def _on_window_close(self):
        """点标题栏 X：通知主窗口（由它复位开关并销毁本窗口）"""
        self.on_close()

    def _place_near_parent(self):
        """默认位置：父窗口右缘内侧、标题栏下方约 60 逻辑像素处

        DPI 说明：CTk 的 geometry() 把"宽高"按缩放换算成物理像素，
        "+x+y" 位置则原样交给窗口系统（物理坐标）；而 winfo_rootx/
        winfo_width 同为物理像素——两套坐标天然一致，不用换算。
        但 winfo_screenwidth/height 返回的是逻辑值（经过实测验证），
        用于边界限制时要先乘缩放系数换成物理坐标。
        """
        try:
            parent = self.master
            scaling = self._get_window_scaling()      # 如 150% DPI → 1.5
            win_w = int(360 * scaling)                # 浮窗物理宽
            win_h = int(170 * scaling)                # 浮窗物理高
            margin = int(10 * scaling)

            x = (parent.winfo_rootx() + parent.winfo_width()
                 - win_w - int(30 * scaling))
            y = parent.winfo_rooty() + int(60 * scaling)

            # 防止超出屏幕：winfo_screenwidth/height 是逻辑值，乘缩放换物理
            screen_w = int(self.winfo_screenwidth() * scaling)
            screen_h = int(self.winfo_screenheight() * scaling)
            x = max(0, min(x, screen_w - win_w - margin))
            y = max(0, min(y, screen_h - win_h - margin))
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass    # 定位失败不影响功能，窗口系统会给出默认位置

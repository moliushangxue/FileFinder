#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FileFinder - 文件冲突处理对话框

当复制/移动文件时，如果目标文件夹已有同名文件，或者选中的多个源文件同名，
就会弹出这个对话框让用户选择怎么处理。

三种处理方式：
  - 覆盖（overwrite）：直接替换目标文件
  - 重命名（rename）：自动给文件名加编号，如 file(1).txt
  - 跳过（skip）：不处理这个文件

v2.2 - 界面从 tkinter.ttk 迁移到 customtkinter（浅色现代风）
"""

import os
import tkinter as tk

import customtkinter as ctk

# 从 constants.py 导入格式化函数、冲突类型常量和 UI 配色
from constants import fmt_size, CONFLICT_TARGET_EXISTS, UI


def _safe_size(path):
    """安全获取文件大小：文件被占用/删除/无权限时返回 0，不让弹窗崩掉"""
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


class ConflictDialog(ctk.CTkToplevel):
    """文件冲突处理对话框

    ctk.CTkToplevel 是 customtkinter 的弹窗类，表示一个独立于主窗口的子窗口。

    参数:
        parent: 父窗口（主界面），弹窗会显示在父窗口前方
        conflicts: 冲突列表，每项是 (文件名, 源路径, 目标路径, 冲突类型描述)
    """

    def __init__(self, parent, conflicts):
        """
        conflicts: list of (filename, src_path, dest_path, conflict_type)
        """
        super().__init__(parent)                # 调用父类 ctk.CTkToplevel 的初始化
        self.title("文件冲突")
        self.geometry("640x480")
        self.resizable(False, False)             # 禁止调整窗口大小
        self.configure(fg_color=UI.BG)           # 与主窗口一致的底色
        self.transient(parent)                   # 设为父窗口的附属窗口（总在前方）

        self.conflicts = conflicts
        # result 字典：记录每个源文件的处理决策
        # 键是源文件路径，值是 "skip" / "overwrite" / "rename" 之一
        self.result = {}

        self._build_ui()
        # 点右上角 X 按钮时调用 _on_cancel（等同取消）
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # 让弹窗居中显示在父窗口中央
        self.update_idletasks()                   # 先刷新布局，拿到真实尺寸
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

        # 模态窗口：阻止操作主窗口，直到关闭此弹窗
        # 注意：放在居中之后调用，否则 grab 期间取到的窗口位置可能不准
        self.grab_set()

    def _build_ui(self):
        """构建对话框的界面元素"""

        # ── 顶部：统计冲突类型 ──
        target_conflicts = sum(1 for _, _, _, ct in self.conflicts if ct == CONFLICT_TARGET_EXISTS)
        source_conflicts = len(self.conflicts) - target_conflicts

        summary_parts = []
        if target_conflicts:
            summary_parts.append(f"{target_conflicts} 个与目标文件夹冲突")
        if source_conflicts:
            summary_parts.append(f"{source_conflicts} 个源文件之间同名冲突")

        ctk.CTkLabel(
            self, text=f"发现文件冲突（{'，'.join(summary_parts)}），请选择处理方式：",
            font=(UI.FONT, 13, "bold"), text_color=UI.TEXT,
            wraplength=600, justify=tk.LEFT,
        ).pack(fill=tk.X, padx=14, pady=(14, 8))

        # ── 中间：冲突文件列表（白底卡片 + tk.Listbox 配色融入） ──
        list_card = ctk.CTkFrame(
            self, fg_color=UI.CARD, corner_radius=8,
            border_width=1, border_color=UI.BORDER,
        )
        list_card.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 8))

        scrollbar = ctk.CTkScrollbar(list_card)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=4)

        self.listbox = tk.Listbox(
            list_card, height=10,
            yscrollcommand=scrollbar.set,
            font=(UI.FONT, 11),
            bg=UI.CARD, fg=UI.TEXT,
            selectbackground=UI.ACCENT_LIGHT,     # 列表不需要选中，浅色即可
            selectforeground=UI.TEXT,
            activestyle="none",
            relief=tk.FLAT, highlightthickness=0,
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=4)
        scrollbar.configure(command=self.listbox.yview)

        # 遍历每个冲突，显示文件名、冲突类型、文件大小
        for fname, src, dest, conflict_type in self.conflicts:
            src_size = _safe_size(src)
            if conflict_type != CONFLICT_TARGET_EXISTS:
                # 源文件之间同名冲突：只显示源文件大小
                self.listbox.insert(
                    tk.END,
                    f"⚠ {fname}  — {conflict_type}（大小: {fmt_size(src_size)}）"
                )
            else:
                # 目标文件夹已有同名：显示源和目标的大小对比
                dest_size = _safe_size(dest)
                self.listbox.insert(
                    tk.END,
                    f"⚠ {fname}  — {conflict_type}（源: {fmt_size(src_size)} → 目标: {fmt_size(dest_size)}）"
                )

        # ── 底部：操作按钮 ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill=tk.X, padx=14, pady=(0, 14))

        # "全部覆盖"是危险操作（会替换已有文件），用红色提示
        ctk.CTkButton(
            btn_frame, text="全部覆盖",
            command=lambda: self._apply_all_action("overwrite"),
            font=(UI.FONT, 12), width=100, height=32,
            fg_color=UI.DANGER, hover_color=UI.DANGER_HOVER,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ctk.CTkButton(
            btn_frame, text="全部重命名",
            command=lambda: self._apply_all_action("rename"),
            font=(UI.FONT, 12), width=110, height=32,
            fg_color=UI.ACCENT, hover_color=UI.ACCENT_HOVER,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ctk.CTkButton(
            btn_frame, text="全部跳过",
            command=lambda: self._apply_all_action("skip"),
            font=(UI.FONT, 12), width=100, height=32,
            fg_color=UI.CARD, hover_color=UI.ACCENT_LIGHT,
            border_width=1, border_color=UI.ACCENT, text_color=UI.ACCENT,
        ).pack(side=tk.LEFT)
        ctk.CTkButton(
            btn_frame, text="取消", command=self._on_cancel,
            font=(UI.FONT, 12), width=80, height=32,
            fg_color="transparent", hover_color=UI.BORDER,
            text_color=UI.TEXT_DIM,
        ).pack(side=tk.RIGHT)

    def _apply_all_action(self, action):
        """用户点击"全部覆盖/重命名/跳过"时的处理

        把所有冲突文件的决策统一设为 action，然后关闭对话框。
        """
        for _, src_path, _, _ in self.conflicts:
            self.result[src_path] = action        # 每个源文件 → 对应决策
        self.destroy()                            # 关闭对话框

    def _on_cancel(self):
        """用户点击取消或关闭窗口"""
        self.result = None                        # None 表示用户取消了操作
        self.destroy()

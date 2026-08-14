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
"""

import os
import tkinter as tk
from tkinter import ttk

# 从 constants.py 导入格式化函数和冲突类型常量
from constants import fmt_size, CONFLICT_TARGET_EXISTS


def _safe_size(path):
    """安全获取文件大小：文件被占用/删除/无权限时返回 0，不让弹窗崩掉"""
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


class ConflictDialog(tk.Toplevel):
    """文件冲突处理对话框

    tk.Toplevel 是 tkinter 的弹窗基类，表示一个独立于主窗口的子窗口。

    参数:
        parent: 父窗口（主界面），弹窗会显示在父窗口前方
        conflicts: 冲突列表，每项是 (文件名, 源路径, 目标路径, 冲突类型描述)
    """

    def __init__(self, parent, conflicts):
        """
        conflicts: list of (filename, src_path, dest_path, conflict_type)
        """
        super().__init__(parent)                # 调用父类 tk.Toplevel 的初始化
        self.title("文件冲突")
        self.geometry("620x450")
        self.resizable(False, False)             # 禁止调整窗口大小
        self.transient(parent)                   # 设为父窗口的附属窗口（总在前方）
        self.grab_set()                          # 模态窗口：阻止操作主窗口，直到关闭此弹窗

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

    def _build_ui(self):
        """构建对话框的界面元素"""

        # ── 顶部：统计冲突类型 ──
        # 遍历 conflicts，统计"与目标文件夹冲突"和"源文件之间同名"各有多少
        target_conflicts = sum(1 for _, _, _, ct in self.conflicts if ct == CONFLICT_TARGET_EXISTS)
        source_conflicts = len(self.conflicts) - target_conflicts

        summary_parts = []
        if target_conflicts:
            summary_parts.append(f"{target_conflicts} 个与目标文件夹冲突")
        if source_conflicts:
            summary_parts.append(f"{source_conflicts} 个源文件之间同名冲突")

        ttk.Label(
            self, text=f"发现文件冲突（{'，'.join(summary_parts)}），请选择处理方式：",
            padding=10, wraplength=580            # wraplength: 文字自动换行宽度
        ).pack(fill=tk.X)

        # ── 中间：冲突文件列表 ──
        list_frame = ttk.Frame(self, padding=(10, 0))
        list_frame.pack(fill=tk.BOTH, expand=True)

        # 滚动条 + 列表框
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(list_frame, height=10, yscrollcommand=scrollbar.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)

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
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X)

        # "全部覆盖/重命名/跳过"：对所有冲突文件统一处理
        ttk.Button(btn_frame, text="全部覆盖", command=lambda: self._apply_all_action("overwrite")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="全部重命名", command=lambda: self._apply_all_action("rename")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="全部跳过", command=lambda: self._apply_all_action("skip")).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="取消", command=self._on_cancel).pack(side=tk.RIGHT, padx=4)

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

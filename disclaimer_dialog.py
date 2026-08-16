#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FileFinder - 启动风险提示弹窗

程序启动时展示免责声明和风险提示，用户必须勾选"我已知晓风险"才能使用；
勾选"不再提示"后写入配置文件，以后启动不再弹出。

与 ConflictDialog / PackDialog 一样基于 CTkToplevel，样式与主界面一致。
"""

import tkinter as tk

import customtkinter as ctk

from constants import UI


# ─── 提示全文（与 README「重要提示」一致，内嵌常量以便打包进 exe） ───
DISCLAIMER_TEXT = """⚠️ 使用本工具前，请务必阅读以下全部内容。

本工具完全免费！如果您是通过付费购得本工具，请及时申请退款。

本工具涉及文件复制、移动、剪切等操作，这些操作不可逆，请谨慎操作。

1. 操作不可逆：文件移动（剪切）和复制操作执行后，无法通过本工具撤销。请在操作前确认目标路径正确。

2. 做好备份：使用本工具前，请务必对重要文件进行备份。因文件丢失、损坏或误操作导致的任何损失，由用户自行承担。

3. 结果自负：本工具按「原样」提供，不对以下情况承担任何责任：
   - 文件在操作过程中丢失、损坏或被覆盖
   - 因同名文件冲突处理方式选择不当导致的数据丢失
   - 因用户误选文件或误选目标文件夹导致的后果
   - 任何直接或间接的数据损失或业务中断

4. 本工具不保证其适用性、安全性、准确性，包括但不限于：
   - 适合特定用途
   - 运行过程无错误
   - 任何功能符合用户预期

5. 因使用本工具所引发的任何直接或间接的损害，包括文件丢失、数据损坏、系统故障或其他任何形式的损失，作者概不承担任何责任。

6. 使用即表示理解并同意以上全部内容。如不同意上述条款，请勿使用本工具。

────────────────────────────
项目主页：https://github.com/moliushangxue/FileFinder
欢迎反馈问题、提交建议或贡献代码。"""


class DisclaimerDialog(ctk.CTkToplevel):
    """启动风险提示弹窗（模态，必须同意才能继续使用）

    属性:
        agreed:         用户是否点过"确定"（False 表示拒绝/关窗，调用方应退出程序）
        dont_ask_again: 用户是否勾选了"不再提示"
    """

    def __init__(self, master):
        super().__init__(master)
        self.agreed = False
        self.dont_ask_again = False

        self.title("重要提示")
        self.geometry("580x580")
        self.minsize(480, 420)
        self.configure(fg_color=UI.BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.transient(master)      # 依附于主窗口
        self.grab_set()             # 模态：主窗口不可操作

        self._build_ui()
        self.after(10, self._center_on_parent)

    # ── 界面构建 ──
    def _build_ui(self):
        # 标题行：⚠️ 重要提示
        ctk.CTkLabel(
            self, text="⚠️  重要提示", font=(UI.FONT, 16, "bold"),
            text_color=UI.DANGER,
        ).pack(anchor=tk.W, padx=16, pady=(16, 2))
        ctk.CTkLabel(
            self, text="使用本工具前，请务必阅读以下全部内容",
            font=(UI.FONT, 12), text_color=UI.TEXT_DIM,
        ).pack(anchor=tk.W, padx=16, pady=(0, 10))

        # 可滚动文本区（只读）
        self.textbox = ctk.CTkTextbox(
            self, font=(UI.FONT, 12), text_color=UI.TEXT,
            fg_color=UI.CARD, border_width=1, border_color=UI.BORDER,
            wrap="word",
        )
        self.textbox.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))
        self.textbox.insert("1.0", DISCLAIMER_TEXT)
        self.textbox.configure(state="disabled")

        # 勾选：已知晓风险（控制"确定"按钮可用性）
        self.agree_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self, text="我已知晓风险并同意上述条款",
            variable=self.agree_var, command=self._on_agree_toggled,
            font=(UI.FONT, 12, "bold"), text_color=UI.TEXT,
            fg_color=UI.ACCENT, hover_color=UI.ACCENT_HOVER,
        ).pack(anchor=tk.W, padx=16, pady=(0, 8))

        # 勾选：不再提示
        self.dont_ask_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self, text="不再提示",
            variable=self.dont_ask_var,
            font=(UI.FONT, 12), text_color=UI.TEXT_DIM,
            fg_color=UI.ACCENT, hover_color=UI.ACCENT_HOVER,
        ).pack(anchor=tk.W, padx=16, pady=(0, 12))

        # 底部按钮行
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill=tk.X, side=tk.BOTTOM, padx=16, pady=(0, 14))
        self.confirm_btn = ctk.CTkButton(
            footer, text="确 定", command=self._on_confirm,
            font=(UI.FONT, 13, "bold"), width=120, height=36,
            fg_color=UI.ACCENT, hover_color=UI.ACCENT_HOVER,
            state="disabled",                       # 必须先勾选"已知晓"才能点
        )
        self.confirm_btn.pack(side=tk.RIGHT)

    # ── 事件处理 ──
    def _on_agree_toggled(self):
        """勾选"我已知晓风险"时启用/禁用确定按钮"""
        if self.agree_var.get():
            self.confirm_btn.configure(state="normal")
        else:
            self.confirm_btn.configure(state="disabled")

    def _on_confirm(self):
        """点确定：记录勾选状态并关闭弹窗"""
        self.agreed = True
        self.dont_ask_again = self.dont_ask_var.get()
        self.destroy()

    def _on_close(self):
        """点 X 关窗 = 拒绝同意，调用方应退出程序"""
        self.agreed = False
        self.destroy()

    def _center_on_parent(self):
        """把弹窗居中显示在父窗口上方"""
        self.update_idletasks()
        try:
            parent = self.master
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            w = self.winfo_width()
            h = self.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 3          # 稍微偏上一点
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except tk.TclError:
            pass                            # 窗口尚未就绪时忽略

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FileFinder - 打包到 ZIP 对话框

把用户选择的文件/文件夹打包成一个 zip 压缩包，功能：
  - 自由添加/移除多个文件或文件夹
  - 自定义 zip 文件名（默认取第一个条目的名字，可改）
  - 选择是否在压缩包内包含顶层文件夹（默认包含，避免解压后文件散落）
  - 保存位置可手动浏览，或一键复用主界面的目标文件夹
  - 目标位置已有同名 zip 时询问（覆盖 / 重命名 / 取消）
  - 子线程打包 + 进度条，大目录不卡界面

v2.3 - 新增（风格与 v2.2 一致：浅色现代风，配色走 constants.UI）
"""

import os
import threading
import time
import tkinter as tk
import zipfile

import customtkinter as ctk
from tkinter import filedialog, messagebox

from constants import UI
from clipboard_mixin import copy_files_to_clipboard_platform


# ────────────────────────────────────────────────────────────────
#  模块级工具函数（不依赖 UI，方便单独测试）
# ────────────────────────────────────────────────────────────────

def sanitize_filename(name):
    r"""把文件名里的非法字符替换成下划线，避免生成无效路径

    Windows 文件名的非法字符：\ / : * ? " < > |
    """
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "_")
    return name.strip()


def unique_path(path):
    """生成不重复的路径：file.zip → file(1).zip → file(2).zip ..."""
    base, ext = os.path.splitext(path)
    counter = 1
    while os.path.exists(f"{base}({counter}){ext}"):
        counter += 1
    return f"{base}({counter}){ext}"


def count_files(items):
    """统计 items 里所有文件的总数（用于进度条）"""
    total = 0
    for item in items:
        if os.path.isfile(item):
            total += 1
        elif os.path.isdir(item):
            for _, _, files in os.walk(item):
                total += len(files)
    return total


def pack_to_zip(items, dest_path, include_top_folder, progress_cb=None):
    """把 items（文件/文件夹路径列表）打包到 dest_path

    参数:
        items:             要打包的路径列表（文件和文件夹可混合）
        dest_path:         生成的 zip 完整路径
        include_top_folder: True 时文件夹在压缩包内保留自己的名字作为顶层目录
        progress_cb:       进度回调 (done, total)，在打包线程中被调用

    返回:
        (文件总数, zip 路径)

    注意:
        - 自动排除输出 zip 自身：当打包内容包含保存目录（如默认打包目标文件夹
          且 zip 就放在里面）时，os.walk 会遍历到正在写入的 zip，读取自身会
          卡住并导致 zip 句柄无法释放。因此跳过与 dest_path 相同的文件。
        - 进度回调做了节流（最多约每秒 20 次），避免超大目录时 after() 回调
          风暴把主线程 UI 队列塞满。
    """
    total = count_files(items)
    done = 0
    dest_abs = os.path.abspath(dest_path)
    last_report = [0.0]          # 用列表可变对象，供嵌套函数闭包更新

    def report():
        """节流后的进度上报：完成时强制上报，其余最多每 0.05 秒一次"""
        if progress_cb:
            now = time.monotonic()
            if done >= total or now - last_report[0] >= 0.05:
                last_report[0] = now
                progress_cb(done, total)

    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for item in items:
            if os.path.isfile(item):
                if os.path.abspath(item) == dest_abs:
                    continue          # 跳过输出 zip 自身
                # 单个文件：压缩包内直接放文件名
                zf.write(item, os.path.basename(item))
                done += 1
                report()
            elif os.path.isdir(item):
                top_name = os.path.basename(item.rstrip("\\/"))
                # 顶层文件夹自身也写成目录条目，空文件夹才不会被丢掉
                if include_top_folder:
                    zf.writestr(top_name + "/", "")
                for root, _, files in os.walk(item):
                    if root != item:
                        # 子目录条目（含空文件夹）
                        rel_dir = os.path.relpath(root, item)
                        arc_dir = os.path.join(top_name, rel_dir) if include_top_folder else rel_dir
                        zf.writestr(arc_dir.replace("\\", "/") + "/", "")
                    for fname in files:
                        full = os.path.join(root, fname)
                        if os.path.abspath(full) == dest_abs:
                            continue          # 跳过输出 zip 自身
                        rel = os.path.relpath(full, item)
                        arcname = os.path.join(top_name, rel) if include_top_folder else rel
                        zf.write(full, arcname.replace("\\", "/"))
                        done += 1
                        report()
    return total, dest_path


# ────────────────────────────────────────────────────────────────
#  打包对话框
# ────────────────────────────────────────────────────────────────

class PackDialog(ctk.CTkToplevel):
    """打包到 ZIP 对话框

    参数:
        parent:        父窗口（主界面）
        initial_paths: 打开对话框时预填的路径列表（如当前源文件夹）
        target_folder: 主界面已设的目标文件夹路径（用于"一键复用"）
    """

    def __init__(self, parent, initial_paths=None, target_folder=""):
        super().__init__(parent)
        self.title("打包到 ZIP")
        self.geometry("680x600")
        self.resizable(False, False)
        self.configure(fg_color=UI.BG)
        self.transient(parent)

        self.parent = parent
        self.target_folder = target_folder
        self.items = []                    # 要打包的路径列表（去重、保序）
        self._busy = False                 # 是否正在打包（打包中禁用操作按钮）

        self.save_dir_var = tk.StringVar()
        self.zip_name_var = tk.StringVar()
        self.include_top_var = tk.BooleanVar(value=True)

        self._init_paths(initial_paths)
        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self.destroy)

        # 居中显示在父窗口中央（与 ConflictDialog 一致）
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        self.grab_set()

    # ── 初始化 ──

    def _init_paths(self, initial_paths):
        """把预填路径加进去，并据此给 zip 文件名和保存位置一个默认值"""
        if initial_paths:
            for p in initial_paths:
                if p and os.path.exists(p) and p not in self.items:
                    self.items.append(p)
        # 保存位置默认 = 主界面的目标文件夹（与打包内容一致，打开即可直接打包）
        if self.target_folder and os.path.isdir(self.target_folder):
            self.save_dir_var.set(self.target_folder)
        self.zip_name_var.set(self._default_zip_name())

    def _default_zip_name(self):
        """默认 zip 名：第一个条目是文件夹用文件夹名，是文件用文件名（去扩展名）"""
        if not self.items:
            return "archive"
        first = self.items[0]
        base = os.path.basename(first.rstrip("\\/"))
        if os.path.isdir(first):
            return base
        return os.path.splitext(base)[0]

    # ── 界面搭建 ──

    def _build_ui(self):
        # 顶部说明
        ctk.CTkLabel(
            self, text="把选中的文件/文件夹打包成一个 zip 压缩包",
            font=(UI.FONT, 13, "bold"), text_color=UI.TEXT,
        ).pack(anchor=tk.W, padx=14, pady=(14, 8))

        # ── 底部固定区：按钮行、进度条、状态 ──
        # 用 side=BOTTOM 最先 pack，钉在窗口底部，窗口再小也不会被上面的内容挤出
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill=tk.X, side=tk.BOTTOM, padx=14, pady=(0, 14))
        ctk.CTkButton(
            footer, text="取消", command=self.destroy,
            font=(UI.FONT, 12), width=90, height=34,
            fg_color="transparent", hover_color=UI.BORDER, text_color=UI.TEXT_DIM,
        ).pack(side=tk.RIGHT)
        self.pack_copy_btn = ctk.CTkButton(
            footer, text="打包并复制到剪贴板",
            command=lambda: self._start_pack(copy_to_clipboard=True),
            font=(UI.FONT, 12), width=150, height=34,
            fg_color=UI.CARD, hover_color=UI.ACCENT_LIGHT,
            border_width=1, border_color=UI.ACCENT, text_color=UI.ACCENT,
        )
        self.pack_copy_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self.pack_btn = ctk.CTkButton(
            footer, text="开始打包",
            command=lambda: self._start_pack(copy_to_clipboard=False),
            font=(UI.FONT, 12, "bold"), width=110, height=34,
            fg_color=UI.ACCENT, hover_color=UI.ACCENT_HOVER,
        )
        self.pack_btn.pack(side=tk.RIGHT)

        self.progress_bar = ctk.CTkProgressBar(self, height=8, fg_color=UI.BORDER,
                                               progress_color=UI.ACCENT)
        self.progress_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=14, pady=(0, 10))
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(
            self, text="", font=(UI.FONT, 12), text_color=UI.TEXT_DIM,
        )
        self.status_label.pack(anchor=tk.W, side=tk.BOTTOM, padx=14, pady=(0, 2))

        # ── 区域 1：打包内容 ──
        self._section_title("要打包的内容")
        list_card = ctk.CTkFrame(
            self, fg_color=UI.CARD, corner_radius=8,
            border_width=1, border_color=UI.BORDER,
        )
        list_card.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 6))

        scrollbar = ctk.CTkScrollbar(list_card)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=4)

        self.listbox = tk.Listbox(
            list_card, height=8,
            selectmode=tk.EXTENDED, yscrollcommand=scrollbar.set,
            font=(UI.FONT, 11),
            bg=UI.CARD, fg=UI.TEXT,
            selectbackground=UI.ACCENT_LIGHT, selectforeground=UI.TEXT,
            activestyle="none", relief=tk.FLAT, highlightthickness=0,
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=4)
        scrollbar.configure(command=self.listbox.yview)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill=tk.X, padx=14, pady=(0, 10))
        self.add_file_btn = self._small_button(btn_row, "添加文件...", self._add_files)
        self.add_file_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.add_dir_btn = self._small_button(btn_row, "添加文件夹...", self._add_folder)
        self.add_dir_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.remove_btn = self._small_button(btn_row, "移除选中", self._remove_selected)
        self.remove_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.clear_btn = self._small_button(btn_row, "清空", self._clear_all)
        self.clear_btn.pack(side=tk.LEFT)

        # ── 区域 2：保存位置 ──
        self._section_title("保存位置")
        save_card = ctk.CTkFrame(self, fg_color="transparent")
        save_card.pack(fill=tk.X, padx=14, pady=(0, 10))
        ctk.CTkEntry(
            save_card, textvariable=self.save_dir_var,
            placeholder_text="选择保存 zip 的文件夹...",
            font=(UI.FONT, 12), height=34,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.browse_dir_btn = self._small_button(save_card, "浏览...", self._browse_save_dir)
        self.browse_dir_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.use_target_btn = self._small_button(save_card, "使用目标文件夹", self._use_target_folder)
        self.use_target_btn.pack(side=tk.LEFT)

        # ── 区域 3：命名 ──
        self._section_title("命名")
        name_card = ctk.CTkFrame(self, fg_color="transparent")
        name_card.pack(fill=tk.X, padx=14, pady=(0, 6))
        ctk.CTkLabel(name_card, text="zip 文件名：", font=(UI.FONT, 12), text_color=UI.TEXT,
                     ).pack(side=tk.LEFT, padx=(0, 6))
        ctk.CTkEntry(
            name_card, textvariable=self.zip_name_var,
            font=(UI.FONT, 12), height=34, width=280,
        ).pack(side=tk.LEFT)
        ctk.CTkLabel(name_card, text="（自动补全 .zip）", font=(UI.FONT, 11), text_color=UI.TEXT_DIM,
                     ).pack(side=tk.LEFT, padx=(8, 0))

        ctk.CTkCheckBox(
            self, text="压缩包内包含顶层文件夹（解压后文件不散落）",
            variable=self.include_top_var, font=(UI.FONT, 12), text_color=UI.TEXT,
            fg_color=UI.ACCENT, hover_color=UI.ACCENT_HOVER,
        ).pack(anchor=tk.W, padx=14, pady=(0, 10))

        # 状态/进度/按钮行已在 _build_ui 开头用 side=BOTTOM 钉在底部

        self._refresh_list()

    def _section_title(self, text):
        """小节标题：浅蓝底 + 深色文字，与主界面卡片标题风格一致"""
        bar = ctk.CTkFrame(self, fg_color=UI.ACCENT_LIGHT, corner_radius=6, height=30)
        bar.pack(fill=tk.X, padx=14, pady=(0, 6))
        ctk.CTkLabel(
            bar, text=text, font=(UI.FONT, 12, "bold"), text_color=UI.ACCENT,
        ).pack(side=tk.LEFT, padx=10, pady=4)

    def _small_button(self, parent, text, command):
        """小号辅助按钮：outline 风格，视觉上比主按钮轻"""
        return ctk.CTkButton(
            parent, text=text, command=command,
            font=(UI.FONT, 11), height=30,
            fg_color=UI.CARD, hover_color=UI.ACCENT_LIGHT,
            border_width=1, border_color=UI.ACCENT, text_color=UI.ACCENT,
        )

    # ── 列表管理 ──

    def _refresh_list(self):
        """重绘打包内容列表"""
        self.listbox.delete(0, tk.END)
        for path in self.items:
            kind = "文件夹" if os.path.isdir(path) else "文件"
            self.listbox.insert(tk.END, f"[{kind}]  {path}")
        self._update_zip_name_hint()

    def _update_zip_name_hint(self):
        """列表变化后若用户还没改过 zip 名，同步默认名"""
        current = self.zip_name_var.get()
        if current in ("", "archive") or current == self._default_zip_name():
            self.zip_name_var.set(self._default_zip_name())

    def _add_files(self):
        paths = filedialog.askopenfilenames(title="选择要打包的文件")
        for p in paths:
            if p not in self.items:
                self.items.append(p)
        self._refresh_list()

    def _add_folder(self):
        path = filedialog.askdirectory(title="选择要打包的文件夹")
        if path and path not in self.items:
            self.items.append(path)
        self._refresh_list()

    def _remove_selected(self):
        for idx in reversed(self.listbox.curselection()):
            del self.items[idx]
        self._refresh_list()

    def _clear_all(self):
        self.items.clear()
        self._refresh_list()

    # ── 保存位置 ──

    def _browse_save_dir(self):
        path = filedialog.askdirectory(title="选择 zip 保存位置")
        if path:
            self.save_dir_var.set(path)

    def _use_target_folder(self):
        if not self.target_folder:
            messagebox.showinfo("提示", "主界面尚未设置目标文件夹。", parent=self)
            return
        if not os.path.isdir(self.target_folder):
            messagebox.showerror("错误", "目标文件夹不存在！", parent=self)
            return
        self.save_dir_var.set(self.target_folder)

    # ── 打包执行 ──

    def _start_pack(self, copy_to_clipboard=False):
        """点击"开始打包"（或"打包并复制到剪贴板"）：校验 → 处理同名 → 子线程打包

        参数:
            copy_to_clipboard: True 时打包完成后把 zip 复制到系统剪贴板
        """
        if self._busy:
            return

        # 校验输入
        if not self.items:
            messagebox.showwarning("警告", "请先添加要打包的文件或文件夹！", parent=self)
            return
        save_dir = self.save_dir_var.get().strip()
        if not save_dir:
            messagebox.showwarning("警告", "请选择保存位置！", parent=self)
            return
        if not os.path.isdir(save_dir):
            messagebox.showerror("错误", "保存位置不是有效的文件夹！", parent=self)
            return
        zip_name = sanitize_filename(self.zip_name_var.get().strip())
        if not zip_name:
            messagebox.showwarning("警告", "zip 文件名不能为空！", parent=self)
            return
        if not zip_name.lower().endswith(".zip"):
            zip_name += ".zip"

        dest_path = os.path.join(save_dir, zip_name)

        # 目标位置已有同名 zip → 询问（覆盖 / 重命名 / 取消）
        if os.path.exists(dest_path):
            choice = messagebox.askyesnocancel(
                "文件已存在",
                f"「{zip_name}」已存在。\n\n"
                "选择「是」：直接覆盖旧文件\n"
                "选择「否」：自动重命名为新名字\n"
                "选择「取消」：中止打包",
                parent=self,
            )
            if choice is None:          # 取消
                return
            if choice is False:         # 重命名
                dest_path = unique_path(dest_path)

        # 锁定界面，进入打包状态
        self._busy = True
        self._set_controls_enabled(False)
        self.status_label.configure(text="正在打包… 0/0", text_color=UI.TEXT)
        self.progress_bar.set(0)

        items = list(self.items)
        include_top = self.include_top_var.get()
        threading.Thread(
            target=self._pack_worker,
            args=(items, dest_path, include_top, copy_to_clipboard),
            daemon=True,
        ).start()

    def _set_controls_enabled(self, enabled):
        """打包期间禁用/恢复所有操作按钮，防止重复操作"""
        state = "normal" if enabled else "disabled"
        for btn in (self.add_file_btn, self.add_dir_btn, self.remove_btn,
                    self.clear_btn, self.browse_dir_btn, self.use_target_btn):
            btn.configure(state=state)

    def _pack_worker(self, items, dest_path, include_top, copy_to_clipboard=False):
        """打包线程：真正执行压缩，完成后回到主线程更新界面"""
        try:
            total, zip_path = pack_to_zip(items, dest_path, include_top, self._on_progress)
            self.after(0, lambda: self._on_pack_done(total, zip_path, copy_to_clipboard))
        except Exception as e:
            # 打包失败：删掉可能残留的半成品 zip
            try:
                if os.path.exists(dest_path):
                    os.remove(dest_path)
            except OSError:
                pass
            self.after(0, lambda: self._on_pack_error(str(e)))

    def _on_progress(self, done, total):
        """打包线程里的进度回调 → 转发到主线程刷新 UI"""
        self.after(0, lambda: self._update_progress(done, total))

    def _update_progress(self, done, total):
        self.progress_bar.set(done / total if total else 0)
        self.status_label.configure(text=f"正在打包… {done}/{total}", text_color=UI.TEXT)

    def _on_pack_done(self, total, zip_path, copy_to_clipboard=False):
        self._busy = False
        self.progress_bar.set(1)
        self._set_controls_enabled(True)
        self.pack_btn.configure(text="完成", command=self.destroy)
        self.pack_copy_btn.configure(text="完成", command=self.destroy)

        if copy_to_clipboard:
            try:
                copy_files_to_clipboard_platform([zip_path])
                self.status_label.configure(
                    text=f"打包完成，zip 已复制到剪贴板：{os.path.basename(zip_path)}（{total} 个文件）",
                    text_color=UI.ACCENT,
                )
                messagebox.showinfo(
                    "成功",
                    "打包完成，zip 已复制到剪贴板！\n\n"
                    "现在可以在其他文件夹中按 Ctrl+V 粘贴文件。",
                    parent=self,
                )
            except Exception as e:
                self.status_label.configure(
                    text=f"打包完成，但复制到剪贴板失败：{os.path.basename(zip_path)}",
                    text_color=UI.DANGER,
                )
                messagebox.showerror(
                    "复制失败",
                    f"打包完成，但复制到剪贴板失败：\n{e}",
                    parent=self,
                )
        else:
            self.status_label.configure(
                text=f"打包完成：{os.path.basename(zip_path)}（{total} 个文件）",
                text_color=UI.ACCENT,
            )

    def _on_pack_error(self, error):
        self._busy = False
        self.progress_bar.set(0)
        self.status_label.configure(text="打包失败", text_color=UI.DANGER)
        self._set_controls_enabled(True)
        self.pack_btn.configure(text="开始打包")
        self.pack_copy_btn.configure(text="打包并复制到剪贴板")
        messagebox.showerror("打包失败", f"打包过程中出现错误：\n{error}", parent=self)

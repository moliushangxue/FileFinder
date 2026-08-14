#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FileFinder - 剪贴板操作 Mixin（混入类）

Mixin 模式：把"剪贴板相关功能"从主类里拆出来，单独放一个文件。
主类通过多继承混入这个类后，就自动拥有这些方法，主类不会太臃肿。

这个文件负责：把选中的文件（或文件路径文字）复制到系统剪贴板，
这样用户就可以在资源管理器里直接 Ctrl+V 粘贴文件了。

支持三个平台：
  - Windows：用 .NET 的 System.Windows.Forms.Clipboard.SetFileDropList
  - macOS：用 AppleScript 告诉 Finder 把文件放入剪贴板
  - Linux：用 xclip 工具，往 clipboard 写入 file:// 格式的 URI
"""

import platform
import subprocess
import urllib.parse

from tkinter import messagebox


class ClipboardMixin:
    """剪贴板操作混入类

    需要宿主类（主类）提供以下属性才能正常工作：
        self.root              — tkinter.Tk 根窗口（用于操作剪贴板）
        self.file_listbox      — tkinter.Listbox，显示文件列表的控件
        self.found_files       — list[str]，扫描到的完整文件路径列表
        self.status_var        — tkinter.StringVar，底部状态栏的文字变量
    """

    # ════════════════════════════════════════════════════════════
    #  功能一：复制文件路径（文字）到剪贴板
    # ════════════════════════════════════════════════════════════

    def copy_paths_to_clipboard(self):
        """把选中文件的"路径文字"复制到剪贴板

        注意：这里复制的是"文字"（比如 D:/xxx/a.txt），
        而不是文件本身。粘贴时会得到一段文字，不是文件。
        """
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要复制路径的文件！")
            return

        # 根据列表里的选中索引，找到对应的完整文件路径
        selected_files = [self.found_files[i] for i in selected_indices]
        # 用换行符把多个路径拼接成一个多行文本
        paths_text = '\n'.join(selected_files)

        # tkinter 自带的剪贴板操作（纯文字）
        self.root.clipboard_clear()           # 先清空剪贴板
        self.root.clipboard_append(paths_text) # 写入文字
        self.root.update()                    # 立即刷新（确保写入生效）

        self.status_var.set(f"已复制 {len(selected_files)} 个文件路径到剪贴板")
        messagebox.showinfo("成功", f"已复制 {len(selected_files)} 个文件路径到剪贴板！\n\n可以直接在其他地方粘贴使用。")

    # ════════════════════════════════════════════════════════════
    #  功能二：复制文件本身到剪贴板（可 Ctrl+V 粘贴文件）
    # ════════════════════════════════════════════════════════════

    def copy_files_to_clipboard(self):
        """把选中的"文件本身"复制到系统剪贴板

        这个和上面的区别是：
          上面 → 复制"文字"（路径），粘贴得到文字
          这个 → 复制"文件对象"，粘贴得到文件（出现在目标文件夹里）

        不同平台实现方式完全不同，所以分三个静态方法处理。
        """
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要复制的文件！")
            return

        selected_files = [self.found_files[i] for i in selected_indices]

        try:
            system = platform.system()    # 获取操作系统名称
            if system == "Windows":
                self._copy_files_windows(selected_files)
            elif system == "Darwin":       # macOS 的内核名是 Darwin
                self._copy_files_macos(selected_files)
            else:                          # Linux 等其他系统
                self._copy_files_linux(selected_files)

            self.status_var.set(f"已复制 {len(selected_files)} 个文件到剪贴板")
            messagebox.showinfo(
                "成功",
                f"已复制 {len(selected_files)} 个文件到剪贴板！\n\n"
                f"现在可以在其他文件夹中按 Ctrl+V (Mac: Cmd+V) 粘贴文件。"
            )
        except Exception as e:
            messagebox.showerror("错误", f"复制文件到剪贴板失败：{str(e)}")

    # ════════════════════════════════════════════════════════════
    #  平台实现：Windows
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _copy_files_windows(files):
        """Windows 平台：使用 .NET 的 FileDrop 格式复制文件到剪贴板

        PowerShell 的 Set-Clipboard -Path 不能复制文件对象，
        所以这里使用 .NET 的 System.Windows.Forms 来创建 FileDrop 格式的剪贴板数据。

        注意：必须使用 -STA 参数启动 PowerShell，因为 System.Windows.Forms.Clipboard
        是 Windows Forms API，必须在单线程公寓（STA）模式下运行。

        安全说明：通过 stdin 传递文件列表（每行一个路径），避免字符串拼接，
        彻底消除命令注入风险。
        """
        if not files:
            return

        # PowerShell 脚本：从 stdin 读取文件路径列表
        # 使用 [Console]::In.ReadLine() 逐行读取，避免字符串拼接
        # 显式设置输入编码为 UTF-8，防止中文路径在非 UTF-8 系统（如中文 Windows GBK）上乱码
        script = """
        [Console]::InputEncoding = [System.Text.Encoding]::UTF8
        Add-Type -AssemblyName System.Windows.Forms
        $fdo = New-Object System.Collections.Specialized.StringCollection
        while (-not [Console]::In.EndOfStream) {
            $line = [Console]::In.ReadLine()
            if ($line) {
                $fdo.Add($line)
            }
        }
        if ($fdo.Count -gt 0) {
            [System.Windows.Forms.Clipboard]::SetFileDropList($fdo)
        }
        """
        
        # 通过 stdin 传递文件路径，每行一个
        file_list = "\n".join(files)
        try:
            result = subprocess.run(
                ["powershell", "-STA", "-NoProfile", "-Command", script],
                input=file_list.encode("utf-8"),
                capture_output=True,
                timeout=30,                     # 和 macOS/Linux 一样加超时，防止卡死
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("PowerShell 执行超时（30秒）")
        if result.returncode != 0:
            raise RuntimeError(f"PowerShell执行失败: {result.stderr}")

    # ════════════════════════════════════════════════════════════
    #  平台实现：macOS
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _copy_files_macos(files):
        """macOS 平台：用 AppleScript 告诉 Finder 把文件放入剪贴板

        macOS 的剪贴板操作需要通过 Finder 来完成，
        AppleScript 是 macOS 自带的脚本语言，可以控制 Finder。
        """
        if not files:
            return

        # 构造 AppleScript 需要的文件列表字符串
        # 每个文件路径写成 POSIX file "/path/to/file" 的格式，多个用逗号分隔
        # 注意：需要转义路径中的特殊字符，避免破坏 AppleScript 语法
        # 转义顺序很重要：先转义反斜杠，再转义其他字符
        def escape_applescript(s):
            return (s.replace(chr(92), chr(92)+chr(92))   # \ → \\
                     .replace(chr(34), chr(92)+chr(34))   # " → \"
                     .replace(chr(10), chr(92)+chr(110))  # 换行 → \n
                     .replace(chr(13), chr(92)+chr(114))  # 回车 → \r
                     .replace(chr(9), chr(92)+chr(116)))  # 制表 → \t
        
        posix_files = ", ".join([f'POSIX file "{escape_applescript(f)}"' for f in files])
        # AppleScript 脚本正文
        script = f'''
        tell application "Finder"
            set theFiles to {{{posix_files}}}
            set the clipboard to theFiles
        end tell
        '''
        # 用 osascript 命令执行 AppleScript，加超时防止卡死
        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr)
        except subprocess.TimeoutExpired:
            raise RuntimeError("AppleScript 执行超时（30秒）")

    # ════════════════════════════════════════════════════════════
    #  平台实现：Linux
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _copy_files_linux(files):
        """Linux 平台：用 xclip 工具把文件 URI 写入剪贴板

        Linux 的剪贴板协议规定：要粘贴文件，需要写入 file:///path/to/file 格式的 URI，
        内容类型为 text/uri-list。
        xclip 是一个命令行工具，可以往 X11 剪贴板里写内容。
        """
        if not files:
            return

        try:
            # 构造 file:// URI 列表（每行一个）
            # 使用 urllib.parse.quote 对路径进行百分号编码，处理空格、中文、#、? 等特殊字符
            file_uris = "\n".join([f"file://{urllib.parse.quote(f, safe='/')}" for f in files])
            # 启动 xclip，往 clipboard 写入 text/uri-list 类型的内容
            proc = subprocess.Popen(
                ['xclip', '-selection', 'clipboard', '-t', 'text/uri-list'],
                stdin=subprocess.PIPE       # 通过标准输入传内容
            )
            # 把 URI 列表写入 stdin，等待完成，加超时防止卡死
            try:
                proc.communicate(input=file_uris.encode(), timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()  # 等待进程真正结束，避免僵尸进程
                raise RuntimeError("xclip 执行超时（30秒）")
            if proc.returncode != 0:
                raise RuntimeError("xclip执行失败")
        except FileNotFoundError:
            # xclip 没装
            raise RuntimeError("需要安装xclip工具（sudo apt-get install xclip）")

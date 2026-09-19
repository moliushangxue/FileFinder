#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FileFinder - 剪贴板操作 Mixin（混入类）

Mixin 模式：把"剪贴板相关功能"从主类里拆出来，单独放一个文件。
主类通过多继承混入这个类后，就自动拥有这些方法，主类不会太臃肿。

这个文件负责：把选中的文件（或文件路径文字）复制到系统剪贴板，
这样用户就可以在资源管理器里直接 Ctrl+V 粘贴文件了。

支持三个平台：
  - Windows：用 pywin32 的 win32clipboard 直接写入 CF_HDROP 剪贴板数据
  - macOS：用 AppleScript 告诉 Finder 把文件放入剪贴板
  - Linux：用 xclip 工具，往 clipboard 写入 file:// 格式的 URI
"""

import base64
import os
import platform
import struct
import subprocess
import time
import urllib.parse

from tkinter import messagebox


def copy_files_to_clipboard_platform(files):
    """把文件列表复制到系统剪贴板（跨平台分发，供 Mixin 与打包对话框共用）

    参数:
        files: 要复制的文件路径列表
    异常:
        平台复制失败时抛出 RuntimeError
    """
    system = platform.system()          # 获取操作系统名称
    if system == "Windows":
        ClipboardMixin._copy_files_windows(files)
    elif system == "Darwin":            # macOS 的内核名是 Darwin
        ClipboardMixin._copy_files_macos(files)
    else:                               # Linux 等其他系统
        ClipboardMixin._copy_files_linux(files)


def _copy_files_windows_native(files):
    """原生 Windows API 方案（需要 pywin32）：构造 CF_HDROP 格式数据写入剪贴板

    Windows 复制文件到剪贴板的本质是：写入 CF_HDROP 格式的剪贴板数据。
    CF_HDROP 的数据布局 = DROPFILES 结构体 + UTF-16LE 编码的路径列表（\0 分隔，末尾双 \0）。
    粘贴时由系统负责实际的文件拷贝，和资源管理器里 Ctrl+C 的行为完全一致。
    """
    import win32clipboard

    # 1. 路径规范化：转为绝对路径、统一反斜杠
    abs_paths = []
    for p in files:
        p = os.path.abspath(p)
        abs_paths.append(p.replace('/', '\\'))

    # 2. 拼接路径字符串
    #    CF_HDROP 规定列表必须以「两个」宽 NUL 结尾：一个结束最后一条路径，
    #    一个结束整个列表。若只补一个 NUL，系统会越界继续解析缓冲区外的堆内存，
    #    粘贴时可能冒出不存在的“垃圾文件”。
    paths_joined = '\0'.join(abs_paths) + '\0\0'
    paths_bytes = paths_joined.encode('utf-16-le')  # Windows 原生 UTF-16

    # 3. 构造 DROPFILES 结构体（20 字节）
    #    - pFiles: 从结构体起始到路径数据起始的偏移量 = sizeof(DROPFILES) = 20
    #    - x, y: 拖放坐标（非拖放场景设为 0）
    #    - fNC: 非客户区标志（设为 0）
    #    - fWide: 非零 = 使用 Unicode（UTF-16），这是必须的，否则中文路径会乱码
    dropfiles = struct.pack('<IiiII', 20, 0, 0, 0, 1)
    data = dropfiles + paths_bytes

    # 4. 写入剪贴板
    #    剪贴板可能被其他程序短暂占用（如复制大文件、安全软件挂钩），
    #    OpenClipboard 失败时重试 10 次（每次间隔 200ms）。
    #    同时设置 "Preferred DropEffect" 格式 = 复制（1）。
    #    没有这个附加格式时，部分程序粘贴时会使用默认行为（可能是剪切）。
    last_error = None
    for _ in range(10):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_HDROP, data)
                # RegisterClipboardFormat 返回自定义格式的 ID
                cf_drop_effect = win32clipboard.RegisterClipboardFormat('Preferred DropEffect')
                win32clipboard.SetClipboardData(cf_drop_effect, struct.pack('<I', 1))
            finally:
                win32clipboard.CloseClipboard()
            return  # 写入成功
        except Exception as e:
            last_error = e
            time.sleep(0.2)
    raise RuntimeError(f'剪贴板被占用，写入失败（已重试 10 次）：{last_error}') from last_error


def _copy_files_windows_powershell(files):
    """PowerShell 回退方案：使用 .NET 的 FileDrop 格式复制文件到剪贴板

    仅在 pywin32 未安装时使用。部分安全软件可能拦截 PowerShell 启动。
    """
    items = ", ".join("'" + p.replace("'", "''") + "'" for p in files)
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$fdo = New-Object System.Collections.Specialized.StringCollection;"
        f"$paths = @({items});"
        "foreach ($p in $paths) { if ($p) { [void]$fdo.Add($p) } };"
        "if ($fdo.Count -gt 0) {"
        "  $ok = $false;"
        "  for ($i = 0; $i -lt 10 -and -not $ok; $i++) {"
        "    try { [System.Windows.Forms.Clipboard]::SetFileDropList($fdo); $ok = $true }"
        "    catch { Start-Sleep -Milliseconds 200 }"
        "  }"
        "  if (-not $ok) { throw '剪贴板被占用，操作失败' }"
        "}"
    )
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    try:
        result = subprocess.run(
            ['powershell', '-STA', '-NoProfile', '-EncodedCommand', encoded],
            capture_output=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError('PowerShell 执行超时（30秒）')
    if result.returncode != 0:
        raise RuntimeError(
            'PowerShell执行失败: ' + result.stderr.decode('utf-8', 'replace')
        )


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
        """把选中文件的“路径文字”复制到剪贴板

        注意：这里复制的是“文字”（比如 D:/xxx/a.txt），
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
        """把选中的“文件本身”复制到系统剪贴板

        这个和上面的区别是：
          上面 → 复制“文字”（路径），粘贴得到文字
          这个 → 复制“文件对象”，粘贴得到文件（出现在目标文件夹里）

        不同平台实现方式完全不同，所以分三个静态方法处理。
        """
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要复制的文件！")
            return

        selected_files = [self.found_files[i] for i in selected_indices]

        try:
            copy_files_to_clipboard_platform(selected_files)
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
        """Windows 平台：用 pywin32 的 win32clipboard 直接写入 CF_HDROP 剪贴板数据

        原方案通过 PowerShell 调用 .NET 的 System.Windows.Forms.Clipboard.SetFileDropList，
        但部分安全软件（如 360）会将 PowerShell 进程启动拦截并报“线程注入”。

        新方案直接在进程内构造 CF_HDROP 数据写入剪贴板，
        不再依赖外部 PowerShell 进程，从根本上消除安全软件的误报问题。

        如果 pywin32 未安装，自动回退到 PowerShell 方案（保持兼容）。
        """
        if not files:
            return

        # 只在导入处捕获 ImportError（pywin32 不可用）：
        # 原生写入本身的异常绝不能吞掉并静默降级到可能被安全软件拦截的方案
        try:
            import win32clipboard  # noqa: F401  仅探测 pywin32 是否可用
        except ImportError:
            # ── 回退方案：PowerShell（保留兼容性） ──
            _copy_files_windows_powershell(files)
            return

        # ── 优先方案：pywin32 原生 API ──
        _copy_files_windows_native(files)

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

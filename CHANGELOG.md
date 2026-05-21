# 更新日志

所有对 FileFinder 的重要更改都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 计划添加
- 添加撤销功能

## [2.1.0] - 2026-05-22

### ✨ 新功能
- **正则表达式搜索**：在"源文件夹"区域新增"正则表达式"复选框，勾选后关键词将作为正则表达式进行匹配
  - 在 `constants.py` 中新增 `compile_regex_patterns()` 函数，用于编译正则表达式
  - 在 `constants.py` 中新增 `match_file()` 函数，支持普通关键词和正则表达式两种匹配模式
  - 支持多个正则表达式（每行一个），匹配任一即命中
  - 正则表达式验证：扫描前自动验证关键词是否为有效的正则表达式，无效时弹出错误提示
  - 鼠标悬浮提示：将鼠标放在"正则表达式"复选框上，会弹出通俗易懂的功能解释，不了解正则的用户也能看懂

### 🔒 安全修复
- **🔴 修复 Windows 剪贴板命令注入漏洞**：`_copy_files_windows` 原先使用 f-string 拼接文件名到 PowerShell 命令，文件名含特殊字符（如 `'`、`$()`、`` ` ``）可被注入执行任意命令。现改用临时文件中转 + `Get-Content -LiteralPath` 安全读取，彻底消除注入风险
- **macOS AppleScript 注入**：对文件路径中的双引号进行转义（`"` → `\"`），防止破坏 AppleScript 语法
- **Linux URI 特殊字符**：使用 `urllib.parse.quote` 对文件路径进行百分号编码，正确处理空格、中文、`#`、`?` 等特殊字符

### 🏗️ 架构重构
- **🟡 单文件拆分为多模块架构**：原 `file_manager.py`（917行）拆分为 5 个模块：
  - `constants.py` — 常量、`_fmt_size()` 公共工具函数、`COMMON_TYPES`、`compile_regex_patterns()`、`match_file()`
  - `conflict_dialog.py` — `ConflictDialog` 冲突处理对话框
  - `preview_mixin.py` — `PreviewMixin` 文件预览功能（文本/Office/媒体）
  - `clipboard_mixin.py` — `ClipboardMixin` 跨平台剪贴板操作
  - `file_manager.py` — `FileManagerApp` 主类（UI + 扫描 + 文件操作）
- 使用 Mixin 模式保持原有方法调用方式不变
- 将 `_match_file()` 方法从 `file_manager.py` 迁移到 `constants.py`，重命名为 `match_file()`
- 将正则表达式编译逻辑提取为独立函数 `compile_regex_patterns()`

### ⚡ 改进
- **🟡 文件扫描改为子线程执行**：`scan_files` 中的 `os.walk` 现在在 daemon 线程中运行，扫描完成后通过 `root.after(0, ...)` 回到主线程更新 UI，大目录扫描不再卡死界面
- **🟡 换源文件夹后扩展名列表自动刷新**：移除 `if not self.all_extensions` 守卫，`collect_extensions` 每次扫描都调用，切换源文件夹后扩展名复选框正确更新
- **超时保护**：
  - macOS 的 `osascript` 命令添加 30 秒超时
  - Linux 的 `xclip` 命令添加 30 秒超时
  - 超时后调用 `proc.wait()` 等待进程真正结束，避免僵尸进程
- **错误处理增强**：
  - 文件操作失败时记录失败文件名和原因到 `failed_files` 列表
  - 结果对话框中显示失败详情（最多显示5个失败文件）
  - 使用 `traceback.format_exc()` 记录完整的错误堆栈信息，方便调试
- **🟢 统一 `_fmt_size` 函数**：原在 `ConflictDialog` 和 `FileManagerApp` 各写一遍，现提取到 `constants.py` 作为模块级函数，两处共用
- **🟢 补充 TEXT_PREVIEW_EXTS**：添加更多常见文本格式（`.vue`, `.svelte`, `.ini`, `.conf`, `.env`, `.dockerfile`, `.editorconfig`, `.gradle` 等）
- **🟢 顶层导入 zipfile / xml.etree.ElementTree**：原在函数内部导入，现移至文件顶部（`preview_mixin.py`）
- **🟢 修复 TEXT_PREVIEW_EXTS 语法错误**：集合定义行首多余冒号已移除
- **🟢 移除冗余的"直接移动"按钮**：与"剪切到目标文件夹"功能完全重复，已移除

## [2.0.0] - 2026-05-03

### 新增
- **递归搜索子文件夹**：勾选"递归搜索子文件夹"复选框即可遍历所有子目录
  - 文件列表中显示相对路径，方便定位文件来源
  - 扩展名收集也支持递归模式
- **文件预览面板**：选中文件后右侧面板实时预览
  - 纯文本文件（59 种扩展名）直接显示内容，大文件自动截断至 100KB
  - Office 文档解析预览：
    - `.docx` 按段落结构提取纯文本
    - `.xlsx` / `.xlsm` 提取所有 sheet 文本内容
    - `.pptx` 提取幻灯片文本内容
  - 旧版 Office（`.doc` / `.xls` / `.ppt`）提示转换格式后预览
  - 图片/音视频/压缩包/PDF 显示文件类型和大小信息
  - 显示文件大小、修改时间、完整路径
- **文件冲突处理**：复制/移动时检测目标文件夹中的同名文件及源文件之间的同名冲突
  - 弹出冲突对话框，标注冲突类型（目标已有同名 / 源文件之间同名）
  - 支持三种处理方式：覆盖 / 重命名 / 跳过
  - 支持"全部覆盖"、"全部重命名"、"全部跳过"批量操作
  - 重命名自动生成 `file(1).txt`, `file(2).txt` 格式，跟踪已占用路径防止互相覆盖
- **清空关键词按钮**：一键清空搜索关键词输入框

### 改进
- 文件类型筛选改为横向滚动单行布局，节省垂直空间
- 窗口尺寸从 900x700 调整为 1100x750 以容纳预览面板
- 文件列表与预览面板使用 PanedWindow，可拖拽调整比例
- 版本号更新为 v2.0

### 修复
- 修复冲突对话框中"全部覆盖/重命名/跳过"按钮点击无效的问题（元组解包错误）
- 修复 `.docx` 等 Office 文件预览显示乱码的问题（改为 ZIP+XML 解析）

## [1.0.0] - 2026-05-02

### 新增
- 初始版本发布
- 多关键词批量搜索功能
- 文件类型自动检测和筛选
- 文件选择功能（全选/全不选/反选）
- 文件操作：复制、剪切、移动到目标文件夹
- 剪贴板功能：
  - 复制文件路径到剪贴板
  - 复制文件本体到剪贴板
- 跨平台支持（Windows/macOS/Linux）
- 图形用户界面（基于 tkinter）
- Windows 批处理启动脚本

### 技术特点
- 纯 Python 实现，无需额外依赖
- 使用标准库（tkinter, shutil, os）
- 轻量级应用，启动快速

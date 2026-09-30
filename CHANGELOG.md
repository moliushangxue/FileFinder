# 更新日志

所有对 FileFinder 的重要更改都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 计划添加
- 添加撤销功能

## [3.0.0] - 2026-09-30

主版本号从 2.x 提升到 3.0：FileFinder 从一个 Windows 工具，变为**源码可在 Windows / macOS / Linux 三个平台运行**的跨平台项目。

### ✨ 新功能

- **新增 macOS 平台支持：源码可直接在 macOS 上运行**
  - **字体按平台选择**：原 `UI.FONT` 固定为 `Microsoft YaHei UI` / `Consolas`，在 macOS 上这两个字体族不存在，tkinter 会静默回退到默认字体——程序能开，但界面观感整体跑偏且难以排查。现按平台分支：Windows 用微软雅黑 / Consolas，macOS 用苹方（PingFang SC）/ Menlo，Linux 用 DejaVu Sans / DejaVu Sans Mono
  - **打包配置 `FileFinder.spec` 按平台选择资源**：图标在 Windows 用 `.ico`、macOS 用 `.icns`；`version_info.txt`（Windows PE 版本资源）在 macOS 上不再传入；对应文件不存在时传 `None` 跳过而非中断打包。新增 macOS 专属 `BUNDLE` 段以产出 `.app`（该段在 Windows 上不执行，不影响现有打包流程）
  - **新增 macOS 启动脚本 `启动FileFinder.command`**：双击即可运行——自动探测「带 tkinter 的解释器」（不同来源的 python3 是否带 Tk 并不一致，不能假设）、在项目目录里建好独立的虚拟环境、装好依赖后启动；异常退出时保留窗口以便查看报错
  - **新增 `.gitattributes`**：强制 `*.command` / `*.sh` 使用 LF 行尾，避免 CRLF 导致 shell 脚本无法执行
  - **README 平台说明修正**：明确「源码三平台可运行，构建产物仅提供 Windows 版」；补充 macOS 安装 Tk 的注意事项（官方安装包自带，Homebrew 需另装 python-tk）、启动方式，以及 macOS 剪贴板需授权「自动化 → 访达」的说明

### ⚡ 改进

- **macOS 依赖安装改用虚拟环境，绕开 PEP 668**：原启动脚本用 `pip install --user customtkinter` 装依赖，而 Homebrew 的 Python 遵守 PEP 668，安装会被拦下并报 `externally-managed-environment`（`--user` 也不能绕过），双击启动会卡在依赖安装这一步。现改为在项目目录内创建 `.venv`、把依赖装进虚拟环境、再用 `.venv/bin/python` 启动程序——不写入系统目录、不写入 `/opt/homebrew`、不需要 `sudo`，删掉 `.venv` 即卸载干净（`.venv` 已在 `.gitignore` 中）。同时补充「venv 创建失败」「venv 内 tkinter 不可用」两条报错分支，避免启动后闪退却看不到原因
- **README 的 macOS 安装说明重写**：原说明让人直接 `pip install customtkinter`（正是会被 PEP 668 拦下的做法），现改为虚拟环境流程；修正「系统自带 python3 一定不含 tkinter」的过时表述，并新增 `externally-managed-environment` 的排错 FAQ

> 说明：`dist/FileFinder.exe` 仍是 Windows 平台产物。PyInstaller 不支持交叉编译，macOS 版需在 Mac 上重新执行打包。

## [2.5.0] - 2026-09-20

### ✨ 新功能
- **操作历史记录（JSONL 日志）**：每次“复制/剪切到目标文件夹”完成后，把每个文件的源路径、最终落点（含自动重命名后的实际名字）和执行结果（成功/重命名/覆盖/跳过/失败）追加写入 `%LOCALAPPDATA%\FileFinder\operation_history.jsonl`（macOS/Linux 对应配置目录），供用户回顾操作、对照日志手动回退
  - 覆盖类操作的原文件已被替换，条目中标注“原内容无法恢复”
  - 写日志失败不影响文件操作本身（record_operation 内部兜底异常）
  - 主界面右上角新增“操作记录”按钮：一键用记事本打开历史日志（Windows 直接指定记事本，因 .jsonl 无系统文件关联、走默认打开方式会弹“选择打开方式”对话框；macOS/Linux 用系统默认程序），无需手动寻找配置目录；日志还不存在时给出提示
  - 实现：新增 `operation_log.py`；`perform_action` 逐文件收集最终路径与结果后调用 `record_operation()`
- **关键词浮窗（常驻置顶）**：主界面“关键词”标签行新增“关键词浮窗”开关，开启后弹出一个带标题栏的小输入窗并常驻在最前，在其他软件里翻找文件时可直接往浮窗里输入关键词（每行一个），不用来回切换主窗口
  - 浮窗内容与主界面关键词框**实时双向同步**：任一边输入/粘贴/清空，另一边立即跟随（监听底层 tkinter.Text 的 `<<Modified>>` 事件 + 内容比较去重防死循环，键盘输入、Ctrl+V、右键粘贴全覆盖）
  - 开关与浮窗联动：点浮窗右上角 X 关闭时开关自动复位，不会出现状态不一致
  - 浮窗默认出现在主窗口右缘内侧，位置计算自适应 DPI 缩放；窗口宽高均可自由拖拽调整（最小尺寸 240x100 逻辑像素）
  - 实现：新增 `keyword_float.py`（`KeywordFloatWindow`）；`file_manager.py` 新增 `toggle_keyword_float()` / `_sync_keywords()` 等方法

### ⚡ 改进
- **🟢 清理 `file_manager.py` 顶部的重复 import 块**：原文件在两处重复导入 `constants` / `ConflictDialog` / `PreviewMixin` / `ClipboardMixin`（其中 `PackDialog` 只在第二处），合并为顶部单处导入
- **🟢 Windows 剪贴板复制文件改用原生 API**：原方案通过 PowerShell 调用 .NET 的 `System.Windows.Forms.Clipboard.SetFileDropList`，360 等安全软件会将 PowerShell 进程启动拦截并报“线程注入”。新方案优先用 pywin32 在进程内直接构造 CF_HDROP 格式数据写入剪贴板（`win32clipboard` + `struct.pack`，剪贴板被占用时自动重试 10 次）——pywin32 已安装时不再启动任何外部进程，消除安全软件误报；未安装时回退到 PowerShell 方案（回退方案同时增加 `CREATE_NO_WINDOW` 标志隐藏控制台窗口）

### 🏗️ 依赖变更
- 新增可选依赖：`pywin32`（Windows 平台推荐安装，启用原生剪贴板 API；未安装时回退 PowerShell 方案）

## [2.4.0] - 2026-08-16

### ✨ 新功能
- **启动风险提示弹窗**：新增 `disclaimer_dialog.py`，程序首次启动（或未勾选"不再提示"时）弹出免责声明提示
  - 内容包含全部风险提示（操作不可逆/做好备份/结果自负）、"本工具完全免费，付费购得请及时退款"声明，以及 GitHub 项目地址
  - 必须勾选"我已知晓风险并同意上述条款"才能点击确定使用；直接关窗视为拒绝，程序退出
  - 勾选"不再提示"后持久化到用户配置目录（Windows `%LOCALAPPDATA%\FileFinder\config.json`，macOS/Linux 对应 `~/.config`），以后启动不再弹出
  - 提示文本内嵌为常量，打包成 exe 后同样生效

### 🐛 修复
- **🔴 启动弹窗不显示、程序启动后无窗口**：`main()` 用 `root.withdraw()` 隐藏主窗口后弹出 `CTkToplevel` 提示，但 customtkinter 的子窗口在父窗口 withdrawn 状态下不会渲染，导致程序启动后没有任何窗口、后台卡住。改为用透明度（`-alpha 0.0`）隐藏主窗口，弹窗正常显示，同意后恢复透明度进入主界面

## [2.3.0] - 2026-08-16

### ✨ 新功能
- **一键打包到 ZIP**：新增"打包到 ZIP"对话框（`pack_dialog.py`），支持：
  - 自由添加/移除多个文件或文件夹；打开时默认预填**目标文件夹**（保存位置也默认为目标文件夹），未设置则不预填
  - 自定义 zip 文件名（默认取顶层文件夹名），可选择压缩包内是否包含顶层文件夹（空目录也会保留）
  - 目标位置已有同名 zip 时询问（覆盖 / 自动重命名 / 取消）
  - 子线程打包 + 进度条，大目录不卡界面
- **打包并复制到剪贴板**：打包对话框中新增"打包并复制到剪贴板"按钮，打包完成后自动把 zip 复制到系统剪贴板，可在其他位置 Ctrl+V 粘贴

### ⚡ 改进
- **全选/全不选/反选 与 剪贴板按钮移到"文件操作"卡片**：原在文件列表卡片底部，窗口缩小时会被挤出可视区；现移至底部卡片（`side=BOTTOM` 钉住），任何窗口大小都可见
- **打包对话框按钮行钉在底部**："取消 / 打包并复制到剪贴板 / 开始打包" 用 `side=BOTTOM` 固定，窗口再小也不会被上方内容挤出

### 🐛 修复
- **🔴 复制文件到剪贴板 PowerShell 超时**：PowerShell 5.1 的 `[Console]::In` 在 `-Command` 模式绑定的是控制台输入而非管道，经 stdin 传文件列表会一直等待直至 30 秒超时。改用 `-EncodedCommand`（base64）内嵌路径数组传递，注入风险同样为零；`SetFileDropList` 增加重试（剪贴板被短暂占用时自动重试）
- **🔴 打包卡进度条且 zip 被占用**：当打包内容包含保存目录（zip 输出在被打包目录内部）时，`os.walk` 会遍历到正在写入的 zip 自身导致卡死、zip 句柄无法释放。修复：打包时自动排除输出 zip 自身；进度回调节流（每 0.05s 最多一次），避免超大目录回调风暴

## [2.2.0] - 2026-08-15

### ✨ 新功能
- **🟡 界面全面重做（customtkinter）**：UI 框架从 tkinter.ttk 迁移到 customtkinter，全新浅色现代风 + 蓝色点缀
  - 主界面改为 6 区卡片式布局，配色统一集中在 `constants.UI` 类，便于整体调整
  - `ConflictDialog` 冲突对话框迁移到 `CTkToplevel`，"全部覆盖"按钮使用红色警示样式
  - 预览区文本组件适配 customtkinter（`.config` → `.configure`）
  - 适配高分屏 DPI 缩放（150% 等），窗口尺寸与位置按逻辑单位计算
  - 逻辑层（扫描/筛选/文件操作/冲突处理）与 v2.1 完全一致，仅替换 UI 层
- **启动脚本锁定 Python 3.11**：`启动文件管理工具.bat` 优先使用 `py -3.11` 启动，解决多版本 Python 共存时解析到未安装 customtkinter 的解释器（如微软商店版 3.10）导致启动失败的问题

### 🏗️ 依赖变更
- 新增第三方依赖：`customtkinter`（≥ 6.0.0，随其安装 `pillow`）
- 最低 Python 版本要求从 3.6 提升至 **3.11**（customtkinter 运行所需）

## [2.1.0] - 2026-05-22

### ✨ 新功能
- **正则表达式搜索**：在"源文件夹"区域新增"正则表达式"复选框，勾选后关键词将作为正则表达式进行匹配
  - 在 `constants.py` 中新增 `compile_regex_patterns()` 函数，用于编译正则表达式
  - 在 `constants.py` 中新增 `match_file()` 函数，支持普通关键词和正则表达式两种匹配模式
  - 支持多个正则表达式（每行一个），匹配任一即命中
  - 正则表达式验证：扫描前自动验证关键词是否为有效的正则表达式，无效时弹出错误提示
  - 鼠标悬浮提示：将鼠标放在"正则表达式"复选框上，会弹出通俗易懂的功能解释，不了解正则的用户也能看懂

### 🔒 安全修复
- **🔴 修复 Windows 剪贴板命令注入漏洞**：`_copy_files_windows` 原先使用 f-string 拼接文件名到 PowerShell 命令，文件名含特殊字符（如 `'`、`$()`、`` ` ``）可被注入执行任意命令。现改用 stdin 传递文件列表，配合 PowerShell `[Console]::In.ReadLine()` 逐行安全读取，彻底消除注入风险
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

### 🐛 修复
- **🔴 覆盖冲突数据丢失**：`perform_action` 中 `decision=="overwrite"` 时未检查 `used_dest_paths`。源文件之间同名（如 `A/a.txt` 与 `B/a.txt`）选择"全部覆盖"时，后处理的文件会覆盖先处理的结果导致数据丢失。修复：目标路径已被本批次占用时强制重命名
- **🔴 xlsx 预览显示索引数字**：sheet XML 中字符串单元格存储的是 sharedStrings 索引，旧代码直接显示索引数字。修复：新增 `_extract_xlsx_text`，解析 sharedStrings.xml 映射回真实文本，sheet 按数字排序
- **扫描并发防护**：`_scan_generation` 代际标记丢弃过期扫描线程的结果，扫描期间禁用扫描按钮
- 冲突类型字符串抽为 `constants.py` 常量 `CONFLICT_TARGET_EXISTS` / `CONFLICT_SOURCE_DUP`
- 清理无用属性（`file_extensions` / `selected_files`）与无用导入，扩展名筛选改用 set 提升性能

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

# -*- mode: python ; coding: utf-8 -*-
import os
import sys

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# pywin32（可选依赖）：Windows 原生剪贴板 API。
# 打包机器上未安装时跳过；不收集时打出的 exe 会静默回退到 PowerShell 方案，
# 可能继续触发 360 等安全软件拦截。
try:
    tmp_ret = collect_all('win32clipboard')
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
except Exception:
    pass


# ─── 平台相关资源 ───
# PyInstaller 不支持交叉编译：在 Windows 上只能打出 exe，在 macOS 上只能打出 app，
# 所以这两份平台专属资源要按「当前在哪个平台上打包」来挑，同一份 spec 才能在两边都用。
#   - 图标：Windows 要 .ico，macOS 要 .icns（两种格式互不通用）
#   - 版本资源：version_info.txt 是 Windows PE 的版本信息块，macOS 不认，传了无意义
if sys.platform == 'darwin':
    _icon = 'icon.icns'
    _version = None
else:
    _icon = 'icon.ico'
    _version = 'version_info.txt'

# 对应格式的图标还没做出来时传 None：PyInstaller 会跳过图标，
# 而不是因为找不到文件直接中断打包
if not os.path.exists(_icon):
    _icon = None
if _version and not os.path.exists(_version):
    _version = None


a = Analysis(
    ['file_manager.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FileFinder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
    version=_version,
)


# ─── macOS 专属：把可执行文件包成 .app ───
# 这段只在 macOS 上执行，Windows 打包流程完全不受影响。
# 没有它，mac 上打出来只是一个 Unix 可执行文件（双击没反应，要从终端跑）。
# 注意：BUNDLE 的 icon 必须给 .icns，给 None 就是系统默认图标。
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='FileFinder.app',
        icon=_icon,
        bundle_identifier='com.moliushangxue.filefinder',
    )

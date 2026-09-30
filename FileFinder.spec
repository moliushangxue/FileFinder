# -*- mode: python ; coding: utf-8 -*-
import importlib.util
import os
import re
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


# ─── 构建期版本一致性校验 ───
# 版本号在项目里存了两份、且这两份没法在运行时互相推导：
#   - constants.py 的 APP_VERSION  → 运行时窗口标题用（file_manager.py 引用）
#   - version_info.txt             → 构建期写进 exe 的 PE 资源块，资源管理器「属性→详细信息」读的就是它
# 一旦两边不一致，就会出现「窗口标题写 3.0.0、文件属性写 2.5.0」这种自相矛盾的产物，
# 而且平时完全看不出来——只有出问题时才被发现。
# 所以在这里读一遍两边对齐：不相等就中断打包。宁可打不出包，也不发一个版本号对不上的 exe。
_spec_dir = globals().get('SPECPATH') or os.getcwd()


def _read_code_version():
    """从 constants.py 里读出 APP_VERSION（不通过 import constants，避免依赖构建机的 sys.path）"""
    path = os.path.join(_spec_dir, 'constants.py')
    module_spec = importlib.util.spec_from_file_location('_ff_constants_for_check', path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)   # exec_module 挂在 spec.loader 上，不是 spec 本身
    return module.APP_VERSION


def _read_pe_version():
    """从 version_info.txt 里抠出 FileVersion 的字符串形式（如 '3.0.0'）"""
    path = os.path.join(_spec_dir, 'version_info.txt')
    with open(path, encoding='utf-8') as f:
        matched = re.search(r"u'FileVersion',\s*u'([^']+)'", f.read())
    return matched.group(1) if matched else None


if _version:   # 只有 Windows 会走到这里（macOS 传的是 None，不生成 PE 资源）
    _code_version = _read_code_version()
    _pe_version = _read_pe_version()
    if _pe_version != _code_version:
        raise SystemExit(
            "\n[版本号不一致，已中断打包]\n"
            "  constants.py 的 APP_VERSION   = %r\n"
            "  version_info.txt 的 FileVersion = %r\n"
            "请把两处改成同一个值后重新打包。\n" % (_code_version, _pe_version)
        )
    print("[FileFinder] 版本号校验通过：%s" % _code_version)


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

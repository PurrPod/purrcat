# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all

# 把项目根目录加入 sys.path，否则 spec 执行时 collect_all/collect_data_files
# 找不到 src/tui 包，导致源码里的数据文件（harness 节点 JSON、系统规则、TUI 样式）漏打包
# 注意：spec 由 exec() 执行，没有 __file__，PyInstaller 执行前会切到 spec 所在目录，用 os.getcwd()
sys.path.insert(0, os.path.abspath(os.getcwd()))

datas = [('ui/dist', 'ui/dist')]
binaries = []
hiddenimports = []
datas += collect_data_files('tui')
tmp_ret = collect_all('src')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# chromadb / sentence-transformers 等库存在大量动态 import 和数据文件，
# PyInstaller 静态分析收集不全，缺了会导致打包后 ChromaDB 初始化失败
# （表现为记忆页工作经验库一片空白）
for pkg in ['chromadb', 'sentence_transformers', 'tokenizers', 'onnxruntime', 'huggingface_hub']:
    tmp = collect_all(pkg)
    datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# pywinpty 的 PTY 后端依赖包内的 winpty-agent.exe（WinPTY 回退）和 OpenConsole.exe
# （ConPTY 会话宿主），PyInstaller 静态分析只收 .pyd/.dll，漏掉这两个 exe 会导致
# 打包后终端 PTY 实例化失败（打开即红字：ConPTY 无效句柄 + winpty-agent.exe 不存在）。
# collect_all 把整个 winpty 目录（含 exe）收进 _internal/winpty/。非 Windows 构建无此包，跳过。
try:
    tmp = collect_all('winpty')
    datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]
except Exception:
    pass


a = Analysis(
    ['main.py'],
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
    [],
    exclude_binaries=True,
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    # UPX 会压坏 torch/onnxruntime 等原生 DLL 导致运行时崩溃
    # （GitHub Actions Windows runner 预装 UPX，PyInstaller 会自动使用）
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='main',
)

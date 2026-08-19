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
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='main',
)

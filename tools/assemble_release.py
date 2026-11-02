# -*- coding: utf-8 -*-
from __future__ import annotations

import re, shutil, zipfile

from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

SOURCE=ROOT/'Page_Operations_Monitor.py'

README=ROOT/'README.md'

PLUGIN_DIR=ROOT/'browser-extension'

ART=ROOT/'artifacts'

OUT=ROOT/'final-release'

META=ROOT/'release-meta'

TITLE='专业监控工具'


def version():
    t=SOURCE.read_text(encoding='utf-8-sig')

    m=re.search(r'APP_VERSION\s*=\s*["\']v?(\d+\.\d+\.\d+)["\']',t)

    if not m:raise RuntimeError('主程序找不到 APP_VERSION')

    return m.group(1)


def locate(name):
    m=[p for p in ART.rglob(name) if p.is_file()]

    if len(m)!=1:raise RuntimeError(f'无法唯一找到 {name}: {m}')

    return m[0]


def bundle(path,installer,icon,plugin_files):
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zf:
        zf.write(installer,installer.name)
        if README.exists():
            zf.write(README,README.name)
        if icon.exists():
            zf.write(icon,icon.name)
        for src,arc in plugin_files:
            zf.write(src,arc)


def plugin_files():
    """浏览器插件/ contents, sorted for deterministic zips."""
    if not PLUGIN_DIR.is_dir():
        return []
    files=[]
    for p in sorted(PLUGIN_DIR.rglob('*')):
        if p.is_file():
            files.append((p,'浏览器插件/'+p.relative_to(PLUGIN_DIR).as_posix()))
    if not files:
        raise RuntimeError('browser-extension/ 为空，无法组装浏览器插件')
    return files


def notes(ver):
    t=README.read_text(encoding='utf-8-sig') if README.exists() else ''

    m=re.search(rf'(?ms)^##\s+v?{re.escape(ver)}\b[^\n]*\n(.*?)(?=^##\s+|\Z)',t)

    body=m.group(1).strip() if m else '本版本更新详见项目说明。'

    return f'# {TITLE} v{ver}\n\n{body}\n\n下载对应系统 ZIP；连接器已内置在软件中，可从“浏览器连接”窗口导出。\n'


def main():
    ver=version();OUT.mkdir(parents=True,exist_ok=True);META.mkdir(parents=True,exist_ok=True)

    for p in OUT.iterdir():
        if p.is_file():p.unlink()
        elif p.is_dir():shutil.rmtree(p)

    win=locate(f'ProfessionalMonitorTool-{ver}-windows-x64-deployer.exe')

    arm=locate(f'ProfessionalMonitorTool-{ver}-macos-arm64.pkg')

    x64=locate(f'ProfessionalMonitorTool-{ver}-macos-x64.pkg')

    plugins=plugin_files()

    bundles=[
        (OUT/f'ProfessionalMonitorTool-{ver}-windows-x64.zip',win,ROOT/'PageOperationsMonitor.ico'),
        (OUT/f'ProfessionalMonitorTool-{ver}-macos-arm64.zip',arm,ROOT/'PageOperationsMonitor.icns'),
        (OUT/f'ProfessionalMonitorTool-{ver}-macos-x64.zip',x64,ROOT/'PageOperationsMonitor.icns'),
    ]

    for out,installer,icon in bundles:bundle(out,installer,icon,plugins)

    (META/'RELEASE_NOTES.md').write_text(notes(ver),encoding='utf-8')

    print('\n'.join(str(x[0]) for x in bundles));return 0

if __name__=='__main__':raise SystemExit(main())

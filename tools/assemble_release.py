# -*- coding: utf-8 -*-
from __future__ import annotations
import re, shutil, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'Page_Operations_Monitor.py';README=ROOT/'README.md';EXT=ROOT/'browser-extension';ART=ROOT/'artifacts';OUT=ROOT/'final-release';META=ROOT/'release-meta'
TITLE='专业监控工具'
def version():
    t=SOURCE.read_text(encoding='utf-8-sig');m=re.search(r'APP_VERSION\s*=\s*["\']v?(\d+\.\d+\.\d+)["\']',t)
    if not m:raise RuntimeError('主程序找不到 APP_VERSION')
    return m.group(1)
def locate(name):
    m=[p for p in ART.rglob(name) if p.is_file()]
    if len(m)!=1:raise RuntimeError(f'无法唯一找到 {name}: {m}')
    return m[0]
def add_plugin(zf):
    for p in sorted(EXT.rglob('*')):
        if p.is_file():zf.write(p,(Path('浏览器插件')/p.relative_to(EXT)).as_posix())
def bundle(path,installer):
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zf:
        zf.write(installer,installer.name);add_plugin(zf)
def notes(ver):
    t=README.read_text(encoding='utf-8-sig') if README.exists() else ''
    m=re.search(rf'(?ms)^##\s+v?{re.escape(ver)}\s*$\n(.*?)(?=^##\s+|\Z)',t)
    body=m.group(1).strip() if m else '本版本更新详见项目说明。'
    return f'# {TITLE} v{ver}\n\n{body}\n\n下载对应系统 ZIP；每个 ZIP 只包含部署/安装文件和浏览器插件。\n'
def main():
    ver=version();OUT.mkdir(parents=True,exist_ok=True);META.mkdir(parents=True,exist_ok=True)
    for p in OUT.iterdir():
        if p.is_file():p.unlink()
        elif p.is_dir():shutil.rmtree(p)
    win=locate(f'ProfessionalMonitorTool-{ver}-windows-x64-deployer.exe')
    arm=locate(f'ProfessionalMonitorTool-{ver}-macos-arm64.pkg')
    x64=locate(f'ProfessionalMonitorTool-{ver}-macos-x64.pkg')
    bundles=[
        (OUT/f'ProfessionalMonitorTool-{ver}-windows-x64.zip',win),
        (OUT/f'ProfessionalMonitorTool-{ver}-macos-arm64.zip',arm),
        (OUT/f'ProfessionalMonitorTool-{ver}-macos-x64.zip',x64),
    ]
    for out,installer in bundles:bundle(out,installer)
    (META/'RELEASE_NOTES.md').write_text(notes(ver),encoding='utf-8')
    print('\n'.join(str(x[0]) for x in bundles));return 0
if __name__=='__main__':raise SystemExit(main())

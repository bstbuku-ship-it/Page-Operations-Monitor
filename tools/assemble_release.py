# -*- coding: utf-8 -*-
from __future__ import annotations

import json, re, shutil, zipfile

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


def bundle_files(path,entries):
    # entries: (source_path, archive_name) pairs, written in given order.
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zf:
        for src,arc in entries:
            zf.write(src,arc)


def bundle(path,installer,plugin_files):
    # ZIP 内只有两样：当前系统的安装文件 + 浏览器插件。不放 README，不放图标。
    bundle_files(path,[(installer,installer.name)]+list(plugin_files))


def portable_files(ver):
    """Staged portable tree (artifact `windows-x64-portable`): same app files
    as the installer payload, plus the portable.mode marker at the top level.
    The marker is validated: mode must be portable and version must match."""
    root=ART/'windows-x64-portable'
    if not root.is_dir():
        markers=[p for p in ART.rglob('portable.mode') if p.is_file()]
        if len(markers)!=1:raise RuntimeError(f'无法唯一找到便携版目录: {markers}')
        root=markers[0].parent
    marker=root/'portable.mode'
    try:
        obj=json.loads(marker.read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:
        raise RuntimeError('便携版标记 portable.mode 无效') from exc
    if not isinstance(obj,dict) or obj.get('mode')!='portable' or str(obj.get('version'))!=ver:
        raise RuntimeError(f'便携版标记内容不符：{obj}')
    files=[]
    for q in sorted(root.rglob('*')):
        if q.is_file():
            files.append((q,q.relative_to(root).as_posix()))
    if not files:
        raise RuntimeError('便携版目录为空')
    return files


def plugin_files():
    """浏览器插件/ contents, sorted for deterministic zips."""
    if not PLUGIN_DIR.is_dir():
        raise RuntimeError('browser-extension/ 目录不存在，无法组装浏览器插件')
    files=[]
    for p in sorted(PLUGIN_DIR.rglob('*')):
        if p.is_file():
            files.append((p,'浏览器插件/'+p.relative_to(PLUGIN_DIR).as_posix()))
    if not files:
        raise RuntimeError('browser-extension/ 为空，无法组装浏览器插件')
    return files


def notes(ver):
    t=README.read_text(encoding='utf-8-sig') if README.exists() else ''

    m=re.search(rf'(?ms)^###\s+v?{re.escape(ver)}\b[^\n]*\n(.*?)(?=^###\s+|^##\s+|\Z)',t)

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
        (OUT/f'ProfessionalMonitorTool-{ver}-windows-x64.zip',win),
        (OUT/f'ProfessionalMonitorTool-{ver}-macos-arm64.zip',arm),
        (OUT/f'ProfessionalMonitorTool-{ver}-macos-x64.zip',x64),
    ]

    for out,installer in bundles:bundle(out,installer,plugins)

    portable_zip=OUT/f'ProfessionalMonitorTool-{ver}-windows-x64-portable.zip'
    bundle_files(portable_zip,portable_files(ver)+plugins)

    (META/'RELEASE_NOTES.md').write_text(notes(ver),encoding='utf-8')

    print('\n'.join([str(x[0]) for x in bundles]+[str(portable_zip)]));return 0

if __name__=='__main__':raise SystemExit(main())

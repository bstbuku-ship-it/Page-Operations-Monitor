# -*- coding: utf-8 -*-
"""把 GitHub Actions 各平台产物整理成最终 Release 文件。"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Page_Operations_Monitor.py"
README = ROOT / "README.md"
EXTENSION = ROOT / "browser-extension"
ARTIFACTS = ROOT / "artifacts"
OUT = ROOT / "final-release"
META = ROOT / "release-meta"
APP_ID = "PageOperationsMonitor"


def version() -> str:
    text = SOURCE.read_text(encoding="utf-8-sig")
    m = re.search(r'APP_VERSION\s*=\s*["\']v?(\d+\.\d+\.\d+)["\']', text)
    if not m:
        raise RuntimeError("主程序找不到 APP_VERSION")
    return m.group(1)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def locate(name: str) -> Path:
    matches = [p for p in ARTIFACTS.rglob(name) if p.is_file()]
    if len(matches) != 1:
        raise RuntimeError(f"无法唯一找到构建文件 {name}：{matches}")
    return matches[0]


def write_zip(path: Path, entries: list[tuple[Path, str]], folders: list[tuple[Path, str]] = []) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for src, arc in entries:
            zf.write(src, arc)
        for folder, prefix in folders:
            for src in sorted(folder.rglob("*")):
                if src.is_file():
                    zf.write(src, str(Path(prefix) / src.relative_to(folder)))


def release_notes(ver: str) -> str:
    text = README.read_text(encoding="utf-8-sig")
    # README 里使用 “## v1.3.0” 作为本版本日志标题。
    pat = re.compile(rf"(?ms)^##\s+v?{re.escape(ver)}\s*$\n(.*?)(?=^##\s+|\Z)")
    m = pat.search(text)
    if m:
        body = m.group(1).strip()
        return f"# 主页运营监控工具 v{ver}\n\n{body}\n"
    return f"# 主页运营监控工具 v{ver}\n\n详见 README.md。\n"


def main() -> int:
    ver = version()
    OUT.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)
    for p in OUT.iterdir():
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)

    windows_name = f"{APP_ID}-{ver}-windows-x64-setup.exe"
    mac_arm_name = f"{APP_ID}-{ver}-macos-arm64.pkg"
    mac_x64_name = f"{APP_ID}-{ver}-macos-x64.pkg"
    windows = locate(windows_name)
    mac_arm = locate(mac_arm_name)
    mac_x64 = locate(mac_x64_name)

    # 把安装器复制到 Release 根目录，软件内置更新器会直接下载这些文件。
    installers = []
    for src in (windows, mac_arm, mac_x64):
        dst = OUT / src.name
        shutil.copy2(src, dst)
        installers.append(dst)

    connector_zip = OUT / f"POM-Browser-Connector-{ver}.zip"
    write_zip(connector_zip, [], [(EXTENSION, "POM_Browser_Connector")])

    install_txt = OUT / "安装说明.txt"
    install_txt.write_text(
        "主页运营监控工具安装说明\n\n"
        "1. 先运行当前系统对应的软件安装包。\n"
        "2. 打开 Chrome：chrome://extensions\n"
        "3. 开启“开发者模式”。\n"
        "4. 点击“加载已解压的扩展程序”，选择完整包里的“浏览器插件”文件夹。\n"
        "5. 打开软件和需要监控的 Chrome Profile；插件会自动发现同一台电脑上的软件。\n"
        "6. 如果检测到多个浏览器/Profile，在软件右上角“浏览器”中选择要使用的连接。\n\n"
        "注意：macOS 当前云端包若未配置 Apple Developer ID 签名/公证，系统可能显示未知开发者提示。\n",
        encoding="utf-8-sig",
    )

    # 用户真正需要的“一次下载：软件 + 插件”完整包。每个平台单独一个，避免用户下错安装器。
    bundles = [
        (windows, f"{APP_ID}-{ver}-windows-x64-bundle.zip"),
        (mac_arm, f"{APP_ID}-{ver}-macos-arm64-bundle.zip"),
        (mac_x64, f"{APP_ID}-{ver}-macos-x64-bundle.zip"),
    ]
    for installer, bundle_name in bundles:
        write_zip(
            OUT / bundle_name,
            [(installer, installer.name), (README, "README.md"), (install_txt, "安装说明.txt")],
            [(EXTENSION, "浏览器插件")],
        )

    # 供源码用户下载；不参与安装版自动更新。
    source_zip = OUT / f"{APP_ID}-{ver}-source.zip"
    source_entries = [
        (SOURCE, "Page_Operations_Monitor.py"),
        (ROOT / "PageOperationsMonitor.ico", "PageOperationsMonitor.ico"),
        (README, "README.md"),
    ]
    mac_icon = ROOT / "PageOperationsMonitor.icns"
    if mac_icon.is_file():
        source_entries.append((mac_icon, "PageOperationsMonitor.icns"))
    write_zip(source_zip, source_entries, [(EXTENSION, "browser-extension")])

    manifest = {
        "schema": 1,
        "version": ver,
        "platforms": {
            "windows-x64": {
                "asset": windows_name,
                "sha256": sha256(OUT / windows_name),
                "installer": "inno",
            },
            "macos-arm64": {
                "asset": mac_arm_name,
                "sha256": sha256(OUT / mac_arm_name),
                "installer": "pkg",
            },
            "macos-x64": {
                "asset": mac_x64_name,
                "sha256": sha256(OUT / mac_x64_name),
                "installer": "pkg",
            },
        },
    }
    (OUT / "update-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (META / "RELEASE_NOTES.md").write_text(release_notes(ver), encoding="utf-8")
    (META / "VERSION.txt").write_text(ver + "\n", encoding="ascii")
    print(ver)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

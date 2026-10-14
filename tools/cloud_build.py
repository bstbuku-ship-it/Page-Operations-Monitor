# -*- coding: utf-8 -*-
"""
GitHub Actions 云端构建脚本。

重要：
- 本脚本只设计给 GitHub Actions 运行；不要求用户在自己电脑打包。
- Windows runner 负责生成 Windows 安装包。
- macOS runner 负责生成 macOS .pkg。
- 浏览器插件与最终“软件+插件完整包”由 assemble_release.py 统一组装。

仓库根目录只需要长期保留：
    Page_Operations_Monitor.py
    PageOperationsMonitor.ico
    PageOperationsMonitor.icns
    README.md
    browser-extension/
    .github/workflows/release.yml
    tools/
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Page_Operations_Monitor.py"
ICON_WIN = ROOT / "PageOperationsMonitor.ico"
ICON_MAC = ROOT / "PageOperationsMonitor.icns"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
OUT = ROOT / "cloud-release"
APP_ID = "PageOperationsMonitor"
APP_TITLE = "主页运营监控工具"
BUNDLE_ID = "com.bstbuku.pageoperationsmonitor"


def run(args: list[str], *, cwd: Path | None = None) -> None:
    print("\n>", " ".join(map(str, args)), flush=True)
    subprocess.run(args, cwd=cwd or ROOT, check=True)


def read_version() -> str:
    if not SOURCE.exists():
        raise RuntimeError(f"仓库根目录缺少 {SOURCE.name}")
    text = SOURCE.read_text(encoding="utf-8-sig")
    match = re.search(r'APP_VERSION\s*=\s*["\']v?(\d+\.\d+\.\d+)["\']', text)
    if not match:
        raise RuntimeError("主程序中找不到 APP_VERSION = \"x.y.z\"")
    return match.group(1)


def pyinstaller_common(icon: Path | None = None) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        APP_ID,
        "--workpath",
        str(BUILD / "pyinstaller"),
        "--distpath",
        str(DIST),
        "--specpath",
        str(BUILD / "pyinstaller"),
        # 主程序仍保留 Playwright 相关代码，所以把驱动资源一起收进安装版。
        "--collect-all",
        "playwright",
    ]
    if icon is not None:
        cmd.extend(["--icon", str(icon)])
    return cmd


def clean() -> None:
    shutil.rmtree(BUILD, ignore_errors=True)
    shutil.rmtree(DIST, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)


def find_iscc() -> Path:
    candidates = [
        shutil.which("ISCC.exe"),
        shutil.which("iscc.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise RuntimeError("GitHub Windows runner 中没有找到 Inno Setup 6 / ISCC.exe")


def build_windows(version: str) -> Path:
    if not ICON_WIN.exists():
        raise RuntimeError("缺少 PageOperationsMonitor.ico")
    run(pyinstaller_common(ICON_WIN) + [str(SOURCE)])

    app_dir = DIST / APP_ID
    exe = app_dir / f"{APP_ID}.exe"
    if not exe.exists():
        raise RuntimeError("PyInstaller 未生成 Windows exe")

    filename = f"{APP_ID}-{version}-windows-x64-setup.exe"
    iss = BUILD / "PageOperationsMonitor.iss"
    # 使用当前用户目录安装，后续软件内置更新可以静默覆盖，不需要管理员权限。
    lines = [
        f'#define MyAppName "{APP_TITLE}"',
        f'#define MyAppVersion "{version}"',
        f'#define MyAppExeName "{APP_ID}.exe"',
        "",
        "[Setup]",
        "AppId={{7C3E5A92-1D4B-4F8A-9E26-B05D8A1C74F3}",
        "AppName={#MyAppName}",
        "AppVersion={#MyAppVersion}",
        "AppPublisher=bstbuku-ship-it",
        "AppPublisherURL=https://github.com/bstbuku-ship-it/Page-Operations-Monitor",
        "AppSupportURL=https://github.com/bstbuku-ship-it/Page-Operations-Monitor/issues",
        "AppUpdatesURL=https://github.com/bstbuku-ship-it/Page-Operations-Monitor/releases",
        r"DefaultDirName={localappdata}\Programs\PageOperationsMonitor",
        "UsePreviousAppDir=yes",
        "DisableProgramGroupPage=yes",
        f"OutputDir={OUT}",
        f"OutputBaseFilename={filename[:-4]}",
        "Compression=lzma2",
        "SolidCompression=yes",
        "WizardStyle=modern",
        "PrivilegesRequired=lowest",
        "CloseApplications=force",
        "RestartApplications=no",
        "Uninstallable=yes",
        r"UninstallDisplayIcon={app}\{#MyAppExeName}",
        "ArchitecturesAllowed=x64compatible",
        "ArchitecturesInstallIn64BitMode=x64compatible",
        f"SetupIconFile={ICON_WIN}",
        "",
        "[Files]",
        f'Source: "{app_dir}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs',
        "",
        "[Tasks]",
        'Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："',
        "",
        "[Icons]",
        'Name: "{autoprograms}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"',
        'Name: "{autodesktop}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"; Tasks: desktopicon',
        "",
        "[Run]",
        'Filename: "{app}\\{#MyAppExeName}"; Description: "安装完成后启动{#MyAppName}"; Flags: nowait postinstall skipifsilent',
    ]
    iss.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    run([str(find_iscc()), str(iss)])
    result = OUT / filename
    if not result.exists():
        raise RuntimeError(f"Inno Setup 未生成 {filename}")
    return result


def build_macos(version: str, arch: str) -> Path:
    # 没有 ICNS 时仍可构建 macOS 安装包，只是使用系统默认应用图标。
    mac_icon = ICON_MAC if ICON_MAC.exists() else None
    run(
        pyinstaller_common(mac_icon)
        + ["--osx-bundle-identifier", BUNDLE_ID, str(SOURCE)]
    )
    app = DIST / f"{APP_ID}.app"
    if not app.exists():
        raise RuntimeError("PyInstaller 未生成 macOS .app")

    stage = BUILD / "pkgroot"
    target = stage / "Applications" / app.name
    target.parent.mkdir(parents=True, exist_ok=True)
    run(["ditto", str(app), str(target)])

    filename = f"{APP_ID}-{version}-macos-{arch}.pkg"
    result = OUT / filename
    run(
        [
            "pkgbuild",
            "--root",
            str(stage),
            "--identifier",
            BUNDLE_ID,
            "--version",
            version,
            "--install-location",
            "/",
            str(result),
        ]
    )
    if not result.exists():
        raise RuntimeError(f"pkgbuild 未生成 {filename}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="GitHub Actions cloud builder")
    parser.add_argument(
        "--target",
        required=True,
        choices=("windows-x64", "macos-arm64", "macos-x64"),
    )
    args = parser.parse_args()

    version = read_version()
    print(f"APP_VERSION={version}")
    print(f"Target={args.target}")
    print(f"Runner={platform.platform()}")
    clean()

    if args.target == "windows-x64":
        if os.name != "nt":
            raise RuntimeError("windows-x64 必须在 GitHub Windows runner 构建")
        result = build_windows(version)
    else:
        if sys.platform != "darwin":
            raise RuntimeError("macOS 安装包必须在 GitHub macOS runner 构建")
        expected = "arm64" if args.target.endswith("arm64") else "x64"
        machine = platform.machine().lower()
        actual = "arm64" if machine in ("arm64", "aarch64") else "x64"
        if actual != expected:
            raise RuntimeError(f"Runner 架构不匹配：需要 {expected}，实际 {machine}")
        result = build_macos(version, expected)

    print(f"BUILD_OUTPUT={result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

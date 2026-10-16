# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
try:
    import winreg
except ImportError:
    winreg = None

APP_TITLE = "专业监控工具"
APP_VERSION = "1.5.0"
APP_EXE = "ProfessionalMonitorTool.exe"
PORTABLE_MARKER = "portable.mode"
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ProfessionalMonitorTool"
SHORTCUT_NAME = APP_TITLE + ".lnk"


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def default_target() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Programs"
    return base / APP_TITLE


def deployment_mode(target: Path) -> str:
    drive = target.resolve().drive.upper() if target.exists() else Path(os.path.abspath(str(target))).drive.upper()
    return "standard" if drive == "C:" else "portable"


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_powershell(script_text: str, wait=True) -> subprocess.Popen | subprocess.CompletedProcess:
    fd, path = tempfile.mkstemp(prefix="pmt_", suffix=".ps1")
    os.close(fd)
    script = Path(path)
    script.write_text(script_text, encoding="utf-8-sig")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    if wait:
        try:
            return subprocess.run(args, check=False, creationflags=flags)
        finally:
            try: script.unlink(missing_ok=True)
            except OSError: pass
    p = subprocess.Popen(args, creationflags=flags)
    return p


def desktop_shortcut_path() -> str:
    code = "[Environment]::GetFolderPath('Desktop')"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.run(["powershell.exe", "-NoProfile", "-Command", code], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=flags)
    base = (p.stdout or "").strip() or str(Path.home() / "Desktop")
    return str(Path(base) / SHORTCUT_NAME)


def create_shortcut(target: Path) -> None:
    exe = target / APP_EXE
    shortcut = desktop_shortcut_path()
    script = (
        "$ws=New-Object -ComObject WScript.Shell\n"
        f"$s=$ws.CreateShortcut({ps_quote(shortcut)})\n"
        f"$s.TargetPath={ps_quote(str(exe))}\n"
        f"$s.WorkingDirectory={ps_quote(str(target))}\n"
        f"$s.IconLocation={ps_quote(str(exe)+',0')}\n"
        "$s.Save()\n"
    )
    run_powershell(script, wait=True)


def remove_shortcut() -> None:
    try:
        Path(desktop_shortcut_path()).unlink(missing_ok=True)
    except OSError:
        pass


def write_uninstall_registry(target: Path, uninstall_exe: Path) -> None:
    if winreg is None:
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
        values = {
            "DisplayName": APP_TITLE,
            "DisplayVersion": APP_VERSION,
            "Publisher": "bstbuku-ship-it",
            "InstallLocation": str(target),
            "DisplayIcon": str(target / APP_EXE),
            "UninstallString": f'"{uninstall_exe}" --uninstall --target "{target}"',
            "QuietUninstallString": f'"{uninstall_exe}" --uninstall --silent --target "{target}"',
        }
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)


def remove_uninstall_registry_if_target(target: Path) -> None:
    if winreg is None:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as key:
            existing = winreg.QueryValueEx(key, "InstallLocation")[0]
        if Path(existing).resolve() != target.resolve():
            return
    except OSError:
        return
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    except OSError:
        pass


def clear_program_files(target: Path, portable: bool) -> None:
    target.mkdir(parents=True, exist_ok=True)
    keep = {"data", PORTABLE_MARKER} if portable else set()
    current = Path(sys.executable).resolve()
    for child in list(target.iterdir()):
        if child.name in keep:
            continue
        try:
            if child.resolve() == current:
                continue
        except OSError:
            pass
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
        except OSError:
            # Locked stale files should not destroy the update; the application is already stopped during auto-update.
            pass


def extract_payload(target: Path) -> None:
    payload = resource_path("payload.zip")
    if not payload.is_file():
        raise RuntimeError("部署器内部缺少应用文件，请重新下载。")
    with zipfile.ZipFile(payload, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            rel = Path(info.filename.replace("\\", "/"))
            if rel.is_absolute() or ".." in rel.parts:
                raise RuntimeError("部署包路径异常，已停止。")
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, out.open("wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)


def deploy(target: Path, *, force_mode: str | None = None) -> str:
    target = Path(os.path.abspath(str(target)))
    mode = force_mode or deployment_mode(target)
    portable = mode == "portable"
    target.mkdir(parents=True, exist_ok=True)
    clear_program_files(target, portable)
    extract_payload(target)
    marker = target / PORTABLE_MARKER
    if portable:
        marker.write_text(json.dumps({"mode":"portable","version":APP_VERSION}, ensure_ascii=False), encoding="utf-8")
    else:
        marker.unlink(missing_ok=True)
        uninstaller = target / "卸载专业监控工具.exe"
        shutil.copy2(Path(sys.executable), uninstaller)
        write_uninstall_registry(target, uninstaller)
    create_shortcut(target)
    return mode


def uninstall(target: Path, silent: bool) -> int:
    target = Path(os.path.abspath(str(target)))
    if not silent:
        import tkinter as tk
        from tkinter import messagebox
        root=tk.Tk();root.withdraw()
        ok=messagebox.askyesno("卸载专业监控工具", f"确定删除专业监控工具吗？\n\n程序目录：{target}\n\n用户监控数据不会自动删除。")
        root.destroy()
        if not ok:return 0
    remove_shortcut();remove_uninstall_registry_if_target(target)
    script=("Start-Sleep -Seconds 2\n"+f"Remove-Item -LiteralPath {ps_quote(str(target))} -Recurse -Force -ErrorAction SilentlyContinue\n")
    run_powershell(script, wait=False)
    return 0


def silent_update(target: Path) -> int:
    target = Path(os.path.abspath(str(target)))
    mode = "portable" if (target / PORTABLE_MARKER).is_file() else "standard"
    deploy(target, force_mode=mode)
    return 0


def launch_app(target: Path) -> None:
    exe=target/APP_EXE
    if exe.is_file():subprocess.Popen([str(exe)], cwd=str(target))


class DeployUI:
    def __init__(self):
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        self.tk=tk;self.filedialog=filedialog;self.messagebox=messagebox;self.ttk=ttk
        self.root=tk.Tk();self.root.title(APP_TITLE+" 部署向导");self.root.geometry("720x470");self.root.resizable(False,False)
        self.root.configure(bg="#071421")
        try:self.root.iconbitmap(default=str(resource_path("PageOperationsMonitor.ico")))
        except Exception:pass
        self.path=tk.StringVar(value=str(default_target()));self.mode=tk.StringVar();self.status=tk.StringVar(value="请选择部署位置，然后开始部署。")
        self._build();self._update_mode();self.path.trace_add("write",lambda *_:self._update_mode())
    def _build(self):
        tk=self.tk;ttk=self.ttk
        outer=tk.Frame(self.root,bg="#071421",padx=32,pady=28);outer.pack(fill="both",expand=True)
        tk.Label(outer,text=APP_TITLE,bg="#071421",fg="#F3F7FB",font=("Microsoft YaHei UI",22,"bold")).pack(anchor="w")
        tk.Label(outer,text="简洁部署 · 可选择标准安装或绿色便携模式",bg="#071421",fg="#93AFC2",font=("Microsoft YaHei UI",10)).pack(anchor="w",pady=(4,24))
        card=tk.Frame(outer,bg="#0C2032",highlightbackground="#244D68",highlightthickness=1,padx=22,pady=20);card.pack(fill="x")
        tk.Label(card,text="部署位置",bg="#0C2032",fg="#F3F7FB",font=("Microsoft YaHei UI",11,"bold")).pack(anchor="w")
        line=tk.Frame(card,bg="#0C2032");line.pack(fill="x",pady=(9,12))
        entry=tk.Entry(line,textvariable=self.path,bg="#0A1B2A",fg="#F3F7FB",insertbackground="#FF9F43",relief="flat",font=("Microsoft YaHei UI",10));entry.pack(side="left",fill="x",expand=True,ipady=9)
        tk.Button(line,text="选择位置",command=self._browse,bg="#173A55",fg="#F3F7FB",activebackground="#244D68",activeforeground="#FFFFFF",relief="flat",padx=16,pady=8,font=("Microsoft YaHei UI",10,"bold")).pack(side="left",padx=(10,0))
        self.mode_label=tk.Label(card,textvariable=self.mode,bg="#0C2032",fg="#FFB05C",font=("Microsoft YaHei UI",10,"bold"),anchor="w",justify="left");self.mode_label.pack(fill="x")
        tk.Label(card,text="C 盘：注册为正常应用，可在系统/Geek 中卸载。\n其他盘：绿色便携部署，不写卸载注册项，数据也保存在软件目录内。",bg="#0C2032",fg="#93AFC2",font=("Microsoft YaHei UI",9),justify="left").pack(anchor="w",pady=(7,0))
        self.progress=ttk.Progressbar(outer,mode="indeterminate");self.progress.pack(fill="x",pady=(22,8))
        tk.Label(outer,textvariable=self.status,bg="#071421",fg="#93AFC2",font=("Microsoft YaHei UI",9)).pack(anchor="w")
        buttons=tk.Frame(outer,bg="#071421");buttons.pack(fill="x",side="bottom",pady=(24,0))
        tk.Button(buttons,text="退出",command=self.root.destroy,bg="#14314A",fg="#F3F7FB",relief="flat",padx=22,pady=10,font=("Microsoft YaHei UI",10)).pack(side="right")
        self.go=tk.Button(buttons,text="开始部署",command=self._install,bg="#FF9F43",fg="#1B1208",activebackground="#FFB466",relief="flat",padx=24,pady=10,font=("Microsoft YaHei UI",11,"bold"));self.go.pack(side="right",padx=(0,10))
    def _browse(self):
        chosen=self.filedialog.askdirectory(title="选择部署目录")
        if not chosen:return
        p=Path(chosen)
        if str(p).rstrip("\\/") in (p.drive, p.drive+"\\"):
            p=p/APP_TITLE
        self.path.set(str(p))
    def _update_mode(self):
        try:mode=deployment_mode(Path(self.path.get().strip() or default_target()))
        except Exception:mode="portable"
        self.mode.set("标准安装模式（C 盘，可正常卸载）" if mode=="standard" else "绿色便携模式（非 C 盘，不写卸载记录）")
    def _install(self):
        target=Path(self.path.get().strip())
        if not str(target):return
        self.go.configure(state="disabled");self.progress.start(12);self.status.set("正在部署，请稍候……");self.root.update_idletasks()
        try:
            mode=deploy(target)
            self.progress.stop();self.status.set("部署完成")
            message=("已完成标准安装。" if mode=="standard" else "已完成绿色便携部署。")+"\n\n已创建桌面快捷方式。是否现在启动？"
            if self.messagebox.askyesno("部署完成",message):launch_app(target)
            self.root.destroy()
        except Exception as exc:
            self.progress.stop();self.go.configure(state="normal");self.status.set("部署失败")
            self.messagebox.showerror("部署失败",str(exc))
    def run(self):self.root.mainloop()


def main() -> int:
    if os.name != "nt":return 2
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument("--silent-update",action="store_true")
    parser.add_argument("--uninstall",action="store_true")
    parser.add_argument("--silent",action="store_true")
    parser.add_argument("--target",default="")
    args,_=parser.parse_known_args()
    if args.uninstall:return uninstall(Path(args.target),args.silent)
    if args.silent_update:
        if not args.target:return 3
        return silent_update(Path(args.target))
    DeployUI().run();return 0

if __name__=="__main__":raise SystemExit(main())

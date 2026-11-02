# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse
import json
import queue
import threading
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
import stat
from pathlib import Path
try:
    import winreg
except ImportError:
    winreg = None

APP_TITLE = "专业监控工具"
APP_VERSION = "1.6.1"
APP_EXE = "ProfessionalMonitorTool.exe"
PORTABLE_MARKER = "portable.mode"
INSTALL_MARKER = ".professional-monitor-install.json"
PRODUCT_ID = "ProfessionalMonitorTool"
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


def _resolved(target: Path) -> Path:
    return Path(os.path.abspath(str(target))).resolve(strict=False)


def _is_reparse(path: Path) -> bool:
    try:
        st = path.lstat()
        attrs = getattr(st, "st_file_attributes", 0)
        return bool(attrs & 0x400) or path.is_symlink()
    except OSError:
        return False


def _protected_targets() -> set[Path]:
    values = [Path.home()]
    for key in ("SystemRoot","WINDIR","ProgramFiles","ProgramFiles(x86)","USERPROFILE","APPDATA","LOCALAPPDATA"):
        value = os.environ.get(key)
        if value:
            values.append(Path(value))
    for drive in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        values.append(Path(drive + ":\\"))
    out=set()
    for p in values:
        try:out.add(_resolved(p))
        except OSError:pass
    return out


def validate_target(target: Path) -> Path:
    raw=Path(os.path.abspath(str(target)))
    if raw.exists() and _is_reparse(raw):
        raise RuntimeError("部署目录不能是符号链接、目录联接或其他重解析点。")
    if raw.parent.exists() and _is_reparse(raw.parent):
        raise RuntimeError("部署目录的上级目录不能是重解析点。")
    target=_resolved(raw)
    if target in _protected_targets():
        raise RuntimeError("为防止误删系统或用户目录，请选择/新建一个专用的“专业监控工具”文件夹。")
    return target


def _registry_matches_target(target: Path) -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as key:
            existing = winreg.QueryValueEx(key, "InstallLocation")[0]
        return _resolved(Path(existing)) == _resolved(target)
    except (OSError, ValueError):
        return False


def read_install_marker(target: Path) -> dict | None:
    marker=target/INSTALL_MARKER
    try:
        if not marker.is_file() or marker.is_symlink() or marker.stat().st_size>4096:
            return None
        obj=json.loads(marker.read_text("utf-8"))
        if not isinstance(obj,dict) or obj.get("product")!=PRODUCT_ID:
            return None
        if obj.get("mode") not in ("standard","portable"):
            return None
        if _resolved(Path(str(obj.get("path") or ""))) != _resolved(target):
            return None
        return obj
    except (OSError,ValueError,TypeError,json.JSONDecodeError):
        return None


def write_install_marker(target: Path, mode: str) -> None:
    marker=target/INSTALL_MARKER
    temp=target/(INSTALL_MARKER+".tmp")
    payload={"schema":1,"product":PRODUCT_ID,"mode":mode,"version":APP_VERSION,"path":str(_resolved(target))}
    temp.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    os.replace(temp,marker)


def owned_install(target: Path, mode: str | None = None) -> bool:
    target=validate_target(target)
    marker=read_install_marker(target)
    if marker and (mode is None or marker.get("mode")==mode):
        # Standard installs are registered in HKCU; require that second signal
        # so a forged marker file alone cannot authorize destructive update/uninstall.
        if marker.get("mode")=="standard":
            return _registry_matches_target(target)
        return True
    if not (target/APP_EXE).is_file():
        return False
    legacy_portable=(target/PORTABLE_MARKER).is_file()
    if mode=="portable":
        return legacy_portable
    if mode=="standard":
        return (not legacy_portable) and _registry_matches_target(target)
    return legacy_portable or _registry_matches_target(target)


def ensure_safe_deploy_target(target: Path, mode: str, updating: bool) -> Path:
    target=validate_target(target)
    if target.exists():
        entries=list(target.iterdir())
        if entries:
            if updating:
                # 允许切换部署方式（标准安装 <-> 绿色便携）：只要目录是本工具
                # 已登记的安装目录即可，模式可以不同。
                if not (owned_install(target,mode) or owned_install(target)):
                    raise RuntimeError("更新目标不是本工具已登记的安装目录，已停止，避免误删其他文件。")
            elif not owned_install(target):
                raise RuntimeError("所选目录不是空目录，也不是已有的专业监控工具目录。请新建空文件夹后再部署。")
    return target


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


def write_uninstall_registry(target: Path, main_exe: Path) -> None:
    if winreg is None:
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
        values = {
            "DisplayName": APP_TITLE,
            "DisplayVersion": APP_VERSION,
            "Publisher": "bstbuku-ship-it",
            "InstallLocation": str(target),
            "DisplayIcon": str(target / APP_EXE),
            "UninstallString": f'"{main_exe}" --uninstall --target "{target}"',
            "QuietUninstallString": f'"{main_exe}" --uninstall --silent --target "{target}"',
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


def standard_data_dir() -> Path | None:
    if os.name != "nt":
        return None
    base = os.environ.get("LOCALAPPDATA") or ""
    if not base:
        return None
    return Path(base) / "FBGrowthRadar"


def backup_portable_data(target: Path) -> Path | None:
    """把便携版文件夹内的 data 移到旁边的备份目录，返回备份路径；没有数据则返回 None。"""
    data = target / "data"
    if not data.is_dir():
        return None
    parent = target.parent
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = parent / (target.name + "-数据备份")
    if candidate.exists():
        candidate = parent / (target.name + "-数据备份-" + stamp)
    shutil.move(str(data), str(candidate))
    return candidate


def clear_program_files(target: Path, portable: bool) -> None:
    target=validate_target(target)
    target.mkdir(parents=True, exist_ok=True)
    # 用户数据（data）两种模式都保留：更新/替换文件绝不能删数据。
    keep = {"data", PORTABLE_MARKER, INSTALL_MARKER}
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
            if _is_reparse(child):
                # Never traverse a junction/reparse point inside the install tree.
                if child.is_dir() and not child.is_symlink():
                    os.rmdir(child)
                else:
                    child.unlink(missing_ok=True)
            elif child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
        except OSError:
            # Locked stale files should not destroy the update; the application is already stopped during auto-update.
            pass


def extract_payload(target: Path, on_progress=None) -> None:
    target=validate_target(target)
    payload = resource_path("payload.zip")
    if not payload.is_file():
        raise RuntimeError("部署器内部缺少应用文件，请重新下载。")
    root=target.resolve(strict=False)
    total=0;files=0;entries=[]
    with zipfile.ZipFile(payload, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            files+=1;total+=int(info.file_size)
            if files>20000 or total>2*1024*1024*1024 or info.file_size>1024*1024*1024:
                raise RuntimeError("部署包文件数量或大小异常，已停止。")
            mode=(info.external_attr>>16)&0o170000
            if mode==stat.S_IFLNK:
                raise RuntimeError("部署包包含符号链接，已停止。")
            rel = Path(info.filename.replace("\\", "/"))
            if rel.is_absolute() or ".." in rel.parts or not rel.parts:
                raise RuntimeError("部署包路径异常，已停止。")
            if rel.parts[0] in ("data",PORTABLE_MARKER,INSTALL_MARKER):
                raise RuntimeError("部署包试图覆盖用户数据或安装标记，已停止。")
            out=(target/rel).resolve(strict=False)
            try:
                if os.path.commonpath([str(root),str(out)]) != str(root):
                    raise RuntimeError("部署包路径越界，已停止。")
            except ValueError:
                raise RuntimeError("部署包路径越界，已停止。")
            entries.append((info,out))
        done=0
        for info,out in entries:
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, out.open("wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            done+=int(info.file_size)
            if on_progress is not None:
                try:on_progress(done,total,info.filename)
                except Exception:pass


def deploy(target: Path, *, force_mode: str | None = None, updating: bool = False, on_progress=None) -> str:
    def emit(frac,label):
        if on_progress is not None:
            try:on_progress(max(0,min(1000,int(frac*1000))),1000,label)
            except Exception:pass
    target = validate_target(target)
    mode = force_mode or deployment_mode(target)
    if mode not in ("standard","portable"):
        raise RuntimeError("部署模式无效")
    portable = mode == "portable"
    emit(0.02,"正在准备部署…")
    target=ensure_safe_deploy_target(target,mode,updating)
    target.mkdir(parents=True, exist_ok=True)
    clear_program_files(target, portable)
    emit(0.05,"正在解压应用文件…")
    def _extract_progress(done,total,filename):
        frac=0.05+0.80*(done/total if total else 1)
        emit(frac,"正在解压："+Path(filename).name)
    extract_payload(target,_extract_progress)
    emit(0.88,"正在写入安装信息…")
    marker = target / PORTABLE_MARKER
    if portable:
        marker.write_text(json.dumps({"mode":"portable","version":APP_VERSION}, ensure_ascii=False), encoding="utf-8")
        remove_uninstall_registry_if_target(target)
    else:
        marker.unlink(missing_ok=True)
        # No separate maintenance program anymore (1.6.1): the registry
        # uninstall entry points at the main exe itself (--uninstall),
        # which shows the confirm dialog and deletes in the background.
        write_uninstall_registry(target, target / APP_EXE)
    write_install_marker(target,mode)
    create_shortcut(target)
    emit(1.0,"部署完成")
    return mode


def silent_update(target: Path) -> int:
    target = validate_target(target)
    marker=read_install_marker(target)
    mode=(marker or {}).get("mode") or ("portable" if (target / PORTABLE_MARKER).is_file() else "standard")
    if not owned_install(target,mode):
        raise RuntimeError("更新目标不是本工具已有安装目录，已停止。")
    deploy(target, force_mode=mode, updating=True)
    return 0


def launch_app(target: Path) -> None:
    exe=target/APP_EXE
    if exe.is_file():
        kwargs={}
        if os.name=="nt":kwargs["creationflags"]=getattr(subprocess,"CREATE_NO_WINDOW",0)
        subprocess.Popen([str(exe)],cwd=str(target),**kwargs)


class DeployUI:
    # 云白主题（与主界面默认主题一致）；窗口 720x510，内容留足边距，不裁切。
    BG="#F7F7F5";CARD="#FFFFFF";BORDER="#E8E8E3";TEXT="#1C1C1C";MUTED="#6E6E6E"
    ACCENT="#1D4ED8";ACCENT2="#1E40AF";PILL_BG="#EAF0FE";FIELD_BG="#F2F2EF"
    WARN_BG="#FFF8EC";WARN_TEXT="#B45309"
    def __init__(self):
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        self.tk=tk;self.filedialog=filedialog;self.messagebox=messagebox;self.ttk=ttk
        self.root=tk.Tk();self.root.title(APP_TITLE+" 部署向导");self.root.geometry("720x510");self.root.resizable(False,False)
        self.root.configure(bg=self.BG)
        try:self.root.iconbitmap(default=str(resource_path("PageOperationsMonitor.ico")))
        except Exception:pass
        self.path=tk.StringVar(value=str(default_target()));self.status=tk.StringVar(value="请选择部署位置和部署方式，然后开始部署。")
        self.stage=tk.StringVar(value="准备就绪");self.percent=tk.StringVar(value="0%")
        self.hint=tk.StringVar(value="")
        self._chosen_mode=None  # 用户点过卡片后固定，不再随盘符变
        self._mode="portable"
        self._progress_queue=queue.Queue();self._deploy_thread=None;self._deploy_target=None
        self._build();self._update_mode();self.path.trace_add("write",lambda *_:self._update_mode())
    def _draw_logo(self,parent):
        tk=self.tk
        cv=tk.Canvas(parent,width=46,height=46,bg=self.BG,highlightthickness=0);cv.pack(side="left")
        x0,y0,x1,y1=1,1,45,45;r=11
        cv.create_rectangle(x0+r,y0,x1-r,y1,fill=self.ACCENT,outline="")
        cv.create_rectangle(x0,y0+r,x1,y1-r,fill=self.ACCENT,outline="")
        for cx,cy in ((x0+r,y0+r),(x1-r,y0+r),(x0+r,y1-r),(x1-r,y1-r)):
            cv.create_oval(cx-r,cy-r,cx+r,cy+r,fill=self.ACCENT,outline="")
        pts=[(9.2,23),(15.6,23),(19.3,14.4),(22.9,30.7),(26.6,18.2),(30.3,23),(35.7,23)]
        cv.create_line([c for p in pts for c in p],fill="#FFFFFF",width=3,capstyle="round",joinstyle="round")
    def _bind_click(self, widget, fn):
        widget.bind("<Button-1>", fn)
        for child in widget.winfo_children():
            self._bind_click(child, fn)
    def _mode_card(self, parent, mode, title, desc):
        tk=self.tk
        card=tk.Frame(parent,bg=self.CARD,highlightbackground=self.BORDER,highlightthickness=1,padx=16,pady=12)
        top=tk.Frame(card,bg=self.CARD);top.pack(fill="x")
        tk.Label(top,text=title,bg=self.CARD,fg=self.ACCENT,font=("Microsoft YaHei UI",13,"bold")).pack(side="left")
        check=tk.Label(top,text="",bg=self.CARD,fg=self.ACCENT,font=("Microsoft YaHei UI",13,"bold"));check.pack(side="right")
        tk.Label(card,text=desc,bg=self.CARD,fg=self.MUTED,font=("Microsoft YaHei UI",10),wraplength=280,justify="left").pack(anchor="w",pady=(6,0))
        self._bind_click(card, lambda e, m=mode: self._pick_mode(m))
        return card, check
    def _pick_mode(self, mode):
        self._chosen_mode=mode
        self._mode=mode
        self._refresh_mode_cards()
    def _refresh_mode_cards(self):
        for mode, (card, check) in self._cards.items():
            selected = (mode == self._mode)
            card.configure(highlightthickness=2 if selected else 1,
                           highlightbackground=self.ACCENT if selected else self.BORDER)
            check.configure(text="✓" if selected else "")
    def _build(self):
        tk=self.tk;ttk=self.ttk
        try:
            style=ttk.Style(self.root);style.theme_use("clam")
            style.configure("Deploy.Horizontal.TProgressbar",thickness=8,background=self.ACCENT,troughcolor="#E8E8E3",borderwidth=0,relief="flat",lightcolor=self.ACCENT,darkcolor=self.ACCENT)
        except Exception:pass
        outer=tk.Frame(self.root,bg=self.BG,padx=30,pady=18);outer.pack(fill="both",expand=True)
        header=tk.Frame(outer,bg=self.BG);header.pack(fill="x")
        self._draw_logo(header)
        tk.Label(header,text=APP_TITLE,bg=self.BG,fg=self.TEXT,font=("Microsoft YaHei UI",22,"bold")).pack(side="left",padx=(12,0))
        tk.Label(outer,text="部署向导 · 选择一种部署方式",bg=self.BG,fg=self.MUTED,font=("Microsoft YaHei UI",11)).pack(anchor="w",pady=(6,14))
        card=tk.Frame(outer,bg=self.CARD,highlightbackground=self.BORDER,highlightthickness=1,padx=20,pady=16);card.pack(fill="x")
        tk.Label(card,text="部署位置",bg=self.CARD,fg=self.TEXT,font=("Microsoft YaHei UI",11,"bold")).pack(anchor="w")
        line=tk.Frame(card,bg=self.CARD);line.pack(fill="x",pady=(9,12))
        self.entry=tk.Entry(line,textvariable=self.path,bg=self.FIELD_BG,fg=self.TEXT,insertbackground=self.ACCENT,relief="flat",highlightbackground=self.BORDER,highlightthickness=1,font=("Microsoft YaHei UI",10));self.entry.pack(side="left",fill="x",expand=True,ipady=8)
        self.browse_btn=tk.Button(line,text="选择位置",command=self._browse,bg=self.CARD,fg=self.ACCENT,activebackground=self.PILL_BG,activeforeground=self.ACCENT,relief="flat",highlightbackground=self.ACCENT,highlightthickness=1,padx=14,pady=7,font=("Microsoft YaHei UI",10,"bold"));self.browse_btn.pack(side="left",padx=(10,0))
        tk.Label(card,text="部署方式（点卡片选择）",bg=self.CARD,fg=self.TEXT,font=("Microsoft YaHei UI",11,"bold")).pack(anchor="w")
        modes=tk.Frame(card,bg=self.CARD);modes.pack(fill="x",pady=(9,0))
        c1, k1 = self._mode_card(modes, "standard", "标准安装",
            "注册为系统应用，可在「设置 → 应用」或 Geek 中卸载；创建桌面快捷方式；数据保存在系统本地目录。")
        c1.pack(side="left", fill="both", expand=True)
        c2, k2 = self._mode_card(modes, "portable", "绿色便携",
            "不写注册表，不动系统；程序和数据都在所选文件夹里，整个文件夹拷走即用，删除即卸载。")
        c2.pack(side="left", fill="both", expand=True, padx=(12,0))
        self._cards={"standard":(c1,k1),"portable":(c2,k2)}
        self.hint_label=tk.Label(card,textvariable=self.hint,bg=self.WARN_BG,fg=self.WARN_TEXT,font=("Microsoft YaHei UI",10),wraplength=600,justify="left")
        prow=tk.Frame(outer,bg=self.BG);prow.pack(fill="x",pady=(18,4))
        tk.Label(prow,textvariable=self.stage,bg=self.BG,fg=self.MUTED,font=("Microsoft YaHei UI",11)).pack(side="left")
        tk.Label(prow,textvariable=self.percent,bg=self.BG,fg=self.TEXT,font=("Microsoft YaHei UI",11,"bold")).pack(side="right")
        self.progress=ttk.Progressbar(outer,mode="determinate",maximum=1000,value=0,style="Deploy.Horizontal.TProgressbar");self.progress.pack(fill="x")
        tk.Label(outer,textvariable=self.status,bg=self.BG,fg=self.MUTED,font=("Microsoft YaHei UI",11)).pack(anchor="w",pady=(8,0))
        buttons=tk.Frame(outer,bg=self.BG);buttons.pack(fill="x",side="bottom",pady=(14,0))
        self.exit_btn=tk.Button(buttons,text="退出",command=self.root.destroy,bg=self.CARD,fg=self.TEXT,relief="flat",highlightbackground="#D8D8D2",highlightthickness=1,padx=20,pady=9,font=("Microsoft YaHei UI",11));self.exit_btn.pack(side="right")
        self.go=tk.Button(buttons,text="开始部署",command=self._install,bg=self.ACCENT,fg="#FFFFFF",activebackground=self.ACCENT2,activeforeground="#FFFFFF",relief="flat",padx=22,pady=9,font=("Microsoft YaHei UI",11,"bold"));self.go.pack(side="right",padx=(0,10))
    def _browse(self):
        chosen=self.filedialog.askdirectory(title="选择部署目录")
        if not chosen:return
        p=Path(chosen)
        if str(p).rstrip("\\/") in (p.drive, p.drive+"\\"):
            p=p/APP_TITLE
        self.path.set(str(p))
    def _update_mode(self):
        raw=(self.path.get() or "").strip()
        try:
            target=Path(raw) if raw else default_target()
        except Exception:
            target=default_target()
        if self._chosen_mode is None:
            try:self._mode=deployment_mode(target)
            except Exception:self._mode="portable"
        self._refresh_mode_cards()
        try:
            owned = target.exists() and owned_install(target)
        except Exception:
            owned = False
        if owned:
            self.hint.set("检测到该位置已有安装：开始部署将替换程序文件，并保留已有数据。")
            self.hint_label.pack(fill="x", pady=(12,0))
        else:
            self.hint.set("")
            self.hint_label.pack_forget()
    def _install(self):
        target=Path(self.path.get().strip())
        if not str(target):return
        self._deploy_target=target
        self._deploy_mode=self._mode
        self.go.configure(state="disabled");self.browse_btn.configure(state="disabled");self.entry.configure(state="disabled")
        self.stage.set("正在部署，请稍候……");self.status.set("正在部署，请稍候……");self.percent.set("0%");self.progress.configure(value=0)
        self.root.update_idletasks()
        self._deploy_thread=threading.Thread(target=self._run_deploy,daemon=True);self._deploy_thread.start()
        self.root.after(60,self._poll_deploy)
    def _run_deploy(self):
        try:
            try:
                updating = owned_install(self._deploy_target)
            except Exception:
                updating = False
            mode=deploy(self._deploy_target, force_mode=self._deploy_mode, updating=updating,
                        on_progress=lambda d,t,label:self._progress_queue.put(("progress",d,t,label)))
            self._progress_queue.put(("done",mode,"",""))
        except Exception as exc:
            self._progress_queue.put(("error",str(exc),"",""))
    def _poll_deploy(self):
        try:
            while True:
                kind,a,b,c=self._progress_queue.get_nowait()
                if kind=="progress":
                    frac=a/b if b else 0;self.progress.configure(value=int(frac*1000));self.percent.set(f"{int(frac*100)}%");self.stage.set(c)
                elif kind=="done":self._show_done(a);return
                elif kind=="error":
                    self.go.configure(state="normal");self.browse_btn.configure(state="normal");self.entry.configure(state="normal")
                    self.stage.set("部署失败");self.status.set("部署失败");self.progress.configure(value=0);self.percent.set("0%")
                    self.messagebox.showerror("部署失败",a);return
        except queue.Empty:pass
        self.root.after(60,self._poll_deploy)
    def _show_done(self,mode):
        target=self._deploy_target
        self.progress.configure(value=1000);self.percent.set("100%");self.stage.set("部署完成")
        self.status.set(("已完成标准安装，已创建桌面快捷方式。" if mode=="standard" else "已完成绿色便携部署，已创建桌面快捷方式。"))
        self.exit_btn.configure(text="完成")
        self.go.configure(state="normal",text="现在启动",command=self._launch_and_close)
    def _launch_and_close(self):
        try:launch_app(self._deploy_target)
        except Exception:pass
        self.root.destroy()
    def run(self):self.root.mainloop()


def main() -> int:
    if os.name != "nt":return 2
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument("--silent-update",action="store_true")
    parser.add_argument("--target",default="")
    args,_=parser.parse_known_args()
    if args.silent_update:
        if not args.target:return 3
        return silent_update(Path(args.target))
    # No maintenance program anymore (1.6.1): this exe is the installer.
    # Double-clicking it always opens the deploy wizard; uninstall lives
    # in the main program's Settings (registry points at the main exe).
    DeployUI().run();return 0


if __name__=="__main__":raise SystemExit(main())

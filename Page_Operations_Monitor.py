# -*- coding: utf-8 -*-
"""Page Operations Monitor 1.5.2 -- automatic multi-Chrome Connector edition.
Run .py / .pyw; install PyQt6 Pillow (no connector network dependency).
Unpack extension/ in Chrome. It connects automatically. Select only when several browsers are online.
No remote-debugging switch, no cookie export, no unattended launch of the old default browser.
Version-independent single-instance activation. Closing to tray is silent.
"""
from __future__ import annotations

import csv
from contextlib import contextmanager
import os
import re
import sqlite3
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlsplit
import hashlib
import html
import json
import zipfile
import shutil
import subprocess
import sys
import io
import math
import random
import uuid
import logging
from datetime import timedelta
from urllib.parse import urljoin
import platform
import urllib.request
import urllib.error
import ssl
import base64
import shlex

APP_TITLE = "专业监控工具"
APP_VERSION = "1.7.0"
APP_BUILD = "professional-portable-deployer-ui-v170-20261103-rev23"
DEFAULT_INTERVAL_MINUTES = 240
DEFAULT_PAGE_GAP_SECONDS = 8  # compatibility for callers using a fixed interval
DEFAULT_ROUND_JITTER_MIN = 15
DEFAULT_ROUND_JITTER_MAX = 25
DEFAULT_PAGE_GAP_MIN = 6
DEFAULT_PAGE_GAP_MAX = 9
DEFAULT_SHOW_BROWSER = False
APP_USER_MODEL_ID = "bstbuku.PageOperationsMonitor.Desktop"
FACEBOOK_HOME = "https://www.facebook.com/"
PAGE_LOAD_TIMEOUT_MS = 45000


def ensure_private_directory(path: Path) -> Path:
    if path.is_symlink():
        raise RuntimeError("数据目录不能是符号链接")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        try:
            path.chmod(0o700)
        except OSError:
            pass
    return path


def _atomic_write_bytes(path: Path, data: bytes, mode: int = 0o600, *,
                        private_parent: bool = True) -> Path:
    """Write bytes through an exclusive, unpredictable temporary file.

    Refuse a symlink destination and never follow a pre-created temporary path.
    Application data is kept private; user-selected export folders are not chmodded.
    """
    path = Path(path)
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("data must be bytes-like")
    if private_parent:
        ensure_private_directory(path.parent)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise RuntimeError("拒绝写入符号链接目标")

    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = None
    try:
        fd = os.open(str(temp), flags, mode)
        with os.fdopen(fd, "wb") as stream:
            fd = None  # fdopen owns the descriptor now
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        if os.name == "posix":
            try:
                path.chmod(mode)
            except OSError:
                pass
        return path
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def portable_install_root() -> Path | None:
    """Application directory for explicit green/portable deployment only."""
    if not getattr(sys, "frozen", False):
        return None
    try:
        root = Path(sys.executable).resolve().parent
        return root if (root / "portable.mode").is_file() else None
    except OSError:
        return None


def app_data_dir() -> Path:
    override = os.environ.get("FBPM_DATA_DIR", "").strip()
    if override:
        return ensure_private_directory(Path(override).expanduser())
    portable = portable_install_root()
    if portable is not None:
        return ensure_private_directory(portable / "data")
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "FBGrowthRadar"
    else:
        base = Path.home() / ".fb_growth_radar"
    return base

DATA_DIR = app_data_dir()
DB_PATH = DATA_DIR / "fb_growth_radar_v1.db"
BROWSER_PROFILE_DIR = DATA_DIR / "browser_profile"
AVATAR_DIR = DATA_DIR / "avatars"
TOAST_AVATAR_SIZE = 96
TOAST_AVATAR_MAX_BYTES = 200000


def toast_avatar_dir():
    """Short, stable directory for toast-ready avatar copies."""
    d = DATA_DIR / "toast_avatars"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def _validate_toast_image(path):
    """True only if the file is a readable, square-ish PNG/JPEG under the limit."""
    try:
        p = Path(path)
        if not p.is_file() or p.stat().st_size <= 0 or p.stat().st_size > TOAST_AVATAR_MAX_BYTES:
            return False
        from PIL import Image
        with Image.open(p) as im:
            im.verify()
        with Image.open(p) as im:
            fmt = (im.format or "").upper()
            w, h = im.size
        if fmt not in ("PNG", "JPEG", "JPG"):
            return False
        if w < 48 or h < 48 or max(w, h) / max(1, min(w, h)) > 1.3:
            return False
        return True
    except Exception:
        return False


def _draw_logo_c_png(path, size=96):
    """Logo C (pulse) rendered with PIL only, so the toast fallback works
    without a QApplication and is identical in every theme."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.25), fill=(29, 78, 216, 255))
    pts = [(.208, .50), (.354, .50), (.438, .312), (.521, .667), (.604, .396), (.688, .50), (.812, .50)]
    xy = [(x * size, y * size) for x, y in pts]
    draw.line(xy, fill=(255, 255, 255, 255), width=max(2, int(size * 0.052)), joint="curve")
    img.save(path, format="PNG", optimize=True)
    return path


def prepare_toast_avatar(page_id, avatar_path=""):
    """Prepare a toast-ready avatar, trying several paths in order.

    1. Re-encode the cached avatar (or avatar_path) into a 96x96 PNG under
       a short ASCII filename in DATA_DIR/toast_avatars — this avoids the
       classic failure modes: Chinese/space/long paths, oversized or
       non-square images, and formats Windows cannot display.
    2. Use the original file directly, but only after PIL validation.
    3. Fall back to a freshly rendered Logo C PNG (always available).

    Returns (path, source). The outcome is recorded in toast_check.json so
    a failed avatar can be diagnosed on the real machine instead of
    silently showing a blank toast.
    """
    pid = re.sub(r"[^0-9]", "", str(page_id or "")) or "unknown"
    out_dir = toast_avatar_dir()
    out = out_dir / ("toast-" + pid + ".png")
    candidates = []
    for raw in (avatar_path, str(AVATAR_DIR / (pid + ".png"))):
        if raw:
            candidates.append(Path(str(raw)))
    for src in candidates:
        try:
            if not src.is_file():
                continue
            from PIL import Image, ImageOps
            with Image.open(src) as im:
                im.load()
                fitted = ImageOps.fit(im.convert("RGBA"), (TOAST_AVATAR_SIZE, TOAST_AVATAR_SIZE), Image.LANCZOS)
            tmp = out.with_suffix(".tmp.png")
            fitted.save(tmp, format="PNG", optimize=True)
            if _validate_toast_image(tmp):
                tmp.replace(out)
                _record_toast_avatar(pid, out, "avatar-reencoded")
                return out, "avatar-reencoded"
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            if _validate_toast_image(src):
                _record_toast_avatar(pid, src, "avatar-direct")
                return src, "avatar-direct"
        except Exception:
            continue
    logo = out_dir / "logo-c.png"
    try:
        if not _validate_toast_image(logo):
            _draw_logo_c_png(logo)
        _record_toast_avatar(pid, logo, "logo")
        return logo, "logo"
    except Exception:
        return logo, "logo"


def _record_toast_avatar(pid, path, source):
    try:
        record = toast_avatar_dir() / "toast_check.json"
        data = {}
        if record.is_file() and record.stat().st_size < 200000:
            data = json.loads(record.read_text("utf-8")) or {}
        avatars = data.get("avatars") or {}
        try:
            size = Path(path).stat().st_size
        except OSError:
            size = -1
        avatars[str(pid)] = {"path": str(path), "source": source, "bytes": size, "at": now_iso()}
        data["avatars"] = dict(list(avatars.items())[-200:])
        record.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _window_label(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""
    if seconds >= 3600:
        hours = seconds / 3600
        return _hours_1dp(seconds) + " 小时"
    if seconds >= 60:
        return "%d 分钟" % (seconds // 60)
    return "%d 秒" % seconds


def _age_label(ts, ref=None):
    if ts is None:
        return "待获取"
    ref = time.time() if ref is None else float(ref)
    seconds = max(0.0, ref - float(ts))
    if seconds < 60:
        return "不足1分钟"
    if seconds < 3600:
        return "%d分钟" % int(seconds // 60)
    if seconds < 48 * 3600:
        return _hours_1dp(seconds) + "小时"
    return "%d天" % round(seconds / 86400)


def _hours_1dp(seconds):
    """Hours with at most one decimal; a trailing .0 is stripped: 8 / 8.3."""
    text = f"{float(seconds) / 3600:.1f}"
    return text[:-2] if text.endswith(".0") else text


def _scaled_stylesheet(sheet, scale_pct):
    """Scale font-size, padding and margin in a stylesheet by the UI zoom.

    Every px number in those declarations is scaled (shorthands included:
    "padding:10px 20px" scales both). Font sizes keep an 8px floor;
    padding/margin keep a 1px floor so a 1px gap never collapses to 0.
    Border widths and radii are untouched.
    """
    if scale_pct == 100:
        return sheet

    def _decl(m):
        prop = m.group(1)
        floor = 8 if prop == "font-size" else 1

        def _num(n):
            return "%spx" % max(floor, round(float(n.group(1)) * scale_pct / 100))

        return prop + ":" + re.sub(r"(\d+(?:\.\d+)?)px", _num, m.group(2))

    return re.sub(r"(font-size|padding(?:-[a-z]+)?|margin(?:-[a-z]+)?)\s*:\s*([^;{}]+)", _decl, sheet)


def _normalize_legacy_hours(text):
    """Rewrite long-decimal hour figures in legacy stored text to 1 decimal.

    "8.00003小时" -> "8小时", "8.30002小时" -> "8.3小时". Figures that
    already have at most one decimal are left untouched.
    """
    def _fmt(m):
        try:
            hours = float(m.group(1))
        except (TypeError, ValueError):
            return m.group(0)
        return _hours_1dp(hours * 3600) + "小时"

    return re.sub(r"(\d+\.\d{2,})\s*小时", _fmt, str(text))


def _toast_body_parts(entry):
    """Structured (growth_part, post_part) for one alert entry.

    Structured fields win; a legacy free-text message is used only as a
    fallback (with any trailing ' ID <digits>' stripped). The page ID is
    never part of a toast body.
    """
    growth_part = None
    post_part = None
    kind = str(entry.get("kind") or "")
    if kind == "growth" or entry.get("growth") is not None:
        try:
            growth = int(entry.get("growth"))
        except (TypeError, ValueError):
            growth = None
        if growth is not None:
            window = _window_label(entry.get("window_seconds"))
            threshold = entry.get("threshold")
            single = "新增 %s" % format_delta(growth)
            if window:
                single += " · " + window
            if threshold is not None:
                single += " · 标准 %s" % threshold
                combined = "粉丝新增 %s（标准 %s）" % (format_delta(growth), threshold)
            else:
                combined = "粉丝新增 %s" % format_delta(growth)
            growth_part = (single, combined)
    if kind == "post" or entry.get("last_post_ts") is not None:
        ref = entry.get("alerted_ts")
        try:
            ref = float(ref) if ref is not None else None
        except (TypeError, ValueError):
            ref = None
        age = _age_label(entry.get("last_post_ts"), ref)
        limit = entry.get("limit_hours")
        if limit is not None:
            post_part = ("最近贴文 %s 前 · 标准 %s 小时" % (age, limit),
                         "最近贴文 %s 前（标准 %s 小时）" % (age, limit))
    if growth_part is None and post_part is None:
        message = str(entry.get("message") or "").strip()
        message = re.sub(r"\s*ID \d+\s*$", "", message)
        return _normalize_legacy_hours(message), None
    return growth_part, post_part


def build_toast_payload(entries):
    """Pure payload for one system toast covering a flush of alerts.

    One toast per flush (not one per entry): the first entry supplies the
    avatar and message, extra entries are counted in the message, and the
    button opens the full notification list. The body carries only numbers
    and thresholds — never the page ID. When the first page has both a
    growth and a post alert, one combined template covers both.
    """
    entries = list(entries or [])
    first = dict(entries[0]) if entries else {}
    pid = str(first.get("page_id") or "")
    name = str(first.get("name") or first.get("page_name") or "名称待获取")
    same_page = [dict(e) for e in entries if str(e.get("page_id") or "") == pid] if pid else [first]
    kinds = {str(e.get("kind") or "") for e in same_page}
    consumed = len(same_page)
    if "growth" in kinds and "post" in kinds:
        title = "两项预警 · " + name
        growth_entry = next(e for e in same_page if str(e.get("kind")) == "growth")
        post_entry = next(e for e in same_page if str(e.get("kind")) == "post")
        growth_text, _ = _toast_body_parts(growth_entry)
        _, post_text = _toast_body_parts(post_entry)
        growth_text = growth_text[1] if isinstance(growth_text, tuple) else (growth_text or "")
        post_text = post_text[1] if isinstance(post_text, tuple) else (post_text or "")
        message = "；".join(part for part in (growth_text, post_text) if part)
    elif str(first.get("kind") or "growth") == "post":
        title = "发帖超时 · " + name
        _, part = _toast_body_parts(first)
        message = part[0] if isinstance(part, tuple) else (part or "")
    else:
        title = "粉丝增长超标 · " + name
        part, _ = _toast_body_parts(first)
        message = part[0] if isinstance(part, tuple) else (part or "")
    remaining = len(entries) - consumed
    if remaining > 0:
        message = (message + " · 另有 %d 条预警" % remaining).strip()
    image, source = prepare_toast_avatar(pid, str(first.get("avatar_path") or ""))
    return {"title": title, "message": message, "image_path": image,
            "image_source": source, "page_id": pid, "count": len(entries)}

_SYSTEM_TOASTERS = []
_SYSTEM_TOASTS = []
_AUMID_REGISTER_STATE = {"done": False, "ok": False, "detail": ""}


def _ensure_toast_aumid_registered():
    """Register this app's AUMID under HKCU so Windows shows its toasts.

    Unpackaged apps get their toasts silently dropped when neither a Start
    shortcut carrying the AUMID nor this registry entry exists, and
    WinRT's Show() does not raise in that case. This mirrors the
    windows-toasts register_hkey_aumid script: HKCU
    SOFTWARE\\Classes\\AppUserModelId\\<AUMID> with DisplayName and,
    when an .ico can be produced, IconUri. Best effort, once per process.
    """
    if _AUMID_REGISTER_STATE["done"]:
        return _AUMID_REGISTER_STATE["ok"], _AUMID_REGISTER_STATE["detail"]
    _AUMID_REGISTER_STATE["done"] = True
    if os.name != "nt":
        _AUMID_REGISTER_STATE.update(ok=False, detail="not-windows")
        return False, "not-windows"
    try:
        import winreg
        icon_path = None
        try:
            logo = toast_avatar_dir() / "logo-c.png"
            if not _validate_toast_image(logo):
                _draw_logo_c_png(logo)
            from PIL import Image
            ico = toast_avatar_dir() / "app-icon.ico"
            with Image.open(logo) as im:
                im.convert("RGBA").save(ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
            icon_path = ico
        except Exception:
            icon_path = None
        key_path = "SOFTWARE\\Classes\\AppUserModelId\\" + APP_USER_MODEL_ID
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_TITLE)
            if icon_path is not None:
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(icon_path.resolve()))
        _AUMID_REGISTER_STATE.update(ok=True, detail="registered" + ("+icon" if icon_path is not None else ""))
        return True, _AUMID_REGISTER_STATE["detail"]
    except Exception as exc:
        _AUMID_REGISTER_STATE.update(ok=False, detail=str(exc)[:160])
        return False, _AUMID_REGISTER_STATE["detail"]


def _record_toast_failed(detail):
    try:
        record = toast_avatar_dir() / "toast_check.json"
        data = {}
        if record.is_file() and record.stat().st_size < 200000:
            data = json.loads(record.read_text("utf-8")) or {}
        last = data.get("last_send") or {}
        last["failed_event"] = {"detail": str(detail)[:200], "at": now_iso()}
        data["last_send"] = last
        record.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _toast_activation_is_view(*args):
    """True only when the user pressed the toast's 'view' action.

    windows-toasts delivers ToastActivatedEventArgs with an ``arguments``
    string: 'pom:view' for 查看通知, 'pom:view' never for 关闭, and an
    empty value for a body click. Anything else (including a missing or
    unrecognised payload) must NOT open the notification page.
    """
    ev = args[0] if args else None
    value = getattr(ev, "arguments", None)
    if value is None and isinstance(ev, str):
        value = ev
    if value is None and isinstance(ev, dict):
        value = ev.get("arguments", ev.get("Arguments"))
    return str(value or "").strip() == "pom:view"


def _record_toast_activation(arguments, is_view):
    """Best-effort diagnosis record: what Windows actually delivered."""
    try:
        record = toast_avatar_dir() / "toast_check.json"
        data = {}
        if record.is_file() and record.stat().st_size < 200000:
            data = json.loads(record.read_text("utf-8")) or {}
        data["last_activation"] = {"arguments": arguments, "view": is_view, "at": now_iso()}
        record.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def send_system_toast(entries, on_activated=None, silent=False):
    """Send the native Windows toast. Returns (ok, detail).

    Windows only. If windows-toasts is missing or the send fails, the
    caller must NOT show the old custom popup (removed by user decision);
    the alert itself stays in the notification list and the failure is
    recorded in toast_check.json for diagnosis.
    """
    if os.name != "nt":
        return False, "not-windows"
    try:
        payload = build_toast_payload(entries)
    except Exception as exc:
        return False, "payload:" + str(exc)[:160]
    try:
        from windows_toasts import (InteractableWindowsToaster, Toast,
                                    ToastButton, ToastDisplayImage, ToastDuration,
                                    ToastImage, ToastImagePosition, ToastScenario)
        try:
            from windows_toasts import ToastAudio
        except Exception:
            ToastAudio = None
    except Exception as exc:
        return False, "windows-toasts-not-installed:" + str(exc)[:160]
    try:
        image = None
        try:
            image = ToastDisplayImage.fromPath(str(payload["image_path"]),
                                               position=ToastImagePosition.AppLogo, circleCrop=True)
        except Exception:
            image = ToastDisplayImage(ToastImage(str(payload["image_path"])),
                                      position=ToastImagePosition.AppLogo, circleCrop=True)
        toast = Toast()
        toast.text_fields = [payload["title"], payload["message"]]
        try:
            toast.AddImage(image)
        except Exception:
            try:
                toast.images.append(image)
            except Exception:
                pass
        try:
            toast.scenario = ToastScenario.Reminder
        except Exception:
            pass
        try:
            toast.duration = ToastDuration.Long
        except Exception:
            pass
        if silent and ToastAudio is not None:
            try:
                toast.audio = ToastAudio(silent=True)
            except Exception:
                pass
        for _label, _arg in (("查看通知", "pom:view"), ("关闭", "pom:dismiss")):
            try:
                toast.AddAction(ToastButton(_label, _arg))
            except Exception:
                try:
                    toast.add_action(ToastButton(_label, _arg))
                except Exception:
                    try:
                        toast.actions.append(ToastButton(_label, _arg))
                    except Exception:
                        pass
        def _failed(*_args, **_kwargs):
            try:
                _ev = _args[0] if _args else None
                _record_toast_failed(getattr(_ev, "error_code", _ev))
            except Exception:
                pass
        toast.on_failed = _failed
        _SYSTEM_TOASTS.append(toast)
        del _SYSTEM_TOASTS[:-10]
        aumid_ok, aumid_detail = _ensure_toast_aumid_registered()
        if on_activated is not None:
            def _activated(*_args, **_kwargs):
                try:
                    ev = _args[0] if _args else None
                    raw = getattr(ev, "arguments", None)
                    if raw is None and isinstance(ev, str):
                        raw = ev
                    is_view = _toast_activation_is_view(*_args)
                    _record_toast_activation("" if raw is None else str(raw), is_view)
                    if is_view:
                        on_activated()
                except Exception:
                    pass
            toast.on_activated = _activated
        try:
            toaster = InteractableWindowsToaster(APP_TITLE, notifierAUMID=APP_USER_MODEL_ID)
        except Exception:
            try:
                toaster = InteractableWindowsToaster(APP_TITLE)
            except Exception:
                from windows_toasts import WindowsToaster
                toaster = WindowsToaster(APP_TITLE)
        _SYSTEM_TOASTERS.append(toaster)
        toaster.show_toast(toast)
        try:
            record = toast_avatar_dir() / "toast_check.json"
            data = {}
            if record.is_file() and record.stat().st_size < 200000:
                data = json.loads(record.read_text("utf-8")) or {}
            data["last_send"] = {"ok": True, "image_source": payload["image_source"],
                                 "image": str(payload["image_path"]), "count": payload["count"],
                                 "aumid_ok": aumid_ok, "aumid_detail": aumid_detail, "at": now_iso()}
            record.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
        return True, payload["image_source"] + ("" if aumid_ok else "; AUMID未注册：" + aumid_detail)
    except Exception as exc:
        detail = str(exc)[:200]
        try:
            record = toast_avatar_dir() / "toast_check.json"
            data = {}
            if record.is_file() and record.stat().st_size < 200000:
                data = json.loads(record.read_text("utf-8")) or {}
            data["last_send"] = {"ok": False, "detail": detail,
                                 "image_source": payload.get("image_source", ""), "at": now_iso()}
            record.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
        log_exception("系统通知发送失败：" + detail)
        return False, detail




def monitor_profile_dir() -> Path:
    """The one application-owned browser profile; never scans or opens daily Chrome accounts."""
    return BROWSER_PROFILE_DIR








def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def format_count(v) -> str:
    return "—" if v is None else f"{int(v):,}"


def format_compact_count(v) -> str:
    """Compact follower number for cards; exact value remains in the tooltip."""
    if v is None:
        return "—"
    n = int(v)
    if abs(n) < 7000:
        return f"{n:,}"
    text = f"{n / 10000.0:.1f}".rstrip("0").rstrip(".")
    return text + "W"


def format_delta(v) -> str:
    return "—" if v is None else (f"+{int(v):,}" if v > 0 else f"{int(v):,}")


def format_delta_compact(v) -> str:
    """Short delta for card values (V5): full below 1000, k-units above.
    The exact value stays in the value tooltip; notifications and metric
    cards keep using format_delta."""
    if v is None:
        return "—"
    n = int(v)
    if abs(n) < 1000:
        return f"+{n:,}" if n > 0 else f"{n:,}"
    sign = "+" if n > 0 else "-"
    a = abs(n)
    if a < 100000:
        return f"{sign}{a / 1000.0:.1f}k"
    return f"{sign}{a // 1000}k"


def compact_elapsed(ts, now=None, approximate=False) -> str:
    if not ts:
        return "—"
    now = time.time() if now is None else float(now)
    seconds = max(0.0, now - float(ts))
    mark = "≈" if approximate else ""
    if seconds < 3600:
        return f"{mark}{max(1, int(seconds // 60))}M"
    hours = seconds / 3600.0
    if hours < 100:
        return f"{mark}{hours:.1f}H"
    return f"{mark}{hours / 24.0:.1f}D"


def local_time_label(value: str, with_date=True) -> str:
    if not value:
        return "—"
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo:
            d = d.astimezone()
        return d.strftime("%m-%d %H:%M" if with_date else "%H:%M")
    except (ValueError, TypeError):
        return value[:16].replace("T", " ")


def safe_csv_cell(value):
    if isinstance(value, str):
        probe = value.lstrip("\ufeff \t\r\n\v\f")
        if probe.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
            return "'" + value
    return value


@dataclass
class PasteParseResult:
    ids: list[str]
    rejected: list[str]
    duplicates: int = 0


# Real 谷歌表格 copies contain tabs/newlines; some copied data contains
# Markdown / terminal table decorations as well.
BORDERS = "│┃┆┇┊┋╎╏┌┐└┘├┤┬┴┼─━═║╔╗╚╝╠╣╦╩╬┏┓┗┛┣┫┳┻╋"
INVISIBLE = ("\ufeff", "\u200b", "\u200c", "\u200d", "\u2060", "\u00ad")
HEADERS = {"id", "pageid", "page_id", "facebookid", "facebookpageid", "专业id", "专页id", "主页id", "编号", "主页编号", "facebook主页", "name", "page", "主页名称", "专页名称"}


def _facebook_id_from_url(raw: str) -> str | None:
    candidate = raw.strip().strip("<>[]{}()\"'“”‘’.,;，；")
    if "facebook.com" not in candidate.lower() and "fb.com" not in candidate.lower():
        return None
    if "://" not in candidate:
        candidate = "https://" + candidate
    try:
        url = urlsplit(candidate)
        host = (url.hostname or "").lower()
        if not (host in ("facebook.com", "fb.com") or host.endswith(".facebook.com") or host.endswith(".fb.com")):
            return None
        qs = parse_qs(url.query)
        for key in ("id", "page_id"):
            for val in qs.get(key, []):
                if re.fullmatch(r"\d{5,25}", val):
                    return val
        segments = [x for x in url.path.split("/") if x]
        if segments and re.fullmatch(r"\d{5,25}", segments[-1]):
            return segments[-1]
    except ValueError:
        pass
    return None


def normalize_page_ids(text: str) -> PasteParseResult:
    """Parse IDs pasted from Sheets, Excel, ASCII / Markdown tables and URLs.

    Never convert floating-point or exponential notation to an ID.  When Sheets
    has rounded a 15-digit number, the lost digits cannot be recovered.
    """
    if not text:
        return PasteParseResult([], [])
    source = unicodedata.normalize("NFKC", str(text))
    for char in INVISIBLE:
        source = source.replace(char, "")
    source = source.replace("\u00a0", " ").replace("\u3000", " ")
    source = source.translate(str.maketrans({c: "|" for c in BORDERS}))
    ids, seen, rejected, duplicates = [], set(), [], 0

    def add(token: str):
        nonlocal duplicates
        if token in seen:
            duplicates += 1
        else:
            ids.append(token)
            seen.add(token)

    def process(raw: str):
        token = raw.strip().strip("\"“”‘’`")
        while token.startswith(("'", "’", "＇")):
            token = token[1:].strip()
        token = token.strip("\"“”‘’`")
        if not token or token in {"-", "--", ":-", "—", "…"}:
            return
        if re.fullmatch(r"[-+=:|_ ]{3,}", token):
            return
        if re.fullmatch(r"=[\"']?\d+[\"']?", token):
            token = re.sub(r"[^0-9]", "", token)
        if "facebook.com" in token.lower() or "fb.com" in token.lower():
            found = _facebook_id_from_url(token)
            if found:
                add(found)
            else:
                rejected.append(raw.strip()[:100])
            return
        if re.search(r"(?:\d+\.?\d*)[Ee][+-]?\d+", token):
            rejected.append(raw.strip()[:100] + "（科学计数法无法保证精确）")
            return
        if re.fullmatch(r"\d{1,3}(?:[,，]\d{3})+", token):
            token = token.replace(",", "").replace("，", "")
        if re.fullmatch(r"\d{5,25}", token):
            add(token)
        elif re.fullmatch(r"\d+", token):
            rejected.append(raw.strip()[:100] + "（长度不像 主页编号）")
        elif any(ch.isdigit() for ch in token):
            rejected.append(raw.strip()[:100])
        elif re.sub(r"[\s_-]+", "", token.lower()) not in HEADERS:
            # Other columns of a spreadsheet (e.g. page name) are safely skipped.
            return

    # Split first on actual pasted rows/cells. Comma splitting is handled per
    # cell to distinguish thousands separators from comma-separated ID lists.
    for cell in re.split(r"[\r\n\t|;；]+", source):
        cell = cell.strip()
        if not cell or re.fullmatch(r"[-+:_= ]{3,}", cell):
            continue
        if "facebook.com" in cell.lower() or "fb.com" in cell.lower():
            for part in re.split(r"\s+", cell):
                process(part)
            continue
        # Multiple IDs on the same line, including from multi-cell paste.
        if re.fullmatch(r"\d{1,3}(?:[,，]\d{3})+", cell):
            process(cell)
            continue
        for part in re.split(r"[,，\s]+", cell):
            process(part)
    return PasteParseResult(ids, rejected, duplicates)


# ---------- Facebook text extraction (legacy parser preserved + safer patterns) ----------

def parse_human_number(raw):
    s = unicodedata.normalize("NFKC", str(raw)).strip().lower().replace("\u00a0", " ").replace("，", ",")
    suffixes = [
        (r"\s*(?:k|千|rb|ribu|mil)$", 1000),
        (r"\s*(?:m|million|millions|millón|millones|mio\.?|jt)$", 1_000_000),
        (r"\s*(?:b|billion|billions)$", 1_000_000_000),
        (r"\s*万$", 10_000),
        (r"\s*亿$", 100_000_000),
        (r"\s*萬$", 10_000),
        (r"\s*億$", 100_000_000),
    ]
    multiplier = 1
    for pat, factor in suffixes:
        if re.search(pat, s, re.I):
            multiplier = factor
            s = re.sub(pat, "", s, flags=re.I).strip()
            break
    s = re.sub(r"[^0-9.,]", "", s)
    if not s:
        raise ValueError("未识别到数字")
    if multiplier == 1:
        return int(re.sub(r"[.,]", "", s)), False
    if "," in s and "." in s:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif "," in s:
        s = s.replace(",", "." if len(s.split(",")[-1]) <= 2 else "")
    elif "." in s and len(s.split(".")[-1]) > 2:
        s = s.replace(".", "")
    return int(round(float(s) * multiplier)), True


FOLLOWER_PATTERNS = [
    r"(?P<num>[0-9][0-9.,\s]*(?:[KkMm]|万|萬|亿|億|千)?)\s*(?:位|名)?\s*(?:追蹤者|追踪者|关注者|關注者|追蹤人|追踪人)",
    r"(?:追蹤者|追踪者|关注者|關注者)\s*[:：]?\s*(?P<num>[0-9][0-9.,\s]*(?:[KkMm]|万|萬|亿|億|千)?)",
    r"(?P<num>[0-9][0-9.,\s]*(?:[KkMm]|万|萬|亿|億|千)?)\s*(?:人|位|名)\s*(?:追蹤|追踪|关注|關注)",
    r"(?P<num>[0-9][0-9.,\s]*(?:[KkMmBb])?)\s+(?:followers?|Follower)",
    r"(?P<num>[0-9][0-9.,\s]*(?:万|亿|[KkMm])?)\s*(?:位)?粉丝",
    r"(?P<num>[0-9][0-9.,\s]*(?:rb|ribu|jt|[KkMm])?)\s+(?:pengikut)",
    r"(?P<num>[0-9][0-9.,\s]*(?:mil|millones?|[KkMm])?)\s+(?:seguidores?)",
    r"(?P<num>[0-9][0-9.,\s]*(?:k|m|millions?)?)\s+(?:abonnés?)",
    r"(?P<num>[0-9][0-9.,\s]*(?:mila|milioni?|[KkMm])?)\s+(?:follower)",
    r"(?P<num>[0-9][0-9.,\s]*(?:bin|milyon|[KkMm])?)\s+(?:takipçi)",
]


def extract_followers_from_text(text: str):
    candidates = []
    for pattern in FOLLOWER_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            try:
                count, approx = parse_human_number(match.group("num"))
            except (ValueError, OverflowError):
                continue
            if 0 <= count <= 10_000_000_000:
                candidates.append((match.start(), count, approx, match.group(0).strip()))
    if not candidates:
        raise RuntimeError("页面未识别到粉丝数。可能需要登录、等待加载，或 脸书页面格式发生了变化。")
    # Prefer the first follower count in the page's heading region.  All results
    # are tentative; the UI shows approximations explicitly.
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1], candidates[0][2], candidates[0][3]


def clean_page_name(raw):
    if not raw:return ""
    text=str(raw)
    for _ in range(3):
        decoded=html.unescape(text)
        if decoded==text:break
        text=decoded
    text=re.sub(r"\s+", " ", text).strip()
    text=re.sub(r"^\(\d+\)\s*", "", text).strip()
    text=re.sub(r"\s*[|\-–—·]\s*Facebook\s*$", "", text, flags=re.I).strip()
    text=re.sub(r"\s*\|\s*Meta\s*$", "", text, flags=re.I).strip()
    text=re.sub(r"\s*[|\-–—·]\s*(?:Home|Posts|About|Photos|Videos|Reels|主页|首页|帖子|关于|照片|视频|短视频)\s*$",
                "", text, flags=re.I).strip()
    return text if len(text)<=180 else ""


# Name extractor from the supplied reference.zip / facebook_follower_tracker_v6.py.
# Identity-source order and filtering retained; integrated after follower-text parsing.
GENERIC_UI_NAMES = {
    "facebook", "meta", "home", "首页", "主页", "通知", "消息", "菜单", "搜索", "好友", "视频", "游戏", "群组",
    "动态消息", "动态", "创建", "更多", "个人主页", "设置", "设置和隐私", "帮助和支持", "查看全部", "通知中心",
    "赞", "点赞", "关注", "已关注", "正在关注", "发消息", "简介", "关于", "帖子", "照片", "短视频", "提及", "点评", "社区",
    "直播", "分享", "管理", "切换", "搜索 facebook", "notifications", "notification", "menu", "search", "friends",
    "watch", "marketplace", "groups", "gaming", "messenger", "messages", "settings", "like", "liked", "follow",
    "following", "message", "about", "posts", "photos", "videos", "reels", "mentions", "reviews", "community", "live",
    "share", "log in", "login", "sign up", "register", "详细信息", "详情", "更多信息", "专页详情", "页面详情",
    "个人资料详情", "个人资料详细信息", "公开详情", "基本信息", "信息", "介绍", "联系方式", "details", "detail",
    "page details", "profile details", "public details", "more information", "additional information", "contact info", "information",
    "facebook - log in or sign up", "facebook – log in or sign up", "facebook - 登录或注册", "facebook – 登录或注册",
    "全部", "所有", "全部内容", "查看全部", "显示全部", "全部帖子", "全部动态", "all", "all posts",
    "see all", "show all", "overview", "timeline", "精选", "筛选", "排序", "最近", "最相关", "热门",
    "查看所有照片", "查看全部照片", "所有照片", "see all photos", "view all photos", "all photos",
    "posts by", "more", "更多内容", "管理帖子", "筛选条件",
}

BAD_NAME_FRAGMENTS = [
    "followers", "follower", "粉丝", "pengikut", "seguidores", "abonn", "following", "likes", "people like this",
    "people follow this", "登录", "注册", "log in", "sign up", "notification", "通知中心", "详细信息", "个人资料详细信息",
    "公开详情", "page details", "profile details", "查看所有照片", "查看全部照片", "see all photos", "view all photos",
]

# Facebook 的页头区域同时会出现“关注 360 人 / 关注 0 人 / 1 人关注”等统计或操作文字。
# 这些文字字体较大，旧版本有时会把它们误判成专页名称。
STAT_OR_ACTION_PATTERNS = [
    r"^(?:已?关注|正在关注|关注了|关注中)\s*[0-9０-９][0-9０-９.,，\s万亿千kmbKMB]*\s*(?:人|位|个)?$",
    r"^[0-9０-９][0-9０-９.,，\s万亿千kmbKMB]*\s*(?:人|位|个)?\s*(?:已?关注|正在关注|关注中)$",
    r"^(?:following|followed by)\s*[0-9][0-9.,\sKkMmBb]*\s*(?:people|persons?)?$",
    r"^[0-9][0-9.,\sKkMmBb]*\s*(?:people\s+)?following$",
    r"^[0-9０-９][0-9０-９.,，\s万亿千kmbKMB]*\s*(?:人|位|people|persons?)$",
    r"^(?:赞|点赞|likes?)\s*[0-9０-９][0-9０-９.,，\s万亿千kmbKMB]*\s*(?:人|位|个)?$",
]


def looks_like_stat_or_action(value: str) -> bool:
    s = clean_page_name(value)
    if not s:
        return True
    compact = re.sub(r"\s+", " ", s).strip()
    for pat in STAT_OR_ACTION_PATTERNS:
        if re.fullmatch(pat, compact, flags=re.I):
            return True

    # 只要包含明显的数字统计 + UI 关键词，也不要作为名称。
    has_number = bool(re.search(r"[0-9０-９]", compact))
    if has_number and re.search(
        r"(?:关注|正在关注|已关注|粉丝|点赞|赞|followers?|following|likes?|people\s+follow)",
        compact,
        flags=re.I,
    ):
        return True
    return False


def looks_like_page_name(value, page_id=""):
    s = clean_page_name(value)
    if not s:
        return False
    low = s.lower().strip()
    if low in {x.lower() for x in GENERIC_UI_NAMES}:
        return False
    for frag in BAD_NAME_FRAGMENTS:
        if frag in low:
            # A real name may contain a UI word ("粉丝团", "关注者协会"). Only
            # reject when nothing meaningful remains after removing the
            # fragment and any digits/quantifiers, e.g. "详细信息" or
            # "123 people like this". Exact UI words are already rejected
            # above and stat/action text is rejected below.
            rest = re.sub(r"[\d\s.,:+\-/%万亿千kmb]+", "", low.replace(frag, " "), flags=re.I)
            if not rest or rest in {x.lower() for x in GENERIC_UI_NAMES}:
                return False
    if looks_like_stat_or_action(s):
        return False
    if page_id and s == str(page_id):
        return False
    if re.search(r"https?://|www\.", low):
        return False
    if re.fullmatch(r"[\d\s.,:+\-/%万亿千kmb]+", low, flags=re.I):
        return False
    if not re.search(r"[A-Za-z\u00C0-\u024F\u4e00-\u9fff\u3040-\u30ff\u0E00-\u0E7F]", s):
        return False
    return True

def _meta_content(page, selector):
    try:
        return page.locator(selector).first.get_attribute("content", timeout=1200) or ""
    except Exception:
        return ""


def _clean_profile_alt(raw):
    s = clean_page_name(raw)
    if not s:
        return ""
    suffixes = [
        r"'s\s+profile\s+picture$", r"profile\s+picture$", r"'s\s+profile\s+photo$",
        r"profile\s+photo$", r"的头像$", r"的大头贴$", r"的个人头像$", r"头像$",
        r"foto de perfil$", r"photo de profil$", r"profilbild$", r"immagine del profilo$",
    ]
    for pat in suffixes:
        s = re.sub(pat, "", s, flags=re.I).strip()
    return clean_page_name(s)


def _strict_h1_candidates(page):
    """Return visible h1 text outside navigation/tab/dialog chrome, top first."""
    try:
        rows = page.locator("h1").evaluate_all(
            r"""
            (els) => {
              const out = [];
              for (const el of els) {
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > innerHeight * 2) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                if (el.closest('[role="navigation"],[role="tablist"],[role="menu"],[role="dialog"]')) continue;
                const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                if (!text || text.length > 180) continue;
                out.push({text, top:r.top, left:r.left, fs:parseFloat(st.fontSize || '0') || 0});
              }
              out.sort((a,b) => (a.top-b.top) || (b.fs-a.fs) || (a.left-b.left));
              return out.slice(0, 20);
            }
            """
        )
        return rows or []
    except Exception:
        return []


def _profile_alt_candidates(page):
    try:
        rows = page.locator('img[alt]').evaluate_all(
            r"""
            (els) => {
              const out = [];
              for (const el of els.slice(0, 300)) {
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 28 || r.height < 28 || r.bottom < 0 || r.top > 1200) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                if (el.closest('[role="navigation"],[role="menu"],[role="dialog"]')) continue;
                const alt = (el.getAttribute('alt') || '').replace(/\s+/g, ' ').trim();
                if (!alt || alt.length > 220) continue;
                const isProfile = /(?:'s\s+profile\s+(?:picture|photo)|profile\s+(?:picture|photo)|的头像|的大头贴|的个人头像|头像|foto de perfil|photo de profil|profilbild|immagine del profilo)$/i.test(alt);
                if (!isProfile) continue;
                out.push({text:alt, top:r.top, size:Math.max(r.width, r.height)});
              }
              out.sort((a,b) => (a.top-b.top) || (b.size-a.size));
              return out.slice(0, 30);
            }
            """
        )
        return rows or []
    except Exception:
        return []


def _self_link_candidates(page, page_id):
    try:
        return page.locator('a[href]').evaluate_all(
            r"""
            (els, pageId) => {
              const out = [];
              const id = String(pageId || '');
              const cur = new URL(location.href);
              const curPath = cur.pathname.replace(/\/+$/, '');
              for (const el of els.slice(0, 1200)) {
                if (el.closest('[role="navigation"],[role="tablist"],[role="menu"],[role="dialog"]')) continue;
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > 1100) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                if (!text || text.length > 180) continue;
                let u; try { u = new URL(el.href, location.href); } catch (_) { continue; }
                const path = u.pathname.replace(/\/+$/, '');
                const idHit = id && (path === '/' + id || path.startsWith('/' + id + '/'));
                const profileId = id && u.searchParams.get('id') === id;
                const samePath = curPath && path === curPath;
                if (!(idHit || profileId || samePath)) continue;
                out.push({
                  text,
                  top:r.top,
                  fs:parseFloat(st.fontSize || '0') || 0,
                  fw:parseInt(st.fontWeight || '400', 10) || 400,
                  strong:idHit || profileId
                });
              }
              out.sort((a,b) => (Number(b.strong)-Number(a.strong)) || (a.top-b.top) || (b.fs-a.fs) || (b.fw-a.fw));
              return out.slice(0, 60);
            }
            """,
            str(page_id or ""),
        ) or []
    except Exception:
        return []


def _near_follower_candidates(page, matched_text):
    """Find visible text just above/alongside the actual follower-count element."""
    if not matched_text:
        return []
    try:
        return page.locator('body').evaluate(
            r"""
            (body, needle) => {
              needle = String(needle || '').replace(/\s+/g, ' ').trim();
              if (!needle) return [];
              const all = Array.from(document.querySelectorAll('a,span,div'));
              const hits = [];
              for (const el of all.slice(0, 5000)) {
                if (el.closest('[role="navigation"],[role="tablist"],[role="menu"],[role="dialog"]')) continue;
                const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                if (!text || text.length > 220) continue;
                if (!(text === needle || text.includes(needle))) continue;
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > 1400) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                hits.push({el, r});
              }
              if (!hits.length) return [];
              hits.sort((a,b) => (a.r.top-b.r.top) || (a.r.left-b.r.left));
              const target = hits[0].r;
              const out = [];
              const candidates = Array.from(document.querySelectorAll('h1,h2,[role="heading"],a,span,strong'));
              for (const el of candidates.slice(0, 5000)) {
                if (el.closest('[role="navigation"],[role="tablist"],[role="menu"],[role="dialog"]')) continue;
                const r = el.getBoundingClientRect();
                const st = getComputedStyle(el);
                if (!r || r.width < 2 || r.height < 2) continue;
                if (r.top < target.top - 320 || r.top > target.bottom + 90) continue;
                if (Math.abs(r.left - target.left) > 900) continue;
                if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity || 1) === 0) continue;
                const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                if (!text || text.length > 180 || text === needle) continue;
                const fs = parseFloat(st.fontSize || '0') || 0;
                const fw = parseInt(st.fontWeight || '400', 10) || 400;
                const distance = Math.max(0, target.top - r.bottom);
                out.push({text, distance, fs, fw, top:r.top});
              }
              out.sort((a,b) => (a.distance-b.distance) || (b.fs-a.fs) || (b.fw-a.fw));
              return out.slice(0, 80);
            }
            """,
            str(matched_text),
        ) or []
    except Exception:
        return []


def _wait_for_page_identity(page, timeout_ms=7000):
    """Give Facebook SPA a little time to replace generic chrome with Page identity."""
    deadline = time.monotonic() + max(0.5, timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        for row in _strict_h1_candidates(page):
            name = clean_page_name((row or {}).get("text", ""))
            if looks_like_page_name(name):
                return
        try:
            title = clean_page_name(page.title())
            if looks_like_page_name(title):
                return
        except Exception:
            pass
        try:
            page.wait_for_timeout(350)
        except Exception:
            break


def extract_page_name(page, body_text, page_id="", matched_text=""):
    """Extract the Page display name using identity-specific DOM before generic text.

    The old versions used a broad largest-text heuristic. Facebook UI words such as
    “通知”, “详细信息”, “关注 360 人”, and “全部” can be large too, so this version
    only trusts identity-bearing locations first and heavily filters navigation text.
    """
    _wait_for_page_identity(page, timeout_ms=4500)

    # 1) Facebook Pages normally expose the display name as a visible top-level h1.
    # Take the first valid h1 outside navigation/tab/dialog chrome.
    for row in _strict_h1_candidates(page):
        name = clean_page_name((row or {}).get("text", ""))
        if looks_like_page_name(name, page_id):
            return name

    # 2) The profile image accessible name is highly specific to the Page identity.
    for row in _profile_alt_candidates(page):
        name = _clean_profile_alt((row or {}).get("text", ""))
        if looks_like_page_name(name, page_id):
            return name

    # 3) A link that points back to the current numeric Page identity.
    for row in _self_link_candidates(page, page_id):
        name = clean_page_name((row or {}).get("text", ""))
        if looks_like_page_name(name, page_id):
            return name

    # 4) Open Graph/document metadata. These are useful but can remain generic in SPA views.
    for raw in [
        _meta_content(page, 'meta[property="og:title"]'),
        _meta_content(page, 'meta[name="twitter:title"]'),
    ]:
        name = clean_page_name(raw)
        if looks_like_page_name(name, page_id):
            return name
    try:
        name = clean_page_name(page.title())
        if looks_like_page_name(name, page_id):
            return name
    except Exception:
        pass

    # 5) Only search text physically near the follower count that we actually parsed.
    for row in _near_follower_candidates(page, matched_text):
        name = clean_page_name((row or {}).get("text", ""))
        if looks_like_page_name(name, page_id):
            return name

    # 6) Last resort: visible heading roles outside navigation. No generic large-text scan.
    try:
        rows = page.locator('[role="heading"]').evaluate_all(
            r"""
            (els) => {
              const out=[];
              for (const el of els.slice(0, 250)) {
                if (el.closest('[role="navigation"],[role="tablist"],[role="menu"],[role="dialog"]')) continue;
                const r=el.getBoundingClientRect(), st=getComputedStyle(el);
                if (!r || r.width<2 || r.height<2 || r.bottom<0 || r.top>1200) continue;
                if (st.visibility==='hidden' || st.display==='none' || Number(st.opacity||1)===0) continue;
                const text=(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim();
                if (!text || text.length>180) continue;
                const level = Number(el.getAttribute('aria-level') || 99);
                out.push({text, level, top:r.top, fs:parseFloat(st.fontSize||'0')||0});
              }
              out.sort((a,b)=>(a.level-b.level)||(a.top-b.top)||(b.fs-a.fs));
              return out.slice(0,80);
            }
            """
        )
        for row in rows or []:
            name = clean_page_name((row or {}).get("text", ""))
            if looks_like_page_name(name, page_id):
                return name
    except Exception:
        pass

    return ""




def should_alert(current: int, previous: dict | None, current_ts: float,
                 current_approx: bool, interval_seconds: int, threshold: int) -> bool:
    """Avoid false alerts after missing samples or with rounded follower numbers."""
    if previous is None or current_approx or previous.get("approx"):
        return False
    elapsed = current_ts - float(previous.get("ts") or 0)
    if elapsed < 60 or elapsed > max(300, 2.5 * interval_seconds):
        return False
    return current - int(previous["count"]) >= threshold



# Phrases shown by Facebook itself on an unavailable Page. Checked against
# short heading/title candidates or the visible body text only, never against
# post content. Login is checked first elsewhere; these phrases mean the Page
# itself cannot be opened (deleted / unpublished / restricted / blocked all
# render the same screen, so the software reports "unavailable", never a
# guessed "deleted").
UNAVAILABLE_PHRASES = (
    "content isn't available", "this content isn't available",
    "this page isn't available", "page not found", "content not found",
    "the link you followed may be broken", "page may have been removed",
    "this page may have been removed",
    "内容不可用", "此内容目前无法显示", "此内容暂时无法显示",
    "这个页面暂时无法显示", "页面不存在", "链接可能已损坏",
    "该页面可能已被移除", "此页面不存在",
    "內容不可用", "此內容目前無法顯示", "這個頁面暫時無法顯示",
    "連結可能已損壞", "頁面不存在",
    "conteúdo não disponível", "página não encontrada",
    "esta página não está disponível", "o link que você seguiu pode estar quebrado",
    "contenido no disponible", "página no encontrada",
    "esta página no está disponible", "el enlace que seguiste puede estar roto",
    "page introuvable", "contenu indisponible", "cette page n'est pas disponible",
    "seite nicht verfügbar", "inhalt nicht verfügbar", "seite nicht gefunden",
)
RESTRICTED_PHRASES = (
    "age", "年龄", "年齡", "not available in your region", "地区", "地區",
    "country", "国家", "國家",
)
PAGE_UNAVAILABLE_DETAIL = "页面显示内容不可用，可能是已删除 / 已下架 / 被限制访问"


def detect_unavailable_page(text):
    """Return (is_unavailable, hint_phrase) for short UI text or body text.

    The hint is the matched UI phrase itself (capped), never surrounding
    page content, so it is safe to store and display.
    """
    if not isinstance(text, str) or not text:
        return False, ""
    collapsed = re.sub(r"\s+", " ", text).strip().casefold()
    if not collapsed:
        return False, ""
    for phrase in UNAVAILABLE_PHRASES:
        if phrase in collapsed:
            hint = phrase
            for marker in RESTRICTED_PHRASES:
                if marker in collapsed:
                    hint += "（可能受年龄 / 地区限制）"
                    break
            return True, hint[:80]
    return False, ""


def normalize_name(value, pid=""):
    """Reject generated placeholders and decode HTML without turning an ID into a name."""
    name = clean_page_name(value or "")
    for _ in range(2):
        decoded = html.unescape(name)
        if decoded == name:
            break
        name = decoded
    name = re.sub(r"\s+", " ", name).strip()
    banned = {"名称待获取", "待获取", "facebook", "log in to facebook", "登录 facebook",
              "登录或注册", "登录或註冊", "此内容目前无法显示", "content isn't available",
              "this content isn't available right now", "this page isn't available right now",
              "page not found", "content not found", "log in or sign up", "log into facebook",
              "内容不可用", "此内容暂时无法显示", "这个页面暂时无法显示"}
    if name.casefold() in {x.casefold() for x in banned}:
        return ""
    if re.fullmatch(r"(?:主页|公共主页|專頁|专页|page)\s*[:：#]?\s*[\d\W]+", name, re.I):
        return ""
    if name.isdigit() or (pid and name == str(pid)):
        return ""
    return name[:180] if looks_like_page_name(name,pid) else ""


def display_name(row):
    return (str(row.get("custom_name") or "").strip()
            or normalize_name(row.get("page_name"), row.get("page_id"))
            or "名称待获取")


def is_true(value, default=False):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "none")
    return bool(value)


def _bounded_int(value, default, low, high):
    try:
        value = int(value)
    except (ValueError, TypeError, OverflowError):
        value = default
    return max(low, min(high, value))


def inspection_timing(settings):
    """One source of defaults/ranges for both UI locations and runtime scheduling."""
    return (
        _bounded_int(settings.value("interval_minutes", DEFAULT_INTERVAL_MINUTES),
                     DEFAULT_INTERVAL_MINUTES, 5, 1440),
        _bounded_int(settings.value("page_gap_seconds", DEFAULT_PAGE_GAP_SECONDS),
                     DEFAULT_PAGE_GAP_SECONDS, 0, 120),
    )


def normalize_random_timing(minutes, jitter_min, jitter_max, gap_min, gap_max):
    """Five persisted values; jitter is a magnitude with a randomly chosen sign."""
    minutes = _bounded_int(minutes, DEFAULT_INTERVAL_MINUTES, 5, 1440)
    low = _bounded_int(jitter_min, DEFAULT_ROUND_JITTER_MIN, 0, minutes-1)
    high = _bounded_int(jitter_max, DEFAULT_ROUND_JITTER_MAX, 0, minutes-1)
    g0 = _bounded_int(gap_min, DEFAULT_PAGE_GAP_MIN, 0, 120)
    g1 = _bounded_int(gap_max, DEFAULT_PAGE_GAP_MAX, 0, 120)
    return (minutes, min(low, high), max(low, high), min(g0, g1), max(g0, g1))


def random_inspection_timing(settings):
    return normalize_random_timing(
        settings.value("interval_minutes", DEFAULT_INTERVAL_MINUTES),
        settings.value("round_jitter_min_minutes", DEFAULT_ROUND_JITTER_MIN),
        settings.value("round_jitter_max_minutes", DEFAULT_ROUND_JITTER_MAX),
        settings.value("page_gap_min_seconds", DEFAULT_PAGE_GAP_MIN),
        settings.value("page_gap_max_seconds", DEFAULT_PAGE_GAP_MAX))


def save_random_timing(settings, values):
    values = normalize_random_timing(*values)
    for key, value in zip(("interval_minutes", "round_jitter_min_minutes",
                          "round_jitter_max_minutes", "page_gap_min_seconds",
                          "page_gap_max_seconds"), values):
        settings.setValue(key, value)
    # Keep legacy settings readable to older tooling; actual scheduling uses both bounds.
    settings.setValue("page_gap_seconds", int(round((values[3]+values[4])/2)))
    return values


def migrate_random_preferences(settings):
    """Never reset explicit startup consent; retain deliberately customized old page gaps."""
    marker = "migrations/random_timing_130"
    if not settings.contains("page_gap_min_seconds"):
        old = _bounded_int(settings.value("page_gap_seconds", 8), 8, 0, 120)
        bounds = (6, 9) if old == 8 else (old, old)
        settings.setValue("page_gap_min_seconds", bounds[0])
        settings.setValue("page_gap_max_seconds", bounds[1])
    if not settings.contains("silent_to_tray"):
        settings.setValue("silent_to_tray", int(is_true(settings.value("min_to_tray", 1), True)))
    save_random_timing(settings, random_inspection_timing(settings))
    settings.setValue(marker, 1)
    settings.sync()


def sample_round_minutes(values, rng=None):
    minutes, low, high, _, _ = normalize_random_timing(*values)
    rng = rng or random
    if high == 0:
        return minutes
    delta = rng.randint(low, high)
    return minutes + rng.choice((-1, 1))*delta


def plan_next_round(values, started_at, now=None, rng=None):
    """Draw once per scheduled round. Preserve the existing start-to-start cadence."""
    now = time.time() if now is None else float(now)
    minutes = sample_round_minutes(values, rng)
    start = float(started_at) if started_at is not None else now
    delay = max(30.0, start + minutes*60.0 - now)
    return minutes, now + delay, max(1000, int(round(delay*1000)))


def inspection_stamp_label(value):
    if not value:
        return "\u2014"
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.astimezone().strftime("%m/%d %H:%M")
    except (ValueError, TypeError, OverflowError, OSError):
        return "\u2014"


def latest_inspection_stamp(settings, rows):
    stored = settings.value("last_inspection_at", "")
    if inspection_stamp_label(stored) != "\u2014":
        return str(stored)
    candidates = []
    for row in rows:
        value = row.get("last_inspected_at")
        if inspection_stamp_label(value) != "\u2014":
            try:
                ts = datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
                candidates.append((ts, str(value)))
            except (ValueError, TypeError, OverflowError, OSError):
                pass
    return max(candidates)[1] if candidates else ""


def toast_position(parent_width, parent_height, width, height, position="bottom_center"):
    """Toast anchor inside the parent window. Default is bottom-center."""
    pw, ph = int(parent_width), int(parent_height)
    w, h = int(width), int(height)
    if position == "top_right":
        return (max(12, pw - w - 12), 76)
    if position == "bottom_left":
        return (12, max(12, ph - h - 26))
    if position == "bottom_right":
        return (max(12, pw - w - 12), max(12, ph - h - 26))
    return (max(12, (pw - w) // 2), max(12, ph - h - 26))


def migrate_runtime_preferences(settings):
    """One-time reset of the OLD accidental autostart flag; never overwrite later explicit consent.

    Existing custom intervals survive. Old untouched 30min/3s defaults become 240min/8s.
    Removing selector keys does not delete any stored browser files or logins.
    """
    marker = "migrations/default_browser_191"
    first = not is_true(settings.value(marker, 0))
    if first:
        settings.setValue("start_auto", 0)
        if not settings.contains("interval_minutes") or str(settings.value("interval_minutes")) == "30":
            settings.setValue("interval_minutes", DEFAULT_INTERVAL_MINUTES)
        if not settings.contains("page_gap_seconds") or str(settings.value("page_gap_seconds")) == "3":
            settings.setValue("page_gap_seconds", DEFAULT_PAGE_GAP_SECONDS)
        settings.setValue(marker, 1)
    for key in ("monitor_account", "system_chrome_profile"):
        settings.remove(key)
    if not settings.contains("start_auto"):
        settings.setValue("start_auto", 0)
    if not settings.contains("show_browser"):
        settings.setValue("show_browser", int(DEFAULT_SHOW_BROWSER))
    minutes, gap = inspection_timing(settings)
    settings.setValue("interval_minutes", minutes)
    settings.setValue("page_gap_seconds", gap)
    settings.sync()
    return first


def configure_process_identity():
    """Use one stable taskbar identity for the app; bundled EXE icon is set at build time."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except (OSError, AttributeError):
            pass


def asset_candidates(relative_path):
    """Support source, PyInstaller onedir/onefile and macOS bundles without cwd assumptions."""
    roots = [Path(__file__).resolve().parent]
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        roots.insert(0, Path(bundled))
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        roots.extend([executable.parent, executable.parent.parent / "Resources"])
    seen = set()
    for root in roots:
        candidate = root / relative_path
        if str(candidate) not in seen:
            seen.add(str(candidate))
            yield candidate



def valid_post_ts(value, now=None):
    now = time.time() if now is None else float(now)
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if value > 100_000_000_000:
        value /= 1000.0
    if not math.isfinite(value) or value < 1_075_766_400 or value > now + 90:
        return None
    return min(now, value)


def elapsed_label(ts, now=None):
    if ts is None:
        return "待获取"
    now = time.time() if now is None else float(now)
    seconds = max(0, now - float(ts))
    if seconds < 60:
        return "不足1分钟"
    if seconds < 3600:
        return f"{int(seconds // 60)}分钟"
    hours = seconds / 3600
    if hours < 100:
        return f"{hours:.1f}小时"
    return f"{int(hours)}小时"


def post_view(row, now=None, interval_seconds=DEFAULT_INTERVAL_MINUTES*60):
    """Read-only state; a stale/failed detection cannot become a new timeout alert."""
    now = time.time() if now is None else float(now)
    if not row.get("monitor_posts"):
        return dict(state="off", label="未监控", elapsed="未监控", elapsed_short="未监控", tooltip="未选择发帖时间监控", overdue=False)
    ts = valid_post_ts(row.get("last_post_ts"), now)
    checked = float(row.get("last_post_checked_ts") or 0)
    valid = row.get("post_result") == "ok" and checked > 0 and now - checked <= max(7200, interval_seconds * 2.5)
    if ts is None:
        label = "待获取" if not checked else "无法获取"
        return dict(state="unknown", label=label, elapsed=label, elapsed_short=label,
                    tooltip=row.get("post_error") or "尚未成功读取主页贴文时间", overdue=False)
    approximate = bool(row.get("post_precision_seconds", 1) > 1)
    timestamp = datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    checked_text = datetime.fromtimestamp(checked).astimezone().strftime("%m-%d %H:%M") if checked else "未核实"
    tooltip = f"贴文时间：{'约 ' if approximate else ''}{timestamp}\n检测时间：{checked_text}"
    tooltip += "\n来源：" + str(row.get("post_source") or "历史记录")
    age = max(0, now - ts)
    limit = max(1, int(row.get("post_limit_hours") or 24)) * 3600
    if not valid:
        return dict(state="unverified", label="待核实", elapsed=elapsed_label(ts, now), elapsed_short=compact_elapsed(ts, now, approximate),
                    tooltip=tooltip + "\n本次无法确认最新贴文；仅显示缓存，不据此产生新预警。\n" +
                    str(row.get("post_error") or "检测记录已过期"), overdue=False)
    state = "overdue" if age >= limit else "soon" if age >= limit * .8 else "ok"
    label = {"overdue": "发帖超时", "soon": "即将超时", "ok": "正常"}[state]
    return dict(state=state, label=label, elapsed=("约" if approximate else "") + elapsed_label(ts, now),
                elapsed_short=compact_elapsed(ts, now, approximate),
                tooltip=tooltip + f"\n超时标准：{int(limit / 3600)} 小时\n点击菜单可打开已读取的贴文。",
                overdue=state == "overdue")


def parse_post_time(raw, now=None):
    """Parse only explicit timestamps or unambiguous relative labels. No guessing m/d dates."""
    now = time.time() if now is None else float(now)
    text = html.unescape(str(raw or "")).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return None
    if re.fullmatch(r"\d{10,13}(?:\.\d+)?", text):
        ts = valid_post_ts(text, now)
        return (ts, 1) if ts is not None else None
    try:
        # Require a year in ISO values so arbitrary integers are not parsed as dates.
        if re.match(r"^\d{4}-\d\d-\d\d(?:T| )\d\d:\d\d", text):
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            ts = valid_post_ts(dt.timestamp(), now)
            return (ts, 1) if ts is not None else None
    except (ValueError, OverflowError, OSError):
        pass
    lower = text.casefold().strip(" ·")
    if lower in {"just now", "刚刚", "剛剛"}:
        return now, 60
    m = re.fullmatch(r"(\d+)\s*(秒(?:钟)?|分鐘|分钟|小時|小时|天|seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d)(?:\s*ago|前)?", lower)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        seconds = 86400 if unit in {"天", "day", "days", "d"} else 3600 if unit in {"小时", "小時","hour","hours","hr","hrs","h"} else 60 if unit in {"分钟","分鐘","minute","minutes","min","mins","m"} else 1
        ts = valid_post_ts(now - amount * seconds, now)
        return (ts, seconds) if ts is not None else None
    local = datetime.fromtimestamp(now).astimezone()
    if lower in {"昨天", "昨日", "yesterday"}:
        # Use the end of that day (lower bound on age) rather than inventing a clock time.
        dt = (local - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
        return dt.timestamp(), 86400
    text = re.sub(r"\s*(?:星期|週|周)[一二三四五六日天]\s*", " ", text)
    m = re.fullmatch(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:\s*(上午|下午)?\s*(\d{1,2}):(\d\d))?", text)
    if m:
        year, month, day = map(int, m.group(1,2,3))
        try:
            hour = int(m.group(5) or 23)
            minute = int(m.group(6) or 59)
            if m.group(4) == "下午" and hour < 12: hour += 12
            if m.group(4) == "上午" and hour == 12: hour = 0
            dt = local.replace(year=year, month=month, day=day, hour=hour, minute=minute,
                               second=0 if m.group(5) else 59, microsecond=0)
            ts = valid_post_ts(dt.timestamp(), now)
            return (ts, 60 if m.group(5) else 86400) if ts is not None else None
        except ValueError:
            return None
    cleaned = re.sub(r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+", "", text, flags=re.I)
    cleaned = re.sub(r"\s+at\s+", " ", cleaned, flags=re.I).replace("\u202f", " ")
    for fmt in ("%B %d, %Y %I:%M %p", "%b %d, %Y %I:%M %p", "%d %B %Y %H:%M",
                "%Y-%m-%d %H:%M", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            precision = 86400 if "%H" not in fmt and "%I" not in fmt else 60
            if precision == 86400:
                dt = dt.replace(hour=23, minute=59, second=59)
            ts = valid_post_ts(dt.timestamp(), now)
            if ts is not None:
                return ts, precision
        except (ValueError, OverflowError, OSError):
            pass
    return None


def choose_post_candidate(candidates, now=None):
    """Select the newest eligible timestamp, not the first (possibly pinned) post."""
    now = time.time() if now is None else float(now)
    usable = []
    for item in candidates:
        if item.get("excluded") or not item.get("authored"):
            continue
        parsed = parse_post_time(item.get("raw"), now)
        if parsed is None:
            continue
        ts, precision = parsed
        usable.append(dict(ts=ts, precision=precision, url=str(item.get("url") or ""),
                           source=str(item.get("source") or "主页贴文时间"), raw=str(item.get("raw"))))
    if not usable:
        return None
    grouped={}
    unlinked=[]
    for item in usable:
        if not item["url"]:unlinked.append(item)
        else:grouped.setdefault(item["url"],[]).append(item)
    preferred=list(unlinked)
    for items in grouped.values():
        resolution=min(x["precision"] for x in items)
        preferred.append(max((x for x in items if x["precision"]==resolution),key=lambda x:x["ts"]))
    return max(preferred,key=lambda p:p["ts"]) if preferred else None

class Store:
    def __init__(self,path=None):
        self.path=Path(path or DB_PATH)
        ensure_private_directory(self.path.parent)
        self.lock=threading.RLock();self.upgrade_backup=""
        if self.path.is_file():
            probe=sqlite3.connect(str(self.path))
            try:
                # One safety copy before removing the old history table, never a per-inspection snapshot.
                if probe.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='snapshots'").fetchone():
                    folder=ensure_private_directory(self.path.parent/"backups")
                    target=folder/("before_1_9_"+datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+uuid.uuid4().hex[:6]+".db")
                    backup=sqlite3.connect(str(target))
                    try:probe.backup(backup)
                    finally:backup.close()
                    self.upgrade_backup=str(target)
            finally:probe.close()
        self._init_db()

    @contextmanager
    def _connect(self):
        con = sqlite3.connect(str(self.path), timeout=25)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=25000")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def _columns(conn, table):
        # Table names cannot be parameterized in SQLite PRAGMA statements.
        # Keep this helper future-safe by accepting identifiers only.
        table = str(table)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise ValueError("数据库表名格式无效")
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}

    def _init_db(self):
        with self.lock,self._connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS app_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pages (
                    page_id TEXT PRIMARY KEY,page_name TEXT NOT NULL DEFAULT '',
                    avatar_path TEXT NOT NULL DEFAULT '',enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                    last_followers INTEGER,previous_followers INTEGER,last_collected_at TEXT,
                    status TEXT NOT NULL DEFAULT '待采集',approx INTEGER NOT NULL DEFAULT 0,
                    custom_name TEXT NOT NULL DEFAULT '',avatar_state TEXT NOT NULL DEFAULT '待获取'
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,page_id TEXT NOT NULL,
                    alerted_at TEXT NOT NULL,alerted_ts REAL NOT NULL,
                    current_count INTEGER NOT NULL,baseline_count INTEGER,
                    growth INTEGER NOT NULL,window_seconds INTEGER NOT NULL,
                    threshold INTEGER NOT NULL,acknowledged INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,started_at TEXT NOT NULL,finished_at TEXT,
                    total_pages INTEGER NOT NULL,success_count INTEGER NOT NULL DEFAULT 0,
                    fail_count INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'running'
                );
                CREATE TABLE IF NOT EXISTS removed_pages(page_id TEXT PRIMARY KEY,removed_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS post_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,page_id TEXT NOT NULL,
                    alerted_at TEXT NOT NULL,alerted_ts REAL NOT NULL,last_post_ts REAL NOT NULL,
                    limit_hours INTEGER NOT NULL,message TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS follower_state (
                    page_id TEXT PRIMARY KEY,latest_ts REAL NOT NULL,latest_count INTEGER NOT NULL,
                    latest_approx INTEGER NOT NULL DEFAULT 0,prior_ts REAL,prior_count INTEGER,prior_approx INTEGER,
                    baseline_date TEXT NOT NULL,baseline_ts REAL NOT NULL,baseline_count INTEGER NOT NULL,
                    baseline_approx INTEGER NOT NULL DEFAULT 0,partial INTEGER NOT NULL DEFAULT 1,
                    yesterday_date TEXT NOT NULL DEFAULT '',yesterday_delta INTEGER,
                    yesterday_partial INTEGER NOT NULL DEFAULT 1,yesterday_approx INTEGER NOT NULL DEFAULT 0
                );
            """)
            previous=self._columns(c,"pages")
            columns={"custom_name":"TEXT NOT NULL DEFAULT ''","approx":"INTEGER NOT NULL DEFAULT 0",
                "avatar_state":"TEXT NOT NULL DEFAULT '待获取'",
                "monitor_growth":"INTEGER NOT NULL DEFAULT 0","monitor_posts":"INTEGER NOT NULL DEFAULT 0",
                "post_limit_hours":"INTEGER NOT NULL DEFAULT 24","sort_order":"INTEGER NOT NULL DEFAULT 0",
                "notes":"TEXT NOT NULL DEFAULT ''","last_inspected_at":"TEXT","metadata_checked_at":"TEXT",
                "last_post_ts":"REAL","last_post_checked_ts":"REAL","post_result":"TEXT NOT NULL DEFAULT 'pending'",
                "post_error":"TEXT NOT NULL DEFAULT ''","post_url":"TEXT NOT NULL DEFAULT ''",
                "post_source":"TEXT NOT NULL DEFAULT ''","post_precision_seconds":"INTEGER NOT NULL DEFAULT 1",
                "post_alert_key":"TEXT NOT NULL DEFAULT ''","growth_error":"TEXT NOT NULL DEFAULT ''",
                "name_error":"TEXT NOT NULL DEFAULT ''",
                "diagnosis_code":"TEXT NOT NULL DEFAULT ''","diagnosis_detail":"TEXT NOT NULL DEFAULT ''"}
            for name,typ in columns.items():
                if name not in previous:c.execute(f"ALTER TABLE pages ADD COLUMN {name} {typ}")
            follower_columns=self._columns(c,"follower_state")
            for name,typ in {
                "yesterday_date":"TEXT NOT NULL DEFAULT ''",
                "yesterday_delta":"INTEGER",
                "yesterday_partial":"INTEGER NOT NULL DEFAULT 1",
                "yesterday_approx":"INTEGER NOT NULL DEFAULT 0",
            }.items():
                if name not in follower_columns:c.execute(f"ALTER TABLE follower_state ADD COLUMN {name} {typ}")
            if "monitor_growth" not in previous:c.execute("UPDATE pages SET monitor_growth=enabled")
            if "sort_order" not in previous:
                for order,row in enumerate(c.execute("SELECT page_id FROM pages ORDER BY created_at,page_id").fetchall(),1):
                    c.execute("UPDATE pages SET sort_order=? WHERE page_id=?",(order,row["page_id"]))
            self._migrate_snapshot_storage(c)
            for row in c.execute("SELECT page_id,page_name,custom_name FROM pages").fetchall():
                if not normalize_name(row["page_name"],row["page_id"]):
                    c.execute("UPDATE pages SET page_name='' WHERE page_id=?",(row["page_id"],))
                custom=row["custom_name"] or ""
                if re.fullmatch(r"(?:主页|公共主页|专页|Page)\s*[:：]?\s*[\d\W]+",custom,re.I):
                    c.execute("UPDATE pages SET custom_name='' WHERE page_id=?",(row["page_id"],))
            c.execute("CREATE INDEX IF NOT EXISTS idx_alert_page_ts ON alerts(page_id,alerted_ts)")
            c.execute("INSERT OR REPLACE INTO app_meta VALUES('schema','2.0')")


    def add_pages(self,ids,monitor_growth=True,monitor_posts=True,limit_hours=24):
        return self.import_ids(ids,"add",monitor_growth,monitor_posts,limit_hours)["added"]

    def replace_pages(self,ids):
        result=self.import_ids(ids,"replace",True,True,24)
        return result["total"]

    def list_pages(self, enabled_only=False):
        with self.lock,self._connect() as c:
            query="SELECT * FROM pages"
            if enabled_only: query+=" WHERE monitor_growth=1 OR monitor_posts=1"
            return [dict(r) for r in c.execute(query+" ORDER BY sort_order,page_id")]

    def page(self,pid):
        with self.lock,self._connect() as c:
            row=c.execute("SELECT * FROM pages WHERE page_id=?",(str(pid),)).fetchone()
            return dict(row) if row else None

    def rename_page(self,pid,name):
        name=str(name).strip()[:160]
        with self.lock,self._connect() as c:
            c.execute("UPDATE pages SET custom_name=?,updated_at=? WHERE page_id=?",(name,now_iso(),str(pid)))

    def set_enabled(self,pid,enabled):
        # Compatibility API: pausing all modules / explicitly enabling both.
        self.update_config([pid],monitor_growth=bool(enabled),monitor_posts=bool(enabled))

    def delete_page(self,pid,delete_history=False):
        self.delete_ids([pid],delete_history)

    def update_status(self, pid: str, status: str):
        with self.lock, self._connect() as c:
            c.execute("UPDATE pages SET status=?,updated_at=? WHERE page_id=?", (str(status)[:180],now_iso(),pid))

    def update_metadata(self,pid,name="",avatar_path="",name_error="",diagnosis_code="",diagnosis_detail=""):
        name=normalize_name(name,pid)
        avatar=str(avatar_path or "")
        if not avatar or not Path(avatar).is_file(): avatar=""
        with self.lock,self._connect() as c:
            if not c.execute("SELECT 1 FROM pages WHERE page_id=?",(str(pid),)).fetchone(): return False
            c.execute("""UPDATE pages SET
                page_name=CASE WHEN ?<>'' THEN ? ELSE page_name END,
                avatar_path=CASE WHEN ?<>'' THEN ? ELSE avatar_path END,
                avatar_state=CASE WHEN ?<>'' THEN '已获取' ELSE avatar_state END,
                metadata_checked_at=?,name_error=?,diagnosis_code=?,diagnosis_detail=?,updated_at=? WHERE page_id=?""",
                (name,name,avatar,avatar,avatar,now_iso(),str(name_error)[:220] if not name else "",
                 str(diagnosis_code)[:40],str(diagnosis_detail)[:220],now_iso(),str(pid)))
        return bool(avatar or name)

    def mark_avatar_failed(self,pid:str,error:str):
        with self.lock,self._connect() as c:
            c.execute("UPDATE pages SET avatar_state=?,updated_at=? WHERE page_id=?",
                      ("未识别头像："+str(error or '页面未提供可识别头像')[:120],now_iso(),pid))





    def dashboard_rows(self,window_seconds=None,interval_seconds=DEFAULT_INTERVAL_MINUTES*60):
        now=time.time()
        with self.lock,self._connect() as c:
            states={r["page_id"]:dict(r) for r in c.execute("SELECT * FROM follower_state")}
        rows=self.list_pages()
        for row in rows:
            st=states.get(row["page_id"]);has=bool(st)
            delta=st["latest_count"]-st["prior_count"] if st and st["prior_count"] is not None else None
            reliable=bool(st and not st["latest_approx"] and not st["prior_approx"] and delta is not None)
            row.update(delta=delta,reliable=reliable,has_data=has,
                stale=not st or now-st["latest_ts"]>max(7200,2.5*interval_seconds))
        return rows

    def start_run(self, run_id, total):
        with self.lock, self._connect() as c:
            c.execute("INSERT INTO runs(run_id,started_at,total_pages) VALUES(?,?,?)", (run_id,now_iso(),int(total)))

    def finish_run(self, run_id, success, fail, status):
        with self.lock, self._connect() as c:
            c.execute("UPDATE runs SET finished_at=?,success_count=?,fail_count=?,status=? WHERE run_id=?",
                      (now_iso(),int(success),int(fail),status,run_id))

    def last_run(self):
        with self.lock, self._connect() as c:
            return c.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()

    def add_alert(self, pid: str, current: int, baseline: int, growth: int, window_seconds: int, threshold: int):
        with self.lock, self._connect() as c:
            cur=c.execute("""
                INSERT INTO alerts(page_id,alerted_at,alerted_ts,current_count,baseline_count,growth,
                                   window_seconds,threshold,acknowledged)
                VALUES(?,?,?,?,?,?,?,?,0)
            """, (pid,now_iso(),time.time(),current,baseline,growth,window_seconds,threshold))
            return int(cur.lastrowid)

    def checkpoint(self):
        """Flush SQLite WAL before migrating the live data directory."""
        with self.lock:
            con = sqlite3.connect(str(self.path), timeout=25)
            try:
                con.execute("PRAGMA wal_checkpoint(FULL)")
            finally:
                con.close()

    def unack_alert_count(self):
        with self.lock, self._connect() as c:
            return c.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged=0").fetchone()[0]

    def alert_rows(self,limit=500):
        with self.lock,self._connect() as c:
            return [dict(r) for r in c.execute("""
                SELECT a.*,COALESCE(p.avatar_path,'') avatar_path,COALESCE(NULLIF(p.custom_name,''),NULLIF(p.page_name,''),a.page_id) page_name
                FROM alerts a LEFT JOIN pages p ON a.page_id=p.page_id ORDER BY a.id DESC LIMIT ?
            """,(int(limit),))]

    def acknowledge_all(self):
        with self.lock, self._connect() as c:
            c.execute("UPDATE alerts SET acknowledged=1 WHERE acknowledged=0")


    def export_csv(self,path,kind="current"):
        if Path(path).is_symlink():raise ValueError("导出路径不能是符号链接")
        if kind=="current":return self.export_manager_csv(path)
        if kind!="alerts":raise ValueError("历史快照功能已移除；只支持当前状态或通知导出")
        with open(path,"w",encoding="utf-8-sig",newline="") as f:
            writer=csv.writer(f);writer.writerow(["时间","专业ID","名称","类型","提醒","已读"])
            for row in self.combined_alerts(limit=10000):
                writer.writerow([safe_csv_cell(row.get(k,"")) for k in
                                 ("alerted_at","page_id","page_name","kind","message","acknowledged")])

    def backup(self,destination):
        destination=Path(destination)
        if destination.is_symlink():raise ValueError("备份路径不能是符号链接")
        if destination.resolve()==self.path.resolve():raise ValueError("备份路径不能和当前数据库相同")
        with self.lock,self._connect() as source:
            target=sqlite3.connect(str(destination))
            try:source.backup(target)
            finally:target.close()

    def import_ids(self,ids,mode="add",monitor_growth=True,monitor_posts=True,limit_hours=24):
        if mode not in ("add","replace"):raise ValueError("导入方式无效")
        cleaned=list(dict.fromkeys(str(x).strip() for x in ids))
        if not cleaned or any(not re.fullmatch(r"[0-9]{5,25}",pid) for pid in cleaned):
            raise ValueError("请输入至少一个有效的 5 至 25 位数字主页 ID")
        hours=int(limit_hours)
        if not 1<=hours<=8760:raise ValueError("发帖标准须为 1 至 8760 小时")
        with self.lock,self._connect() as c:
            before={r[0] for r in c.execute("SELECT page_id FROM pages")}
            new=[pid for pid in cleaned if pid not in before]
            order=int(c.execute("SELECT COALESCE(MAX(sort_order),0) FROM pages").fetchone()[0])
            for offset,pid in enumerate(new,1):
                cache=AVATAR_DIR/f"{pid}.png"
                avatar=str(cache) if cache.is_file() else ""
                c.execute("""INSERT INTO pages(page_id,page_name,avatar_path,avatar_state,created_at,updated_at,
                           enabled,monitor_growth,monitor_posts,post_limit_hours,sort_order)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (pid,"",avatar,"已获取" if avatar else "待获取",now_iso(),now_iso(),
                     int(bool(monitor_growth or monitor_posts)),int(bool(monitor_growth)),int(bool(monitor_posts)),hours,order+offset))
                c.execute("DELETE FROM removed_pages WHERE page_id=?",(pid,))
            removed=before-set(cleaned) if mode=="replace" else set()
            for pid in removed:
                c.execute("DELETE FROM pages WHERE page_id=?",(pid,))
                c.execute("DELETE FROM follower_state WHERE page_id=?",(pid,))
                c.execute("INSERT OR REPLACE INTO removed_pages VALUES(?,?)",(pid,now_iso()))
            total=c.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        return {"added":len(new),"skipped":len(cleaned)-len(new),"removed":len(removed),"total":total}


    def update_config(self,ids,**fields):
        allowed={"monitor_growth","monitor_posts","post_limit_hours","sort_order","notes","custom_name"}
        if not fields or set(fields)-allowed: raise ValueError("配置字段无效")
        prepared={}
        for key,value in fields.items():
            if key in ("monitor_growth","monitor_posts"): prepared[key]=int(bool(value))
            elif key=="post_limit_hours":
                prepared[key]=int(value)
                if not 1<=prepared[key]<=8760: raise ValueError("发帖超时标准须为 1–8760 小时")
            elif key=="sort_order":
                prepared[key]=int(value)
                if not 0<=prepared[key]<=999999: raise ValueError("排序号须为 0–999999")
            else: prepared[key]=str(value).strip()[:160 if key=="custom_name" else 500]
        with self.lock,self._connect() as c:
            for pid in dict.fromkeys(str(x) for x in ids):
                row=c.execute("SELECT * FROM pages WHERE page_id=?",(pid,)).fetchone()
                if not row: continue
                reset_post=any(k in prepared and prepared[k]!=row[k] for k in ("monitor_posts","post_limit_hours"))
                values=dict(prepared)
                values["enabled"]=int(bool(values.get("monitor_growth",row["monitor_growth"]) or values.get("monitor_posts",row["monitor_posts"])))
                values["updated_at"]=now_iso()
                if reset_post: values["post_alert_key"]=""
                c.execute("UPDATE pages SET "+",".join(k+"=?" for k in values)+" WHERE page_id=?",(*values.values(),pid))


    def delete_ids(self,ids,delete_history=False):
        unique=list(dict.fromkeys(str(x) for x in ids))
        removed=0
        with self.lock,self._connect() as c:
            for pid in unique:
                removed+=c.execute("DELETE FROM pages WHERE page_id=?",(pid,)).rowcount
                c.execute("DELETE FROM follower_state WHERE page_id=?",(pid,))
                c.execute("INSERT OR REPLACE INTO removed_pages VALUES(?,?)",(pid,now_iso()))
        return removed


    def migrate_legacy_settings(self, rules=None, data=None):
        """One-time copy of old QSettings post rules/cache. Existing missing groups stay opt-in."""
        rules=rules if isinstance(rules,list) else []
        data=data if isinstance(data,dict) else {}
        with self.lock,self._connect() as c:
            if c.execute("SELECT 1 FROM app_meta WHERE key='legacy_posts_copied'").fetchone(): return
            limits={}
            for rule in rules:
                if not isinstance(rule,dict): continue
                try: hours=max(1,min(8760,int(rule.get("hours",24))))
                except (TypeError,ValueError): hours=24
                for pid in rule.get("page_ids",[]) or []:
                    pid=str(pid);limits[pid]=min(hours,limits.get(pid,hours))
            for pid,hours in limits.items():
                c.execute("UPDATE pages SET monitor_posts=1,enabled=1,post_limit_hours=? WHERE page_id=?",(hours,pid))
            for pid,info in data.items():
                if not isinstance(info,dict): continue
                ts=valid_post_ts(info.get("last_post_ts"))
                if ts is None: continue
                try: checked=float(info.get("checked_at") or 0)
                except (ValueError,TypeError): checked=0
                c.execute("""UPDATE pages SET last_post_ts=?,last_post_checked_ts=?,post_result='legacy',
                    post_source='旧版缓存',post_error='旧记录尚未复核，请执行一次巡检' WHERE page_id=?""",
                    (ts,checked,str(pid)))
            c.execute("INSERT INTO app_meta VALUES('legacy_posts_copied',?)",(now_iso(),))
            c.execute("INSERT OR REPLACE INTO app_meta VALUES('legacy_rules_backup',?)",
                      (json.dumps(rules,ensure_ascii=False),))


    def today_change(self,pid,now=None,interval_seconds=DEFAULT_INTERVAL_MINUTES*60):
        now=time.time() if now is None else float(now)
        local=datetime.fromtimestamp(now).astimezone()
        with self.lock,self._connect() as c:
            row=c.execute("SELECT * FROM follower_state WHERE page_id=?",(pid,)).fetchone()
        if not row or row["baseline_date"]!=local.date().isoformat():
            return {"delta":None,"partial":True,"note":"今天尚无成功采集记录"}
        if row["latest_ts"]>now+1 or row["latest_ts"]<=row["baseline_ts"]:
            return {"delta":None,"partial":True,"note":"今天首次检测已建立基准；再次巡检后显示新增"}
        partial=bool(row["partial"]);approx=bool(row["latest_approx"] or row["baseline_approx"])
        note=("自今日首次检测起" if partial else "以零点附近读数为基准")
        note+="（"+datetime.fromtimestamp(row["baseline_ts"]).astimezone().strftime("%H:%M")+"）"
        if approx:note+="；来源为缩写约值"
        return {"delta":row["latest_count"]-row["baseline_count"],"partial":partial,"approx":approx,"note":note}


    def yesterday_change(self,pid,now=None):
        """Return only yesterday's rolled-up delta; no historical time series is stored."""
        now=time.time() if now is None else float(now)
        yesterday=(datetime.fromtimestamp(now).astimezone().date()-timedelta(days=1)).isoformat()
        with self.lock,self._connect() as c:
            row=c.execute("SELECT yesterday_date,yesterday_delta,yesterday_partial,yesterday_approx FROM follower_state WHERE page_id=?",(pid,)).fetchone()
        if not row or row["yesterday_date"]!=yesterday or row["yesterday_delta"] is None:
            return {"delta":None,"partial":True,"approx":False,"note":"需要跨日的成功巡检记录后显示"}
        note="昨天从首次有效基准起计算" if row["yesterday_partial"] else "昨天完整基准"
        if row["yesterday_approx"]:note+="；来源为缩写约值"
        return {"delta":int(row["yesterday_delta"]),"partial":bool(row["yesterday_partial"]),
                "approx":bool(row["yesterday_approx"]),"note":note}


    def record_posts(self,pid,result,now=None):
        """Persist success/failure separately; only fresh, confirmed results can alert."""
        now=time.time() if now is None else float(now)
        with self.lock,self._connect() as c:
            row=c.execute("SELECT * FROM pages WHERE page_id=?",(pid,)).fetchone()
            if not row or not row["monitor_posts"]: return None
            ts=valid_post_ts(result.get("last_post_ts"),now) if result.get("posts_ok") else None
            error=str(result.get("posts_error") or "未读取到可确认的主页贴文时间")[:300]
            if ts is not None and row["last_post_ts"] and ts < float(row["last_post_ts"])-120:
                ts=None;error="本次可见贴文早于历史最新记录，无法确认最新贴文"
            if ts is None:
                c.execute("""UPDATE pages SET last_post_checked_ts=?,post_result='failed',
                    post_error=?,last_inspected_at=?,updated_at=? WHERE page_id=?""",(now,error,now_iso(),now_iso(),pid))
                return None
            limit=int(row["post_limit_hours"] or 24)
            precision=max(1,int(result.get("post_precision_seconds") or 1))
            age=max(0,now-ts)
            overdue=age>=limit*3600
            # Relative timestamps can drift within one display unit, so treat them as the same episode
            # until a substantially newer post or a normal result is observed.
            previous_ts=float(row["last_post_ts"] or 0)
            same_episode=bool(row["post_alert_key"] and row["last_post_ts"] and
                abs(ts-previous_ts)<=max(precision,int(row["post_precision_seconds"] or 1),120))
            key=row["post_alert_key"] if overdue and same_episode else ""
            new_alert=None
            if overdue and not key:
                key=f"{int(ts)}:{limit}:{uuid.uuid4().hex[:8]}"
                message=f"最近贴文 {_age_label(ts,now)} 前，标准 {limit} 小时"
                cur=c.execute("""INSERT INTO post_alerts(page_id,alerted_at,alerted_ts,last_post_ts,limit_hours,message)
                    VALUES(?,?,?,?,?,?)""",(pid,datetime.fromtimestamp(now,timezone.utc).isoformat(),now,ts,limit,message))
                new_alert={"id":cur.lastrowid,"page_id":pid,"name":display_name(dict(row)),"avatar_path":row["avatar_path"] or "","message":message,"kind":"post","last_post_ts":ts,"limit_hours":limit}
            c.execute("""UPDATE pages SET last_post_ts=?,last_post_checked_ts=?,post_result='ok',post_error='',
                post_source=?,post_url=?,post_precision_seconds=?,post_alert_key=?,last_inspected_at=?,updated_at=?
                WHERE page_id=?""",(ts,now,str(result.get("post_source") or "主页可见贴文")[:180],
                str(result.get("post_url") or "")[:1000],precision,key,now_iso(),now_iso(),pid))
            return new_alert


    def apply_collection(self,result,settings=None,purpose="monitor"):
        """Independent persistence of metadata, followers, and posting results."""
        opts=settings or {}
        pid=str(result.get("page_id") or "")
        row=self.page(pid)
        if row is None: return {"ignored":True,"success":False,"alerts":[]}
        name=normalize_name(result.get("page_name"),pid)
        self.update_metadata(pid,name,result.get("avatar_path") or "",result.get("name_error") or "",
                             result.get("diagnosis_code") or "",result.get("diagnosis_detail") or "")
        if purpose=="metadata":
            return {"ignored":False,"success":bool(name or result.get("avatar_fresh")),
                    "alerts":[],"error":result.get("name_error") or result.get("error") or ""}
        notices=[];successes=[];errors=[]
        if row["monitor_growth"]:
            ok=bool(result.get("growth_ok") and result.get("followers_count") is not None)
            if ok:
                try:
                    previous=self.record_followers(result,int(opts.get("interval_minutes",DEFAULT_INTERVAL_MINUTES))*60)
                    value=int(result["followers_count"])
                    interval=int(opts.get("interval_minutes",DEFAULT_INTERVAL_MINUTES))*60
                    threshold=int(opts.get("alert_threshold",500))
                    ts=float(result.get("collected_ts") or time.time())
                    if is_true(opts.get("alert_enabled"),True) and should_alert(value,previous,ts,bool(result.get("approx")),interval,threshold):
                        diff=value-previous["count"]
                        alert_id=self.add_alert(pid,value,previous["count"],diff,interval,threshold)
                        notices.append({"id":alert_id,"kind":"growth","page_id":pid,"name":name or display_name(row),
                                        "avatar_path":result.get("avatar_path") or row.get("avatar_path") or "",
                                        "message":f"粉丝增长 {format_delta(diff)}",
                                        "growth":diff,"window_seconds":interval,"threshold":threshold})
                except Exception as exc:
                    ok=False;errors.append(str(exc)[:220])
            else:
                errors.append(str(result.get("growth_error") or result.get("error") or "粉丝数无法读取"))
            with self.lock,self._connect() as c:
                c.execute("UPDATE pages SET growth_error=? WHERE page_id=?",
                          ("" if ok else errors[-1],pid))
            successes.append(ok)
        if row["monitor_posts"]:
            post_alert=self.record_posts(pid,result)
            if post_alert: notices.append(post_alert)
            posts_row=self.page(pid)
            ok=bool(result.get("posts_ok") and posts_row and posts_row["post_result"]=="ok")
            successes.append(ok)
            if not ok: errors.append(str(posts_row.get("post_error") if posts_row else "主页已删除"))
        with self.lock,self._connect() as c:
            c.execute("UPDATE pages SET last_inspected_at=?,status=?,updated_at=? WHERE page_id=?",
                      (now_iso(),"正常" if successes and all(successes) else "部分成功" if any(successes) else "采集失败",now_iso(),pid))
        return {"ignored":False,"success":bool(successes and all(successes)),"alerts":notices,"error":"；".join(errors)}


    def combined_alerts(self,limit=100,unread_only=False):
        suffix=" AND a.acknowledged=0" if unread_only else ""
        with self.lock,self._connect() as c:
            growth=[dict(r) for r in c.execute("""
                SELECT a.id,a.page_id,a.alerted_at,a.alerted_ts,a.acknowledged,a.growth,COALESCE(p.avatar_path,'') avatar_path,
                COALESCE(NULLIF(p.custom_name,''),NULLIF(p.page_name,''),a.page_id) page_name
                FROM alerts a LEFT JOIN pages p ON a.page_id=p.page_id WHERE 1=1
            """+suffix+" ORDER BY a.alerted_ts DESC LIMIT ?",(limit,))]
            posts=[dict(r) for r in c.execute("""
                SELECT a.*,COALESCE(p.avatar_path,'') avatar_path,COALESCE(NULLIF(p.custom_name,''),NULLIF(p.page_name,''),a.page_id) page_name
                FROM post_alerts a LEFT JOIN pages p ON a.page_id=p.page_id WHERE 1=1
            """+suffix+" ORDER BY a.alerted_ts DESC LIMIT ?",(limit,))]
        for r in growth+posts:
            if not r.get("avatar_path"):
                cached=AVATAR_DIR/(str(r["page_id"])+".png")
                if cached.is_file():r["avatar_path"]=str(cached)
        for r in growth:r.update(kind="growth",message="粉丝增长 "+format_delta(r["growth"]))
        for r in posts:
            r["kind"]="post"
            _ts=r.get("last_post_ts");_lim=r.get("limit_hours")
            if _ts is not None and _lim is not None:
                try:_ref=float(r.get("alerted_ts")) if r.get("alerted_ts") is not None else None
                except (TypeError,ValueError):_ref=None
                r["message"]=f"最近贴文 {_age_label(_ts,_ref)} 前，标准 {_lim} 小时"
            elif r.get("message"):
                r["message"]=_normalize_legacy_hours(r["message"])
        return sorted(growth+posts,key=lambda x:x["alerted_ts"],reverse=True)[:limit]


    def unread_totals(self):
        with self.lock,self._connect() as c:
            g=c.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged=0").fetchone()[0]
            p=c.execute("SELECT COUNT(*) FROM post_alerts WHERE acknowledged=0").fetchone()[0]
            return int(g),int(p)


    def acknowledge_notifications(self):
        with self.lock,self._connect() as c:
            c.execute("UPDATE alerts SET acknowledged=1")
            c.execute("UPDATE post_alerts SET acknowledged=1")

    def clear_acknowledged_alerts(self):
        with self.lock,self._connect() as c:
            c.execute("DELETE FROM alerts WHERE acknowledged=1")
            c.execute("DELETE FROM post_alerts WHERE acknowledged=1")

    def acknowledge_notification(self,kind,alert_id):
        table="post_alerts" if str(kind)=="post" else "alerts" if str(kind)=="growth" else ""
        try:alert_id=int(alert_id)
        except (TypeError,ValueError):return False
        if not table or alert_id<=0:return False
        with self.lock,self._connect() as c:
            return bool(c.execute(f"UPDATE {table} SET acknowledged=1 WHERE id=? AND acknowledged=0",(alert_id,)).rowcount)


    def export_manager_csv(self,path):
        cols=["page_id","page_name","custom_name","monitor_growth","monitor_posts","post_limit_hours",
              "sort_order","notes","last_followers","last_post_ts","post_result","last_inspected_at"]
        with open(path,"w",encoding="utf-8-sig",newline="") as f:
            w=csv.writer(f)
            w.writerow(["专业ID","真实名称","自定义名称","粉丝监控","发帖监控","发帖超时小时","排序号",
                        "备注","当前粉丝","最近贴文时间戳","发帖读取状态","最后巡检"])
            for row in self.list_pages():
                w.writerow([safe_csv_cell(row.get(col,"")) for col in cols])


    def _migrate_snapshot_storage(self,c):
        """Collapse old samples into ONE bounded state row per managed page, then remove history."""
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='snapshots'").fetchone():return
        cols=self._columns(c,"snapshots")
        for name,typ in {"collected_ts":"REAL","is_approx":"INTEGER NOT NULL DEFAULT 0",
                         "fan_count":"INTEGER","followers_count":"INTEGER"}.items():
            if name not in cols:c.execute(f"ALTER TABLE snapshots ADD COLUMN {name} {typ}")
        for row in c.execute("SELECT id,collected_at FROM snapshots WHERE collected_ts IS NULL").fetchall():
            try:ts=datetime.fromisoformat(row["collected_at"].replace("Z","+00:00")).timestamp()
            except (ValueError,TypeError,AttributeError):continue
            c.execute("UPDATE snapshots SET collected_ts=? WHERE id=?",(ts,row["id"]))
        for page in c.execute("SELECT page_id FROM pages").fetchall():
            pid=page["page_id"]
            recent=c.execute("""SELECT collected_ts ts,COALESCE(followers_count,fan_count) count,is_approx approx
                FROM snapshots WHERE page_id=? AND collected_ts>0 AND collected_ts<=?
                AND COALESCE(followers_count,fan_count) IS NOT NULL
                ORDER BY collected_ts DESC,id DESC LIMIT 2""",(pid,time.time()+60)).fetchall()
            if not recent:continue
            latest=recent[0];prior=recent[1] if len(recent)>1 else None
            local=datetime.fromtimestamp(latest["ts"]).astimezone()
            midnight=local.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
            base=c.execute("""SELECT collected_ts ts,COALESCE(followers_count,fan_count) count,is_approx approx
                FROM snapshots WHERE page_id=? AND collected_ts<=? AND COALESCE(followers_count,fan_count) IS NOT NULL
                ORDER BY collected_ts DESC,id DESC LIMIT 1""",(pid,midnight)).fetchone()
            partial=not base or midnight-base["ts"]>4500
            if partial:
                base=c.execute("""SELECT collected_ts ts,COALESCE(followers_count,fan_count) count,is_approx approx
                    FROM snapshots WHERE page_id=? AND collected_ts>=? AND collected_ts<=?
                    AND COALESCE(followers_count,fan_count) IS NOT NULL ORDER BY collected_ts,id LIMIT 1""",
                    (pid,midnight,latest["ts"])).fetchone()
            base=base or latest
            c.execute("""INSERT OR REPLACE INTO follower_state(
                page_id,latest_ts,latest_count,latest_approx,prior_ts,prior_count,prior_approx,
                baseline_date,baseline_ts,baseline_count,baseline_approx,partial)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid,latest["ts"],latest["count"],latest["approx"],prior["ts"] if prior else None,
                 prior["count"] if prior else None,prior["approx"] if prior else None,
                 local.date().isoformat(),base["ts"],base["count"],base["approx"],int(partial)))
            c.execute("UPDATE pages SET last_followers=?,previous_followers=?,last_collected_at=?,approx=? WHERE page_id=?",
                (latest["count"],prior["count"] if prior else None,
                 datetime.fromtimestamp(latest["ts"],timezone.utc).isoformat(),latest["approx"],pid))
        c.execute("DROP TABLE snapshots")
        c.execute("INSERT OR REPLACE INTO app_meta VALUES('history_removed','1')")


    def record_followers(self,result,interval_seconds=DEFAULT_INTERVAL_MINUTES*60):
        """Keep only the current reading, previous reading and today's baseline; no history series."""
        pid=str(result["page_id"]);count=int(result["followers_count"])
        ts=float(result.get("collected_ts") or time.time())
        if not 0<=count<=10_000_000_000 or not math.isfinite(ts) or ts<=0 or ts>time.time()+120:
            raise ValueError("粉丝数或采集时间无效")
        approx=int(bool(result.get("approx")));local=datetime.fromtimestamp(ts).astimezone()
        day=local.date().isoformat();midnight=local.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        stamp=datetime.fromtimestamp(ts,timezone.utc).isoformat(timespec="seconds")
        with self.lock,self._connect() as c:
            if not c.execute("SELECT 1 FROM pages WHERE page_id=?",(pid,)).fetchone():return None
            old=c.execute("SELECT * FROM follower_state WHERE page_id=?",(pid,)).fetchone()
            if old and ts<=old["latest_ts"]:return None
            prior={"ts":old["latest_ts"],"count":old["latest_count"],"approx":bool(old["latest_approx"])} if old else None
            yesterday=(local.date()-timedelta(days=1)).isoformat()
            y_date='';y_delta=None;y_partial=1;y_approx=0
            if old:
                if old["baseline_date"]==day:
                    y_date=str(old["yesterday_date"] or '')
                    y_delta=old["yesterday_delta"]
                    y_partial=int(old["yesterday_partial"] or 0)
                    y_approx=int(old["yesterday_approx"] or 0)
                elif old["baseline_date"]==yesterday:
                    y_date=yesterday
                    y_delta=int(old["latest_count"])-int(old["baseline_count"])
                    y_partial=int(old["partial"] or 0)
                    y_approx=int(bool(old["latest_approx"] or old["baseline_approx"]))
                elif str(old["yesterday_date"] or '')==yesterday:
                    y_date=yesterday;y_delta=old["yesterday_delta"]
                    y_partial=int(old["yesterday_partial"] or 0);y_approx=int(old["yesterday_approx"] or 0)
            if old and old["baseline_date"]==day and old["latest_ts"]>=midnight:
                base_ts,base,base_approx,partial=(old["baseline_ts"],old["baseline_count"],old["baseline_approx"],old["partial"])
            elif old and 0<=midnight-old["latest_ts"]<=max(3600,2.5*interval_seconds):
                base_ts,base,base_approx,partial=old["latest_ts"],old["latest_count"],old["latest_approx"],0
            else:
                base_ts,base,base_approx,partial=ts,count,approx,1
            c.execute("""INSERT OR REPLACE INTO follower_state(
                page_id,latest_ts,latest_count,latest_approx,prior_ts,prior_count,prior_approx,
                baseline_date,baseline_ts,baseline_count,baseline_approx,partial,
                yesterday_date,yesterday_delta,yesterday_partial,yesterday_approx)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid,ts,count,approx,prior["ts"] if prior else None,prior["count"] if prior else None,
                 int(prior["approx"]) if prior else None,day,base_ts,base,base_approx,partial,
                 y_date,y_delta,y_partial,y_approx))
            name=normalize_name(result.get("page_name"),pid)
            c.execute("""UPDATE pages SET last_followers=?,previous_followers=?,last_collected_at=?,approx=?,
                page_name=CASE WHEN ?<>'' THEN ? ELSE page_name END,status='正常',updated_at=? WHERE page_id=?""",
                (count,prior["count"] if prior else None,stamp,approx,name,name,now_iso(),pid))
        return prior


# ========== Browser collector (self-contained) ==========
import io


def prepare_data_migration(store,target):
    """Copy and verify before switching paths. Never deletes the source."""
    old=store.path.parent.resolve();target=Path(target).expanduser().resolve()
    if target==old or target in old.parents or old in target.parents:
        raise ValueError("新目录必须与原目录独立，不能互为上级或子目录")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError("目标目录必须为空，以免覆盖其他文件")
    ensure_private_directory(target)
    skips={store.path.name,store.path.name+"-wal",store.path.name+"-shm",
           "SingletonLock","SingletonCookie","SingletonSocket","DevToolsActivePort","lockfile"}
    manifest=[]
    with store.lock:
        store.checkpoint()
        for source in old.rglob("*"):
            if source.name in skips:continue
            if source.is_symlink():raise ValueError("源目录含未知符号链接，请检查后再迁移："+str(source))
            relative=source.relative_to(old);dest=target/relative
            if source.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
            if source.is_file():
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,dest)
                def digest(path):
                    h=hashlib.sha256()
                    with path.open("rb") as f:
                        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
                    return h.digest()
                if source.stat().st_size!=dest.stat().st_size or digest(source)!=digest(dest):
                    raise RuntimeError("复制校验失败："+str(relative))
                manifest.append(str(relative))
        new_db=target/store.path.name
        store.backup(new_db)
        c=sqlite3.connect(str(new_db))
        try:
            check=c.execute("PRAGMA quick_check").fetchone()
            if not check or check[0]!="ok":raise RuntimeError("目标数据库完整性检查失败")
            for pid,avatar in c.execute("SELECT page_id,avatar_path FROM pages").fetchall():
                if not avatar:continue
                try:relative=Path(avatar).resolve().relative_to(old)
                except ValueError:continue
                c.execute("UPDATE pages SET avatar_path=? WHERE page_id=?",(str(target/relative),pid))
            c.commit()
        finally:c.close()
    pending=target/"updates/pending.json"
    if pending.is_file():
        try:
            info=json.loads(pending.read_text("utf-8"))
            if info.get("path"):
                relative=Path(info["path"]).resolve().relative_to(old)
                info["path"]=str(target/relative);save_json_atomic(pending,info)
        except (ValueError,TypeError,OSError):pass
    # Refuse automatic recursive deletion if an old directory contains unrelated top-level files.
    known={"avatars","browser_profile","monitor_accounts","public_avatar_profile","backups","error.log",
           "settings.ini","connector_registry.json","updates","location.json",".fbpm-owned","fb_growth_radar_v1.db","fb_growth_radar_v1.db-wal","fb_growth_radar_v1.db-shm"}
    unrelated=[p.name for p in old.iterdir() if p.name not in known]
    return {"old":old,"target":target,"database":new_db,"can_delete":not unrelated,"unrelated":unrelated,"files":len(manifest)}


def log_exception(text):
    try:
        ensure_private_directory(DATA_DIR)
        log_path = DATA_DIR/"error.log"
        # Keep the diagnostic log bounded: retain only the newest ~256KB
        # when it grows past 512KB instead of appending forever.
        if log_path.is_file() and log_path.stat().st_size > 512 * 1024:
            try:
                with log_path.open("rb") as src:
                    src.seek(max(0, log_path.stat().st_size - 256 * 1024))
                    tail = src.read()
                log_path.write_bytes(tail)
            except OSError:
                pass
        with log_path.open("a",encoding="utf-8") as f:
            f.write("\n"+now_iso()+"\n"+str(text)+"\n")
    except OSError:pass


class BrowserCollector:
    def __init__(self, profile_dir: Path | None = None, show_browser=DEFAULT_SHOW_BROWSER):
        self.profile_dir = str(ensure_private_directory(Path(profile_dir) if profile_dir is not None else monitor_profile_dir()))
        self.show_browser = is_true(show_browser, DEFAULT_SHOW_BROWSER)
        self._pw = None
        self.context = None
        self.channel = None
        self.home_page = None

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("未安装浏览器控制依赖。请运行：python -m pip install playwright") from exc
        self._pw = sync_playwright().start()
        try:
            # Explicitly use installed Chrome. Do not silently switch to Chromium/Edge.
            self.context = self._pw.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                channel="chrome",
                chromium_sandbox=True,
                headless=not self.show_browser,
                viewport={"width": 1440, "height": 960},
                locale="zh-CN",
                args=["--disable-notifications", "--no-first-run", "--no-default-browser-check"],
            )
            self.channel = "chrome"
            self.ensure_home()
            return self
        except Exception as exc:
            self.__exit__(None, None, None)
            detail = str(exc).strip().splitlines()[0][:260]
            raise RuntimeError(
                "已尝试启动本机谷歌浏览器，但无法正常打开脸书主页。\n"
                "请检查：谷歌浏览器是否安装、网络是否能访问 facebook.com、"
                "以及默认专用浏览器是否仍被其他窗口占用。\n"
                + ("后台模式启动失败，程序没有改为弹出前台浏览器。\n" if not self.show_browser else "")
                + f"具体原因：{detail}"
            ) from exc

    def __exit__(self, typ, exc, tb):
        try:
            if self.context is not None:
                self.context.close()
        except Exception:
            pass
        self.context = None
        self.home_page = None
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._pw = None

    def ensure_home(self):
        """Replace Playwright's initial about:blank with the real Facebook page."""
        if not self.context:
            raise RuntimeError("谷歌浏览器尚未启动")
        page = next((p for p in self.context.pages if not p.is_closed()), None)
        if page is None:
            page = self.context.new_page()
        for p in list(self.context.pages):
            if p is not page and not p.is_closed() and p.url == 'about:blank':
                try:
                    p.close()
                except Exception:
                    pass
        self.home_page = page
        try:
            page.goto(FACEBOOK_HOME, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        except Exception as exc:
            if not (page.url or '').startswith(('https://www.facebook.com/', 'https://facebook.com/')):
                raise RuntimeError(
                    "无法进入 facebook.com，浏览器仍停在空白页。请检查网络、代理或账号环境。"
                ) from exc
        if (page.url or '').startswith('about:blank'):
            raise RuntimeError("浏览器仍停在 about:blank，没有成功打开 Facebook。")
        if self.show_browser:
            page.bring_to_front()
        return page

    def login_interactive(self):
        """Only an explicit login action may request a visible browser."""
        if not self.show_browser:
            raise RuntimeError("后台巡检不会弹出登录窗口；请从设置打开默认专用浏览器登录。")
        if self.home_page is None or self.home_page.is_closed():
            self.ensure_home()
        self.home_page.bring_to_front()
        return self.home_page

    @staticmethod
    def _is_facebook_image_url(url: str) -> bool:
        try:
            u = urlsplit(url)
            host = (u.hostname or "").lower()
            return u.scheme == "https" and (
                host in ("facebook.com", "fbcdn.net", "fbsbx.com")
                or host.endswith(".facebook.com")
                or host.endswith(".fbcdn.net")
                or host.endswith(".fbsbx.com")
            )
        except ValueError:
            return False


    def _extract_name(self,page,body_text="",page_id="",matched_text=""):
        return normalize_name(extract_page_name(page,body_text,page_id,matched_text),page_id)

    def _avatar_candidates(self,page,name:str) -> list[dict]:
        """Discover avatar images from current FB layouts, not just alt text.

        Inspect visible HTML images, SVG image nodes and CSS background images;
        rank profile-like square images near the page title above global nav icons
        and fall back to Open Graph metadata only after visible candidates.
        """
        script=r"""(pageName) => {
          const title=document.querySelector('h1');
          const titleRect=title ? title.getBoundingClientRect() : null;
          const pageTitle=(pageName||'').trim().toLowerCase();
          const hits=[];
          const words=/profile picture|profile photo|avatar|picture of|page picture|page profile|头像|大头贴|大頭貼|头像照片|照片墙|主页照片/i;
          const cover=/cover photo|cover image|封面|封面照片|相册|帖子图片/i;
          function push(el,sel,i) {
            let r;try{r=el.getBoundingClientRect()}catch{return;}
            if(r.width<30||r.height<30||r.top>1800||r.bottom<0)return;
            const ratio=Math.max(r.width,r.height)/Math.max(1,Math.min(r.width,r.height));
            if(ratio>2.2)return;
            const tag=el.tagName.toLowerCase();
            const alt=String(el.getAttribute('alt')||el.getAttribute('aria-label')||'');
            let src=el.currentSrc||el.getAttribute('src')||el.getAttribute('href')||el.getAttribute('xlink:href')||'';
            if(!src) {
              const bg=getComputedStyle(el).backgroundImage||'';
              const m=bg.match(/url\(["']?(.*?)["']?\)/);
              if(m)src=m[1];
            }
            let score=0;
            if(words.test(alt))score+=145;
            if(cover.test(alt))score-=95;
            if(pageTitle&&alt.toLowerCase().includes(pageTitle))score+=42;
            if(ratio<=1.22)score+=35;
            if(r.width>=45&&r.width<=350&&r.height>=45&&r.height<=350)score+=25;
            if(r.top>=0&&r.top<730)score+=20;
            if(titleRect){
              let dist=Math.abs((r.top+r.height/2)-(titleRect.top+titleRect.height/2));
              if(dist<160)score+=45;
              else if(dist<310)score+=21;
            }
            const ancestor=el.closest('a[href]');
            if(ancestor&&/\/profile\.php|\/pages\/|facebook\.com\//i.test(ancestor.href||''))score+=15;
            if(el.closest('nav,[role=navigation],[role=banner],[data-pagelet=RightRail]'))score-=120;
            if(el.closest('article'))score-=85;
            if(r.width<48||r.height<48)score-=55;
            if(src.startsWith('data:image/'))score+=5;
            if(score>=25)hits.push({url:src,selector:sel,index:i,score,alt,width:r.width,height:r.height});
          }
          [...document.querySelectorAll('img')].forEach((el,i)=>push(el,'img',i));
          [...document.querySelectorAll('svg image')].forEach((el,i)=>push(el,'svg image',i));
          [...document.querySelectorAll('[role="img"]')].forEach((el,i)=>push(el,'[role="img"]',i));
          return hits.sort((a,b)=>b.score-a.score).slice(0,24);
        }"""
        try:
            candidates=list(page.evaluate(script,name) or [])
        except Exception:
            candidates=[]
        # Old-style selectors remain useful if Facebook changes the page header.
        if not candidates:
            selectors=("img[alt*='profile picture' i]", "img[alt*='profile photo' i]",
                       "img[alt*='头像']", "img[alt*='大头贴']")
            for sel in selectors:
                try:
                    for item in page.locator(sel).all()[:3]:
                        url=item.get_attribute('src',timeout=800)
                        if url:
                            candidates.append({"url":url,"selector":"","index":-1,"score":70})
                except Exception:
                    pass
        for selector in ("meta[property='og:image']","meta[name='twitter:image']"):
            try:
                url=page.locator(selector).first.get_attribute('content',timeout=1100)
                if url:
                    candidates.append({"url":url,"selector":"","index":-1,"score":0})
            except Exception:
                continue
        # Do not mistake the site's top-nav or large cover for the page avatar.
        candidates.sort(key=lambda item:float(item.get('score') or 0),reverse=True)
        seen=set();dedup=[]
        for candidate in candidates:
            key=(candidate.get('url',''),candidate.get('selector',''),candidate.get('index',-1))
            if key not in seen:
                seen.add(key);dedup.append(candidate)
        return dedup[:25]

    def _save_avatar_bytes(self,pid:str,body:bytes) -> str:
        from PIL import Image,ImageOps
        if not isinstance(body,(bytes,bytearray)) or not 150<=len(body)<=6_000_000:
            raise ValueError('头像图片数据不完整')
        # Only decode common raster formats needed for avatars. Excluding exotic
        # formats avoids activating unrelated optional Pillow decoders on web data.
        with Image.open(io.BytesIO(body),formats=("PNG","JPEG","WEBP","GIF")) as im:
            # Validate dimensions before full decode to avoid allocating a
            # decompression-bomb-sized image from a small compressed response.
            if min(im.width,im.height)<32 or im.width*im.height>24_000_000:
                raise ValueError('头像尺寸不正确')
            # The app uses the first frame only, matching the previous behavior;
            # it never iterates over or decodes later animation frames.
            im.load()
            ratio=max(im.width,im.height)/min(im.width,im.height)
            if ratio>1.55:
                raise ValueError('图片更像横幅或封面，不作为头像保存')
            avatar=ImageOps.fit(im.convert('RGB'),(192,192),method=Image.Resampling.LANCZOS)
        ensure_private_directory(AVATAR_DIR)
        target=AVATAR_DIR / f'{pid}.png'
        output=io.BytesIO()
        avatar.save(output,format='PNG',optimize=True)
        _atomic_write_bytes(target,output.getvalue(),mode=0o600,private_parent=True)
        return str(target)

    def _cache_avatar(self,pid:str,candidates:list[dict],previous:str,page=None,force=False) -> str:
        old=Path(previous) if previous else None
        old_valid=bool(old and old.is_file() and old.stat().st_size>200)
        if old_valid and not force and time.time()-old.stat().st_mtime<5*86400:
            return str(old)
        try:
            from PIL import Image
        except ImportError:
            return str(old) if old_valid else ''
        deadline=time.monotonic()+10.0
        for candidate in candidates[:9]:
            remaining=deadline-time.monotonic()
            if remaining<0.25:
                break
            url=str(candidate.get('url') or '').strip()
            if url and url.startswith('//'):
                url='https:'+url
            if url and self._is_facebook_image_url(url) and not any(x in url.lower() for x in ('emoji.php','static.xx.fbcdn.net/rsrc.php')):
                try:
                    resp=self.context.request.get(url,timeout=min(3800,max(350,int(remaining*1000))))
                    if resp.ok and (resp.headers.get('content-type') or '').lower().startswith('image/'):
                        try:
                            return self._save_avatar_bytes(pid,resp.body())
                        except (OSError,ValueError):
                            pass
                except Exception:
                    pass
            # A browser-rendered image can be visible even if its signed URL
            # cannot be downloaded via the network request context. Screenshot
            # that *element*, not the whole page or cover image.
            selector=str(candidate.get('selector') or '')
            index=candidate.get('index',-1)
            if not page or not selector or not isinstance(index,int) or index<0:
                continue
            if candidate.get('score',0)<48:
                continue
            try:
                locator=page.locator(selector).nth(index)
                remaining=deadline-time.monotonic()
                if remaining<0.25:break
                image_bytes=locator.screenshot(timeout=min(3800,max(350,int(remaining*1000))))
                return self._save_avatar_bytes(pid,image_bytes)
            except Exception:
                continue
        return str(old) if old_valid else ''

    def fetch_page(self,page_row,purpose="monitor"):
        row=dict(page_row);pid=str(row["page_id"])
        if not re.fullmatch(r"[0-9]{5,25}",pid):raise ValueError("主页 ID 格式错误")
        grow=purpose=="monitor" and bool(row.get("monitor_growth",1))
        posts=purpose=="monitor" and bool(row.get("monitor_posts",0))
        info={"page_id":pid,"page_name":"","avatar_path":"","avatar_fresh":False,
              "growth_ok":False,"posts_ok":False,"metadata_ok":False,
              "collected_at":now_iso(),"collected_ts":time.time(),
              "growth_error":"","posts_error":"","name_error":"",
              "diagnosis_code":"","diagnosis_detail":""}
        page=self.context.new_page()
        try:
            try:page.goto(f"https://www.facebook.com/{pid}",wait_until="domcontentloaded",timeout=PAGE_LOAD_TIMEOUT_MS)
            except Exception:
                if not (page.url or "").startswith(("https://www.facebook.com/","https://facebook.com/")):raise
            if any(x in (page.url or "") for x in ("/login","/checkpoint","/recover","/two_factor")):
                raise RuntimeError("请先在设置中登录当前监控账号，完成 Facebook 安全验证")
            # Same initial stabilization and Escape handling as the reference.
            page.wait_for_timeout(2600)
            try:
                page.keyboard.press("Escape");page.wait_for_timeout(250);page.keyboard.press("Escape")
            except Exception:pass
            body="";parsed=None
            for delay in (0,650,1000):
                if delay:page.wait_for_timeout(delay)
                try:
                    body=page.locator("body").inner_text(timeout=8000)
                    parsed=extract_followers_from_text(body)
                    break
                except Exception:
                    if not grow:break
            matched=parsed[2] if parsed else ""
            _unavail,_hint=detect_unavailable_page(body)
            if _unavail:
                info.update(diagnosis_code='page_unavailable',diagnosis_detail=PAGE_UNAVAILABLE_DETAIL,
                            name_error=PAGE_UNAVAILABLE_DETAIL,
                            growth_error=PAGE_UNAVAILABLE_DETAIL if grow else '',
                            posts_error=PAGE_UNAVAILABLE_DETAIL if posts else '',
                            error=PAGE_UNAVAILABLE_DETAIL,
                            collected_at=now_iso(),collected_ts=time.time())
                return info
            # Identity is extracted AFTER follower text so the proximity fallback works.
            name=self._extract_name(page,body,pid,matched)
            if not name:name=self._fallback_name(pid,matched)
            name=normalize_name(name,pid);info["page_name"]=name
            if not name:
                info["name_error"]="已按参考程序尝试标题、头像名称、主页链接、元数据及备用地址；暂未读取到可信名称"
            stamp=time.time()
            info["avatar_path"]=self._cache_avatar(pid,self._avatar_candidates(page,name),
                row.get("avatar_path") or "",page=page,force=purpose=="metadata")
            if info["avatar_path"]:
                try:info["avatar_fresh"]=Path(info["avatar_path"]).stat().st_mtime>=stamp-.2
                except OSError:pass
            info["metadata_ok"]=bool(name or info["avatar_fresh"])
            if grow:
                if parsed is None:info["growth_error"]="未读取到可确认的粉丝数，本次不更新粉丝基准"
                else:
                    count,approx,matched=parsed
                    info.update(growth_ok=True,followers_count=count,approx=approx,matched_text=matched)
            if posts:
                post=self._extract_post(page,pid,name or normalize_name(row.get("page_name"),pid))
                if post:
                    info.update(posts_ok=True,last_post_ts=post["ts"],post_precision_seconds=post["precision"],
                                post_source=post["source"],post_url=post["url"])
                else:info["posts_error"]="未读取到可确认的主页自发贴文时间"
            info["collected_at"]=now_iso();info["collected_ts"]=time.time()
            return info
        except Exception as exc:
            reason=str(exc)[:300];info["error"]=reason
            if grow and not info["growth_ok"]:info["growth_error"]=reason
            if posts and not info["posts_ok"]:info["posts_error"]=reason
            if not info["page_name"]:info["name_error"]=reason
            return info
        finally:
            try:page.close()
            except Exception:pass

    def _fallback_name(self,pid,matched_text=""):
        """Same-session alternate routes used by the supplied reference program."""
        tab=self.context.new_page()
        try:
            for url in (f"https://www.facebook.com/profile.php?id={pid}",f"https://www.facebook.com/{pid}/about"):
                try:
                    tab.goto(url,wait_until="domcontentloaded",timeout=PAGE_LOAD_TIMEOUT_MS)
                    tab.wait_for_timeout(1800)
                    if any(x in (tab.url or "") for x in ("/login","/checkpoint","/recover")):continue
                    try:tab.keyboard.press("Escape")
                    except Exception:pass
                    body=tab.locator("body").inner_text(timeout=8000)
                    name=self._extract_name(tab,body,pid,matched_text)
                    if name:return name
                except Exception:continue
            return ""
        finally:
            try:tab.close()
            except Exception:pass

    def _post_candidates(self, page, pid, name):
        """Read only timestamp nodes attached to page-authored feed posts, not comments."""
        script = r"""
        ({pid, name}) => {
          const norm=s=>(s||'').trim().replace(/\s+/g,' ').toLowerCase();
          const hostOk=h=>h==='facebook.com'||h.endsWith('.facebook.com');
          const parts=u=>{try{const a=new URL(u,location.href);if(!hostOk(a.hostname))return '';
            const id=a.searchParams.get('id');if(id)return id;
            return a.pathname.replace(/^\/|\/$/g,'').split('/')[0];}catch(e){return '';}};
          const alias=new Set([pid,parts(location.href)].filter(Boolean));
          const own=a=>alias.has(parts(a.href)) || (name && norm(a.textContent)===norm(name));
          let articles=[...document.querySelectorAll('main [role="article"], [role="main"] [role="article"]')];
          if(!articles.length)articles=[...document.querySelectorAll('[data-pagelet^="FeedUnit_"], .userContentWrapper')];
          articles=articles.filter(a=>!a.parentElement?.closest('[role="article"]'));
          const rows=[];
          for(const art of articles.slice(0,12)){
            const text=(art.innerText||'').slice(0,260);
            if(/suggested for you|为你推荐|為你推薦|sponsored|赞助内容|贊助內容/i.test(text))continue;
            const nested=n=>{let a=n.closest('[role="article"]');return a&&a!==art;};
            const anchors=[...art.querySelectorAll('a[href]')].filter(a=>!nested(a));
            const header=anchors.slice(0,8);
            const authored=header.some(own);
            if(!authored)continue;
            const links=anchors.filter(a=>/\/posts\/|story_fbid=|\/videos\/|\/reel\/|\/permalink\//.test(a.href));
            const nodes=[...art.querySelectorAll('time[datetime],abbr[data-utime],abbr[title],[data-utime]')]
              .filter(n=>!nested(n) && !n.closest('[aria-label*="Comment"],[aria-label*="评论"],[data-testid*="comment"]'));
            for(const node of nodes.slice(0,3)){
              const link=node.closest('a[href]') || links[0];
              for(const attr of ['datetime','data-utime','title','aria-label']){
                const raw=node.getAttribute(attr);
                if(raw)rows.push({raw,authored:true,url:link?link.href:'',source:'主页贴文时间节点'});
              }
            }
            // Only header/permalink timestamp labels, never the full post text or its comments.
            for(const link of links.slice(0,2)){
              for(const raw of [link.getAttribute('aria-label'),link.getAttribute('title'),link.innerText]){
                if(raw && raw.length<140)rows.push({raw,authored:true,url:link.href,source:'主页贴文链接时间'});
              }
            }
          }
          return rows;
        }
        """
        try:
            return page.evaluate(script,{"pid":str(pid),"name":normalize_name(name,pid)}) or []
        except Exception:
            return []

    def _extract_post(self, page, pid, name):
        candidates=[]
        # Check more than the first item so a pinned old post does not automatically win.
        for step in range(3):
            candidates.extend(self._post_candidates(page,pid,name))
            if step<2:
                try:
                    page.mouse.wheel(0,650)
                    page.wait_for_timeout(650)
                except Exception: break
        chosen=choose_post_candidate(candidates)
        if not chosen:
            urls=list(dict.fromkeys(str(c.get("url") or "") for c in candidates if c.get("authored") and c.get("url")))
            for url in urls[:3]:
                try:
                    index=page.locator("a[href]").evaluate_all("(els,url)=>els.findIndex(e=>e.href===url)",url)
                    if index<0:continue
                    page.locator("a[href]").nth(index).hover(timeout=1800)
                    page.wait_for_timeout(300)
                    for text in page.locator('[role="tooltip"]').all_inner_texts():
                        candidates.append({"raw":text,"authored":True,"url":url,"source":"主页贴文时间提示"})
                except Exception:continue
            chosen=choose_post_candidate(candidates)
        if not chosen:return None
        url=chosen["url"]
        try:
            u=urlsplit(url)
            if u.scheme!="https" or not ((u.hostname or "")=="facebook.com" or (u.hostname or "").endswith(".facebook.com")):
                chosen["url"]=""
        except ValueError:chosen["url"]=""
        return chosen




# ========== GitHub Releases / verified update preparation (no Qt dependency) ==========
REPOSITORY = "bstbuku-ship-it/Page-Operations-Monitor"
REPOSITORY_URL = "https://github.com/" + REPOSITORY
RELEASES_API = "https://api.github.com/repos/" + REPOSITORY + "/releases/latest"
# Fill these when building signed installation packages. Never take publisher pins from remote JSON.
UPDATE_WINDOWS_PUBLISHER_THUMBPRINT = ""
# 1.5.2 is a Windows-only release. The macOS Team ID is intentionally left
# empty, so macOS auto-install stays unavailable (see signed_install_available).
UPDATE_MACOS_TEAM_ID = ""
MAX_UPDATE_BYTES = 2 * 1024 * 1024 * 1024
MAX_UPDATE_JSON_BYTES = 2 * 1024 * 1024

class UpdateError(RuntimeError):
    pass

def release_version(value):
    match=re.fullmatch(r"[vV]?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?",str(value).strip())
    if not match:raise UpdateError("发布版本号须为 v1.9.1 这样的正式版本号")
    return tuple(int(x or 0) for x in match.groups())

def update_platform_key(system=None,machine=None):
    system=system or platform.system();machine=(machine or platform.machine()).lower()
    arch="arm64" if machine in ("arm64","aarch64") else "x64" if machine in ("amd64","x86_64","x64") else ""
    prefix={"Windows":"windows","Darwin":"macos"}.get(system)
    return f"{prefix}-{arch}" if prefix and arch else ""

def _trusted_update_url(url,asset=False):
    try:
        u=urlsplit(str(url))
        if u.scheme!="https" or u.username or u.password or u.port not in (None,443):return False
        host=(u.hostname or "").lower()
        if asset:
            return host=="github.com" and u.path.lower().startswith("/"+REPOSITORY.lower()+"/releases/download/")
        return host in ("api.github.com","github.com","objects.githubusercontent.com",
                        "release-assets.githubusercontent.com","github-releases.githubusercontent.com")
    except (ValueError,TypeError):return False

class _ReleaseRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not _trusted_update_url(newurl):raise UpdateError("下载重定向到非信任地址，已停止")
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def open_update_url(url):
    if not _trusted_update_url(url):raise UpdateError("更新地址不受信任")
    request=urllib.request.Request(url,headers={
        "Accept":"application/vnd.github+json" if urlsplit(url).hostname=="api.github.com" else "application/octet-stream",
        "User-Agent":"Page-Operations-Monitor/"+APP_VERSION,
        "X-GitHub-Api-Version":"2026-03-10"})
    opener=urllib.request.build_opener(_ReleaseRedirectHandler(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    return opener.open(request,timeout=20)

def load_update_json(url,open_fn=None):
    with (open_fn or open_update_url)(url) as response:
        raw=response.read(MAX_UPDATE_JSON_BYTES+1)
    if len(raw)>MAX_UPDATE_JSON_BYTES:raise UpdateError("更新清单过大，已停止")
    try:
        value=json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError,ValueError) as exc:raise UpdateError("更新服务器未返回有效 JSON") from exc
    if not isinstance(value,dict):raise UpdateError("更新信息格式不正确")
    return value

def _asset_digest(asset,manifest_item=None):
    digest=str(asset.get("digest") or "")
    api_hash=digest[7:].lower() if digest.startswith("sha256:") else ""
    declared=str((manifest_item or {}).get("sha256") or "").lower()
    if declared and not re.fullmatch(r"[0-9a-f]{64}",declared):raise UpdateError("清单中的 SHA-256 无效")
    if api_hash and not re.fullmatch(r"[0-9a-f]{64}",api_hash):raise UpdateError("GitHub 的 SHA-256 无效")
    if api_hash and declared and api_hash!=declared:raise UpdateError("清单与 GitHub 资产校验值不一致")
    return declared or api_hash

def select_release_asset(release,manifest=None,system=None,machine=None,frozen=None):
    frozen=bool(getattr(sys,"frozen",False)) if frozen is None else bool(frozen)
    key=update_platform_key(system,machine)
    assets=release.get("assets") or []
    if not isinstance(assets,list):raise UpdateError("版本资产列表无效")
    assets={str(a.get("name")):a for a in assets if isinstance(a,dict) and a.get("state","uploaded")=="uploaded"}
    version=str(release.get("tag_name") or "").lstrip("vV")
    names={
        "windows-x64":f"ProfessionalMonitorTool-{version}-windows-x64.zip",
        "windows-arm64":f"ProfessionalMonitorTool-{version}-windows-arm64.zip",
        "macos-arm64":f"ProfessionalMonitorTool-{version}-macos-arm64.zip",
        "macos-x64":f"ProfessionalMonitorTool-{version}-macos-x64.zip",
    }
    name=names.get(key);asset=assets.get(name) if name else None
    if not asset:return None
    url=str(asset.get("browser_download_url") or "")
    if not _trusted_update_url(url,asset=True):raise UpdateError("更新包不属于指定仓库的 Release")
    try:size=int(asset.get("size",0))
    except (ValueError,TypeError):raise UpdateError("更新包大小无效")
    if not 0<size<=MAX_UPDATE_BYTES:raise UpdateError("更新包大小超出允许范围")
    manifest_item=None
    if isinstance(manifest,dict):
        assets_map=manifest.get("assets")
        if isinstance(assets_map,dict) and isinstance(assets_map.get(name),dict):
            manifest_item=assets_map[name]
        elif isinstance(manifest.get(name),dict):
            manifest_item=manifest[name]
        elif manifest.get("sha256"):
            manifest_item=manifest
    sha=_asset_digest(asset,manifest_item)
    return {"name":name,"url":url,"size":size,"sha256":sha,"installer":"platform-bundle","platform":key,
            "version":version,"source_mode":not frozen}

def query_latest_release(open_fn=None,system=None,machine=None,frozen=None):
    try:
        release=load_update_json(RELEASES_API,open_fn)
    except urllib.error.HTTPError as exc:
        if exc.code==404:return {"status":"unavailable","message":"暂未找到可公开访问的正式 Release（可能尚未发布或仓库暂不可访问）"}
        if exc.code in (403,429):raise UpdateError("GitHub 请求受限，请稍后再检查") from exc
        raise UpdateError(f"GitHub 返回 HTTP {exc.code}") from exc
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        raise UpdateError("无法连接 GitHub，请检查网络后重试；没有把本次检查当作已是最新版") from exc
    if release.get("draft") or release.get("prerelease"):return {"status":"unavailable","message":"没有正式发布的稳定版本"}
    tag=str(release.get("tag_name") or "")
    if release_version(tag)<=release_version(APP_VERSION):return {"status":"current","version":tag}
    manifest=None
    for asset in release.get("assets",[]):
        if isinstance(asset,dict) and asset.get("name")=="update-manifest.json":
            url=str(asset.get("browser_download_url") or "")
            if not _trusted_update_url(url,asset=True):raise UpdateError("更新清单地址无效")
            manifest=load_update_json(url,open_fn);break
    plan=select_release_asset(release,manifest,system,machine,frozen)
    return {"status":"new","version":tag.lstrip("vV"),"title":str(release.get("name") or tag)[:200],
            "notes":str(release.get("body") or "本版本未填写更新日志。")[:50000],
            "published_at":str(release.get("published_at") or ""),
            "release_url":REPOSITORY_URL+"/releases/tag/"+tag,
            "asset":plan}

def file_sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):h.update(block)
    return h.hexdigest()

def download_release_asset(plan,folder,progress=None,cancel=None,open_fn=None):
    # Revalidate even when a pending plan was restored from local settings.
    name=str(plan.get("name") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,180}\.(?:exe|msi|pkg|zip|dmg)",name):
        raise UpdateError("不安全的更新文件名")
    if not _trusted_update_url(plan.get("url"),asset=True):raise UpdateError("更新下载地址无效")
    sha=str(plan.get("sha256") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}",sha):raise UpdateError("发布者尚未提供 SHA-256，不能进行自动下载与安装")
    total=int(plan.get("size") or 0)
    if not 0<total<=MAX_UPDATE_BYTES:raise UpdateError("更新包大小无效")
    folder=ensure_private_directory(Path(folder))
    target=folder/name;part=folder/(name+".part")
    if target.is_symlink() or part.is_symlink():raise UpdateError("下载文件不能是符号链接")
    if target.is_file() and target.stat().st_size==total and file_sha256(target)==sha:
        if progress:progress(total,total)
        return str(target)
    if shutil.disk_usage(folder).free<total+32*1024*1024:raise UpdateError("磁盘剩余空间不足")
    actual=0;h=hashlib.sha256()
    try:
        with (open_fn or open_update_url)(plan["url"]) as response,part.open("wb") as stream:
            while True:
                if cancel and cancel.is_set():raise UpdateError("下载已取消")
                block=response.read(128*1024)
                if not block:break
                actual+=len(block)
                if actual>total or actual>MAX_UPDATE_BYTES:raise UpdateError("下载长度超出声明大小")
                stream.write(block);h.update(block)
                if progress:progress(actual,total)
            stream.flush();os.fsync(stream.fileno())
        if actual!=total or h.hexdigest()!=sha:raise UpdateError("更新包校验失败，已删除不完整下载")
        os.replace(part,target)
        return str(target)
    finally:
        try:part.unlink(missing_ok=True)
        except OSError:pass

def save_json_atomic(path,value):
    payload=json.dumps(value,ensure_ascii=False,indent=2).encode("utf-8")
    return _atomic_write_bytes(Path(path),payload,mode=0o600,private_parent=True)

def validate_staged_update(plan,path,updates_dir):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise UpdateError("下载文件不存在或路径不安全")
    try:path.resolve().relative_to(Path(updates_dir).resolve())
    except ValueError:raise UpdateError("更新文件不在应用更新目录")
    if path.name!=plan.get("name") or path.stat().st_size!=int(plan.get("size",0)):
        raise UpdateError("下载文件与计划不匹配")
    expected=str(plan.get("sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}",expected) or file_sha256(path)!=expected:
        raise UpdateError("安装前校验失败；文件可能已被修改")
    return path.resolve()

def signed_install_available(plan):
    """Whether a downloaded update may be executed.

    The binding verification is the SHA-256 check in validate_staged_update
    (always run before this) plus the trusted-origin check on the download
    URL. A configured publisher thumbprint / Team ID adds a signature check
    inside the install helper; when none is configured the helper skips the
    signature check and the install proceeds on the hash alone, so silent
    auto-update works without a paid certificate. Source (.py) runs never
    self-overwrite and always stay manual.
    """
    if not getattr(sys,"frozen",False):return False,"当前是 Python 源码运行方式，不自动覆盖脚本；下载当前系统更新包后请手动运行其中的部署文件。"
    installer=str(plan.get("installer") or "")
    platform_key=str(plan.get("platform") or "")
    if sys.platform=="win32" and installer in ("inno","msi","deployer","platform-bundle") and platform_key.startswith("windows-"):
        return True,""
    if sys.platform=="darwin" and installer in ("pkg","platform-bundle") and platform_key.startswith("macos-"):
        return True,""
    return False,"当前平台或包格式不支持自动安装；可打开下载目录手动安装。"

def _extract_platform_bundle_installer(plan,path,updates_dir):
    """Extract only the installer/deployer for this running platform."""
    path=validate_staged_update(plan,path,updates_dir)
    key=str(plan.get("platform") or "");version=str(plan.get("version") or "")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?",version):
        raise UpdateError("更新版本号格式无效")
    allowed_platforms={"windows-x64","windows-arm64","macos-x64","macos-arm64"}
    if key not in allowed_platforms or key!=update_platform_key():
        raise UpdateError("更新包与当前系统不匹配")
    if key.startswith("windows-"):
        expected=f"ProfessionalMonitorTool-{version}-{key}-deployer.exe";kind="inno"
    else:
        expected=f"ProfessionalMonitorTool-{version}-{key}.pkg";kind="pkg"

    base=Path(updates_dir).resolve()
    extracted_root=base/"extracted"
    folder_candidate=extracted_root/version
    # Do not follow a pre-existing symlink in the extraction path.
    if extracted_root.is_symlink() or folder_candidate.is_symlink():
        raise UpdateError("更新解压目录不能是符号链接")
    try:
        folder_candidate.resolve().relative_to(base)
    except ValueError as exc:
        raise UpdateError("更新解压目录超出应用更新目录") from exc
    folder=ensure_private_directory(folder_candidate)
    folder=folder.resolve()
    try:
        folder.relative_to(base)
    except ValueError as exc:
        raise UpdateError("更新解压目录超出应用更新目录") from exc

    target=folder/expected
    if target.is_symlink():
        raise UpdateError("拒绝覆盖符号链接安装文件")
    temp=folder/(expected+"."+uuid.uuid4().hex+".part")
    try:
        with zipfile.ZipFile(path,"r") as zf:
            matches=[i for i in zf.infolist() if (not i.is_dir()) and PurePosixPath(i.filename.replace("\\","/")).name==expected]
            if len(matches)!=1:raise UpdateError("更新包中找不到唯一的当前系统部署文件")
            info=matches[0]
            if info.file_size<=0 or info.file_size>MAX_UPDATE_BYTES:raise UpdateError("更新包内部署文件大小异常")
            flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_BINARY",0)
            fd=None;h=hashlib.sha256();written=0
            try:
                fd=os.open(str(temp),flags,0o600)
                with zf.open(info,"r") as src,os.fdopen(fd,"wb") as dst:
                    fd=None
                    while True:
                        block=src.read(128*1024)
                        if not block:break
                        written+=len(block)
                        if written>info.file_size:raise UpdateError("解压后的部署文件长度异常")
                        dst.write(block);h.update(block)
                    dst.flush();os.fsync(dst.fileno())
            finally:
                if fd is not None:
                    os.close(fd)
            if written!=info.file_size:raise UpdateError("部署文件解压不完整")
            os.replace(temp,target)
    except zipfile.BadZipFile as exc:
        raise UpdateError("下载的更新包不是有效 ZIP") from exc
    finally:
        try:temp.unlink(missing_ok=True)
        except OSError:pass
    if os.name=="posix":
        try:target.chmod(0o600)
        except OSError:pass
    return {"name":expected,"size":target.stat().st_size,"sha256":h.hexdigest(),"installer":kind,
            "platform":key,"version":version,"source_mode":False},target



# ---------------- 卸载：设置页入口 + 注册表 --uninstall 入口 ----------------
# 卸载流程（简单化，不再有单独的维护程序）：
#   1. 确认对话框（可勾选是否一并删除监控数据，默认不删）；
#   2. 程序退出后，后台 PowerShell 脚本删除程序目录、系统注册与桌面快捷方式；
#   3. 最后弹出一次完成确认。静默卸载（--silent）全程无界面。
UNINSTALL_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ProfessionalMonitorTool"


def _ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def uninstall_target_info(target=None):
    """Return (target_dir, mode, data_dir) for an owned install, or None.

    mode is 'portable' when the install dir carries portable.mode or a
    portable install marker, else 'standard'. data_dir mirrors app_data_dir()
    for that install. Source runs (not frozen) have no install to remove.
    """
    if target is None:
        if not getattr(sys, "frozen", False):
            return None
        try:
            target = Path(sys.executable).resolve().parent
        except OSError:
            return None
    target = Path(target)
    marker = None
    try:
        marker = json.loads((target / ".professional-monitor-install.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        marker = None
    mode = (marker or {}).get("mode")
    if mode not in ("standard", "portable"):
        mode = "portable" if (target / "portable.mode").is_file() else None
    if mode is None:
        # Last resort: registry InstallLocation match (old installs without a marker).
        if os.name != "nt":
            return None
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH, 0, winreg.KEY_READ) as key:
                loc = winreg.QueryValueEx(key, "InstallLocation")[0]
            if Path(loc).resolve() != target.resolve():
                return None
        except OSError:
            return None
        mode = "standard"
    if not (target / "ProfessionalMonitorTool.exe").is_file():
        return None
    override = os.environ.get("FBPM_DATA_DIR", "").strip()
    if override:
        data_dir = Path(override).expanduser()
    elif mode == "portable":
        data_dir = target / "data"
    elif os.name == "nt":
        data_dir = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "FBGrowthRadar"
    else:
        data_dir = Path.home() / ".fb_growth_radar"
    return target, mode, data_dir


def _uninstall_backup_candidate(target: Path):
    """Non-colliding sibling backup dir for portable data (mirrors the deployer)."""
    candidate = target.parent / (target.name + "-数据备份")
    if candidate.exists():
        candidate = target.parent / (target.name + "-数据备份-" + time.strftime("%Y%m%d-%H%M%S"))
    return candidate


_PS_UNINSTALL_TEMPLATE = r"""
$ErrorActionPreference = 'SilentlyContinue'
$waitPids = @(__PIDS__)
$deadline = (Get-Date).AddSeconds(20)
while ((Get-Date) -lt $deadline) {
  $alive = $false
  foreach ($p in $waitPids) { if (Get-Process -Id $p -ErrorAction SilentlyContinue) { $alive = $true } }
  if (-not $alive) { break }
  Start-Sleep -Milliseconds 500
}
foreach ($p in $waitPids) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1
$target = __TARGET__
$dataDir = __DATADIR__
if (__KEEP_BACKUP__) {
  $backup = __BACKUP__
  if (Test-Path -LiteralPath $dataDir) { Move-Item -LiteralPath $dataDir -Destination $backup -Force }
}
try {
  $loc = (Get-ItemProperty __REGKEY__ -ErrorAction Stop).InstallLocation
  if ($loc -and $loc -eq $target) { Remove-Item __REGKEY__ -Recurse -Force }
} catch {}
try {
  $k2 = Get-ItemProperty __REGKEY_INNO__ -ErrorAction Stop
  $loc2 = $k2.InstallLocation
  $un2 = $k2.UninstallString
  if (($loc2 -and $loc2 -eq $target) -or ($un2 -and $un2.StartsWith('"' + $target, [System.StringComparison]::OrdinalIgnoreCase))) { Remove-Item __REGKEY_INNO__ -Recurse -Force }
} catch {}
$desktop = [Environment]::GetFolderPath('Desktop')
Remove-Item (Join-Path $desktop __SHORTCUT__) -Force
for ($i = 0; $i -lt 8; $i++) {
  try { Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction Stop; break } catch { Start-Sleep -Milliseconds 700 }
}
if (__DELETE_DATA__) {
  if (Test-Path -LiteralPath $dataDir) { Remove-Item -LiteralPath $dataDir -Recurse -Force }
}
if (__SHOW_FINAL__) {
  Add-Type -AssemblyName System.Windows.Forms
  [System.Windows.Forms.MessageBox]::Show(__FINAL_TEXT__, __FINAL_TITLE__)
}
try { Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force } catch {}
"""


def build_uninstall_script(target, mode, data_dir, delete_data, show_final, wait_pids):
    """Pure builder: returns the PowerShell uninstall script text."""
    target = Path(target)
    data_dir = Path(data_dir)
    keep_backup = (mode == "portable" and not delete_data and data_dir.is_dir())
    backup = _uninstall_backup_candidate(target) if keep_backup else target.parent / (target.name + "-数据备份")
    if show_final:
        if delete_data:
            final_text = "专业监控工具已卸载完成，监控数据已一并删除。"
        elif mode == "portable":
            final_text = "专业监控工具已卸载完成，监控数据已移到旁边的备份目录。"
        else:
            final_text = "专业监控工具已卸载完成，监控数据保留在系统本地目录。"
    else:
        final_text = ""
    script = _PS_UNINSTALL_TEMPLATE
    script = script.replace("__PIDS__", ",".join(str(int(p)) for p in wait_pids))
    script = script.replace("__TARGET__", _ps_quote(str(target)))
    script = script.replace("__DATADIR__", _ps_quote(str(data_dir)))
    script = script.replace("__KEEP_BACKUP__", "$true" if keep_backup else "$false")
    script = script.replace("__BACKUP__", _ps_quote(str(backup)))
    script = script.replace("__REGKEY__", _ps_quote("HKCU:\\" + UNINSTALL_REG_PATH))
    script = script.replace("__REGKEY_INNO__", _ps_quote("HKCU:\\" + UNINSTALL_REG_PATH + "_is1"))
    script = script.replace("__SHORTCUT__", _ps_quote(APP_TITLE + ".lnk"))
    script = script.replace("__DELETE_DATA__", "$true" if delete_data else "$false")
    script = script.replace("__SHOW_FINAL__", "$true" if show_final else "$false")
    script = script.replace("__FINAL_TEXT__", _ps_quote(final_text))
    script = script.replace("__FINAL_TITLE__", _ps_quote(APP_TITLE))
    return script


def start_background_uninstall(script_text):
    """Write the script to %TEMP% and launch it detached (no console window);
    it runs after this process exits and deletes the install itself."""
    if os.name != "nt":
        raise RuntimeError("卸载仅支持 Windows 安装版。")
    import tempfile
    path = Path(tempfile.gettempdir()) / ("pmt-uninstall-%d.ps1" % os.getpid())
    path.write_text(script_text, encoding="utf-8-sig")
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen([str(powershell), "-NoProfile", "-NonInteractive",
                      "-ExecutionPolicy", "Bypass", "-File", str(path)],
                     creationflags=flags)
    return path


def _read_running_instance_pid():
    """PID of the currently running instance from its descriptor, if any."""
    try:
        guard = SingleInstanceGuard()
        data = _unprotect_local_secret(json.loads((guard.directory / "desktop.json").read_text(encoding="utf-8")))
        return int(data["pid"])
    except Exception:
        return None


def confirm_uninstall(parent, target, mode, data_dir):
    """Return (accepted, delete_data). One checkbox only; data kept by default."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("卸载" + APP_TITLE)
    dlg.resize(520, 300)
    root = QVBoxLayout(dlg)
    root.setContentsMargins(22, 20, 22, 20)
    root.setSpacing(12)
    title = QLabel("确定卸载" + APP_TITLE + "吗？")
    title.setObjectName("DialogTitle")
    root.addWidget(title)
    if mode == "portable":
        detail = ("程序将关闭，并在后台删除整个程序文件夹。\n程序目录：" + str(target)
                  + "\n文件夹内的监控数据会移到旁边的备份目录，不直接删除。")
        box_text = "同时删除文件夹内的监控数据（不备份）"
    else:
        detail = ("程序将关闭，并在后台删除程序文件、系统注册与桌面快捷方式。\n程序目录：" + str(target)
                  + "\n监控数据保留在系统本地目录，不会自动删除。")
        box_text = "同时删除监控数据（位于系统本地目录）"
    info = QLabel(detail)
    info.setObjectName("SmallMuted")
    info.setWordWrap(True)
    root.addWidget(info)
    var = QCheckBox(box_text)
    var.setChecked(False)
    root.addWidget(var)
    root.addStretch(1)
    btns = QHBoxLayout()
    btns.addStretch(1)
    cancel = QPushButton("取消")
    cancel.clicked.connect(dlg.reject)
    btns.addWidget(cancel)
    ok = QPushButton("确认卸载")
    ok.setObjectName("DangerButton")
    ok.clicked.connect(dlg.accept)
    btns.addWidget(ok)
    root.addLayout(btns)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return True, bool(var.isChecked())
    return False, False


def _run_uninstall_cli(app, silent, target_arg):
    """--uninstall entry point. Runs before the single-instance guard so a
    second process (from Settings/Geek) can uninstall while the app runs."""
    if os.name != "nt":
        if not silent:
            QMessageBox.warning(None, "无法卸载", "卸载仅支持 Windows 安装版。")
        return 0
    info = uninstall_target_info(Path(target_arg) if target_arg else None)
    if info is None:
        if not silent:
            QMessageBox.warning(None, "无法卸载", "找不到已登记的安装目录，已停止。")
        return 0
    target, mode, data_dir = info
    delete_data = False
    if not silent:
        ok, delete_data = confirm_uninstall(None, target, mode, data_dir)
        if not ok:
            return 0
    wait_pids = [os.getpid()]
    run_pid = _read_running_instance_pid()
    if run_pid and run_pid != os.getpid():
        wait_pids.append(run_pid)
    script = build_uninstall_script(target, mode, data_dir, delete_data, not silent, wait_pids)
    try:
        start_background_uninstall(script)
    except Exception as exc:
        if not silent:
            QMessageBox.warning(None, "卸载失败", str(exc))
        return 1
    return 0



def log_window_event(kind, detail=""):
    """Best-effort diagnostic for the flashing-window investigation: one
    timestamped line per main-window show/hide/state/activation event in
    DATA_DIR/window.log (last 200 lines). Never raises, never shows UI."""
    try:
        path = DATA_DIR / "window.log"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        lines.append("%s | %s%s" % (now_iso(), kind, (" | " + str(detail)) if detail else ""))
        path.write_text("\n".join(lines[-200:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def prepare_install_helper(plan,path,updates_dir):
    """Static OS helper: wait for this app to exit, recheck hash/signature, install, relaunch.
    Called after an explicit user confirmation or a verified silent auto-install
    decision. It never disables OS security checks; the signature check runs
    only when a publisher identity is configured, otherwise the SHA-256
    recheck is the verification.
    """
    if str(plan.get("installer") or "")=="platform-bundle":
        plan,path=_extract_platform_bundle_installer(plan,path,updates_dir)
    else:
        path=validate_staged_update(plan,path,updates_dir)
    allowed,reason=signed_install_available(plan)
    if not allowed:raise UpdateError(reason)
    folder=ensure_private_directory(Path(updates_dir)/"helper")
    result=folder/"install-result.json"
    result.unlink(missing_ok=True)
    job={"pid":os.getpid(),"path":str(path),"sha256":plan["sha256"],
         "installer":plan["installer"],"result":str(result),
         "thumbprint":UPDATE_WINDOWS_PUBLISHER_THUMBPRINT,"team":UPDATE_MACOS_TEAM_ID,
         "relaunch":str(Path(sys.executable).resolve()),"target_dir":str(Path(sys.executable).resolve().parent),
         "version":plan["version"]}
    if sys.platform=="win32":
        script=folder/"apply-update.ps1"
        script.write_text(WINDOWS_UPDATE_HELPER,encoding="utf-8-sig")
        jobfile=folder/"job.json";save_json_atomic(jobfile,job)
        powershell=Path(os.environ.get("SystemRoot","C:/Windows"))/"System32/WindowsPowerShell/v1.0/powershell.exe"
        return [str(powershell),"-NoProfile","-NonInteractive","-File",str(script),"-PlanPath",str(jobfile)]
    bundle=next((p for p in Path(sys.executable).resolve().parents if p.suffix==".app"),None)
    if bundle is None:raise UpdateError("找不到当前 macOS 应用包，不能自动重启")
    def aq(value):return json.dumps(str(value),ensure_ascii=False)
    if UPDATE_MACOS_TEAM_ID:
        sig=("/usr/sbin/pkgutil --check-signature "+shlex.quote(str(path))+
             " && /usr/sbin/spctl --assess --type install --verbose=2 "+shlex.quote(str(path)))
    else:
        sig="/usr/bin/true"
    sha="/usr/bin/shasum -a 256 "+shlex.quote(str(path))
    wait=f"i=0; while [ \"$i\" -lt 120 ]; do /bin/kill -0 {os.getpid()} 2>/dev/null || exit 0; /bin/sleep 1; i=$((i+1)); done; exit 1"
    install="/usr/sbin/installer -pkg "+shlex.quote(str(path))+" -target /"
    status_ok="/usr/bin/printf '%s' "+shlex.quote(json.dumps({"status":"installed","version":plan["version"]}))+" > "+shlex.quote(str(result))
    status_bad="/usr/bin/printf '%s' "+shlex.quote(json.dumps({"status":"failed","version":plan["version"]}))+" > "+shlex.quote(str(result))
    script=folder/"apply-update.applescript"
    code="\n".join([
        "try","  do shell script "+aq(wait),
        "  set digestResult to do shell script "+aq(sha),
        "  if digestResult does not contain "+aq(plan["sha256"])+" then error \"SHA mismatch\"",
        "  set signatureResult to do shell script "+aq(sig),
        *([ "  if signatureResult does not contain "+aq("("+UPDATE_MACOS_TEAM_ID+")")+' then error "Publisher mismatch"'] if UPDATE_MACOS_TEAM_ID else []),
        "  do shell script "+aq(install)+" with administrator privileges",
        "  do shell script "+aq(status_ok),
        "  tell application \"System Events\" to open file POSIX file "+aq(str(bundle)),
        "on error errText number errNum",
        "  try","    do shell script "+aq(status_bad),"  end try",
        "end try",
    ])
    script.write_text(code,encoding="utf-8")
    return ["/usr/bin/osascript",str(script)]


WINDOWS_UPDATE_HELPER = r"""
param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference = 'Stop'
$j = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
try {
    $old = Get-Process -Id ([int]$j.pid) -ErrorAction SilentlyContinue
    if ($old -and -not $old.WaitForExit(120000)) { throw 'The application did not exit.' }
    $hash = (Get-FileHash -LiteralPath $j.path -Algorithm SHA256).Hash
    if ($hash.ToLowerInvariant() -ne $j.sha256.ToLowerInvariant()) { throw 'SHA256 mismatch' }
    if ($j.thumbprint) {
        $signature = Get-AuthenticodeSignature -LiteralPath $j.path
        if ($signature.Status -ne 'Valid' -or
            $signature.SignerCertificate.Thumbprint.ToUpperInvariant() -ne $j.thumbprint.ToUpperInvariant()) {
            throw 'Installer signature or publisher mismatch'
        }
    }
    if ($j.installer -eq 'inno') {
        $dir = $j.target_dir -replace '"',''
        if ($dir.Length -gt 3) { $dir = $dir.TrimEnd('\') }
        $args = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /DIR="' + $dir + '" /TASKS="desktopicon"'
        $p = Start-Process -FilePath $j.path -ArgumentList $args -Wait -PassThru
    } elseif ($j.installer -eq 'msi') {
        $args = '/i "' + $j.path + '" /passive /norestart'
        $p = Start-Process -FilePath "$env:SystemRoot\System32\msiexec.exe" -ArgumentList $args -Wait -PassThru
    } elseif ($j.installer -eq 'deployer') {
        $args = @('--silent-update','--target',[string]$j.target_dir)
        $p = Start-Process -FilePath $j.path -ArgumentList $args -Wait -PassThru
    } else { throw 'Unsupported installer type' }
    if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { throw "Installer exit code: $($p.ExitCode)" }
    @{status='installed';version=$j.version;reboot_required=($p.ExitCode -eq 3010)} |
        ConvertTo-Json | Set-Content -LiteralPath $j.result -Encoding UTF8
} catch {
    @{status='failed';version=$j.version;message=$_.Exception.Message} |
        ConvertTo-Json | Set-Content -LiteralPath $j.result -Encoding UTF8
}
if (-not (Get-Process -Id ([int]$j.pid) -ErrorAction SilentlyContinue)) {
    if (Test-Path -LiteralPath $j.relaunch) { Start-Process -FilePath $j.relaunch }
}
"""


def settings_locator_path():
    if os.environ.get("FBPM_DATA_DIR"):
        return Path(os.environ["FBPM_DATA_DIR"])/"location.json"
    if os.name=="nt":
        base=Path(os.environ.get("APPDATA") or Path.home())
    elif sys.platform=="darwin":
        base=Path.home()/"Library/Preferences"
    else:
        base=Path(os.environ.get("XDG_CONFIG_HOME") or Path.home()/".config")
    return base/"PageOperationsMonitor"/"location.json"

def read_settings_location(default,legacy=""):
    if os.environ.get("FBPM_DATA_DIR"):return Path(os.environ["FBPM_DATA_DIR"]).expanduser()
    path=settings_locator_path()
    if path.is_file():
        try:
            obj=json.loads(path.read_text("utf-8"))
            target=Path(str(obj["data_directory"])).expanduser()
            if not target.is_absolute():raise ValueError("relative directory")
            if not target.is_dir():raise ValueError("saved directory unavailable")
            return target
        except (KeyError,ValueError,OSError,TypeError) as exc:
            raise RuntimeError("无法读取已保存的数据目录；为避免另建空数据库，已停止启动。请检查："+str(path)) from exc
    return Path(legacy).expanduser() if legacy else Path(default)

def write_settings_location(path):
    save_json_atomic(settings_locator_path(),{"data_directory":str(Path(path).resolve()),"format":1})



# ========== Authenticated local Chrome connector + single instance ==========
"""POM connector protocol v1; local only, read-only page collection.
This section is embedded in the single-file desktop entry points at build time.
"""
import secrets
import socket
import queue
from dataclasses import dataclass, field
from pathlib import PureWindowsPath

CONNECTOR_VERSION = '1.4.2'
CONNECTOR_PROTOCOL = 1
CONNECTOR_PORT = 17831
CONNECTOR_EXTENSION_ID = 'lpjmbcclokpbgfogjhjepmnpoplgheoh'
CONNECTOR_ORIGIN = 'chrome-extension://' + CONNECTOR_EXTENSION_ID

# BEGIN BUNDLED CONNECTOR PACKAGE
# IMPORTANT: Connector version is independent from the desktop app version.
# Do not change this package/version unless the browser connector itself is intentionally updated.
BUNDLED_CONNECTOR_VERSION = '1.4.2'
BUNDLED_CONNECTOR_FILENAME = '专业监控工具-浏览器连接器-1.4.2.zip'
BUNDLED_CONNECTOR_SHA256 = 'b7b251ede9580ea0b95568be8268f44308a5709d6d6e2280019c0e656669c064'
BUNDLED_CONNECTOR_ZIP_B64 = (
    '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'
    'SFbL+t4rQgqqxA8Hia2rlA+4YvX3fa1/ShTygURLBQfYXPTm2R7uNLv/PBFOzj/+y3f6maIQbdcQ'
    'VBLlj+qMROKzhc+c5jVL//2z7gIFk9bGYfBUBrymDzm3EP2g9VURKfa7u6u4+ZLCE/VLXQGHv/Tk'
    '7/JZsbZUWIKdeRI97emqTsrrZNYWnb7Q0UfCgYIFKCQ9es3OJtVcw75/G+B06CSLp2ft7RV9uScY'
    'e8vcnngTId7w/ebhE+QLTXDgaWh0L1gjfkurMd4C+8OA/XmGgIIXYQXcHzVG/CLjS5I6P08coQ3d'
    'MAlplZgn00mJ7Eaq4LzQPjNjd/y6pdkhjrT12OO8EhJep5cgfE2waWeJPsTB2WNwT0/t1Kth9J3P'
    'tobseqA8V247XbEoaLGFmoM64r1bkFMJFmooo+9jZdSSGrD8wu3bPCe7egOt6wB1+UGf/BmQDRpk'
    'Qx78Nv09gqhut4KA1oDuxn1XXDz+goe1rlvRsiSxmaQzesEW3wH2K/zNk9ntVrxJPqup4fiZZ2tf'
    'qaHUk13zn3IneV/5vB7hrFoP7/4dXH6QLH9mT94WXyi7eU0T7G07Zcz8V4lNXtuVFCPk95vKKwhg'
    'iKNThKiNfTAceRrmgkVh/6hkthiGBaLHuNV7TAo84oCApJWK5h1VJq9k+1UVFr4CubVr2EFTWgie'
    'S8vQJbZPFIVUIf7ie/rjfpP3cH4cCZyLAuCw6Kb7RUFix/vRdAb16z69p3ewG96GbLxBGOT2w8RQ'
    '2bn4cLDi9/YfpfdKPN0PFD9d31p80JdIEqUGG5WC9toWsYgto/yPhFne0wPRqak8bv+bWWrY8pHW'
    'G+I5UZnhSrG4x2WURHu/oKXCiqQLYV8SL+QrpibVc5MCYLaz9Sn479o+7LwZ0yx3xpJWg00D7g4F'
    'NuzaOrReKpvgmpmRvIDC0AeMFFSZsbyj2IXW8PZUacprt/UvU6G1cU9HRxOZF0VDbnsys/XTsf6N'
    'vSz+Nuy0/g3NNB1Q2TxJnot9MMN9bneqieVpsFLKzeq9ead317+OH+r6151lNniMtl6q8al1va/H'
    'XsNldrltf9HOrn2i/tH+9nJQqZVNavSWWqRlxdHBR0JTw8hz3s08oLbS8nJbNJNxvv8NTcGupcvZ'
    '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'
)
# END BUNDLED CONNECTOR PACKAGE

class ConnectorError(RuntimeError):
    pass


def connector_version_tuple(value):
    """Chrome manifest versions are numeric dot-separated values (1-4 parts)."""
    parts = str(value or '').strip().split('.')
    if not parts or len(parts) > 4 or any(not p.isdigit() for p in parts):
        return None
    nums = tuple(int(p) for p in parts)
    return nums + (0,) * (4 - len(nums))


def bundled_connector_bytes():
    """Return the connector ZIP embedded in the desktop application and verify it before export."""
    try:
        data = base64.b64decode(BUNDLED_CONNECTOR_ZIP_B64.encode('ascii'), validate=True)
    except Exception as exc:
        raise ConnectorError('内置连接器数据损坏') from exc
    if hashlib.sha256(data).hexdigest().lower() != BUNDLED_CONNECTOR_SHA256.lower():
        raise ConnectorError('内置连接器校验失败')
    return data


def connector_needs_update(identity):
    current = connector_version_tuple((identity or {}).get('extension_version'))
    bundled = connector_version_tuple(BUNDLED_CONNECTOR_VERSION)
    return bool(current and bundled and current < bundled)


def save_bundled_connector(parent):
    """Let the user export the embedded connector package to a chosen location."""
    try:
        data = bundled_connector_bytes()
    except Exception as exc:
        QMessageBox.warning(parent, '连接器不可用', str(exc))
        return None
    downloads = Path.home() / 'Downloads'
    base = downloads if downloads.is_dir() else Path.home()
    default_path = base / BUNDLED_CONNECTOR_FILENAME
    path, _ = QFileDialog.getSaveFileName(parent, '保存浏览器连接器', str(default_path), 'ZIP 压缩包 (*.zip)')
    if not path:
        return None
    target = Path(path)
    if target.suffix.lower() != '.zip':
        target = target.with_suffix('.zip')
    try:
        _atomic_write_bytes(target,data,mode=0o600,private_parent=False)
    except (OSError,RuntimeError) as exc:
        QMessageBox.warning(parent, '保存失败', str(exc))
        return None
    show_hint(parent, f'连接器 v{BUNDLED_CONNECTOR_VERSION} 已保存；解压后在 Chrome 扩展程序页面加载该文件夹',kind="success")
    return target


def bc_atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ConnectorError('Refusing a symlink registry')
    temp = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        if os.name != 'nt':
            path.chmod(0o600)
    finally:
        try:temp.unlink(missing_ok=True)
        except OSError:pass


def connector_identity(raw):
    """Never treat client labels as detected filesystem or channel evidence."""
    raw = raw if isinstance(raw, dict) else {}
    limits = {'profile_name':80, 'profile_directory':100, 'profile_path':800,
              'channel_label':100, 'browser_brand':100, 'browser_version':80,
              'os':30, 'arch':30, 'extension_version':30,
              'account_name':80, 'account_id':25, 'label_source':40}
    clean = {}
    for key, limit in limits.items():
        value = str(raw.get(key) or '').strip()
        if any(ord(ch) < 32 for ch in value) or len(value) > limit:
            raise ConnectorError('Invalid identity field: ' + key)
        clean[key] = value
    directory, path = clean['profile_directory'], clean['profile_path']
    if directory and not re.fullmatch(r'Default|Profile [0-9]{1,6}', directory):
        raise ConnectorError('Profile directory must be Default or Profile N')
    if path:
        p = PureWindowsPath(path) if re.match(r'^[a-zA-Z]:[\\/]', path) else Path(path)
        if not p.is_absolute():
            raise ConnectorError('Profile path must be absolute')
        if directory and p.name != directory:
            raise ConnectorError('Profile directory and full path do not match')
        if not directory:
            if not re.fullmatch(r'Default|Profile [0-9]{1,6}',p.name):
                raise ConnectorError('Profile path must end in Default or Profile N')
            clean['profile_directory'] = p.name
    clean['identity_source'] = 'profile-and-channel-manually-declared'
    return clean


def inspect_declared_profile(identity):
    """Local filesystem existence is evidence of a path, not proof of socket identity."""
    identity = connector_identity(identity)
    path = identity.get('profile_path', '')
    out = {'exists':False, 'local_state_match':False, 'local_name':'',
           'binding_verified':False, 'explanation':'No path supplied; connection identity is the paired instance ID.'}
    if not path:return out
    if os.name != 'nt' and re.match(r'^[a-zA-Z]:[\\/]', path):
        out['explanation']='Windows path declared on a different operating system; not locally verified.'
        return out
    p = Path(path).expanduser()
    out['exists'] = p.is_dir()
    if not out['exists']:
        out['explanation']='Declared path not found on this computer.'
        return out
    try:
        state = p.parent / 'Local State'
        if state.stat().st_size > 8_000_000:raise ValueError('Local State too large')
        data = json.loads(state.read_text('utf-8'))
        item = data.get('profile', {}).get('info_cache', {}).get(p.name)
        if isinstance(item, dict):
            out['local_state_match']=True
            out['local_name']=str(item.get('name') or '')[:100]
    except (OSError, ValueError, TypeError):pass
    out['explanation']='Path exists locally; its association with this connector is still user-declared.'
    return out


_PROFILE_NAMES_CACHE = {"at": 0.0, "names": {}}


def local_state_profile_names(data_root=None):
    """Chrome profile display names from Local State (desktop-verified).

    Cached for 30 seconds: the connector summary refreshes every second
    and must not re-read the file each time. Returns {folder: name}.
    """
    now = time.monotonic()
    if data_root is None and now - _PROFILE_NAMES_CACHE["at"] < 30 and _PROFILE_NAMES_CACHE["names"]:
        return dict(_PROFILE_NAMES_CACHE["names"])
    names = {}
    try:
        if data_root is not None:
            roots = [Path(data_root)]
        elif os.name == "nt":
            roots = [Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data"]
        elif sys.platform == "darwin":
            roots = [Path.home() / "Library/Application Support/Google/Chrome"]
        else:
            roots = [Path.home() / ".config/google-chrome"]
        for root in roots:
            state = root / "Local State"
            if not state.is_file() or state.stat().st_size > 8_000_000:
                continue
            data = json.loads(state.read_text("utf-8"))
            cache = data.get("profile", {}).get("info_cache", {})
            if isinstance(cache, dict):
                for folder, item in cache.items():
                    if isinstance(item, dict) and re.fullmatch(r"Default|Profile [0-9]{1,6}", str(folder)):
                        nm = str(item.get("name") or "").strip()
                        if nm:
                            names[str(folder)] = nm[:100]
    except (OSError, ValueError, TypeError):
        pass
    if data_root is None:
        _PROFILE_NAMES_CACHE["at"] = now
        _PROFILE_NAMES_CACHE["names"] = dict(names)
    return names


def connector_display_name(identity, instance_id):
    """Automatic connector label, strongest evidence first.

    FB account name (only if a future approved probe supplies it) >
    the manual remark kept for old installs > the Chrome profile name
    verified against this computer's Local State (exact folder, or the
    only profile on the machine) > a stable Chrome + instance-id label.
    Never invents a profile folder: the extension has no API that reports
    its own profile directory.
    """
    ident = identity if isinstance(identity, dict) else {}
    account = str(ident.get("account_name") or "").strip()
    if account:
        return account[:80]
    manual = str(ident.get("profile_name") or "").strip()
    if manual:
        return manual[:80]
    folder = ""
    path = str(ident.get("profile_path") or "")
    if path:
        folder = re.split(r"[\\/]", path.rstrip("\\/"))[-1]
    elif ident.get("profile_directory"):
        folder = str(ident.get("profile_directory"))
    names = local_state_profile_names()
    if folder and names.get(folder):
        return names[folder]
    if not folder and len(names) == 1:
        return next(iter(names.values()))
    return "Chrome " + str(instance_id or "")[:6]


@dataclass
class _ConnectorSession:
    instance_id: str
    connection: object
    identity: dict
    last_seen: float = field(default_factory=time.monotonic)
    send_lock: object = field(default_factory=threading.Lock)

    def send(self, message):
        encoded = json.dumps(message, ensure_ascii=False, separators=(',', ':'))
        with self.send_lock:self.connection.send(encoded)


@dataclass
class _ConnectorJob:
    session: object
    page_id: str
    event: object = field(default_factory=threading.Event)
    result: object = None
    error: str = ''


# Restricted RFC 6455 transport for the local connector. Standard library only.
# It isn't a public HTTP server: only loopback + the pinned extension Origin is accepted.
import socketserver
import struct
import select
import errno

CONNECTOR_BUILD = 'auto-connect-20261031'
CONNECTOR_PORTS = tuple(range(17831, 17841))
CONNECTOR_PRODUCT = 'PageOperationsMonitor'

class ConnectorFault(ConnectorError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class _LocalWebSocket:
    MAX_MESSAGE = 1_048_576
    def __init__(self, sock, remainder=b''):
        self.sock = sock
        self.buffer = bytearray(remainder)
        self.send_lock = threading.RLock()
        self.closed = False
        self.fragments = bytearray()
        self.fragmented = False
        self.partial_since = None
        self.sock.settimeout(5)

    def _fill(self, count, deadline):
        while len(self.buffer) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Connector receive timeout')
            if not select.select([self.sock], [], [], remaining)[0]:
                raise TimeoutError('Connector receive timeout')
            chunk = self.sock.recv(min(65536, max(4096, count - len(self.buffer))))
            if not chunk:
                raise ConnectionError('Browser closed the connection')
            self.buffer.extend(chunk)
            if self.partial_since is None:
                self.partial_since = time.monotonic()

    def _frame(self, payload, opcode=1):
        with self.send_lock:
            if self.closed:
                raise ConnectionError('Connection closed')
            n = len(payload)
            if n > self.MAX_MESSAGE:
                raise ConnectorError('Outgoing message exceeds limit')
            header = bytes([0x80 | opcode])
            if n < 126:
                header += bytes([n])
            elif n < 65536:
                header += bytes([126]) + struct.pack('!H', n)
            else:
                header += bytes([127]) + struct.pack('!Q', n)
            self.sock.sendall(header + payload)

    def send(self, text):
        if not isinstance(text, str):
            raise TypeError('Text messages only')
        self._frame(text.encode('utf-8'))

    def recv(self, timeout=22):
        deadline = time.monotonic() + timeout
        while True:
            # Preserve unread bytes on timeout, including a partly received frame.
            if self.partial_since is not None and time.monotonic() - self.partial_since > 30:
                raise ConnectorError('Incomplete frame deadline exceeded')
            self._fill(2, deadline)
            first, second = self.buffer[0], self.buffer[1]
            fin, opcode = bool(first & 128), first & 15
            if first & 0x70 or not second & 128:
                raise ConnectorError('Compressed or unmasked frame refused')
            if opcode not in (0, 1, 8, 9, 10):
                raise ConnectorError('Only text frames are accepted')
            n, pos = second & 127, 2
            if n == 126:
                self._fill(4, deadline)
                n = struct.unpack('!H', self.buffer[2:4])[0];pos = 4
                if n < 126:raise ConnectorError('Noncanonical frame length')
            elif n == 127:
                self._fill(10, deadline)
                n = struct.unpack('!Q', self.buffer[2:10])[0];pos = 10
                if n < 65536:raise ConnectorError('Noncanonical frame length')
            if n > self.MAX_MESSAGE or (opcode < 8 and n + len(self.fragments) > self.MAX_MESSAGE):
                raise ConnectorError('Incoming message exceeds limit')
            if opcode >= 8 and (not fin or n > 125):
                raise ConnectorError('Invalid control frame')
            self._fill(pos + 4 + n, deadline)
            mask = self.buffer[pos:pos+4]
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(self.buffer[pos+4:pos+4+n]))
            del self.buffer[:pos+4+n]
            if not self.buffer and not self.fragmented:
                self.partial_since = None
            if opcode == 8:
                if len(payload) == 1:raise ConnectorError('Invalid close frame')
                if len(payload) >= 2:
                    code = struct.unpack('!H', payload[:2])[0]
                    if code < 1000 or code >= 5000 or code in (1004,1005,1006,1015) or 1016 <= code < 3000:
                        raise ConnectorError('Invalid close code')
                    payload[2:].decode('utf-8', 'strict')
                try:self._frame(payload, 8)
                except Exception:pass
                raise ConnectionError('Browser disconnected')
            if opcode == 9:
                self._frame(payload, 10);continue
            if opcode == 10:continue
            if opcode == 1:
                if self.fragmented:raise ConnectorError('Unexpected new text fragment')
                if fin:return payload.decode('utf-8', 'strict')
                self.fragments.extend(payload);self.fragmented=True
                self.partial_since=time.monotonic()
            else:
                if not self.fragmented:raise ConnectorError('Unexpected continuation')
                self.fragments.extend(payload)
                if fin:
                    text=bytes(self.fragments).decode('utf-8','strict')
                    self.fragments.clear();self.fragmented=False
                    self.partial_since=time.monotonic() if self.buffer else None
                    return text

    def close(self, code=1000, reason=''):
        with self.send_lock:
            if self.closed:return
            payload=struct.pack('!H', code)+str(reason).encode('utf-8')[:120].decode('utf-8','ignore').encode('utf-8')
            try:self._frame(payload, 8)
            except Exception:pass
            self.closed=True
            try:self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            try:self.sock.close()
            except OSError:pass


class _LocalConnectorHandler(socketserver.BaseRequestHandler):
    def handle(self):
        if self.client_address[0] != '127.0.0.1':return
        sock=self.request;sock.settimeout(4)
        try:
            data=bytearray();deadline=time.monotonic()+4
            while b'\r\n\r\n' not in data:
                if time.monotonic()>deadline or len(data)>8192:
                    raise ValueError('HTTP header limit')
                part=sock.recv(min(2048,8193-len(data)))
                if not part:return
                data.extend(part)
            head,remainder=bytes(data).split(b'\r\n\r\n',1)
            if len(head)>8192:raise ValueError('HTTP header limit')
            lines=head.decode('ascii','strict').split('\r\n')
            if lines[0] != 'GET /connector/v1 HTTP/1.1':
                self.deny(404,'Not found');return
            headers={}
            for line in lines[1:]:
                key,sep,value=line.partition(':');key=key.strip().lower()
                if not sep or key in headers or not key:
                    raise ValueError('Invalid or duplicate header')
                headers[key]=value.strip()
            if headers.get('host') != '127.0.0.1:'+str(self.server.server_address[1]):
                self.deny(403,'Host refused');return
            if self.server.bridge.handshake_throttled():
                self.deny(429,'Too many failed handshakes');return
            if headers.get('origin') != CONNECTOR_ORIGIN:
                self.deny(403,'Extension origin refused');return
            if headers.get('upgrade','').lower()!='websocket' or 'upgrade' not in [x.strip().lower() for x in headers.get('connection','').split(',')]:
                self.deny(400,'WebSocket upgrade required');return
            if headers.get('sec-websocket-version')!='13':
                self.deny(400,'Unsupported WebSocket version');return
            key=headers.get('sec-websocket-key','')
            if len(base64.b64decode(key,validate=True))!=16:
                raise ValueError('Invalid websocket key')
            accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode('ascii')).digest()).decode('ascii')
            sock.sendall(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+'\r\n\r\n').encode('ascii'))
            self.server.bridge._handle(_LocalWebSocket(sock,remainder))
        except (ValueError,UnicodeError):
            self.deny(400,'Invalid request')
        except (OSError,ConnectorError):pass

    def deny(self, code, message):
        try:
            body=message.encode('ascii')
            self.request.sendall(('HTTP/1.1 '+str(code)+' '+message+'\r\nConnection: close\r\nContent-Type: text/plain\r\nContent-Length: '+str(len(body))+'\r\n\r\n').encode('ascii')+body)
        except OSError:pass


class _LocalConnectorServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads=True
    block_on_close=False
    request_queue_size=32
    allow_reuse_address=False
    def __init__(self, address, bridge):
        self.bridge=bridge
        self.slots=threading.BoundedSemaphore(72)
        super().__init__(address,_LocalConnectorHandler)

    def server_bind(self):
        if os.name=='nt' and hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request);return
        try:super().process_request(request,client_address)
        except Exception:
            self.slots.release();raise

    def process_request_thread(self,request,client_address):
        try:super().process_request_thread(request,client_address)
        finally:self.slots.release()


def choose_connected_browser(rows, selected_id='', selection_mode=''):
    """Select a unique online instance; never substitute for an offline selection."""
    usable=[r for r in rows if not r.get('blocked')]
    online=[r for r in usable if r.get('online')]
    chosen=next((r for r in rows if r['instance_id']==selected_id),None)
    if chosen:
        if chosen.get('blocked'):return '', 'blocked'
        if not chosen.get('online'):return '', 'offline_selected'
        if len(online)>1 and selection_mode=='auto':return '', 'multiple'
        return selected_id, 'selected'
    if len(online)==1:return online[0]['instance_id'], 'automatic'
    if len(online)>1:return '', 'multiple'
    return '', 'waiting'



def _dpapi_protect(data: bytes):
    """Windows DPAPI (current user scope) or None when unavailable.

    No password is involved and nothing is stored: Windows derives the
    key from the logged-in user profile. On other platforms this returns
    None and callers fall back to private-file permissions.
    """
    if os.name != "nt" or not data:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        class _Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
        crypt32 = ctypes.windll.crypt32
        blob_in = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
        blob_out = _Blob()
        if not crypt32.CryptProtectData(ctypes.byref(blob_in), "PageOperationsMonitor local secret",
                                       None, None, None, 0x01, ctypes.byref(blob_out)):
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    except Exception:
        return None


def _dpapi_unprotect(data: bytes):
    if os.name != "nt" or not data:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        class _Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
        crypt32 = ctypes.windll.crypt32
        blob_in = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
        blob_out = _Blob()
        if not crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0x01, ctypes.byref(blob_out)):
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    except Exception:
        return None


def _protect_local_secret(value):
    """Wrap a small JSON-able secret for storage.

    Format 2 is DPAPI-protected on Windows; format 1 is the private-file
    fallback used elsewhere (the values protected here are already hashes
    or short-lived tokens, never passwords). Legacy unwrapped objects
    pass through _unprotect_local_secret unchanged.
    """
    try:
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        return value
    blob = _dpapi_protect(raw)
    if blob is not None:
        return {"format": 2, "protected": True,
                "blob": base64.b64encode(blob).decode("ascii")}
    return {"format": 1, "protected": False, "value": value}


def _unprotect_local_secret(obj):
    if not isinstance(obj, dict):
        return obj
    if obj.get("protected"):
        raw = _dpapi_unprotect(base64.b64decode(str(obj.get("blob") or ""), validate=True))
        if raw is None:
            raise ValueError("受保护的本地密钥无法解密（可能不是同一 Windows 用户）")
        return json.loads(raw.decode("utf-8"))
    if "value" in obj and obj.get("format") == 1:
        return obj["value"]
    return obj


class ConnectorBridge:
    """Automatic enrollment from the pinned extension Origin; then per-profile tokens.

    Loopback only. This is not a barrier against malicious local native programs.
    No arbitrary code, URLs, cookies, or filesystem requests are sent to Chrome.
    """
    def __init__(self, registry, port=CONNECTOR_PORT):
        self.registry_path=Path(registry)
        self.port=int(port)
        self.lock=threading.RLock()
        self.records={}
        self.sessions={}
        self.jobs={}
        self.server=None
        self.thread=None
        self.error=''
        self._running=False
        self.pending={}
        self.pending_queue=queue.Queue()
        self._failed_handshakes=[]
        if self.registry_path.is_file():
            try:
                if self.registry_path.stat().st_size > 1_000_000:raise ValueError('Registry too large')
                root=_unprotect_local_secret(json.loads(self.registry_path.read_text('utf-8')))
                if root.get('schema') != 1:raise ValueError('Unsupported registry schema')
                for cid, value in root.get('clients', {}).items():
                    if re.fullmatch(r'[a-zA-Z0-9_-]{12,100}',cid) and isinstance(value,dict):
                        self.records[cid]=value
            except (OSError,ValueError,TypeError,AttributeError) as exc:
                self.error='Connector registry could not be read: '+str(exc)

    def _save(self):
        bc_atomic(self.registry_path, _protect_local_secret({'schema':1,'clients':self.records}))

    def pending_approvals(self):
        now=time.time()
        with self.lock:
            stale=[cid for cid, item in self.pending.items() if now-float(item.get('first_seen') or 0) > 900]
            for cid in stale:self.pending.pop(cid,None)
            return [{'instance_id':cid,'identity':dict(item.get('identity') or {}),
                     'first_seen':float(item.get('first_seen') or 0)}
                    for cid, item in self.pending.items()]

    def approve_pending(self, cid):
        with self.lock:
            item=self.pending.pop(str(cid),None)
            if not item:return False
            record={'token_hash':item['token_hash'],'paired_at':time.time(),
                    'registration':'approved-local','blocked':False,
                    'identity':item.get('identity') or {}}
            record['last_connected_at']=time.time()
            self.records[str(cid)]=record
            self._save()
            return True

    def block_pending(self, cid):
        with self.lock:
            item=self.pending.pop(str(cid),None)
            if not item:return False
            record={'token_hash':item['token_hash'],'paired_at':time.time(),
                    'registration':'blocked-local','blocked':True,
                    'identity':item.get('identity') or {}}
            self.records[str(cid)]=record
            self._save()
            return True

    def _note_handshake_failure(self):
        now=time.monotonic()
        self._failed_handshakes=[t for t in self._failed_handshakes if now-t < 60]
        self._failed_handshakes.append(now)

    def handshake_throttled(self):
        now=time.monotonic()
        self._failed_handshakes=[t for t in self._failed_handshakes if now-t < 60]
        return len(self._failed_handshakes) >= 30

    def relocate(self, path):
        with self.lock:
            self.registry_path=Path(path)
            self._save()

    def start(self):
        if self._running:return
        requested=self.port
        ports=[0] if requested==0 else list(dict.fromkeys([requested]+list(CONNECTOR_PORTS)))
        failures=[]
        for port in ports:
            server=None
            try:
                server=_LocalConnectorServer(('127.0.0.1',port),self)
                self.server=server;self.port=server.server_address[1]
                self._running=True
                self.thread=threading.Thread(target=server.serve_forever,
                    kwargs={'poll_interval':0.15},name='POM-local-connector',daemon=True)
                self.thread.start();self.error='';return
            except OSError as exc:
                if server:server.server_close()
                failures.append(str(port)+': '+str(exc))
                self._running=False;self.server=None
            except Exception:
                if server:server.server_close()
                self._running=False;self.server=None
                raise
        self.error=('\u672c\u673a\u8fde\u63a5\u670d\u52a1\u6682\u65f6\u65e0\u6cd5\u542f\u52a8\uff0c'
                    '\u8bf7\u68c0\u67e5\u7aef\u53e3\u5360\u7528\u6216\u5b89\u5168\u8f6f\u4ef6\u62e6\u622a\u3002\n' + '; '.join(failures))
        raise ConnectorError(self.error)


    def _authenticate(self, message):
        if message.get('protocol') != CONNECTOR_PROTOCOL:
            raise ConnectorFault('PROTOCOL_MISMATCH','Desktop and extension versions do not match')
        kind=message.get('type')
        if kind not in ('auto_hello','hello'):
            raise ConnectorFault('UPGRADE_REQUIRED','Install the automatic-connection extension included with this desktop build')
        if kind=='auto_hello' and message.get('product') != CONNECTOR_PRODUCT:
            raise ConnectorFault('PROTOCOL_MISMATCH','Unexpected connector product')
        cid=str(message.get('instance_id') or '')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{12,100}',cid):
            raise ConnectorFault('BAD_ID','Invalid instance ID')
        identity=connector_identity(message.get('identity'))
        token=str(message.get('token') or '')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{32,256}',token):
            raise ConnectorFault('BAD_TOKEN','Invalid local installation token')
        digest=hashlib.sha256(token.encode('ascii')).hexdigest()
        with self.lock:
            record=self.records.get(cid)
            if record and record.get('blocked'):
                raise ConnectorFault('BLOCKED','This browser has been disabled in the desktop app')
            if record:
                if not secrets.compare_digest(digest,str(record.get('token_hash') or '')):
                    raise ConnectorFault('AUTH_MISMATCH','Connection identity is no longer valid; reset this connector in extension settings')
            else:
                if kind!='auto_hello':raise ConnectorFault('UPGRADE_REQUIRED','Please update the browser extension')
                if len(self.records)>=64:raise ConnectorFault('LIMIT','Maximum saved browser connections reached')
                # First sighting of a new browser: one approval in the
                # desktop app. Already-paired browsers never re-confirm.
                # The extension keeps retrying in the background, so the
                # next handshake after approval succeeds without any
                # action in the browser.
                previous=self.pending.get(cid)
                if previous and previous.get('token_hash') != digest:
                    raise ConnectorFault('AUTH_MISMATCH','Connection identity is no longer valid; reset this connector in extension settings')
                self.pending[cid]={'token_hash':digest,'identity':identity,
                                   'first_seen':previous.get('first_seen',time.time()) if previous else time.time(),
                                   'last_seen':time.time()}
                try:self.pending_queue.put_nowait(cid)
                except queue.Full:pass
                raise ConnectorFault('PENDING_APPROVAL','New browser connection is waiting for approval in the desktop app')
            online=self.sessions.get(cid)
            if online and time.monotonic()-online.last_seen<65:
                raise ConnectorFault('INSTANCE_IN_USE','A copied Profile is using this instance ID')
            record['identity']=identity;record['last_connected_at']=time.time()
            self.records[cid]=record
            self._save()
        return cid,identity,None

    def _handle(self, ws):
        session=None
        try:
            first=ws.recv(timeout=8)
            if not isinstance(first,str) or len(first)>6000:raise ConnectorError('Invalid handshake')
            message=json.loads(first)
            if not isinstance(message,dict):raise ConnectorError('Invalid handshake')
            with self.lock:
                cid,identity,token=self._authenticate(message)
                old=self.sessions.get(cid)
                # A copied browser directory can duplicate storage IDs. Never auto-reroute an active session.
                if old and time.monotonic()-old.last_seen<65:
                    raise ConnectorError('This instance ID is already online; regenerate the connector ID in the copied profile')
                if old:
                    try:old.connection.close(1000,'Reconnected')
                    except Exception:pass
                session=_ConnectorSession(cid,ws,identity)
                self.sessions[cid]=session
            response={'type':'ready','protocol':CONNECTOR_PROTOCOL,'version':CONNECTOR_VERSION,'instance_id':cid,
                      'product':CONNECTOR_PRODUCT,'build':CONNECTOR_BUILD,'connection_mode':'auto'}
            if token:response['token']=token
            session.send(response)
            while self._running:
                try:raw=ws.recv(timeout=22)
                except TimeoutError:
                    if time.monotonic()-session.last_seen>65:break
                    session.send({'type':'ping'});continue
                if not isinstance(raw,str):raise ConnectorError('Text JSON required')
                msg=json.loads(raw)
                if not isinstance(msg,dict):raise ConnectorError('Invalid message')
                session.last_seen=time.monotonic()
                if msg.get('type') in ('ping','pong'):
                    if msg['type']=='ping':session.send({'type':'pong'})
                    continue
                if msg.get('type')=='result':
                    jid=str(msg.get('job_id') or '')
                    with self.lock:
                        job=self.jobs.get(jid)
                        if not job or job.session is not session:continue
                        payload=msg.get('payload')
                        if not isinstance(payload,dict) or str(payload.get('page_id') or '')!=job.page_id:
                            job.error='Result identity mismatch'
                        else:job.result=payload
                        job.event.set()
                else:raise ConnectorError('Unsupported message')
        except Exception as exc:
            if getattr(exc,'code',None) not in (None,'PENDING_APPROVAL'):
                try:self._note_handshake_failure()
                except Exception:pass
            try:ws.send(json.dumps({'type':'error','code':getattr(exc,'code','CONNECTOR_ERROR'),'message':str(exc)[:240]}))
            except Exception:pass
        finally:
            if session:
                with self.lock:
                    if self.sessions.get(session.instance_id) is session:self.sessions.pop(session.instance_id,None)
                    for job in self.jobs.values():
                        if job.session is session and not job.event.is_set():
                            job.error='Selected browser disconnected; no other profile was substituted'
                            job.event.set()
            try:ws.close()
            except Exception:pass

    def clients(self):
        with self.lock:
            rows=[]
            for cid,item in self.records.items():
                session=self.sessions.get(cid)
                online=bool(session and time.monotonic()-session.last_seen<65)
                rows.append({'instance_id':cid,'identity':dict(item.get('identity') or {}),'online':online,
                             'last_connected_at':item.get('last_connected_at',0),'blocked':bool(item.get('blocked'))})
            return rows

    def online(self, cid):
        return any(r['instance_id']==cid and r['online'] for r in self.clients())

    def request(self, cid, row, purpose='monitor', stop=None, timeout=120, retry=False):
        pid=str(row.get('page_id') or '')
        if not re.fullmatch(r'[0-9]{5,25}',pid):raise ConnectorError('Invalid page ID')
        if purpose not in ('monitor','metadata'):raise ConnectorError('Unsupported purpose')
        with self.lock:
            session=self.sessions.get(cid)
            if not session or time.monotonic()-session.last_seen>=65:raise ConnectorError('Selected browser is offline')
            if any(j.session is session and not j.event.is_set() for j in self.jobs.values()):
                raise ConnectorError('Selected browser is busy')
            jid=secrets.token_hex(16);job=_ConnectorJob(session,pid);self.jobs[jid]=job
        try:
            session.send({'type':'collect','job_id':jid,'page_id':pid,'purpose':purpose,
                          'retry':bool(retry),
                          'growth':bool(purpose=='monitor' and row.get('monitor_growth',1)),
                          'posts':bool(purpose=='monitor' and row.get('monitor_posts',0)),
                          'timeout_ms':max(5000,min(110000,int(timeout*1000)-5000))})
            end=time.monotonic()+timeout
            while not job.event.wait(.15):
                if stop and stop.is_set():raise ConnectorError('Task stopped')
                if time.monotonic()>end:raise ConnectorError('Browser task timed out')
            if job.error:raise ConnectorError(job.error)
            if not job.result:raise ConnectorError('No result received')
            return job.result
        finally:
            with self.lock:self.jobs.pop(jid,None)
            # Late results are ignored; cancel never touches tabs not created by this connector.
            if not job.event.is_set():
                try:session.send({'type':'cancel','job_id':jid})
                except Exception:pass

    def identify(self,cid):
        with self.lock:session=self.sessions.get(cid)
        if not session:raise ConnectorError('Selected browser is offline')
        session.send({'type':'identify'})

    def revoke(self,cid):
        # Keep a tombstone: offline disabled profiles must not auto-enroll again.
        with self.lock:
            record=self.records.get(cid)
            if not record:return
            record['blocked']=True;self._save()
            session=self.sessions.get(cid)
        if session:
            try:session.send({'type':'revoked'});session.connection.close(1000,'Disabled')
            except Exception:pass

    def allow(self,cid):
        with self.lock:
            if cid in self.records:
                self.records[cid]['blocked']=False;self._save()

    def forget(self,cid):
        """Delete an offline historical record. Online instances must be closed first."""
        with self.lock:
            session=self.sessions.get(cid)
            if session and time.monotonic()-session.last_seen<65:
                raise ConnectorError('请先关闭该浏览器或停用连接后再删除记录')
            self.records.pop(cid,None);self.sessions.pop(cid,None);self._save()

    def stop(self):
        self._running=False
        with self.lock:
            sessions=list(self.sessions.values())
            for job in self.jobs.values():job.error='Desktop connector stopped';job.event.set()
        for session in sessions:
            try:session.connection.close(1001,'Desktop stopped')
            except Exception:pass
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server=None
        if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=2)
        self.thread=None


def chrome_launch_command(identity):
    """Explicit user action only. Launch known Chrome stable, never a supplied executable."""
    identity=connector_identity(identity)
    if identity.get('channel_label') not in ('Chrome Stable','Chrome \u7a33\u5b9a\u7248'):
        raise ConnectorError('One-click launch currently supports explicitly selected Chrome Stable only')
    directory=identity.get('profile_directory','')
    if not re.fullmatch(r'Default|Profile [0-9]{1,6}',directory):raise ConnectorError('Configure the Profile directory first')
    if os.name=='nt':
        roots=[Path(os.environ.get('LOCALAPPDATA',''))/'Google/Chrome/User Data']
        candidates=[Path(os.environ.get(k,''))/'Google/Chrome/Application/chrome.exe'
                    for k in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA')]
    elif sys.platform=='darwin':
        roots=[Path.home()/'Library/Application Support/Google/Chrome']
        candidates=[Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
                    Path.home()/'Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    else:
        roots=[Path.home()/'.config/google-chrome']
        candidates=[Path(x) for x in ('/usr/bin/google-chrome-stable','/usr/bin/google-chrome','/opt/google/chrome/google-chrome')]
    p=Path(identity.get('profile_path') or '')
    if not p.is_dir() or p.is_symlink() or p.resolve().parent!=roots[0].resolve() or p.name!=directory:
        raise ConnectorError('Only an existing Profile in this computer\'s standard Chrome Stable data directory can be launched')
    executable=next((x for x in candidates if x.is_file()),None)
    if executable is None:raise ConnectorError('Chrome Stable executable was not found')
    return [str(executable),'--profile-directory='+directory,'https://www.facebook.com/']


class SingleInstanceGuard:
    """Version-independent OS lock + authenticated loopback activation (no Qt required).
    The OS releases the file lock on crash. Never deletes another process's lock file.
    """
    def __init__(self, directory=None):
        if directory is None:
            if os.environ.get('POM_INSTANCE_DIR'):directory=Path(os.environ['POM_INSTANCE_DIR'])
            elif os.name=='nt':directory=Path(os.environ.get('LOCALAPPDATA') or Path.home())/'PageOperationsMonitorRuntime'
            elif sys.platform=='darwin':directory=Path.home()/'Library/Application Support/PageOperationsMonitorRuntime'
            else:directory=Path.home()/'.local/state/PageOperationsMonitorRuntime'
        self.directory=ensure_private_directory(Path(directory))
        self.lock_file=None;self.primary=False;self.socket=None;self.thread=None
        self.commands=queue.Queue();self.stopping=threading.Event();self.token=''

    def acquire(self):
        path=self.directory/'desktop.lock'
        if path.is_symlink():raise ConnectorError('Unsafe single-instance lock path')
        self.lock_file=open(path,'a+b')
        self.lock_file.seek(0,2)
        if self.lock_file.tell()==0:self.lock_file.write(b'0');self.lock_file.flush()
        self.lock_file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.lock_file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.lock_file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.lock_file.close();self.lock_file=None
            return False
        self.primary=True
        try:
            self.socket=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            if os.name=='nt' and hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            self.socket.bind(('127.0.0.1',0));self.socket.listen(4);self.socket.settimeout(.3)
            self.token=secrets.token_urlsafe(32)
            bc_atomic(self.directory/'desktop.json',_protect_local_secret({'pid':os.getpid(),'port':self.socket.getsockname()[1],'token':self.token}))
            self.thread=threading.Thread(target=self._listen,name='POM-activate',daemon=True);self.thread.start()
            return True
        except Exception:
            self.close();raise

    def _listen(self):
        while not self.stopping.is_set():
            try:conn,_=self.socket.accept()
            except socket.timeout:continue
            except OSError:break
            try:
                with conn:
                    conn.settimeout(1);buf=b''
                    while b'\n' not in buf and len(buf)<1024:
                        chunk=conn.recv(1024-len(buf))
                        if not chunk:break
                        buf+=chunk
                    data=json.loads(buf.decode('utf-8').strip())
                    if data.get('action')=='show' and secrets.compare_digest(str(data.get('token') or ''),self.token):
                        self.commands.put('show');conn.sendall(b'OK\n')
                    else:conn.sendall(b'DENIED\n')
            except (OSError,ValueError,AttributeError):pass

    def activate_existing(self, timeout=10):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            try:
                path=self.directory/'desktop.json'
                if path.stat().st_size>4096:raise ValueError('Invalid instance descriptor')
                data=_unprotect_local_secret(json.loads(path.read_text('utf-8')))
                if os.name=='nt':
                    try:
                        import ctypes
                        ctypes.windll.user32.AllowSetForegroundWindow(int(data['pid']))
                    except Exception:pass
                with socket.create_connection(('127.0.0.1',int(data['port'])),timeout=1) as conn:
                    conn.sendall((json.dumps({'action':'show','token':data['token']})+'\n').encode())
                    if conn.recv(16).startswith(b'OK'):return True
            except (OSError,ValueError,KeyError,TypeError):pass
            time.sleep(.15)
        return False

    def take_activation(self):
        found=False
        while True:
            try:self.commands.get_nowait();found=True
            except queue.Empty:return found

    def close(self):
        self.stopping.set()
        if self.socket:
            try:self.socket.close()
            except OSError:pass
        if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=2)
        if self.primary and self.lock_file:
            try:
                descriptor=self.directory/'desktop.json'
                if descriptor.exists():descriptor.unlink()
            except OSError:pass
            try:
                self.lock_file.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(self.lock_file.fileno(),msvcrt.LK_UNLCK,1)
                else:
                    import fcntl
                    fcntl.flock(self.lock_file.fileno(),fcntl.LOCK_UN)
            finally:self.lock_file.close()
        self.primary=False;self.lock_file=None

def connector_record(row, payload, purpose='monitor'):
    """Validate a connector observation, then reuse the desktop's existing parsers.
    No content returned by Chrome is executed by Python or used as a local path.
    """
    row=dict(row);pid=str(row['page_id']);stamp=time.time()
    result={'page_id':pid,'page_name':'','avatar_path':'','avatar_fresh':False,
            'metadata_ok':False,'growth_ok':False,'posts_ok':False,
            'name_error':'','growth_error':'','posts_error':'',
            'collected_ts':stamp,'collected_at':now_iso()}
    error=str(payload.get('error') or '')[:350] if isinstance(payload,dict) else 'Invalid connector result'
    _page_state=str(payload.get('page_state') or '').strip().lower()
    _raw_candidates=[]
    if isinstance(payload,dict) and isinstance(payload.get('name_candidates'),list):
        for _item in payload.get('name_candidates')[:160]:
            if isinstance(_item,dict):_raw_candidates.append(str(_item.get('text') or ''))
    _unavail_hint=str(payload.get('unavailable_hint') or '')[:80]
    _unavail,_detected_hint=detect_unavailable_page(' \n '.join(_raw_candidates))
    _force_unavailable=(_page_state=='unavailable') or _unavail
    if _force_unavailable and not _unavail_hint:_unavail_hint=_detected_hint
    if not isinstance(payload,dict) or str(payload.get('page_id'))!=pid:
        raise ConnectorError('Connector result does not belong to this Page ID')
    if payload.get('observed_url'):
        u=urlsplit(str(payload['observed_url']))
        if u.scheme!='https' or u.hostname not in ('facebook.com','www.facebook.com','web.facebook.com','m.facebook.com'):
            raise ConnectorError('Unexpected result origin')
        if re.search(r'/(?:login|login.php|checkpoint|recover|two_factor)(?:/|$)',u.path):
            error='Facebook login/security verification is required in the selected profile'
    # Candidate order is supplied by the bundled extractor, which ports the supplied reference code.
    names=payload.get('name_candidates') or []
    if isinstance(names,list):
        for item in names[:160]:
            if not isinstance(item,dict):continue
            candidate=normalize_name(str(item.get('text') or '')[:240],pid)
            if candidate and looks_like_page_name(candidate,pid):
                result['page_name']=candidate;break
    if not result['page_name']:
        result['name_error']=error or '\u5f53\u524d\u767b\u5f55\u4f1a\u8bdd\u672a\u8fd4\u56de\u53ef\u786e\u8ba4\u7684\u4e3b\u9875\u540d\u79f0'
    image=payload.get('avatar_data')
    if isinstance(image,str) and image.startswith('data:image/png;base64,') and len(image)<300000:
        try:
            raw=base64.b64decode(image.split(',',1)[1],validate=True)
            from PIL import Image,ImageOps
            with Image.open(io.BytesIO(raw),formats=("PNG",)) as im:
                if im.format!='PNG' or im.width!=192 or im.height!=192:
                    raise ValueError('Connector avatar must be a 192px PNG')
                # Only the first PNG frame is used, as before; no frame iterator
                # is exposed to data returned by the connector.
                im.load();im=ImageOps.fit(im.convert('RGB'),(192,192))
            ensure_private_directory(AVATAR_DIR)
            target=AVATAR_DIR/(pid+'.png')
            output=io.BytesIO();im.save(output,format='PNG')
            _atomic_write_bytes(target,output.getvalue(),mode=0o600,private_parent=True)
            result['avatar_path']=str(target);result['avatar_fresh']=True
        except Exception as exc:
            result['avatar_error']=str(exc)[:120]
    result['metadata_ok']=bool(result['page_name'] or result['avatar_fresh'])
    if purpose=='monitor' and row.get('monitor_growth'):
        text=payload.get('follower_text')
        if not isinstance(text,str) or len(text)>12000:text=''
        try:
            parsed=extract_followers_from_text(text)
            if parsed:
                count,approx,matched=parsed
                result.update(growth_ok=True,followers_count=count,approx=approx,matched_text=matched)
            else:raise ValueError('No follower statistic')
        except Exception:
            result['growth_error']=error or '\u672a\u8bfb\u5230\u53ef\u786e\u8ba4\u7684\u7c89\u4e1d\u6570\uff0c\u4e0d\u4f1a\u5199\u5165 0'
    if purpose=='monitor' and row.get('monitor_posts'):
        candidates=[]
        post_rows=payload.get('post_candidates')
        if not isinstance(post_rows,list):post_rows=[]
        for item in post_rows[:160]:
            if not isinstance(item,dict) or item.get('authored') is not True:continue
            try:
                u=urlsplit(str(item.get('url') or ''))
                if u.scheme!='https' or u.hostname not in ('facebook.com','www.facebook.com','web.facebook.com','m.facebook.com'):continue
            except ValueError:continue
            candidates.append({'authored':True,'raw':str(item.get('raw') or '')[:180],
                               'url':str(item.get('url') or '')[:1500],
                               'source':'\u8fde\u63a5\u5668\u8bfb\u53d6\u7684\u4e3b\u9875\u81ea\u53d1\u8d34\u6587'})
        chosen=choose_post_candidate(candidates,now=stamp)
        if chosen:
            result.update(posts_ok=True,last_post_ts=chosen['ts'],post_precision_seconds=chosen['precision'],
                          post_source=chosen['source'],post_url=chosen['url'])
        else:result['posts_error']=error or '\u672a\u8bfb\u5230\u53ef\u786e\u8ba4\u7684\u81ea\u53d1\u8d34\u6587\u65f6\u95f4'
    # Diagnosis snapshot: counts only, never page text. Stored in the DB
    # so a later failure can be told apart from a login/timeout/layout
    # problem instead of showing one generic "could not read" message.
    try:
        _obs = urlsplit(str(payload.get('observed_url') or ''))
        _obs_kind = 'login' if re.search(r'/(?:login|login.php|checkpoint|recover|two_factor)(?:/|$)', _obs.path) else 'page'
    except ValueError:
        _obs_kind = 'unexpected_origin'
    _err_low = str(error or '').lower()
    _name_count = len(payload.get('name_candidates') or []) if isinstance(payload.get('name_candidates'), list) else 0
    _follower_present = bool(str(payload.get('follower_text') or '').strip())
    _post_count = len(payload.get('post_candidates') or []) if isinstance(payload.get('post_candidates'), list) else 0
    if _force_unavailable:
        _diag = ('page_unavailable', PAGE_UNAVAILABLE_DETAIL)
    elif _obs_kind == 'login' or 'login' in _err_low or '安全验证' in str(error or ''):
        _diag = ('login', '需要先在浏览器里登录 Facebook 或完成安全验证')
    elif 'timed out' in _err_low or 'timeout' in _err_low or 'exceeded' in _err_low:
        _diag = ('timeout', '浏览器任务超时，页面可能尚未加载完成')
    elif _name_count == 0 and not _follower_present:
        _diag = ('empty', '页面没有返回可识别的名称与粉丝文本，可能是加载未完成或版面变化')
    elif not result['page_name'] and _name_count > 0:
        _diag = ('filtered', f'返回了 {_name_count} 个名称候选，但都被名称过滤规则排除')
    elif purpose == 'monitor' and row.get('monitor_growth') and not result['growth_ok'] and _follower_present:
        _diag = ('follower_parse', '已返回粉丝文本，但粉丝数解析失败（多为语言/单位词表未覆盖）')
    elif purpose == 'monitor' and row.get('monitor_growth') and not result['growth_ok']:
        _diag = ('follower_empty', '未返回粉丝文本')
    elif purpose == 'monitor' and row.get('monitor_posts') and not result['posts_ok']:
        _diag = ('post_parse', f'返回了 {_post_count} 个贴文候选，但没有可确认的自发贴文时间')
    elif not result['metadata_ok']:
        _diag = ('unknown', '未能确认主页身份')
    else:
        _diag = ('ok', '')
    result['diagnosis_code'] = _diag[0]
    result['diagnosis_detail'] = _diag[1]
    if _diag[0] == 'page_unavailable':
        if not result['name_error']:result['name_error'] = PAGE_UNAVAILABLE_DETAIL
        if purpose == 'monitor' and row.get('monitor_growth') and not result['growth_ok']:
            result['growth_error'] = PAGE_UNAVAILABLE_DETAIL
        if purpose == 'monitor' and row.get('monitor_posts') and not result['posts_ok']:
            result['posts_error'] = PAGE_UNAVAILABLE_DETAIL
        if not error:error = PAGE_UNAVAILABLE_DETAIL
    result['name_candidates_count'] = _name_count
    result['follower_text_present'] = _follower_present
    if error:result['error']=error
    return result


def record_needs_recheck(row, record, purpose='monitor'):
    """Second pass for identity/post uncertainty and for diagnosable growth
    misses (parse/empty/layout). Login and unavailable-page failures are
    not auto-retried: a refresh cannot fix a logged-out profile or a Page
    that cannot be opened, and the manual single-page recheck remains
    available once the situation changes."""
    row=dict(row);record=dict(record or {});pid=str(row.get('page_id') or '')
    if record.get('diagnosis_code') in ('login','page_unavailable'):
        return False
    name_ok=bool(normalize_name(record.get('page_name'),pid) or normalize_name(row.get('page_name'),pid))
    if not name_ok:
        return True
    if purpose=='monitor' and row.get('monitor_posts') and not record.get('posts_ok'):
        return True
    if purpose=='monitor' and row.get('monitor_growth') and not record.get('growth_ok'):
        if record.get('diagnosis_code') in ('follower_parse','follower_empty','empty','filtered','timeout'):
            return True
    return False


def merge_recheck_record(first, second, row, purpose='monitor'):
    """Merge an automatic recheck without discarding a successful first observation.

    Growth data from the first pass is intentionally preserved so the corrective pass
    cannot create a second follower sample. Identity/avatar and post fields prefer the
    recheck only when it produced a confirmed value.
    """
    row=dict(row);first=dict(first or {});second=dict(second or {});out=dict(first)
    pid=str(row.get('page_id') or first.get('page_id') or second.get('page_id') or '')
    second_name=normalize_name(second.get('page_name'),pid)
    first_name=normalize_name(first.get('page_name'),pid)
    if second_name:
        out['page_name']=second_name;out['name_error']=''
    elif first_name:
        out['page_name']=first_name
    else:
        out['page_name']='';out['name_error']=str(second.get('name_error') or first.get('name_error') or '自动复检后仍未读取到可信主页名称')[:300]
    if second.get('avatar_fresh') and second.get('avatar_path'):
        out['avatar_path']=second.get('avatar_path');out['avatar_fresh']=True
    elif not out.get('avatar_path') and second.get('avatar_path'):
        out['avatar_path']=second.get('avatar_path')
    out['metadata_ok']=bool(normalize_name(out.get('page_name'),pid) or out.get('avatar_path'))

    # Keep a successful first growth sample exactly as-is. If the first
    # pass failed, a successful recheck may supply the sample; a failed
    # recheck must never overwrite a successful first sample. (1.5.0
    # always copied the first pass, so a growth recheck could never fix
    # a growth failure.)
    _growth_keys=('growth_ok','followers_count','approx','matched_text','growth_error')
    if first.get('growth_ok'):
        for key in _growth_keys:
            if key in first:out[key]=first[key]
    elif second.get('growth_ok'):
        for key in _growth_keys:
            if key in second:out[key]=second[key]
        out['growth_error']=''
    out['diagnosis_code']=second.get('diagnosis_code') or first.get('diagnosis_code') or 'unknown'
    out['diagnosis_detail']=second.get('diagnosis_detail') or first.get('diagnosis_detail') or ''
    out['name_candidates_count']=max(int(first.get('name_candidates_count') or 0),int(second.get('name_candidates_count') or 0))
    out['follower_text_present']=bool(first.get('follower_text_present') or second.get('follower_text_present'))

    if purpose=='monitor' and row.get('monitor_posts'):
        if second.get('posts_ok'):
            for key in ('posts_ok','last_post_ts','post_precision_seconds','post_source','post_url'):
                if key in second:out[key]=second[key]
            out['posts_error']=''
        elif first.get('posts_ok'):
            for key in ('posts_ok','last_post_ts','post_precision_seconds','post_source','post_url','posts_error'):
                if key in first:out[key]=first[key]
        else:
            out['posts_ok']=False
            detail=str(second.get('posts_error') or first.get('posts_error') or '未读取到可确认的主页自发贴文时间')
            out['posts_error']=(detail+'；已自动复检一次仍无法确认')[:300]
    out['rechecked']=True
    out['recheck_ok']=not record_needs_recheck(row,out,purpose)
    out['collected_ts']=max(float(first.get('collected_ts') or 0),float(second.get('collected_ts') or 0),time.time())
    out['collected_at']=now_iso()
    if out.get('recheck_ok'):
        out.pop('error',None)
    return out


# ========== PyQt6 dashboard and application ==========
import sys
import uuid

# When double-clicking on Windows, missing packages would otherwise flash a
# console briefly and disappear; show an actionable native message instead.
try:
    import PyQt6
except ModuleNotFoundError as exc:
    message = (
        "缺少 PyQt6 图形界面依赖。\n\n请在命令行运行：\n"
        "python -m pip install PyQt6 Pillow\n"
        ""
        "安装后再启动 Page_Operations_Monitor_1.6.0.pyw。"
    )
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, APP_TITLE + " · 依赖未安装", 0x10)
        except Exception:
            pass
    if sys.stderr is not None:
        print(message, file=sys.stderr)
    raise SystemExit(1) from exc

from PyQt6.QtCore import (
    QObject, QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QSettings, QThread, QTimer, QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter, QPalette,
    QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QLayout, QLayoutItem,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSizeGrip, QSpinBox, QGraphicsDropShadowEffect,
    QStackedWidget, QStyle, QSystemTrayIcon, QTableWidget, QTableWidgetItem,
    QToolButton, QToolTip, QVBoxLayout, QWidget, QListWidget, QListWidgetItem, QTabWidget,
    QStyledItemDelegate, QStyleOptionViewItem, QAbstractSpinBox, QProxyStyle, QProgressBar,
)

# Focused palettes. Blue-Orange Obsidian is the default theme.
THEME_PRESETS = {
    "云白": dict(bg="#F7F7F5",sidebar="#FFFFFF",panel="#FFFFFF",panel_2="#F2F2EF",
        border="#E8E8E3",text="#1C1C1C",muted="#6E6E6E",accent="#1D4ED8",accent2="#1E40AF",
        pill="#1D4ED8",pill_hover="#1E40AF",green="#15803D",
        red="#DC2626",amber="#B45309",cyan="#0369A1",input="#FFFFFF",hover="#EFF1F8",soft="#EAF0FE",light=True,
        tooltip_bg="#FFFFFF",tooltip_text="#1C1C1C",tooltip_border="#1D4ED8"),
    "护眼绿": dict(bg="#E9F5EC",sidebar="#F2FAF4",panel="#FFFFFF",panel_2="#E3F2E7",
        border="#C8E6D2",text="#1C1C1C",muted="#5A6B5E",accent="#0B7A43",accent2="#096A3A",
        pill="#0B7A43",pill_hover="#096A3A",green="#12803C",
        red="#DC2626",amber="#B45309",cyan="#0E7490",input="#FFFFFF",hover="#DDF0E3",soft="#D9F2E3",light=True,
        tooltip_bg="#FFFFFF",tooltip_text="#123B22",tooltip_border="#0B7A43"),
    "曜石黑": dict(bg="#101114",sidebar="#17181C",panel="#1A1B1F",panel_2="#232429",
        border="#2A2B31",text="#ECECEC",muted="#9AA0A6",accent="#5B8DEF",accent2="#7AA2F7",
        pill="#5B8DEF",pill_hover="#7AA2F7",green="#7BC98F",
        red="#F0A3A3",amber="#E5B567",cyan="#67B7D6",input="#1E1F24",hover="#24252B",soft="#1E2A44",light=False,
        tooltip_bg="#232429",tooltip_text="#F2F2F2",tooltip_border="#5B8DEF"),
}
TOAST_POSITIONS = (("下居中（默认）", "bottom_center"), ("右上", "top_right"),
                   ("左下角", "bottom_left"), ("右下", "bottom_right"))


def ui_scale_percent(settings):
    """UI zoom percentage from settings: 80-130, default 100."""
    if settings is None:
        return 100
    return _bounded_int(settings.value("ui_scale", 100), 100, 80, 130)


THEME_MIGRATION = {
    "蓝橙曜石": "曜石黑", "石墨黑": "曜石黑", "紫夜渐变": "曜石黑",
    "清爽白": "云白", "海盐晨光": "云白", "青瓷绿": "护眼绿",
}


def migrate_theme_name(name):
    """Map a 1.5.1 theme name to its 1.5.2 successor; unknown names pass through."""
    return THEME_MIGRATION.get(str(name), str(name))


MODULE_GROWTH_KEY = "modules/growth_enabled"
MODULE_POSTS_KEY = "modules/posts_enabled"
MODULES_ASKED_KEY = "modules/asked"


def modules_growth_enabled(settings):
    return is_true(settings.value(MODULE_GROWTH_KEY, True), True)


def modules_posts_enabled(settings):
    return is_true(settings.value(MODULE_POSTS_KEY, False), False)


def apply_module_gating(pages, settings):
    """Return copies of page rows with global module switches applied.

    Per-page flags in the store are preserved; gating only affects what the
    UI and the collector see, so re-enabling a module restores its pages.
    """
    growth = modules_growth_enabled(settings)
    posts = modules_posts_enabled(settings)
    gated = []
    for row in pages:
        copy = dict(row)
        copy["monitor_growth"] = bool(row.get("monitor_growth")) and growth
        copy["monitor_posts"] = bool(row.get("monitor_posts")) and posts
        gated.append(copy)
    return gated


BG = BG = THEME_PRESETS["云白"]["bg"]
SIDEBAR = THEME_PRESETS["云白"]["sidebar"]
PANEL = THEME_PRESETS["云白"]["panel"]
PANEL_2 = THEME_PRESETS["云白"]["panel_2"]
BORDER = THEME_PRESETS["云白"]["border"]
TEXT = THEME_PRESETS["云白"]["text"]
MUTED = THEME_PRESETS["云白"]["muted"]
ACCENT = THEME_PRESETS["云白"]["accent"]
GREEN = THEME_PRESETS["云白"]["green"]
RED = THEME_PRESETS["云白"]["red"]
AMBER = THEME_PRESETS["云白"]["amber"]
CYAN = THEME_PRESETS["云白"]["cyan"]
ACCENT2 = THEME_PRESETS["云白"]["accent2"]
PILL = THEME_PRESETS["云白"]["pill"]
PILL_HOVER = THEME_PRESETS["云白"]["pill_hover"]



def paint_brand(p, rect):
    """Logo C: a monitoring pulse on a flat navy tile. Identical in every theme."""
    p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing)
    x,y,w,h=rect.x(),rect.y(),rect.width(),rect.height()
    p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor("#1D4ED8"))
    p.drawRoundedRect(rect,w*.25,h*.25)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor("#FFFFFF"),w*.052,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    pts=[(.208,.50),(.354,.50),(.438,.312),(.521,.667),(.604,.396),(.688,.50),(.812,.50)]
    path=QPainterPath();path.moveTo(x+w*pts[0][0],y+h*pts[0][1])
    for xx,yy in pts[1:]:path.lineTo(x+w*xx,y+h*yy)
    p.drawPath(path)
    p.restore()


def ui_icon(kind,color=None):
    color=color or MUTED
    pm=QPixmap(64,64);pm.fill(Qt.GlobalColor.transparent)
    p=QPainter(pm);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color),3.1,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    def line(x1,y1,x2,y2):p.drawLine(QPointF(x1,y1),QPointF(x2,y2))
    if kind=="home":
        path=QPainterPath();path.moveTo(10,29);path.lineTo(32,11);path.lineTo(54,29)
        path.moveTo(17,25);path.lineTo(17,53);path.lineTo(47,53);path.lineTo(47,25)
        path.moveTo(27,53);path.lineTo(27,38);path.lineTo(37,38);path.lineTo(37,53);p.drawPath(path)
    elif kind in ("pages","id"):
        p.drawRoundedRect(QRectF(10,13,44,40),7,7)
        p.drawEllipse(QRectF(17,22,10,10));p.drawArc(QRectF(15,32,14,13),0,180*16)
        line(35,24,47,24);line(35,33,47,33);line(35,42,44,42)
    elif kind in ("history","trend"):
        line(12,10,12,53);line(12,53,54,53)
        path=QPainterPath();path.moveTo(20,42);path.lineTo(31,30);path.lineTo(40,34);path.lineTo(52,16);p.drawPath(path)
    elif kind in ("bell","alert"):
        path=QPainterPath();path.moveTo(15,45);path.quadTo(21,38,21,27)
        path.cubicTo(21,10,43,10,43,27);path.quadTo(43,38,49,45);path.closeSubpath();p.drawPath(path)
        p.drawArc(QRectF(26,45,12,12),180*16,180*16)
    elif kind=="browser":
        p.drawRoundedRect(QRectF(10,15,44,32),6,6);line(10,24,54,24)
        p.drawEllipse(QRectF(17,18,2,2));p.drawEllipse(QRectF(23,18,2,2));line(22,53,42,53);line(32,47,32,53)
    elif kind=="theme":
        p.drawEllipse(QRectF(12,12,40,40));p.drawEllipse(QRectF(22,20,7,7));p.drawEllipse(QRectF(34,18,7,7));p.drawEllipse(QRectF(40,31,7,7));line(24,43,33,43)
    elif kind=="settings":
        p.drawEllipse(QRectF(21,21,22,22));p.drawEllipse(QRectF(29,29,6,6))
        for angle in range(0,360,45):
            a=math.radians(angle);line(32+15*math.cos(a),32+15*math.sin(a),32+23*math.cos(a),32+23*math.sin(a))
    elif kind=="update":
        p.drawArc(QRectF(13,13,38,38),30*16,290*16);line(48,9,51,25);line(51,25,36,22)
    elif kind=="info":
        p.drawEllipse(QRectF(11,11,42,42));line(32,30,32,44);line(31,22,33,22)
    elif kind=="clock":
        p.drawEllipse(QRectF(11,11,42,42));line(32,21,32,33);line(32,33,41,38)
    elif kind=="people":
        p.drawEllipse(QRectF(16,13,15,15));p.drawEllipse(QRectF(37,17,11,11))
        p.drawArc(QRectF(11,33,26,24),0,180*16);p.drawArc(QRectF(35,35,19,18),0,180*16)
    elif kind=="play":
        path=QPainterPath();path.moveTo(23,14);path.lineTo(49,32);path.lineTo(23,50);path.closeSubpath();p.drawPath(path)
    elif kind=="pause":
        line(25,16,25,48);line(40,16,40,48)
    elif kind=="more":
        p.setBrush(QColor(color));p.setPen(Qt.PenStyle.NoPen)
        for yy in (17,32,47):p.drawEllipse(QPointF(32,yy),2.8,2.8)
    elif kind=="close":line(20,20,44,44);line(44,20,20,44)
    elif kind=="min":line(19,33,45,33)
    elif kind=="max":p.drawRoundedRect(QRectF(18,18,28,28),2,2)
    else:
        p.drawRoundedRect(QRectF(14,12,36,42),6,6)
        line(23,24,41,24);line(23,33,41,33);line(23,42,35,42)
    p.end();return QIcon(pm)


def icon_button(kind,tip,parent=None,size=40):
    b=QPushButton(parent);b.setObjectName("TopIconButton")
    b.setIcon(ui_icon(kind));b.setIconSize(QSize(21,21));b.setFixedSize(size,size)
    b.setCursor(Qt.CursorShape.PointingHandCursor);b.setToolTip(tip)
    b.setAccessibleName(tip);b.setProperty("iconKind",kind)
    return b


class CaptionHoverFilter(QObject):
    """Recolour the close glyph white while its red hover background shows."""
    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.Enter,QEvent.Type.Leave):
            if str(obj.property("iconKind") or "")=="close":
                obj.setIcon(ui_icon("close","#FFFFFF" if event.type()==QEvent.Type.Enter else MUTED))
            return False
        return super().eventFilter(obj,event)


class ElideLabel(QLabel):
    def __init__(self,text="",parent=None):
        super().__init__(str(text),parent)
        self.setMinimumWidth(0);self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.setTextFormat(Qt.TextFormat.PlainText)
    def paintEvent(self,event):
        # Single-line paint: a multi-line status/log text must not be drawn as
        # two vertically-clipped lines inside a one-line rect. Flatten newlines
        # (the full text stays available via tooltip / status history).
        _text=self.text().replace("\r\n"," ").replace("\n"," ").replace("\r"," ")
        p=QPainter(self);p.setFont(self.font());p.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        p.drawText(self.contentsRect(),self.alignment(),
            self.fontMetrics().elidedText(_text,Qt.TextElideMode.ElideRight,max(0,self.contentsRect().width())))
        p.end()


class ValueLabel(ElideLabel):
    """Numeric labels shrink locally instead of increasing a grid's minimum width."""
    def __init__(self,text="",large=22,parent=None):
        super().__init__(text,parent);self.large=large;self.setMinimumHeight(28)
    def paintEvent(self,event):
        p=QPainter(self);font=QFont(self.font());font.setBold(True)
        for px in range(self.large,12,-1):
            font.setPixelSize(px);p.setFont(font)
            if p.fontMetrics().horizontalAdvance(self.text())<=self.contentsRect().width():break
        p.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        p.drawText(self.contentsRect(),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(self.text(),Qt.TextElideMode.ElideRight,self.contentsRect().width()))
        p.end()


class DirectNumberSpinBox(QSpinBox):
    """Compact numeric field: click selects the value; valid typing commits via valueChanged."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setKeyboardTracking(True)
        self.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
    def focusInEvent(self,event):
        super().focusInEvent(event);QTimer.singleShot(0,self.selectAll)
    def mousePressEvent(self,event):
        super().mousePressEvent(event)
        if event.button()==Qt.MouseButton.LeftButton:QTimer.singleShot(0,self.selectAll)


class CheckDelegate(QStyledItemDelegate):
    """Centered indicator with full-cell hit testing and one integer state write per click."""
    @staticmethod
    def checked(value):
        return getattr(value, "value", value) == Qt.CheckState.Checked.value

    def paint(self, painter, option, index):
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.fillRect(option.rect, option.palette.color(QPalette.ColorRole.Highlight) if selected else option.palette.color(QPalette.ColorRole.AlternateBase if index.row()%2 else QPalette.ColorRole.Base))
        checked = self.checked(index.data(Qt.ItemDataRole.CheckStateRole))
        enabled = bool(index.flags() & Qt.ItemFlag.ItemIsEnabled and index.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        label = ("\u5f00\u542f" if checked else "\u5173\u95ed") if index.column() else ""
        box, space = 19, 7 if label else 0
        text_width = option.fontMetrics.horizontalAdvance(label) if label else 0
        total = box + space + text_width
        left = option.rect.left() + max(2, (option.rect.width()-total)//2)
        rect = QRect(left, option.rect.center().y()-box//2, box, box)
        painter.setOpacity(1.0 if enabled else .5)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(ACCENT if checked else MUTED), 1))
        painter.setBrush(QColor(ACCENT) if checked else option.palette.color(QPalette.ColorRole.Base))
        painter.drawRoundedRect(QRectF(rect), 4, 4)
        if checked:
            painter.setPen(QPen(QColor("#FFFFFF"),2,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            path=QPainterPath();path.moveTo(rect.x()+4,rect.y()+9);path.lineTo(rect.x()+8,rect.y()+13);path.lineTo(rect.x()+15,rect.y()+5)
            painter.drawPath(path)
        if label:
            painter.setPen(QColor(TEXT if checked else MUTED));painter.setFont(option.font)
            text_rect=QRect(left+box+space,option.rect.top(),text_width+1,option.rect.height())
            painter.drawText(text_rect,Qt.AlignmentFlag.AlignCenter,label)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        flags=index.flags()
        if not (flags & Qt.ItemFlag.ItemIsEnabled and flags & Qt.ItemFlag.ItemIsUserCheckable):
            return False
        kind=event.type()
        if kind in (QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonDblClick):
            if event.button()!=Qt.MouseButton.LeftButton:return False
            self._skip_release = kind==QEvent.Type.MouseButtonDblClick
            return option.rect.contains(event.position().toPoint())
        if kind==QEvent.Type.MouseButtonRelease:
            if event.button()!=Qt.MouseButton.LeftButton:return False
            if getattr(self,"_skip_release",False):
                self._skip_release=False;return True
            if not option.rect.contains(event.position().toPoint()):return False
        elif kind==QEvent.Type.KeyPress:
            if event.key() not in (Qt.Key.Key_Space,Qt.Key.Key_Select):return False
            if event.isAutoRepeat():return True
        else:
            return False
        value = Qt.CheckState.Unchecked.value if self.checked(index.data(Qt.ItemDataRole.CheckStateRole)) else Qt.CheckState.Checked.value
        return bool(model.setData(index, value, Qt.ItemDataRole.CheckStateRole))


class SortItem(QTableWidgetItem):
    def __init__(self,text="",key=None):
        super().__init__(str(text));self.sort_key=key if key is not None else str(text).casefold()
    def __lt__(self,other):
        a=self.sort_key;b=getattr(other,"sort_key",other.text().casefold())
        try:return a<b
        except TypeError:return str(a)<str(b)


_EMBEDDED_APP_ICON_PNG = (
    "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"
    "YII="
)

def make_app_icon():
    """Application/window/taskbar/tray icon, drawn from the current logo (Logo C).

    Drawing from code keeps the icon in step with the brand mark; a stale
    .ico/.png sitting next to the script can no longer override the logo.
    """
    icon = QIcon()
    for size in (16,20,24,32,48,64,128,256):
        pm = QPixmap(size,size);pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm);paint_brand(painter,QRectF(1,1,size-2,size-2));painter.end()
        icon.addPixmap(pm)
    return icon


TOAST_THEME_STYLES = {
    "云白": dict(bg="#FFFFFF", border="#DFDFD8", text="#1C1C1C", icon="#1D4ED8",
                 warn="#B45309", warn_glyph="#FFFFFF"),
    "护眼绿": dict(bg="#F2FAF4", border="#B7DFC4", text="#123B22", icon="#0B7A43",
                   warn="#B45309", warn_glyph="#FFFFFF"),
    "曜石黑": dict(bg="#232429", border="#3A3B42", text="#F2F2F2", icon="#5B8DEF",
                   warn="#E5B567", warn_glyph="#101114"),
}


def toast_badge_pixmap(kind, style):
    """20px filled-circle badge: info 'i', success check, warning '!'. Colours follow the theme.

    Drawn at 3x with devicePixelRatio set, so the badge stays sharp on HiDPI
    displays instead of being upscaled from a 1x pixmap. The circle is inset
    1px so antialiasing at its edge is never clipped.
    """
    if kind == "warning":
        fill, glyph_color = style["warn"], style["warn_glyph"]
    else:
        fill, glyph_color = style["icon"], "#FFFFFF"
    pm = QPixmap(60, 60); pm.setDevicePixelRatio(3.0); pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(fill)); painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(1, 1, 18, 18)
    painter.setPen(QPen(QColor(glyph_color), 2.2, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(QColor(glyph_color))
    if kind == "success":
        # Stroke only: drawPath with a brush would fill the implicitly
        # closed triangle, which is why the check used to look like a blob.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath(); path.moveTo(5.5, 10.5); path.lineTo(9.1, 14.1); path.lineTo(15.0, 6.4)
        painter.drawPath(path)
    elif kind == "warning":
        painter.drawLine(QPointF(10, 5.2), QPointF(10, 11.6))
        painter.drawEllipse(QRectF(8.9, 14.0, 2.2, 2.2))
    else:
        painter.drawLine(QPointF(10, 8.4), QPointF(10, 14.8))
        painter.drawEllipse(QRectF(8.9, 5.0, 2.2, 2.2))
    painter.end()
    return pm


def toast_style_for(theme_name):
    """Bubble colours for a theme name; legacy names migrate, unknown names fall back to 云白."""
    return TOAST_THEME_STYLES.get(migrate_theme_name(str(theme_name or "云白")), TOAST_THEME_STYLES["云白"])


class ToastNotice(QFrame):
    """One non-modal, click-through notice anchored by the toast-position setting."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("ToastNotice")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(self);layout.setContentsMargins(20,13,20,13);layout.setSpacing(10)
        self.icon = QLabel();self.icon.setFixedSize(20,20);layout.addWidget(self.icon)
        self.message = QLabel();self.message.setObjectName("ToastMessage")
        self.message.setTextFormat(Qt.TextFormat.PlainText);self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.message,1)
        self.timer = QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.hide)
        self._position = "bottom_center"
        shadow=QGraphicsDropShadowEffect(self);shadow.setBlurRadius(22);shadow.setOffset(0,4);shadow.setColor(QColor(0,0,0,165))
        self.setGraphicsEffect(shadow)
        self.hide()

    def show_message(self, text, duration_ms=3600, kind="info", position=None):
        self.timer.stop()
        kind = kind if kind in ("info", "success", "warning") else "info"
        self._position = str(position or getattr(self.window(), "toast_position", "bottom_center") or "bottom_center")
        self.last_kind = kind
        style = toast_style_for(getattr(self.window(), "theme_name", "云白"))
        self.icon.setPixmap(toast_badge_pixmap(kind, style))
        text = str(text)
        # Apply the themed 14px stylesheet BEFORE measuring, so the metrics
        # use the font that is actually painted (measuring first clipped the
        # last character). +80 covers margins + icon + spacing + overshoot.
        self.setStyleSheet(
            "QFrame#ToastNotice {background:" + style["bg"] + ";border:1px solid " + style["border"] + ";border-radius:14px;}"
            "QLabel#ToastMessage {color:" + style["text"] + ";font-size:14px;font-weight:650;background:transparent;border:0;}"
            "QLabel {background:transparent;border:0;}")
        # Palette fallback as well as the stylesheet: the text must stay
        # visible in every theme even if a stylesheet rule is overridden.
        _pal=self.message.palette();_pal.setColor(QPalette.ColorRole.WindowText,QColor(style["text"]));self.message.setPalette(_pal)
        parent = self.parentWidget()
        available = max(220, parent.width()-64)
        budget = max(120, min(available, 920) - 80)
        # Elide line by line: eliding the whole multi-line string at once
        # and relying on adjustSize() for the height can leave the second
        # line clipped or blank. Cap at 3 lines; keep the first lines intact.
        _fm=self.message.fontMetrics()
        _lines=[_fm.elidedText(_ln,Qt.TextElideMode.ElideRight,budget) if _ln else "" for _ln in str(text).split("\n")]
        while _lines and not _lines[0]:_lines.pop(0)
        while _lines and not _lines[-1]:_lines.pop()
        if not _lines:_lines=[""]
        if len(_lines)>3:
            _lines=_lines[:3]
            _lines[2]=_fm.elidedText(_lines[2]+" …",Qt.TextElideMode.ElideRight,budget)
        shown="\n".join(_lines)
        self.message.setText(shown)
        self.message.setToolTip(text if shown != text else "")
        _text_w=max((_fm.horizontalAdvance(_ln) for _ln in _lines),default=0)
        _width=min(available,920,max(260,_text_w+80))
        _height=26+len(_lines)*_fm.lineSpacing()+2
        self.setFixedSize(_width,_height)
        self.move(*toast_position(parent.width(),parent.height(),_width,_height,self._position))
        self.show();self.raise_()
        self.timer.start(_bounded_int(duration_ms,3600,3000,4000))

    def reposition(self):
        parent=self.parentWidget()
        if parent:
            self.move(*toast_position(parent.width(),parent.height(),self.width(),self.height(),getattr(self,"_position","bottom_center")))


def show_hint(owner, message, duration_ms=3600, kind="info"):
    """Route brief messages from subpages/dialogs to the application's single toast."""
    target = owner
    while target is not None:
        handler = getattr(target,"show_toast",None)
        if callable(handler):
            handler(str(message),duration_ms,kind)
            return
        target = target.parentWidget() if isinstance(target,QWidget) else None
    window = owner.window() if isinstance(owner,QWidget) else QApplication.activeWindow()
    if window:
        if not hasattr(window,"_local_hint"):
            window._local_hint = ToastNotice(window)
        window._local_hint.show_message(str(message),duration_ms,kind)


class LoginWorker(QObject):
    status = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.profile_dir = monitor_profile_dir()
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()


    def run(self):
        try:
            with BrowserCollector(profile_dir=self.profile_dir, show_browser=True) as collector:
                tab = collector.login_interactive()
                self.status.emit("已打开默认专用浏览器，请手动登录 Facebook；登录成功后关闭该窗口，再返回软件巡检。")
                while not self._stop.wait(0.4):
                    try:
                        if tab.is_closed():
                            break
                    except Exception:
                        break
                self.finished.emit("浏览器已关闭；如果你已完成脸书登录，登录会话已保存在默认专用浏览器资料中。")
        except Exception as exc:
            self.finished.emit("登录浏览器失败：" + str(exc)[:240])


class CollectWorker(QObject):
    result=pyqtSignal(dict)
    progress=pyqtSignal(int,int,str)
    finished=pyqtSignal(bool,str)

    def __init__(self, pages, visible=DEFAULT_SHOW_BROWSER, gap=DEFAULT_PAGE_GAP_SECONDS,
                 profile_dir=None, purpose="monitor", gap_range=None):
        super().__init__()
        self.pages = [dict(row) for row in pages]
        self.profile_dir = Path(profile_dir) if profile_dir is not None else monitor_profile_dir()
        self.visible = is_true(visible, DEFAULT_SHOW_BROWSER)
        self.gap = _bounded_int(gap, DEFAULT_PAGE_GAP_SECONDS, 0, 120)
        self._gap_lock = threading.Lock()
        self._gap_range=(self.gap,self.gap)
        if gap_range is not None:self.set_gap_range(*gap_range)
        self.purpose = purpose
        self._stop = threading.Event()
        self._pause = threading.Event()

    def set_gap(self, seconds):
        self.set_gap_range(seconds,seconds)

    def set_gap_range(self, low, high):
        low=_bounded_int(low,DEFAULT_PAGE_GAP_MIN,0,120)
        high=_bounded_int(high,DEFAULT_PAGE_GAP_MAX,0,120)
        with self._gap_lock:
            self._gap_range=(min(low,high),max(low,high))
            self.gap=int(round((low+high)/2))

    def current_gap(self):
        with self._gap_lock:
            low,high=self._gap_range
        return random.uniform(low,high) if low!=high else float(low)

    def stop(self):
        self._stop.set();self._pause.clear()

    def toggle_pause(self):
        if self._pause.is_set():self._pause.clear()
        else:self._pause.set()
        return self._pause.is_set()

    def _wait_ready(self):
        while self._pause.is_set():
            if self._stop.wait(.12):return False
        return not self._stop.is_set()

    def run(self):
        success=0;failure=0;total=len(self.pages);aborted=False
        try:
            with BrowserCollector(self.profile_dir,self.visible) as collector:
                for index,row in enumerate(self.pages,1):
                    if not self._wait_ready():aborted=True;break
                    self.progress.emit(index,total,("同步资料 " if self.purpose=="metadata" else "巡检 ")+display_name(row))
                    try:
                        record=collector.fetch_page(row,purpose=self.purpose)
                    except Exception as exc:
                        record={"page_id":row["page_id"],"error":str(exc)[:260],
                                "growth_ok":False,"posts_ok":False,"metadata_ok":False}
                    if record_needs_recheck(row,record,self.purpose) and not self._stop.is_set():
                        self.progress.emit(index,total,"自动复检 "+display_name(row))
                        try:
                            retry=collector.fetch_page(row,purpose=self.purpose)
                        except Exception as exc:
                            retry={"page_id":row["page_id"],"error":str(exc)[:260],
                                   "growth_ok":False,"posts_ok":False,"metadata_ok":False}
                        record=merge_recheck_record(record,retry,row,self.purpose)
                    checks=[]
                    if self.purpose=="metadata":checks=[bool(record.get("metadata_ok"))]
                    else:
                        if row.get("monitor_growth"):checks.append(bool(record.get("growth_ok")))
                        if row.get("monitor_posts"):checks.append(bool(record.get("posts_ok")))
                    good=bool(checks and all(checks))
                    record["ok"]=good;record["purpose"]=self.purpose
                    self.result.emit(record)
                    if good:success+=1
                    else:failure+=1
                    self.progress.emit(index,total,f"已完成 {index} / {total}")
                    if index<total:
                        remaining=self.current_gap()
                        while remaining>0:
                            if not self._wait_ready():aborted=True;break
                            tick=min(.2,remaining)
                            if self._stop.wait(tick):aborted=True;break
                            remaining-=tick
                        if aborted:break
            task="资料同步" if self.purpose=="metadata" else "主页巡检"
            self.finished.emit(not aborted and failure==0,
                f"{task}{'已停止' if aborted else '完成'} · 完整成功 {success} / 部分或失败 {failure} / 共 {total}")
        except Exception as exc:
            self.finished.emit(False,"任务异常："+str(exc)[:300])


class ConnectorCollectWorker(CollectWorker):
    """Distribute one round across the connected browsers (no cap) and auto-recheck ambiguity.

    A name/post result that cannot be confirmed is retried once.  When another selected
    browser is online the recheck prefers that browser; with only one browser it retries
    the same connector.  A successful first-pass follower observation is preserved so the
    corrective pass never creates a duplicate follower sample.
    """
    def __init__(self,pages,bridge,instance_ids,gap=8,purpose='monitor',gap_range=None):
        super().__init__(pages,gap=gap,purpose=purpose,gap_range=gap_range)
        if isinstance(instance_ids,str):instance_ids=[instance_ids]
        self.bridge=bridge;self.instance_ids=list(dict.fromkeys(str(x) for x in instance_ids if x))

    def _record_good(self,row,record):
        checks=[]
        if self.purpose=='metadata':checks=[bool(record.get('metadata_ok'))]
        else:
            if row.get('monitor_growth'):checks.append(bool(record.get('growth_ok')))
            if row.get('monitor_posts'):checks.append(bool(record.get('posts_ok')))
        return bool(checks and all(checks))

    def _live_online(self):
        """Online, unblocked connectors right now: the start snapshot plus
        any browser that came online later. A snapshot id that went offline
        or was blocked meanwhile drops out."""
        try:
            rows=self.bridge.clients()
        except Exception:
            return [cid for cid in self.instance_ids if self.bridge.online(cid)]
        live=[r['instance_id'] for r in rows if r.get('online') and not r.get('blocked')]
        ordered=[cid for cid in self.instance_ids if cid in live]
        ordered+=[cid for cid in live if cid not in ordered]
        return ordered

    def _recheck_connector(self,source_cid,record=None):
        online=self._live_online()
        others=[cid for cid in online if cid!=source_cid]
        diag=str((record or {}).get('diagnosis_code') or '')
        # Login/offline: another profile cannot fix this account's login
        # state, and switching accounts mid-round would be surprising.
        # Layout/parse failures: another browser may render differently.
        if diag in ('login',):
            return source_cid if source_cid in online else (online[0] if online else '')
        if others and diag in ('empty','filtered','follower_parse','post_parse'):
            return random.choice(others)
        if others and diag in ('follower_empty','timeout'):
            return source_cid if source_cid in online else others[0]
        if others:return random.choice(others)
        return source_cid if source_cid in online else (online[0] if online else '')

    def run(self):
        total=len(self.pages);success=0;failure=0;finalized=0
        if not self.instance_ids:
            self.finished.emit(False,'没有可用浏览器连接器');return
        online=[cid for cid in self.instance_ids if self.bridge.online(cid)]
        if not online:
            self.finished.emit(False,'连接器中断：所有已选择浏览器均已离线');return
        self.instance_ids=online
        self._spawned_ids=set(self.instance_ids)
        if total < len(self.instance_ids):
            self.finished.emit(False,f'任务数 {total} 少于当前在线连接器 {len(self.instance_ids)} 个，请减少连接器');return

        pages=list(self.pages);random.shuffle(pages)
        workq=queue.Queue();outq=queue.Queue();threads=[]
        initial={cid:pages[i] for i,cid in enumerate(self.instance_ids)}
        for row in pages[len(self.instance_ids):]:workq.put(row)
        remaining={'count':total};lock=threading.Lock()

        def mark_done():
            with lock:remaining['count']-=1
        def remaining_count():
            with lock:return remaining['count']

        def lane_worker(cid,first_row):
            row=first_row
            try:
                while not self._stop.is_set():
                    if not self._wait_ready():break
                    if row is None:
                        if remaining_count()<=0:break
                        try:row=workq.get(timeout=.35)
                        except queue.Empty:
                            if remaining_count()<=0:break
                            if not self.bridge.online(cid):
                                outq.put(('offline',cid,'浏览器连接已断开'));break
                            continue
                    if not self.bridge.online(cid):
                        workq.put(row);row=None;outq.put(('offline',cid,'浏览器连接已断开'));break
                    try:
                        payload=self.bridge.request(cid,row,self.purpose,self._stop,timeout=120)
                        if self._stop.is_set():
                            workq.put(row);row=None;break
                        record=connector_record(row,payload,self.purpose)
                    except ConnectorError as exc:
                        if not self.bridge.online(cid):
                            workq.put(row);row=None;outq.put(('offline',cid,str(exc)));break
                        record={'page_id':row['page_id'],'error':str(exc),'growth_ok':False,'posts_ok':False,'metadata_ok':False,
                                'name_error':str(exc),'posts_error':str(exc)}
                    mark_done();outq.put(('result',cid,dict(row),record));row=None
                    if remaining_count()<=0:break
                    remaining_wait=self.current_gap()
                    while remaining_wait>0 and not self._stop.is_set():
                        if not self._wait_ready():break
                        tick=min(.2,remaining_wait)
                        if self._stop.wait(tick):break
                        remaining_wait-=tick
            finally:outq.put(('done',cid))

        for cid in self.instance_ids:
            t=threading.Thread(target=lane_worker,args=(cid,initial[cid]),name='POM-connector-'+cid[:8],daemon=True)
            threads.append(t);t.start()

        spawned=set(self.instance_ids);last_scan=time.monotonic()
        done=0;offline=set();first_seen=0;rechecks=[]
        while done<len(threads):
            # Browsers that came online after the round started join while
            # there is still queued work. Scan on every loop pass (results
            # arrive too steadily for the Empty branch alone to trigger it);
            # a lane with nothing to pull exits on its own, so this can
            # never stall the round.
            if (not self._stop.is_set() and remaining_count()>0 and not workq.empty()
                    and time.monotonic()-last_scan>=0.5):
                last_scan=time.monotonic()
                for cid in self._live_online():
                    if cid in spawned or not self.bridge.online(cid):continue
                    spawned.add(cid);self._spawned_ids.add(cid)
                    t=threading.Thread(target=lane_worker,args=(cid,None),name='POM-connector-'+cid[:8],daemon=True)
                    threads.append(t);t.start()
            try:item=outq.get(timeout=.25)
            except queue.Empty:
                if not any(t.is_alive() for t in threads):break
                continue
            kind=item[0]
            if kind=='done':done+=1;continue
            if kind=='offline':offline.add(item[1]);continue
            _,cid,row,record=item;first_seen+=1
            if record_needs_recheck(row,record,self.purpose) and not self._stop.is_set():
                rechecks.append((cid,row,record))
                self.progress.emit(first_seen,total,f'首检 {first_seen} / {total} · 待自动复检')
                continue
            good=self._record_good(row,record);record['ok']=good;record['purpose']=self.purpose
            self.result.emit(record);finalized+=1
            if good:success+=1
            else:failure+=1
            self.progress.emit(first_seen,total,f'并行巡检 {first_seen} / {total}')

        for t in threads:t.join(timeout=1)

        # Recheck only the ambiguous subset. Prefer another browser when possible.
        for source_cid,row,first in rechecks:
            if self._stop.is_set():break
            target=self._recheck_connector(source_cid,first)
            second={'page_id':row['page_id'],'metadata_ok':False,'growth_ok':False,'posts_ok':False}
            if target:
                retry_row=dict(row)
                retry_purpose='metadata'
                if self.purpose=='monitor' and row.get('monitor_posts') and not first.get('posts_ok'):
                    retry_purpose='monitor';retry_row['monitor_growth']=False;retry_row['monitor_posts']=True
                elif self.purpose=='monitor' and row.get('monitor_growth') and not first.get('growth_ok'):
                    retry_purpose='monitor';retry_row['monitor_growth']=True;retry_row['monitor_posts']=False
                try:
                    self.progress.emit(finalized+1,total,'自动复检 '+display_name(row)+(' · 换浏览器' if target!=source_cid else ' · 当前浏览器'))
                    payload=self.bridge.request(target,retry_row,retry_purpose,self._stop,timeout=120,retry=True)
                    second=connector_record(retry_row,payload,retry_purpose)
                except ConnectorError as exc:
                    second.update(error=str(exc),name_error=str(exc),posts_error=str(exc))
            merged=merge_recheck_record(first,second,row,self.purpose)
            merged['recheck_connector_changed']=bool(target and target!=source_cid)
            good=self._record_good(row,merged);merged['ok']=good;merged['purpose']=self.purpose
            self.result.emit(merged);finalized+=1
            if good:success+=1
            else:failure+=1

        aborted=self._stop.is_set() and finalized<total
        if finalized<total and not aborted:
            active=self._live_online()
            if not active:
                self.finished.emit(False,f'连接器中断：所有已选择浏览器均已离线，当前轮次已停止 · 已处理 {finalized}/{total}');return
            self.finished.emit(False,f'浏览器连接异常，本轮未完成 · 已处理 {finalized}/{total}');return
        task='资料同步' if self.purpose=='metadata' else '主页巡检'
        extra=f' · {len(offline)} 个浏览器中途离线' if offline else ''
        if rechecks:extra+=f' · 自动复检 {len(rechecks)} 个主页'
        self.finished.emit(not aborted and failure==0 and finalized==total,
            f"{task}{'已停止' if aborted else '完成'} · 完整成功 {success} / 部分或失败 {failure} / 共 {total} · 使用 {len(getattr(self,'_spawned_ids',self.instance_ids))} 个浏览器{extra}")


def connector_notice_colors(theme_name):
    """Banner background + warning-note foreground for the connector dialog,
    per theme. The light amber banner is unreadable in the dark theme, so
    dark themes get a dark amber surface and the preset's light amber."""
    preset = THEME_PRESETS.get(theme_name) or THEME_PRESETS["云白"]
    if preset.get("light", True):
        return "#FDF3E3", preset.get("amber", "#B45309")
    return "#33291A", preset.get("amber", "#E5B567")


class BrowserConnectionsDialog(QDialog):
    """Zero-configuration connector view (A3-final).

    Fixed size; the list scrolls internally and the window never grows.
    Every online browser is used automatically with no cap. The checkbox
    column only selects rows for block/delete actions: the action buttons
    appear in the middle of the checked row, between the version note and
    the status column, which never moves.
    """
    FILTERS = (("all", "全部"), ("online", "在线"), ("offline", "离线"), ("blocked", "已停用"))

    def __init__(self, owner):
        super().__init__(owner); self.owner = owner; self.bridge = owner.connector
        self.setWindowTitle('浏览器连接'); self.setFixedSize(560, 450)
        layout = QVBoxLayout(self); layout.setContentsMargins(16, 14, 16, 14); layout.setSpacing(8)
        title_row = QHBoxLayout(); title_row.setSpacing(8)
        title = QLabel('浏览器连接'); title.setObjectName('DialogTitle'); title_row.addWidget(title)
        title_row.addStretch()
        self.retry_button = QPushButton('重新检测'); self.retry_button.clicked.connect(self.retry)
        title_row.addWidget(self.retry_button)
        layout.addLayout(title_row)
        self.chips_box = QHBoxLayout(); self.chips_box.setSpacing(0); layout.addLayout(self.chips_box)
        self.chips = None; self._filter = "all"; self._chip_counts = None
        self.status_label = QLabel(); self.status_label.setObjectName('SmallMuted')
        self.status_label.setWordWrap(True); layout.addWidget(self.status_label)
        self.banner = QWidget()
        # ID-scoped: a bare `background:` rule would also paint every child
        # widget (including the PrimaryButton, whose white text then sat on
        # a light background and vanished).
        self.banner.setObjectName("ConnectorBanner")
        self._apply_banner_theme()
        banner_lay = QHBoxLayout(self.banner)
        banner_lay.setContentsMargins(12, 6, 12, 6); banner_lay.setSpacing(8)
        self.banner_label = QLabel(); self.banner_label.setObjectName('SmallMuted')
        banner_lay.addWidget(self.banner_label, 1)
        self.export_connector_button = QPushButton('获取连接器')
        self.export_connector_button.setObjectName('PrimaryButton')
        self.export_connector_button.clicked.connect(self.export_connector)
        banner_lay.addWidget(self.export_connector_button)
        layout.addWidget(self.banner)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(('', '浏览器备注', '', '', '状态'))
        self.table.verticalHeader().hide(); self.table.setShowGrid(False); self.table.setAlternatingRowColors(True)
        # No row selection and no keyboard focus: clicking a row must not
        # paint a selection/focus frame over the alternating background.
        # Checkboxes still toggle by mouse; the remark label below is
        # drag-selectable for copy. Nothing else in a row is clickable.
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setColumnWidth(0, 40); self.table.setColumnWidth(2, 96)
        self.table.setColumnWidth(3, 148); self.table.setColumnWidth(4, 88)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setItemDelegateForColumn(0, CheckDelegate(self.table))
        layout.addWidget(self.table, 1)
        self.rows = []; self._signature = None; self._loading = False
        self._checked = set(); self._action_widgets = {}
        self.table.itemChanged.connect(self._item_changed)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(900); self.refresh()

    def _row_matches(self, row):
        if self._filter == "online":
            return bool(row['online']) and not row.get('blocked')
        if self._filter == "offline":
            return not row['online'] and not row.get('blocked')
        if self._filter == "blocked":
            return bool(row.get('blocked'))
        return True

    def _rebuild_chips(self, counts):
        while self.chips_box.count():
            item = self.chips_box.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        total, online, offline, blocked = counts
        options = [(f"全部 {total}", "all"), (f"在线 {online}", "online"),
                   (f"离线 {offline}", "offline"), (f"已停用 {blocked}", "blocked")]
        self.chips = SegmentedChoice(options, self._filter)
        self.chips.changed.connect(self._on_filter_changed)
        self.chips_box.addWidget(self.chips)

    def _on_filter_changed(self):
        if self.chips is not None:
            self._filter = self.chips.currentData()
        self._signature = None; self.refresh()

    def _item_changed(self, item):
        if self._loading or item.column() != 0:
            return
        cid = str(item.data(Qt.ItemDataRole.UserRole) or '')
        if not cid:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._checked.add(cid)
        else:
            self._checked.discard(cid)
        holder = self._action_widgets.get(cid)
        if holder is not None:
            for btn in holder.findChildren(QPushButton):
                btn.setVisible(cid in self._checked)

    def refresh(self):
        try:
            if not self.bridge._running:
                self.bridge.start()
        except Exception as exc:
            self.bridge.error = str(exc)
        rows = sorted(self.bridge.clients(), key=lambda r: (r.get('blocked', False), not r['online'], r['identity'].get('profile_name', ''), r['instance_id']))
        self.rows = rows
        online = [r for r in rows if r['online'] and not r.get('blocked')]
        offline = [r for r in rows if not r['online'] and not r.get('blocked')]
        blocked = [r for r in rows if r.get('blocked')]
        counts = (len(rows), len(online), len(offline), len(blocked))
        if counts != self._chip_counts:
            self._chip_counts = counts
            self._rebuild_chips(counts)
        signature = json.dumps(rows, sort_keys=True) + self._filter
        if signature == self._signature:
            return
        self._signature = signature
        self._checked = {cid for cid in self._checked if any(r['instance_id'] == cid for r in rows)}
        visible = [r for r in rows if self._row_matches(r)]
        self._loading = True; self.table.blockSignals(True)
        self.table.setRowCount(len(visible))
        self._action_widgets = {}
        for i, row in enumerate(visible):
            identity = row['identity']; cid = row['instance_id']
            marker = QTableWidgetItem('')
            marker.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
            marker.setData(Qt.ItemDataRole.UserRole, cid)
            marker.setCheckState(Qt.CheckState.Checked if cid in self._checked else Qt.CheckState.Unchecked)
            marker.setTextAlignment(Qt.AlignmentFlag.AlignCenter); self.table.setItem(i, 0, marker)
            name = connector_display_name(identity, cid)
            # A label, not an item: dragging across it selects the text for
            # copying, and a plain label never draws a selection frame.
            # Transparent background keeps the alternating row colour.
            name_label = QLabel(str(name))
            name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_label.setToolTip(html.escape(str(name)))
            name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.table.setCellWidget(i, 1, name_label)
            outdated = connector_needs_update(identity or {})
            note = QTableWidgetItem('版本较旧' if outdated else '')
            note.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if outdated:
                note.setForeground(QColor(connector_notice_colors(getattr(self.owner, "theme_name", "云白"))[1]))
            self.table.setItem(i, 2, note)
            holder = QWidget(); holder_lay = QHBoxLayout(holder)
            holder_lay.setContentsMargins(0, 0, 0, 0); holder_lay.setSpacing(6)
            # The theme's generic QPushButton padding (8px 13px) clipped the
            # two-character labels inside a fixed 52px button on real
            # machines. Small inline padding + a 64px floor keeps the text
            # whole at every zoom level.
            toggle_btn = QPushButton('启用' if row.get('blocked') else '停用')
            toggle_btn.setFixedHeight(24); toggle_btn.setMinimumWidth(64)
            toggle_btn.setStyleSheet("QPushButton{padding:2px 10px;}")
            toggle_btn.clicked.connect(lambda _=False, _cid=cid: self._toggle_row(_cid))
            delete_btn = QPushButton('删除'); delete_btn.setFixedHeight(24); delete_btn.setMinimumWidth(64)
            delete_btn.setStyleSheet("QPushButton{padding:2px 10px;}")
            delete_btn.clicked.connect(lambda _=False, _cid=cid, _name=name: self._delete_row(_cid, _name))
            holder_lay.addWidget(toggle_btn); holder_lay.addWidget(delete_btn); holder_lay.addStretch()
            self.table.setCellWidget(i, 3, holder)
            # QTableView re-shows the cell widget itself on layout, so the
            # per-row buttons (not the holder) carry the checked visibility.
            toggle_btn.setVisible(cid in self._checked)
            delete_btn.setVisible(cid in self._checked)
            self._action_widgets[cid] = holder
            status = '已停用' if row.get('blocked') else ('在线' if row['online'] else '离线')
            scell = QTableWidgetItem(status); scell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            scell.setToolTip(html.escape(status)); self.table.setItem(i, 4, scell)
            self.table.setRowHeight(i, 34)
        self.table.blockSignals(False); self._loading = False
        if self.bridge.error:
            self.status_label.setText('连接服务异常：' + self.bridge.error)
        elif not online:
            self.status_label.setText('未检测到在线连接器')
        elif blocked:
            self.status_label.setText(f'{len(online)} 个在线 · 全部自动使用 · {len(blocked)} 个已停用')
        else:
            self.status_label.setText(f'{len(online)} 个在线 · 全部自动使用')
        self._refresh_connector_bundle_state(rows)

    def export_connector(self):
        save_bundled_connector(self)

    def _apply_banner_theme(self):
        bg, _amber = connector_notice_colors(getattr(self.owner, "theme_name", "云白"))
        self.banner.setStyleSheet(f"QWidget#ConnectorBanner{{background:{bg};border-radius:8px;}}")

    def _refresh_connector_bundle_state(self, rows):
        self._apply_banner_theme()
        online = [r for r in rows if r.get('online') and not r.get('blocked')]
        outdated = [r for r in online if connector_needs_update(r.get('identity') or {})]
        # Keep the browser window clean: when the installed connector is current,
        # there is no download/export action here. Settings always keeps a manual export entry.
        if outdated:
            self.banner_label.setText(f'{len(outdated)} 个连接器版本较旧')
            self.export_connector_button.setText('更新连接器')
            self.export_connector_button.setToolTip(f'导出内置连接器 v{BUNDLED_CONNECTOR_VERSION}')
            self.banner.setVisible(True)
        elif not online:
            self.banner_label.setText('未检测到在线连接器')
            self.export_connector_button.setText('获取连接器')
            self.export_connector_button.setToolTip(f'导出内置连接器 v{BUNDLED_CONNECTOR_VERSION}')
            self.banner.setVisible(True)
        else:
            self.banner.setVisible(False)
        return len(outdated)

    def identify(self):
        row = next((r for r in self.rows if r['instance_id'] in self._checked), None)
        if not row:
            return
        try:
            self.bridge.identify(row['instance_id'])
        except Exception as exc:
            show_hint(self, str(exc), kind="warning")

    def retry(self):
        self._signature = None; self.refresh(); self.owner.refresh_connector_summary()
        show_hint(self, '正在自动检测本机浏览器连接器')

    def _toggle_row(self, cid):
        row = next((r for r in self.rows if r['instance_id'] == cid), None)
        if row is None:
            return
        if row.get('blocked'):
            self.bridge.allow(cid); show_hint(self, '已启用，连接器会自动重新连接', kind="success")
        else:
            self.bridge.revoke(cid); show_hint(self, '已停用该浏览器连接', kind="success")
        self._signature = None; self.refresh(); self.owner.refresh_connector_summary()

    def _delete_row(self, cid, name):
        row = next((r for r in self.rows if r['instance_id'] == cid), None)
        if row is None:
            return
        if row.get('online') and not row.get('blocked'):
            show_hint(self, '请先停用该连接，再删除旧记录', kind="warning"); return
        msg = QMessageBox(self)
        msg.setWindowTitle('删除连接记录')
        msg.setText(f'确定要删除「{name}」的连接记录吗？\n重新检测时可能会再次发现这个浏览器。')
        cancel_btn = msg.addButton('取消', QMessageBox.ButtonRole.RejectRole)
        # AcceptRole (not DestructiveRole): only Accept/Reject roles close the
        # dialog on click, so a DestructiveRole button would leave exec() hung.
        delete_btn = msg.addButton('删除', QMessageBox.ButtonRole.AcceptRole)
        msg.setDefaultButton(cancel_btn)
        msg.exec()
        if msg.clickedButton() is not delete_btn:
            return
        try:
            self.bridge.forget(cid)
        except Exception as exc:
            show_hint(self, str(exc), kind="warning"); return
        self._checked.discard(cid)
        self._signature = None; self.refresh(); self.owner.refresh_connector_summary()
        show_hint(self, '旧连接记录已删除', kind="success")


class MenuButton(QPushButton):
    """Capsule select control: the whole capsule opens a styled menu.

    Replaces the native QComboBox box in the dashboard, alerts and manager
    filters and in the batch-settings dialog. The capsule itself is the
    control; there is no separate dropdown arrow box. QMenu styling lives
    in apply_style, so the popup matches the flat theme instead of the
    platform combo box.
    """
    changed = pyqtSignal()

    def __init__(self, options, current=None, parent=None):
        super().__init__(parent)
        self.setObjectName("MenuButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self._options = []
        self._current = None
        self._menu = QMenu(self)
        self.set_options(options, current=current, emit=False)
        self.clicked.connect(self._show_menu)

    def set_options(self, options, current=None, keep_current=True, emit=False):
        options = [(str(label), key) for label, key in options]
        self._options = options
        keys = [k for _, k in options]
        if current is not None and current in keys:
            self._current = current
        elif keep_current and self._current in keys:
            pass
        elif options:
            self._current = options[0][1]
        else:
            self._current = None
        self._menu.clear()
        for label, key in options:
            act = self._menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(key == self._current)
            act.triggered.connect(lambda _=False, k=key: self.setCurrentData(k))
        self._refresh_text()

    def _refresh_text(self):
        label = next((lab for lab, k in self._options if k == self._current), "")
        self.setText((label or "选择") + "  ▾")

    def _show_menu(self):
        pos = self.mapToGlobal(QPoint(0, self.height() + 4))
        self._menu.popup(pos)

    def currentData(self):
        return self._current

    def setCurrentData(self, key, emit=True):
        if key == self._current and emit:
            return
        if key not in [k for _, k in self._options]:
            return
        self._current = key
        for act in self._menu.actions():
            act.setChecked(act.text() == next((lab for lab, k in self._options if k == key), ""))
        self._refresh_text()
        if emit:
            self.changed.emit()

    def setCurrentIndex(self, index, emit=False):
        if 0 <= index < len(self._options):
            self.setCurrentData(self._options[index][1], emit=emit)

    def currentIndex(self):
        for i, (_, k) in enumerate(self._options):
            if k == self._current:
                return i
        return -1

    def findData(self, key):
        for i, (_, k) in enumerate(self._options):
            if k == key:
                return i
        return -1


class SegmentedChoice(QFrame):
    """Two/three-way segmented capsule choice (import mode, etc.)."""
    changed = pyqtSignal()

    def __init__(self, options, current=None, parent=None):
        super().__init__(parent)
        self.setObjectName("SegmentedChoice")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(3)
        self._buttons = {}
        self._current = None
        for label, key in options:
            btn = QPushButton(str(label))
            btn.setObjectName("SegmentedButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, k=key: self.setCurrentData(k))
            lay.addWidget(btn)
            self._buttons[key] = btn
        self.setCurrentData(current if current is not None else (options[0][1] if options else None), emit=False)

    def currentData(self):
        return self._current

    def setCurrentData(self, key, emit=True):
        if key not in self._buttons:
            return
        changed = key != self._current
        self._current = key
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)
        if emit and changed:
            self.changed.emit()


class SwitchToggle(QWidget):
    """Flat on/off switch used by the settings module section."""
    toggled = pyqtSignal(bool)

    def __init__(self, checked=False, parent=None):
        super().__init__(parent);self._checked = bool(checked)
        self.setFixedSize(40, 22);self.setCursor(Qt.CursorShape.PointingHandCursor)

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        checked = bool(checked)
        if checked != self._checked:
            self._checked = checked;self.update();self.toggled.emit(checked)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked);event.accept()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(ACCENT if self._checked else BORDER))
        p.drawRoundedRect(QRectF(1, 1, 38, 20), 10, 10)
        p.setBrush(QColor("#FFFFFF"));p.drawEllipse(QRectF(19 if self._checked else 3, 3, 16, 16));p.end()


class ClickableFrame(QFrame):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit();event.accept()
        else:
            super().mousePressEvent(event)


class OptionCard(ClickableFrame):
    """Selectable card for the first-run module dialog and theme picker."""

    def __init__(self, title, description, parent=None):
        super().__init__(parent);self.setObjectName("OptionCard");self._selected = False
        layout = QVBoxLayout(self);layout.setContentsMargins(16, 13, 16, 13);layout.setSpacing(3)
        self.title_label = QLabel(title);self.title_label.setObjectName("OptionCardTitle");layout.addWidget(self.title_label)
        self.desc_label = QLabel(description);self.desc_label.setObjectName("SmallMuted");self.desc_label.setWordWrap(True);layout.addWidget(self.desc_label)
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        self.desc_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)

    def setSelected(self, selected):
        self._selected = bool(selected);self.setProperty("selected", self._selected)
        self.style().unpolish(self);self.style().polish(self);self.update()

    def isSelected(self):
        return self._selected


class BrandMark(QWidget):
    def __init__(self,size=40,parent=None):
        super().__init__(parent);self.setFixedSize(size,size)
        self.setToolTip("原创监控图形标志")
    def paintEvent(self,event):
        p=QPainter(self);paint_brand(p,QRectF(1,1,self.width()-2,self.height()-2));p.end()


class DraggableHeader(QFrame):
    """Allow dragging and double-click maximizing the custom title bar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.window().isMaximized():
            self._drag_pos = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton and not self.window().isMaximized():
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().showNormal() if self.window().isMaximized() else self.window().showMaximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


def resolve_avatar_path(page_id="", preferred=""):
    """Resolve the live page avatar first, then the shared ID cache."""
    preferred=str(preferred or "").strip()
    if preferred:
        try:
            p=Path(preferred)
            if p.is_file() and p.stat().st_size>100:return str(p)
        except OSError:pass
    pid=str(page_id or "").strip()
    if pid:
        try:
            cached=AVATAR_DIR/(pid+".png")
            if cached.is_file() and cached.stat().st_size>100:return str(cached)
        except OSError:pass
    return ""


class AvatarWidget(QWidget):
    def __init__(self, name="", path="", size=52, parent=None, page_id=""):
        super().__init__(parent)
        self.name = name or "P"
        self.path = resolve_avatar_path(page_id,path)
        self.setFixedSize(size,size)
        self.image = QPixmap(self.path) if self.path else QPixmap()
        if self.image.isNull():
            self.setToolTip("头像与 ID管理共用同一缓存；正常巡检时自动更新。")
        else:
            self.setToolTip("已缓存的真实主页头像")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0,0,self.width(),self.height())
        clip = QPainterPath(); clip.addRoundedRect(r.adjusted(1,1,-1,-1), self.width()*.28, self.height()*.28); p.setClipPath(clip)
        if not self.image.isNull():
            scaled = self.image.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation)
            sx=(scaled.width()-self.width())//2; sy=(scaled.height()-self.height())//2
            p.drawPixmap(0,0,scaled,sx,sy,self.width(),self.height())
        else:
            p.fillRect(self.rect(),QColor(ACCENT))
            p.setClipping(False); p.setPen(QColor("white"))
            p.setFont(QFont("Microsoft YaHei UI",max(11,self.width()//3),QFont.Weight.DemiBold))
            p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,self.name[:1].upper())
        p.setClipping(False); p.setPen(QPen(QColor(BORDER),1.1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(.7,.7,-.7,-.7), self.width()*.28, self.height()*.28)




class BadgeButton(QPushButton):
    """Push button with a small red count badge at its top-right corner."""
    def __init__(self,text,parent=None):
        super().__init__(text,parent)
        self.badge=QLabel("",self);self.badge.setObjectName("ChipBadge")
        self.badge.setFixedSize(17,17);self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter);self.badge.hide()
    def set_badge(self,count):
        count=int(count or 0)
        if count>0:
            self.badge.setText(str(count) if count<100 else "99+");self.badge.show()
        else:
            self.badge.hide()
        self._place_badge()
    def resizeEvent(self,event):
        super().resizeEvent(event);self._place_badge()
    def _place_badge(self):
        self.badge.move(max(0,self.width()-16),0)


class FlowLayout(QLayout):
    """Row of widgets that wraps onto extra lines when the row is too narrow.

    Used for the dashboard filter chips: at a wide window they stay on one
    line next to the search box; when the window is narrowed they wrap
    instead of being squeezed over the search box.
    """
    def __init__(self,parent=None,hspacing=8,vspacing=6):
        super().__init__(parent);self._items=[];self._hspacing=hspacing;self._vspacing=vspacing
        self.setContentsMargins(0,0,0,0)
    def addItem(self,item):self._items.append(item)
    def count(self):return len(self._items)
    def itemAt(self,index):return self._items[index] if 0<=index<len(self._items) else None
    def takeAt(self,index):return self._items.pop(index) if 0<=index<len(self._items) else None
    def expandingDirections(self):return Qt.Orientation(0)
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):return self._do_layout(QRect(0,0,width,0),True)
    def setGeometry(self,rect):
        super().setGeometry(rect);self._do_layout(rect,False)
    def sizeHint(self):
        width=0;height=0
        for item in self._items:
            widget=item.widget()
            if widget is not None and widget.isHidden():continue
            width+=item.sizeHint().width()+self._hspacing;height=max(height,item.sizeHint().height())
        return QSize(max(0,width-self._hspacing),height)
    def minimumSize(self):
        width=0;height=0
        for item in self._items:
            widget=item.widget()
            if widget is not None and widget.isHidden():continue
            width=max(width,item.minimumSize().width());height=max(height,item.minimumSize().height())
        return QSize(width,height)
    def _do_layout(self,rect,test_only):
        left=rect.x();y=rect.y();line_height=0;x=left
        for item in self._items:
            widget=item.widget()
            if widget is not None and widget.isHidden():continue
            hint=item.sizeHint().expandedTo(item.minimumSize())
            if x+hint.width()>rect.right()+1 and line_height>0:
                x=left;y+=line_height+self._vspacing;line_height=0
            if not test_only:item.setGeometry(QRect(QPoint(x,y),hint))
            x+=hint.width()+self._hspacing;line_height=max(line_height,hint.height())
        return y+line_height-rect.y()


class ChipRow(QWidget):
    """Container whose height follows the wrapped FlowLayout."""
    def __init__(self,parent=None):
        super().__init__(parent);self.setLayout(FlowLayout(self))
        policy=self.sizePolicy();policy.setHeightForWidth(True);self.setSizePolicy(policy)
    def heightForWidth(self,width):return self.layout().heightForWidth(width)
    def sizeHint(self):return self.layout().sizeHint()


class RailAvatarButton(QPushButton):
    """One avatar in the sidebar alert rail. Click copies the page ID."""
    def __init__(self,name,avatar_path,page_id,size,ring_color,on_copy):
        super().__init__();self.page_id=str(page_id);self._on_copy=on_copy
        self.setFixedSize(size,size);self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # No hover tooltip: clicking copies the ID and shows the "已复制 ID"
        # hint; a hover popup would only repeat what the click already says.
        self.setIcon(QIcon(self._pixmap(name,avatar_path,size,ring_color)));self.setIconSize(QSize(size,size))
        self.clicked.connect(self._copy)
    @staticmethod
    def _pixmap(name,path,size,ring):
        pm=QPixmap(size,size);pm.fill(Qt.GlobalColor.transparent)
        painter=QPainter(pm);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip=QPainterPath();clip.addEllipse(1.5,1.5,size-3,size-3);painter.setClipPath(clip)
        img=QPixmap(str(path)) if path else QPixmap()
        if not img.isNull():
            scaled=img.scaled(size,size,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
            sx=(scaled.width()-size)//2;sy=(scaled.height()-size)//2
            painter.drawPixmap(0,0,scaled,sx,sy,size,size)
        else:
            painter.fillRect(pm.rect(),QColor(ACCENT));painter.setPen(QColor("white"))
            painter.setFont(QFont("Microsoft YaHei UI",max(11,size//3),QFont.Weight.DemiBold))
            painter.drawText(pm.rect(),Qt.AlignmentFlag.AlignCenter,(str(name or "P")[:1]).upper())
        painter.setClipping(False);painter.setPen(QPen(QColor(ring),2.5));painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(1.5,1.5,size-3,size-3));painter.end()
        return pm
    def _copy(self):
        QApplication.clipboard().setText(self.page_id)
        show_hint(self,"已复制 ID",kind="success")
        if self._on_copy:self._on_copy(self.page_id)


class MetricCard(QFrame):
    badge_clicked=pyqtSignal()
    def __init__(self,title,accent=None,kind="pages"):
        super().__init__();self.setObjectName("MetricCard");self.setProperty("tone",kind);self.setMinimumWidth(0);self.setFixedHeight(112)
        layout=QVBoxLayout(self);layout.setContentsMargins(16,13,16,12);layout.setSpacing(1)
        self.kind=kind;self.accent=accent or ACCENT
        self.label=ElideLabel(title);self.label.setObjectName("MetricLabel");self.label.setMinimumHeight(22)
        self.badge=QPushButton("");self.badge.setObjectName("MetricBadge");self.badge.setFixedSize(24,20)
        self.badge.setCursor(Qt.CursorShape.PointingHandCursor);self.badge.hide()
        self.badge.clicked.connect(self.badge_clicked.emit)
        header=QHBoxLayout();header.setContentsMargins(0,0,0,0);header.setSpacing(6)
        header.addWidget(self.label,1);header.addWidget(self.badge)
        self.value=ValueLabel("—",32);self.value.setObjectName("MetricValue");self.value.setMinimumHeight(40)
        self.note=ElideLabel("");self.note.setObjectName("SmallMuted");self.note.setMinimumHeight(19)
        layout.addLayout(header);layout.addWidget(self.value);layout.addWidget(self.note)
    def set_badge(self,count):
        if count and int(count)>0:
            self.badge.setText(str(count) if int(count)<100 else "99+");self.badge.show()
        else:
            self.badge.hide()
    def set_values(self,value,note=""):
        # No hover tooltips: the numbers are already fully visible on the card;
        # repeating them on hover adds nothing.
        self.value.setText(str(value));self.value.setToolTip("")
        self.note.setText(str(note));self.note.setToolTip("")



class CopyLabel(ElideLabel):
    def __init__(self,text="",copy_text=None,parent=None):
        super().__init__(text,parent);self.copy_text=str(text if copy_text is None else copy_text)
        self.setCursor(Qt.CursorShape.PointingHandCursor);self.setToolTip(html.escape(str(text))+"\n点击复制")
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            QApplication.clipboard().setText(self.copy_text)
            show_hint(self,"已复制",kind="success")
            event.accept()
        else:super().mouseReleaseEvent(event)

class PageCard(QFrame):
    open_requested=pyqtSignal(str)
    manage_requested=pyqtSignal(str)
    inspect_requested=pyqtSignal(str)
    sync_requested=pyqtSignal(str)
    delete_requested=pyqtSignal(str)
    def __init__(self,row,rank=0,window_label=""):
        super().__init__();self.row=dict(row);self.setObjectName("PageCard")
        self.setMinimumWidth(0);self.setFixedHeight(228)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        pid=str(row["page_id"]);name=display_name(row);post=row.get("post_view") or post_view(row)
        layout=QVBoxLayout(self);layout.setContentsMargins(16,12,16,10);layout.setSpacing(8)
        header=QHBoxLayout();header.setSpacing(9)
        header.addWidget(AvatarWidget(name,row.get("avatar_path",""),60,page_id=pid),0,Qt.AlignmentFlag.AlignTop)
        identity=QVBoxLayout();identity.setSpacing(2)
        title=CopyLabel(name);title.setObjectName("CardTitle");title.setMinimumHeight(22)
        title.setToolTip(html.escape("专业名称："+(normalize_name(row.get("page_name"),pid) or name or "尚未获取"))+"\n点击复制名称")
        ident=CopyLabel("ID  "+pid,pid);ident.setObjectName("CardId");ident.setMinimumHeight(18)
        ident.setToolTip("公共主页编号："+pid+"\n点击复制完整 ID")
        identity.addWidget(title);identity.addWidget(ident);header.addLayout(identity,1)
        menu=icon_button("more","主页操作",self,26);menu.setIconSize(QSize(18,18));menu.clicked.connect(self.show_menu)
        header.addWidget(menu,0,Qt.AlignmentFlag.AlignTop);layout.addLayout(header)

        values=QHBoxLayout();values.setSpacing(8)
        today=row.get("today") or {"delta":None,"partial":True,"note":"暂无记录"}
        _delta_full = format_delta(today["delta"])
        _delta_compact = format_delta_compact(today["delta"])
        _delta_tip = today.get("note", "")
        if row.get("monitor_growth") and _delta_compact != _delta_full:
            _delta_tip = "实际今日新增：" + _delta_full + (("\n" + _delta_tip) if _delta_tip else "")
        specs=[
            ("当前粉丝" if row.get("monitor_growth") else "上次粉丝",
             format_compact_count(row.get("last_followers")),"BigNumber",
             "实际粉丝数："+format_count(row.get("last_followers"))+("\n粉丝监控未开启，显示最后一次已保存值" if not row.get("monitor_growth") else "")+("（约值）" if row.get("approx") else "")),
            ("今日新增",("未监控" if not row.get("monitor_growth") else
              (("≈" if today.get("approx") else "")+_delta_compact)),
             "GrowthUp" if row.get("monitor_growth") and (today.get("delta") or 0)>0 else
             "GrowthDown" if row.get("monitor_growth") and (today.get("delta") or 0)<0 else "GrowthFlat",_delta_tip),
            ("距上次发帖",post.get("elapsed_short",post["elapsed"]),
             "GrowthDown" if post["state"]=="overdue" else "GrowthSoon" if post["state"] in ("soon","unknown","unverified")
             else "GrowthUp" if post["state"]=="ok" else "GrowthFlat",post["tooltip"])
        ]
        if not row.get("monitor_posts"):specs=specs[:2]
        if not row.get("monitor_growth"):specs=specs[2:]
        if not specs:specs=[("监控状态","未开启","GrowthFlat","")]
        for i,(label,text,objectname,tip) in enumerate(specs):
            col=QVBoxLayout();col.setSpacing(1)
            heading=ElideLabel(label);heading.setMinimumHeight(17);heading.setObjectName("SmallMuted")
            value=ValueLabel(text,24 if i==0 else 22);value.setObjectName(objectname);value.setToolTip(tip)
            col.addWidget(heading);col.addWidget(value);values.addLayout(col,9 if i==2 else 10 if i==0 else 12)
        layout.addLayout(values)
        modules=[]
        if row.get("monitor_growth"):modules.append("粉丝监控")
        if row.get("monitor_posts"):modules.append("发帖监控")
        module_hint=ElideLabel(" · ".join(modules) or "尚未选择监控模块")
        module_hint.setObjectName("SmallMuted");module_hint.setMinimumHeight(22)
        layout.addWidget(module_hint)
        diag_parts=[]
        if row.get("name_error"):diag_parts.append("名称："+str(row.get("name_error"))[:90])
        if row.get("monitor_growth") and row.get("growth_error"):diag_parts.append("粉丝："+str(row.get("growth_error"))[:90])
        if row.get("monitor_posts") and row.get("post_error"):diag_parts.append("发帖："+str(row.get("post_error"))[:90])
        if not diag_parts and row.get("diagnosis_detail") and row.get("diagnosis_code") not in ("","ok"):
            diag_parts.append("诊断："+str(row.get("diagnosis_detail"))[:110])
        diag_text=(row.get("diagnosis_detail") or PAGE_UNAVAILABLE_DETAIL) if row.get("diagnosis_code")=="page_unavailable" else " · ".join(diag_parts)
        diag_label=ElideLabel(diag_text);diag_label.setObjectName("SmallMuted");diag_label.setMinimumHeight(18)
        diag_label.setToolTip(html.escape(diag_text))
        # Parent first, show second: setVisible(True) on a still-parentless
        # label opens it as its own tiny top-level window (the title-bar-only flash).
        layout.addWidget(diag_label);diag_label.setVisible(bool(diag_text))
        layout.addStretch(1)

        footer=QHBoxLayout();footer.setSpacing(4)
        checked=row.get("last_inspected_at") or row.get("last_collected_at") or ""
        label=ElideLabel("最近检查 "+local_time_label(checked,False));label.setMinimumHeight(22)
        label.setToolTip(local_time_label(checked));label.setObjectName("SmallMuted");footer.addWidget(label,1)
        # Card badges: the post status and the growth status are independent,
        # so both show when both apply (e.g. overdue + over-threshold), and
        # the page belongs to both filter categories as well. "主页不可用" stays alone: with no
        # page data the other states carry no meaning.
        badges=[]
        if not row.get("monitor_growth") and not row.get("monitor_posts"):badges=[("未选择模块","off")]
        elif row.get("diagnosis_code")=="page_unavailable":badges=[("主页不可用","alert")]
        else:
            if row.get("diagnosis_code")=="login":badges.append(("需登录验证","warning"))
            elif post["state"]=="overdue":badges.append(("发帖超时","alert"))
            elif post["state"]=="soon":badges.append(("即将超时","warning"))
            elif row.get("monitor_growth") and row.get("growth_error") and row.get("monitor_posts") and row.get("post_error"):badges.append(("读取失败","alert"))
            elif post["state"] in ("unknown","unverified"):badges.append(("发帖待核实","warning"))
            elif row.get("monitor_growth") and row.get("growth_error"):badges.append(("粉丝读取失败","warning"))
            elif row.get("monitor_posts") and row.get("post_error"):badges.append(("发帖读取失败","warning"))
            elif not checked:badges.append(("待巡检","off"))
            if row.get("is_growth_alert"):badges.append(("增长超标","alert"))
        if not badges:badges=[("正常","normal")]
        for status,state in badges:
            badge=QLabel(status);badge.setObjectName("StatusBadge");badge.setProperty("state",state)
            badge.setMinimumHeight(23);badge.setAlignment(Qt.AlignmentFlag.AlignCenter);footer.addWidget(badge)
        layout.addLayout(footer)

    def mouseDoubleClickEvent(self,event):
        self.manage_requested.emit(self.row["page_id"]);event.accept()

    def show_menu(self):
        pid=self.row["page_id"]
        menu=QMenu(self)
        menu.addAction("编辑监控模块 / 发帖标准",lambda:self.manage_requested.emit(pid))
        menu.addAction("仅巡检本主页",lambda:self.inspect_requested.emit(pid))
        menu.addAction("仅同步本主页资料",lambda:self.sync_requested.emit(pid))
        menu.addSeparator()
        menu.addAction("打开主页",lambda:self.open_requested.emit(pid))
        menu.addSeparator()
        _del=menu.addAction("删除此主页…");_del.triggered.connect(lambda:self.delete_requested.emit(pid))
        url=self.row.get("post_url")
        if url and urlsplit(url).scheme=="https" and ((urlsplit(url).hostname or "")=="facebook.com" or (urlsplit(url).hostname or "").endswith(".facebook.com")):
            menu.addAction("打开已读取的贴文",lambda:QDesktopServices.openUrl(QUrl(url)))
        menu.popup(self.mapToGlobal(QPoint(max(0,self.width()-190),38)))


class ResponsiveCards(QWidget):
    def __init__(self,parent=None,settings=None):
        super().__init__(parent);self.setObjectName("CardCanvas");self.settings=settings
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,4,6)
        self.grid.setHorizontalSpacing(10);self.grid.setVerticalSpacing(10)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.cards=[];self.columns=0
    def set_cards(self,cards):
        while self.grid.count():
            item=self.grid.takeAt(0)
            if item.widget():
                # Hide first: deleteLater() only runs on the next event-loop
                # turn, and a stale card left visible would paint over the
                # new one until then.
                item.widget().hide();item.widget().deleteLater()
        self.cards=list(cards);self.columns=0;self.reflow()
    def reflow(self):
        available=max(220,self.width()-4)
        columns=max(1,min(4,int((available+10)//(290+10))))
        if columns==self.columns:return
        self.columns=columns
        while self.grid.count():self.grid.takeAt(0)
        for i,w in enumerate(self.cards):
            self.grid.addWidget(w,i//columns,i%columns)
            # A card added while an ancestor is hidden (e.g. geometry restore
            # during startup) would otherwise stay hidden forever.
            w.show()
        for col in range(8):self.grid.setColumnStretch(col,1 if col<columns else 0)
    def resizeEvent(self,event):
        super().resizeEvent(event);self.reflow()


class BatchAddDialog(QDialog):
    def __init__(self,parent=None,initial="",growth_enabled=True,posts_enabled=True):
        super().__init__(parent);self.setWindowTitle("添加专业 ID");self.resize(620,600)
        root=QVBoxLayout(self);root.setContentsMargins(22,20,22,20);root.setSpacing(12)
        title=QLabel("批量添加专业 ID");title.setObjectName("DialogTitle");root.addWidget(title)
        note=QLabel("支持逐行 ID、表格粘贴和带数字 ID 的主页链接。重复 ID 会跳过；已有主页的模块、名称和备注不会被覆盖。")
        note.setWordWrap(True);note.setObjectName("SmallMuted");root.addWidget(note)
        form=QFormLayout()
        self.mode_box=SegmentedChoice((("新增 ID（保留已有主页）","add"),("覆盖当前 ID 列表（保留已有配置）","replace")),"add")
        form.addRow("导入方式",self.mode_box);root.addLayout(form)
        self.edit=QPlainTextEdit();self.edit.setPlaceholderText("在这里粘贴专业 ID，一行一个…")
        self.edit.setPlainText(initial);self.edit.setMinimumHeight(200);root.addWidget(self.edit,1)
        self.preview=QLabel();self.preview.setTextFormat(Qt.TextFormat.PlainText);self.preview.setWordWrap(True);self.preview.setObjectName("SmallMuted");root.addWidget(self.preview)
        box=QFrame();box.setObjectName("SettingsCard");bl=QVBoxLayout(box);bl.setContentsMargins(14,12,14,12)
        label=QLabel("新添加主页默认监控模块");label.setObjectName("SettingsTitle");bl.addWidget(label)
        modules=QHBoxLayout();self.growth=QCheckBox("粉丝监控");self.posts=QCheckBox("发帖时间监控")
        self.growth.setChecked(bool(growth_enabled));self.posts.setChecked(bool(posts_enabled))
        if not posts_enabled:self.posts.setEnabled(False)
        modules.addWidget(self.growth);modules.addWidget(self.posts);modules.addStretch();bl.addLayout(modules)
        threshold=QHBoxLayout();threshold.addWidget(QLabel("超过多久未发帖提醒"))
        self.hours=QSpinBox();self.hours.setRange(1,8760);self.hours.setValue(24);self.hours.setSuffix(" 小时")
        if not posts_enabled:self.hours.setEnabled(False)
        threshold.addWidget(self.hours);threshold.addStretch();bl.addLayout(threshold);root.addWidget(box)
        actions=QHBoxLayout();actions.addStretch()
        cancel=QPushButton("取消");cancel.clicked.connect(self.reject);actions.addWidget(cancel)
        save=QPushButton("确认导入");save.setObjectName("PrimaryButton");save.clicked.connect(self.accept);actions.addWidget(save);root.addLayout(actions)
        self.edit.textChanged.connect(self.update_preview);self.update_preview()
    def text(self):return self.edit.toPlainText()
    def mode(self):return self.mode_box.currentData()
    def update_preview(self):
        parsed=normalize_page_ids(self.text())
        self.preview.setText(f"有效 ID {len(parsed.ids)} 个 · 重复 {parsed.duplicates} 个 · 无法识别 {len(parsed.rejected)} 项")
    def accept(self):
        parsed=normalize_page_ids(self.text())
        if not parsed.ids:
            QMessageBox.warning(self,"没有有效 ID","请粘贴有效的数字主页 ID 后再导入。");return
        if parsed.rejected:
            answer=QMessageBox.question(self,"确认跳过无效内容",
                f"有 {len(parsed.rejected)} 项无法识别，将跳过：\n"+ "\n".join(html.escape(x) for x in parsed.rejected[:8])+"\n\n继续导入其余有效 ID？",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
        super().accept()




def today_growth_over_threshold(row, threshold, today_delta=None):
    """Whether today's accumulated growth reached the threshold.

    THE definition of fan-growth over-standard for display classification:
    today's growth (the card's 今日新增: latest reading minus today's
    baseline) reaching the threshold counts. A single-interval jump does
    NOT count on its own: one jump of 50 is not required, and one jump
    of 50 with only 40 of net growth today does not count either.
    An unread growth alert also counts (via is_growth_alert in refresh).
    Abbreviated readings (Facebook shows 1.2\u4e07 / 12K style counts) count
    here: the numbers on screen are the evidence, and cards already
    annotate them as approx. The age of the reading does NOT exclude it:
    today_delta only exists when today_change anchors the reading to
    today's baseline (baseline_date is today and the latest reading is
    newer than the baseline), so a same-day reading always describes
    today's growth, however many hours old it is. A page whose last
    reading is old still shows its 今日新增 on the card, and the
    category must match the number on the card. Freshness still gates
    alert generation (should_alert) and post verification (post_view);
    this creates no alert row and changes nothing there.
    """
    try:
        threshold = int(threshold)
    except (TypeError, ValueError, OverflowError):
        return False
    if threshold <= 0 or not row.get("monitor_growth"):
        return False
    return today_delta is not None and today_delta >= threshold


def dashboard_row_flags(row, posts_on):
    """Return (growth_alert, post_overdue, needs_attention) for one dashboard row.

    Growth, post timeout and needs attention are independent dimensions:
    a row can belong to several at once, and it then belongs to each
    category (and each chip count). A pending/unverified post detection
    ("发帖待核实") belongs to 需处理 and never to 发帖超时, and it does
    not affect the growth category, which is computed from the actual
    follower numbers alone. Unavailable pages stay needs-only.
    Thresholds and detection rules are NOT changed here; the predicates
    only reuse the existing signals (unread growth alert, or today's
    accumulated growth at/over the threshold, stored in is_growth_alert
    by refresh(); post_view() state, stored errors / post_result).
    - growth_alert: unread growth alert for the page, or today's
      accumulated growth (今日新增) reaching the existing threshold
      (see today_growth_over_threshold). A single-interval jump alone
      does not count. The threshold itself is unchanged.
    - post_overdue: post_view() state "overdue" (fresh, verified detection only;
      stale/unverified detections report overdue=False and never land here).
    - needs_attention: pending review (post_result "pending" while post
      monitoring is on), uncertain state (unknown/unverified), other
      records that need a human look, or an unavailable page. It is
      independent of growth (a page can be both needs and growth), and
      only stays exclusive with overdue.
    """
    if row.get("diagnosis_code") == "page_unavailable":
        return (False, False, True)
    growth = bool(row.get("is_growth_alert"))
    pv = row.get("post_view") or {}
    overdue = bool(pv.get("state") == "overdue")
    pending_review = bool(posts_on and row.get("monitor_posts") and row.get("post_result") == "pending")
    uncertain = pv.get("state") in ("unknown", "unverified")
    other = (row.get("status") in ("采集失败", "部分成功") or bool(row.get("growth_error"))
             or bool(posts_on and row.get("post_error")) or bool(row.get("name_error")))
    needs = bool(pending_review or uncertain or other) and not overdue
    return (growth, overdue, needs)


class DashboardPage(QWidget):
    collect_once=pyqtSignal()
    collect_subset_requested=pyqtSignal(str)
    inspect_page=pyqtSignal(str)
    sync_page=pyqtSignal(str)
    toggle_auto=pyqtSignal()
    view_alerts=pyqtSignal()
    open_manager=pyqtSignal(str)
    open_page=pyqtSignal(str)
    open_settings_requested=pyqtSignal()
    delete_page=pyqtSignal(str)

    def __init__(self,store,settings):
        super().__init__();self.setObjectName("DashboardPage");self.store=store;self.settings=settings
        self.paused=False;self._active=False;self._auto=False
        self.build_ui();self.refresh()

    def build_ui(self):
        root=QVBoxLayout(self);root.setContentsMargins(20,16,20,10);root.setSpacing(12)
        self.action_bar=QWidget();action_lay=QHBoxLayout(self.action_bar);action_lay.setContentsMargins(0,0,0,0);action_lay.setSpacing(10)
        self.run_badge=QLabel("上次巡检时间：—");self.run_badge.setObjectName("RunBadge");action_lay.addWidget(self.run_badge)
        self.once_btn=QPushButton("立即巡检");self.once_btn.setIcon(ui_icon("play","#FFFFFF"))
        self.once_btn.setIconSize(QSize(16,16));self.once_btn.setObjectName("PrimaryButton");self.once_btn.setFixedSize(140,40)
        self._once_menu=QMenu(self.once_btn)
        self._once_menu.addAction("仅巡检读取失败的主页",lambda:self.collect_subset_requested.emit("failed"))
        self._once_menu.addAction("仅巡检未巡检的主页",lambda:self.collect_subset_requested.emit("uninspected"))
        self.once_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.once_btn.customContextMenuRequested.connect(lambda _pos: self._once_menu.popup(self.once_btn.mapToGlobal(QPoint(0, self.once_btn.height()))))
        self.once_btn.clicked.connect(self.collect_once.emit);action_lay.addWidget(self.once_btn)
        self.auto_btn=QPushButton("启用自动巡检");self.auto_btn.setObjectName("AutoButton");self.auto_btn.setFixedSize(140,40)
        self.auto_btn.clicked.connect(self.toggle_auto.emit);action_lay.addWidget(self.auto_btn)
        # No separate settings button/panel: hovering the auto-inspection
        # button shows the current settings as a floating tooltip
        # (_refresh_auto_tooltip). Editing stays in Settings.
        self._timing_values=random_inspection_timing(self.settings)
        self._refresh_auto_tooltip()
        metrics=QHBoxLayout();metrics.setSpacing(12)
        self.metric_pages=MetricCard("专业主页数",ACCENT,"pages")
        self.metric_total=MetricCard("当前粉丝总量",CYAN,"people")
        self.metric_yesterday=MetricCard("昨日新增",AMBER,"history")
        self.metric_today=MetricCard("今日新增数",RED,"bell")
        self.metric_today.badge_clicked.connect(lambda:self._set_filter_mode("needs"))
        for metric in (self.metric_pages,self.metric_total,self.metric_yesterday,self.metric_today):metrics.addWidget(metric,1)
        root.addLayout(metrics)
        toolbar=QHBoxLayout();toolbar.setSpacing(8)
        self.search=QLineEdit();self.search.setPlaceholderText("搜索名称 / 专业 ID");self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(150);self.search.setMaximumWidth(300);self.search.setFixedHeight(36)
        self.search.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.search.textChanged.connect(lambda _:self.refresh())
        toolbar.addWidget(self.search,0,Qt.AlignmentFlag.AlignTop)
        self._chip_row=ChipRow()
        self._filter_chips={}
        for name,mode in (("全部","all"),("粉丝监控","growth"),("发帖监控","posts"),("发帖超时","post_overdue"),("粉丝增长超标","growth_alert"),("需处理","needs")):
            chip=BadgeButton(name) if mode in ("needs","post_overdue","growth_alert") else QPushButton(name)
            chip.setObjectName("FilterChip");chip.setFixedHeight(30)
            if mode in ("needs","post_overdue","growth_alert"):chip.setMinimumWidth(chip.sizeHint().width()+20)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False,m=mode:self._set_filter_mode(m))
            self._chip_row.layout().addWidget(chip);self._filter_chips[mode]=chip
        toolbar.addWidget(self._chip_row,1)
        self._sort_mode=str(self.settings.value("dashboard/sort","growth"))
        if self._sort_mode not in ("growth","post","name"):self._sort_mode="growth"
        self.sort_box=MenuButton((("增长预警优先","growth"),("发帖超时优先","post"),("名称排序","name")),self._sort_mode)
        self.sort_box.setFixedWidth(140)
        self.sort_box.changed.connect(self._on_sort_changed)
        toolbar.addWidget(self.sort_box,0,Qt.AlignmentFlag.AlignTop)
        root.addLayout(toolbar)
        split=QHBoxLayout();split.setSpacing(14)
        self.scroll=QScrollArea();self.scroll.setObjectName("CardScroll");self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True);self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards=ResponsiveCards(settings=self.settings);self.scroll.setWidget(self.cards)
        self.cards.setAutoFillBackground(False);self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.setMinimumHeight(230);split.addWidget(self.scroll,1)
        rail=QVBoxLayout();rail.setSpacing(10);rail.setContentsMargins(0,0,0,0)
        alerts_card=QFrame();alerts_card.setObjectName("RailCard")
        al=QVBoxLayout(alerts_card);al.setContentsMargins(10,10,10,10);al.setSpacing(7)
        arow=QHBoxLayout();at=QLabel("最近预警");at.setObjectName("PanelTitle");arow.addWidget(at);arow.addStretch()
        al.addLayout(arow)
        self.rail_alerts=QVBoxLayout();self.rail_alerts.setSpacing(10);al.addLayout(self.rail_alerts)
        rail.addWidget(alerts_card)
        overview_card=QFrame();overview_card.setObjectName("RailCard")
        ol=QVBoxLayout(overview_card);ol.setContentsMargins(14,10,14,10);ol.setSpacing(7)
        ot=QLabel("概览");ot.setObjectName("PanelTitle");ol.addWidget(ot)
        def _kv2(label):
            # Numbers sit a fixed 3-5 character gap after the title instead of
            # being pushed to the far right edge, so they are never clipped.
            row=QHBoxLayout();row.setSpacing(0);row.addWidget(QLabel(label));row.addSpacing(40)
            val=QLabel("—");val.setObjectName("SmallMuted");row.addWidget(val);row.addStretch();ol.addLayout(row);return val
        self.rail_inspected=_kv2("已巡检主页");self.rail_failed=_kv2("读取失败");self.rail_unavailable=_kv2("主页不可用");self.rail_growth_alerts=_kv2("增长超标提醒")
        rail.addWidget(overview_card)
        rail.addStretch(1)
        rail_widget=QWidget();rail_widget.setLayout(rail)
        self.rail_widget=rail_widget
        root.addLayout(split,1)
        self.status=ElideLabel("就绪");self.status.setMinimumHeight(20);self.status.setObjectName("FooterText")
        self.next_run=QLabel("自动巡检未开启");self.next_run.setObjectName("FooterText")
        stored=str(self.settings.value("dashboard/filter","all"))
        if stored=="overdue":stored="post_overdue"
        elif stored=="unknown":stored="needs"
        elif stored=="unavailable":stored="needs"
        elif stored=="off":stored="all"
        if stored not in ("all","growth","posts","needs","post_overdue","growth_alert"):stored="all"
        self._filter_mode=stored
        self.search.blockSignals(True);self.search.setText(str(self.settings.value("dashboard/search","")));self.search.blockSignals(False)
        self.search.textChanged.connect(self._remember_view)
        self._apply_filter_chips()

    def filter_mode(self):
        return getattr(self,"_filter_mode","all")

    def _apply_filter_chips(self):
        posts_on=modules_posts_enabled(self.settings)
        growth_on=modules_growth_enabled(self.settings)
        if not posts_on and getattr(self,"_filter_mode","all") in ("posts","post_overdue"):self._filter_mode="all"
        if not growth_on and getattr(self,"_filter_mode","all")=="growth_alert":self._filter_mode="all"
        for mode,chip in self._filter_chips.items():
            if mode in ("posts","post_overdue"):visible=posts_on
            elif mode=="growth_alert":visible=growth_on
            else:visible=True
            chip.setVisible(visible)
            chip.setProperty("active",mode==self._filter_mode);chip.style().unpolish(chip);chip.style().polish(chip)

    def _set_filter_mode(self,mode):
        self._filter_mode=mode;self._apply_filter_chips();self._remember_view();self.refresh()

    def _on_sort_changed(self):
        self._sort_mode=self.sort_box.currentData();self._remember_view();self.refresh()

    def _refresh_auto_tooltip(self):
        # Floating tooltip on the auto-inspection button: current settings
        # only, read live from settings so a change in Settings shows up
        # on the next refresh without reopening anything.
        minutes,j0,j1,g0,g1=getattr(self,"_timing_values",None) or random_inspection_timing(self.settings)
        threshold=_bounded_int(self.settings.value("alert_threshold",500),500,1,100_000_000)
        start_auto="开启" if is_true(self.settings.value("start_auto",0)) else "关闭"
        self.auto_btn.setToolTip(
            f"每轮间隔：{minutes} 分钟\n"
            f"浮动范围：± {j0}–{j1} 分钟\n"
            f"主页间隔：{g0}–{g1} 秒\n"
            f"启动时自动巡检：{start_auto}\n"
            f"当日增长提醒阈值：{threshold} 粉丝\n"
            "如需修改巡检参数，请前往设置中修改。")

    def set_timing_values(self,minutes,j0,j1,g0,g1):
        self._timing_values=(minutes,j0,j1,g0,g1)
        self._refresh_auto_tooltip()

    def _remember_view(self,*_):
        self.settings.setValue("dashboard/sort",getattr(self,"_sort_mode","growth"))
        self.settings.setValue("dashboard/filter",self._filter_mode)
        self.settings.setValue("dashboard/search",self.search.text())
        self.settings.sync()


    def set_running(self,auto,active):
        self._auto=auto;self._active=active
        label="暂停中" if active and self.paused else "巡检中" if active else "自动巡检已开启" if auto else "待巡检"
        self.run_badge.setToolTip("")
        self.once_btn.setText("继续巡检" if active and self.paused else "暂停巡检" if active else "立即巡检")
        self.once_btn.setIcon(ui_icon("pause" if active and not self.paused else "play","#FFFFFF"))
        self.once_btn.setToolTip("暂停在当前主页处理完成后生效；继续不会从头重跑" if active else "巡检所有已选择模块的专业 ID")
        self.auto_btn.setText("暂停自动巡检" if auto else "启用自动巡检")
        self.auto_btn.setProperty("autoEnabled",auto)
        self._refresh_auto_tooltip()
        self.auto_btn.style().unpolish(self.auto_btn);self.auto_btn.style().polish(self.auto_btn)

    def refresh(self):
        now=time.time()
        try:interval=int(self.settings.value("interval_minutes",DEFAULT_INTERVAL_MINUTES))*60
        except (ValueError,TypeError):interval=DEFAULT_INTERVAL_MINUTES*60
        rows=apply_module_gating(self.store.dashboard_rows(None,interval),self.settings)
        posts_on=modules_posts_enabled(self.settings)
        self._apply_filter_chips()
        if not self._active or not hasattr(self,"_last_inspection_stamp"):
            self._last_inspection_stamp=latest_inspection_stamp(self.settings,rows)
        self.run_badge.setText("上次巡检时间："+inspection_stamp_label(self._last_inspection_stamp))
        unread_pages={a["page_id"] for a in self.store.alert_rows() if not a["acknowledged"]}
        _threshold=_bounded_int(self.settings.value("alert_threshold",500),500,1,100_000_000)
        today_sum=0;covered=0;partial=0;yesterday_sum=0;yesterday_covered=0;yesterday_partial=0
        growth_rows=[r for r in rows if r["monitor_growth"]]
        post_rows=[r for r in rows if r["monitor_posts"]]
        for row in rows:
            row["post_view"]=post_view(row,now,interval)
            if row["monitor_growth"]:
                row["today"]=self.store.today_change(row["page_id"],now,interval)
                row["yesterday"]=self.store.yesterday_change(row["page_id"],now)
                if row["today"]["delta"] is not None:
                    today_sum+=row["today"]["delta"];covered+=1
                    partial+=int(row["today"]["partial"])
                if row["yesterday"]["delta"] is not None:
                    yesterday_sum+=row["yesterday"]["delta"];yesterday_covered+=1
                    yesterday_partial+=int(row["yesterday"]["partial"])
            # Growth category is state-based, not unread-only: an alert row
            # is created on every over-threshold collection (should_alert
            # still applies its elapsed/approx guards), and it stops
            # counting once read. A page whose today's accumulated growth
            # reached the threshold counts even with no unread alert row
            # left; a single-interval jump alone does not count
            # (see today_growth_over_threshold).
            row["is_growth_alert"]=row["monitor_growth"] and (row["page_id"] in unread_pages or today_growth_over_threshold(row,_threshold,(row.get("today") or {}).get("delta")))
            _gf,_of,_nf=dashboard_row_flags(row,posts_on)
            row["cat_growth"]=_gf;row["is_post_overdue"]=_of;row["needs_attention"]=_nf
        total=sum(r["last_followers"] for r in growth_rows if r["last_followers"] is not None)
        sampled=sum(r["last_followers"] is not None for r in growth_rows)
        overdue=sum(r["post_view"]["state"]=="overdue" for r in rows)
        unverified=sum(r["post_view"]["state"] in ("unknown","unverified") for r in rows)
        g,p=self.store.unread_totals()
        unavailable=sum(1 for r in rows if r.get("diagnosis_code")=="page_unavailable")
        failed=sum(1 for r in rows if r.get("diagnosis_code")!="page_unavailable" and (r.get("status") in ("采集失败","部分成功") or r.get("growth_error") or (posts_on and r.get("post_error")) or r.get("name_error")))
        self.metric_pages.set_values(len(rows),(f"粉丝 {len(growth_rows)} · 发帖 {len(post_rows)}" if posts_on else f"仅粉丝监控 {len(growth_rows)}")+(f" · 失败 {failed}" if failed else ""))
        self.metric_total.set_values(format_count(total) if sampled else "—",f"有粉丝记录 {sampled} / {len(growth_rows)}")
        self.metric_yesterday.set_values(format_delta(yesterday_sum) if yesterday_covered else "—",
            ((f"可比较 {yesterday_covered} 个"+(f" · {yesterday_partial} 个为部分日" if yesterday_partial else "")) if yesterday_covered else "暂无可比较记录"))
        self.metric_today.set_values(format_delta(today_sum) if covered else "—",
            ((f"可比较 {covered} 个"+(f" · {partial} 个为部分日" if partial else "")) if covered else "今日暂无可比较记录"))
        self.metric_today.set_badge(unavailable)
        self._unavailable_count=unavailable
        _needs_count=sum(1 for r in rows if r.get("needs_attention"))
        _growth_count=sum(1 for r in rows if r.get("cat_growth"))
        _overdue_count=sum(1 for r in rows if r.get("is_post_overdue"))
        for _mode,_count in (("needs",_needs_count),("growth_alert",_growth_count),("post_overdue",_overdue_count)):
            _chip=self._filter_chips.get(_mode)
            if _chip is not None and hasattr(_chip,"set_badge"):_chip.set_badge(_count)
        self._apply_filter_chips()
        needle=self.search.text().strip().casefold();mode=self.filter_mode()
        filtered=[]
        for r in rows:
            if needle and needle not in (display_name(r)+" "+r["page_id"]+" "+r.get("notes","")).casefold():continue
            if mode=="growth" and not r["monitor_growth"]:continue
            if mode=="posts" and not r["monitor_posts"]:continue
            if mode=="needs" and not r.get("needs_attention"):continue
            if mode=="post_overdue" and not r.get("is_post_overdue"):continue
            if mode=="growth_alert" and not r.get("cat_growth"):continue
            filtered.append(r)
        _sort=getattr(self,"_sort_mode","growth")
        def _delta_key(r):
            _d=(r.get("today") or {}).get("delta")
            return -_d if _d is not None else 10**18
        if _sort=="name":
            filtered.sort(key=lambda r:display_name(r).casefold())
        elif _sort=="growth":
            filtered.sort(key=lambda r:(0 if r.get("cat_growth") else 1,0 if r.get("is_post_overdue") else 1,_delta_key(r),int(r.get("sort_order") or 0),str(r["page_id"])))
        elif _sort=="post":
            filtered.sort(key=lambda r:(0 if r.get("is_post_overdue") else 1,0 if r.get("cat_growth") else 1,float(r.get("last_post_ts") or 0),int(r.get("sort_order") or 0),str(r["page_id"])))
        else:
            filtered.sort(key=lambda r:(int(r.get("sort_order") or 0),str(r["page_id"])))
        self.search.setToolTip("匹配 %s 个，共 %s 个主页" % (len(filtered),len(rows)))
        cards=[]
        for r in filtered:
            card=PageCard(r)
            card.open_requested.connect(self.open_page.emit)
            card.manage_requested.connect(self.open_manager.emit)
            card.inspect_requested.connect(self.inspect_page.emit)
            card.sync_requested.connect(self.sync_page.emit)
            card.delete_requested.connect(self.delete_page.emit);cards.append(card)
        if not cards:
            empty=QFrame();empty.setObjectName("EmptyState");layout=QVBoxLayout(empty);layout.setContentsMargins(20,30,20,30)
            # "打开 ID管理" is only for the no-pages case in the three
            # module views (全部 / 粉丝监控 / 发帖监控). A category view
            # (需处理 / 发帖超时 / 粉丝增长超标) lists pages
            # that already have IDs, so an empty category means "no records
            # in this category", not "no IDs": show plain no-record text
            # with no button. A search with no match is the same in every
            # view: the pages exist, only the search matched none.
            if mode in ("needs","post_overdue","growth_alert") or needle:
                title=QLabel("暂无记录");title.setObjectName("SectionTitle");layout.addWidget(title)
                msg=QLabel("没有与搜索条件匹配的主页。" if needle else "当前分类下暂无符合条件的主页。")
                msg.setWordWrap(True);msg.setObjectName("SmallMuted");layout.addWidget(msg)
            else:
                title=QLabel("尚无匹配主页");title.setObjectName("SectionTitle");layout.addWidget(title)
                msg=QLabel("在左侧「ID管理」添加 ID，并勾选监控模块。")
                msg.setWordWrap(True);msg.setObjectName("SmallMuted");layout.addWidget(msg)
                add=QPushButton("打开 ID管理");add.setObjectName("PrimaryButton");add.clicked.connect(lambda:self.open_manager.emit(""))
                layout.addWidget(add,0,Qt.AlignmentFlag.AlignLeft)
            cards=[empty]
        scroll=self.scroll.verticalScrollBar().value()
        self.cards.set_cards(cards)
        self.scroll.verticalScrollBar().setValue(scroll)
        _tv=random_inspection_timing(self.settings);self.set_timing_values(*_tv)
        if hasattr(self,"rail_alerts"):
            while self.rail_alerts.count():
                _item=self.rail_alerts.takeAt(0)
                if _item.widget():
                    _item.widget().hide();_item.widget().deleteLater()
            entries=self.store.combined_alerts(limit=500,unread_only=True)
            if not posts_on:entries=[e for e in entries if e["kind"]!="post"]
            if not entries:
                _none=QLabel("暂无未读预警");_none.setObjectName("SmallMuted");self.rail_alerts.addWidget(_none)
            else:
                _by_page={};_order=[]
                for _e in entries:
                    _pid=str(_e.get("page_id") or "")
                    if _pid not in _by_page:
                        _by_page[_pid]={"entry":_e,"kinds":set()};_order.append(_pid)
                    _by_page[_pid]["kinds"].add(str(_e.get("kind") or ""))
                # Fixed: 4 large avatars, never shrunk; a 5th slot shows the
                # remainder count ("+N") instead of more avatars.
                _shown=_order[:4];_extra=len(_order)-len(_shown)
                _size=34
                _arow=QHBoxLayout();_arow.setSpacing(5);_arow.setContentsMargins(0,0,0,0)
                for _pid in _shown:
                    _info=_by_page[_pid];_entry=_info["entry"]
                    _kinds=_info["kinds"]
                    _ring=RED if len(_kinds)>1 else (AMBER if "post" in _kinds else GREEN)
                    _av=RailAvatarButton(str(_entry.get("page_name") or _entry.get("name") or ""),str(_entry.get("avatar_path") or ""),_pid,_size,_ring,lambda _pid:None)
                    _arow.addWidget(_av)
                if _extra>0:
                    _more=QLabel("+%d" % _extra);_more.setFixedSize(_size,_size);_more.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    _more.setStyleSheet("background:%s;color:%s;border-radius:%dpx;font-size:12px;font-weight:800;" % (PANEL_2,MUTED,_size//2))
                    _arow.addWidget(_more)
                _arow.addStretch(1)
                _awrap=QWidget();_awrap.setLayout(_arow);self.rail_alerts.addWidget(_awrap)
                # Summary counts match the avatars: distinct pages per kind,
                # not raw alert entries (one page may hold several entries).
                _gc=sum(1 for _info in _by_page.values() if "growth" in _info["kinds"])
                _pc=sum(1 for _info in _by_page.values() if "post" in _info["kinds"])
                _parts=[]
                if _pc:_parts.append("发帖超时 %d 个" % _pc)
                if _gc:_parts.append("粉丝增长超标 %d 个" % _gc)
                _sum=QLabel(" · ".join(_parts));_sum.setObjectName("SmallMuted");_sum.setWordWrap(True)
                self.rail_alerts.addWidget(_sum)
        if hasattr(self,"rail_inspected"):
            _inspected=sum(1 for r in rows if r.get("last_inspected_at"))
            self.rail_inspected.setText(f"{_inspected} / {len(rows)}")
            self.rail_failed.setText(f"{failed} 个")
            self.rail_unavailable.setText(f"{unavailable} 个")
            self.rail_growth_alerts.setText(f"{g} 条")



class AlertsPage(QWidget):
    ack_requested=pyqtSignal()
    clear_history_requested=pyqtSignal()
    read_changed=pyqtSignal()
    def __init__(self,store,settings=None):
        super().__init__();self.store=store;self.settings=settings;self.setObjectName("AlertsPage");self.mode="current";self._highlight_key=None
        root=QVBoxLayout(self);root.setContentsMargins(24,22,24,18);root.setSpacing(12)
        head=QHBoxLayout()
        self.summary=QLabel();self.summary.setObjectName("NoticeSummary");head.addWidget(self.summary)
        head.addStretch()
        self.history_btn=QPushButton("历史记录");self.history_btn.setObjectName("NoticeHistoryButton");self.history_btn.clicked.connect(self.toggle_history);head.addWidget(self.history_btn)
        self.filter=MenuButton((("全部类型","all"),("粉丝增长","growth"),("发帖超时","post")),"all")
        self.filter.setFixedWidth(126);self.filter.changed.connect(lambda:self.refresh());head.addWidget(self.filter)
        self.ack_btn=QPushButton("全部标为已读");self.ack_btn.setObjectName("SecondaryButton");self.ack_btn.clicked.connect(self.ack_requested.emit);head.addWidget(self.ack_btn)
        self.clear_btn=QPushButton("清空已读");self.clear_btn.setObjectName("SecondaryButton");self.clear_btn.clicked.connect(self.clear_history_requested.emit);head.addWidget(self.clear_btn);root.addLayout(head)
        note=QLabel("默认只显示未读通知；点击任意一条即视为已读并移入历史记录。历史记录可在历史模式中清空已读。")
        note.setObjectName("SmallMuted");note.setWordWrap(True);root.addWidget(note)
        self.table=QTableWidget(0,7);self.table.setObjectName("AlertsTable");self.table.setHorizontalHeaderLabels(("头像","类型","专业名称","专业 ID","通知内容","记录时间","状态"))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.verticalHeader().setVisible(False);self.table.setAlternatingRowColors(True);self.table.setShowGrid(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for col,width in ((0,58),(1,100),(2,190),(3,170),(5,150),(6,75)):self.table.setColumnWidth(col,width)
        self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch)
        self.table.cellClicked.connect(self._row_clicked)
        root.addWidget(self.table,1)
        self.empty_view=QWidget();_ev=QVBoxLayout(self.empty_view);_ev.setContentsMargins(0,0,0,0)
        _ev.addStretch(1);self.empty_label=QLabel();self.empty_label.setObjectName("EmptyHint")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter);_ev.addWidget(self.empty_label);_ev.addStretch(1)
        root.addWidget(self.empty_view,1);self.empty_view.hide()
        self.open_current()

    def open_current(self):
        self.mode="current";self._highlight_key=None
        self.history_btn.setText("历史记录");self.history_btn.setProperty("active",False)
        self.history_btn.style().unpolish(self.history_btn);self.history_btn.style().polish(self.history_btn)
        self.ack_btn.setVisible(True);self.clear_btn.setVisible(False);self.refresh()

    def toggle_history(self):
        if self.mode=="history":
            self.open_current();return
        self.mode="history";self._highlight_key=None
        self.history_btn.setText("返回当前");self.history_btn.setProperty("active",True)
        self.history_btn.style().unpolish(self.history_btn);self.history_btn.style().polish(self.history_btn)
        self.ack_btn.setVisible(False);self.clear_btn.setVisible(True);self.refresh()

    def _visible_rows(self):
        rows=self.store.combined_alerts(limit=5000)
        if self.settings is not None and not modules_posts_enabled(self.settings):
            rows=[r for r in rows if r["kind"]!="post"]
        kind=self.filter.currentData()
        if kind!="all":rows=[r for r in rows if r["kind"]==kind]
        if self.mode=="current":rows=[r for r in rows if not bool(r.get("acknowledged"))]
        else:rows=[r for r in rows if bool(r.get("acknowledged"))]
        return rows

    def refresh(self):
        if self.settings is not None:
            _posts_on=modules_posts_enabled(self.settings)
            _opts=[("全部类型","all"),("粉丝增长","growth")] + ([("发帖超时","post")] if _posts_on else [])
            self.filter.set_options(_opts,keep_current=True,emit=False)
        rows=self._visible_rows();self.table.clearContents();self.table.setRowCount(len(rows));matched=None
        for i,r in enumerate(rows):
            cell=QWidget();layout=QHBoxLayout(cell);layout.setContentsMargins(9,3,9,3);layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(AvatarWidget(r["page_name"],r.get("avatar_path",""),36,page_id=r.get("page_id","")));self.table.setCellWidget(i,0,cell)
            values=("发帖超时" if r["kind"]=="post" else "粉丝增长",r["page_name"],r["page_id"],r["message"],local_time_label(r["alerted_at"]),"已读" if r["acknowledged"] else "未读")
            key=(r["kind"],int(r.get("id") or 0),r["page_id"])
            for j,text in enumerate(values,1):
                item=QTableWidgetItem(str(text));item.setToolTip(html.escape(str(text)));item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if j in (1,3,5,6) else Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft)
                item.setData(Qt.ItemDataRole.UserRole,key)
                if j==1:item.setForeground(QColor(AMBER if r["kind"]=="post" else RED))
                self.table.setItem(i,j,item)
            self.table.setRowHeight(i,50)
            if self._highlight_key==(r["kind"],int(r.get("id") or 0)):matched=i
        g,p=self.store.unread_totals()
        if self.settings is not None and not modules_posts_enabled(self.settings):p=0
        if self.mode=="current":
            if g+p:
                if self.settings is not None and not modules_posts_enabled(self.settings):
                    self.summary.setText(f"当前未读 {g} 条 · 粉丝增长 {g}")
                else:
                    self.summary.setText(f"当前未读 {g+p} 条 · 粉丝增长 {g} · 发帖超时 {p}")
            else:
                self.summary.setText("")
        else:self.summary.setText(f"历史记录 {len(rows)} 条")
        _empty=len(rows)==0
        self.table.setVisible(not _empty);self.empty_view.setVisible(_empty)
        if _empty:self.empty_label.setText("暂无历史记录" if self.mode=="history" else "当前没有未读通知")
        if matched is not None:
            self.table.setCurrentCell(matched,1);self.table.selectRow(matched);item=self.table.item(matched,1)
            if item:self.table.scrollToItem(item,QAbstractItemView.ScrollHint.PositionAtCenter)

    def _row_clicked(self,row,col):
        if self.mode!="current":return
        item=self.table.item(row,1) or self.table.item(row,col)
        if not item:return
        key=item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(key,(tuple,list)) or len(key)<2:return
        kind,alert_id=key[0],key[1]
        if self.store.acknowledge_notification(kind,alert_id):
            self._highlight_key=None;self.read_changed.emit();self.refresh()

    def focus_alert(self,entry):
        try:self._highlight_key=(str(entry.get("kind") or ""),int(entry.get("id") or 0))
        except (TypeError,ValueError):self._highlight_key=(str(entry.get("kind") or ""),0)
        self.mode="current";self.history_btn.setText("历史记录");self.history_btn.setProperty("active",False)
        self.history_btn.style().unpolish(self.history_btn);self.history_btn.style().polish(self.history_btn)
        self.ack_btn.setVisible(True);self.clear_btn.setVisible(False)
        # A previous type filter must not hide the notification opened from the popup.
        self.filter.setCurrentData("all",emit=False)
        self.refresh()
        if self.table.currentRow()>=0:self.table.setFocus(Qt.FocusReason.OtherFocusReason)


# 1.8: 发帖监控已移入每个专业 ID 的配置。


# 1.8: 发帖监控已移入每个专业 ID 的配置。



class PageEditDialog(QDialog):
    def __init__(self,row,parent=None,posts_enabled=True):
        super().__init__(parent);self.row=row;self._posts_enabled=bool(posts_enabled);self.setWindowTitle("编辑专业 ID");self.resize(560,450)
        root=QVBoxLayout(self);root.setContentsMargins(22,20,22,20);root.setSpacing(14)
        head=QHBoxLayout();head.addWidget(AvatarWidget(display_name(row),row.get("avatar_path",""),54,page_id=row.get("page_id","")))
        texts=QVBoxLayout()
        name=QLabel(display_name(row));name.setTextFormat(Qt.TextFormat.PlainText);name.setWordWrap(True);name.setObjectName("SectionTitle");texts.addWidget(name)
        pid=CopyLabel("公共主页编号："+row["page_id"],row["page_id"]);pid.setMinimumHeight(23);texts.addWidget(pid)
        head.addLayout(texts,1);root.addLayout(head)
        real=QLabel("最近读取的真实名称："+(normalize_name(row.get("page_name"),row["page_id"]) or "尚未成功读取"))
        real.setTextFormat(Qt.TextFormat.PlainText);real.setWordWrap(True);real.setObjectName("SmallMuted");root.addWidget(real)
        form=QFormLayout();form.setVerticalSpacing(12)
        self.custom=QLineEdit(str(row.get("custom_name") or ""));self.custom.setPlaceholderText("留空时显示自动采集的真实名称")
        form.addRow("自定义显示名称",self.custom)
        modules=QWidget();ml=QHBoxLayout(modules);ml.setContentsMargins(0,0,0,0)
        self.growth=QCheckBox("粉丝监控");self.posts=QCheckBox("发帖监控")
        self.growth.setChecked(bool(row["monitor_growth"]));self.posts.setChecked(bool(row["monitor_posts"]))
        if not self._posts_enabled:self.posts.setEnabled(False)
        ml.addWidget(self.growth);ml.addWidget(self.posts);ml.addStretch();form.addRow("监控模块（可多选）",modules)
        self.hours=QSpinBox();self.hours.setRange(1,8760);self.hours.setValue(int(row["post_limit_hours"]));self.hours.setSuffix(" 小时")
        if not self._posts_enabled:self.hours.setEnabled(False)
        form.addRow("发帖超时标准",self.hours)
        self.notes=QPlainTextEdit(str(row.get("notes") or ""));self.notes.setMaximumHeight(82);form.addRow("备注",self.notes);root.addLayout(form)
        actions=QHBoxLayout();actions.addStretch()
        cancel=QPushButton("取消");cancel.clicked.connect(self.reject);actions.addWidget(cancel)
        save=QPushButton("保存");save.setObjectName("PrimaryButton");save.clicked.connect(self.accept);actions.addWidget(save);root.addLayout(actions)
    def values(self):
        return dict(custom_name=self.custom.text().strip(),monitor_growth=self.growth.isChecked(),
                    monitor_posts=bool(self.row["monitor_posts"]) if not self._posts_enabled else self.posts.isChecked(),post_limit_hours=self.hours.value(),
                    sort_order=int(self.row["sort_order"]),notes=self.notes.toPlainText().strip())


class PageManagementPage(QWidget):
    add_requested=pyqtSignal()
    delete_requested=pyqtSignal(list)
    config_changed=pyqtSignal()
    inspect_requested=pyqtSignal(list)
    open_settings_requested=pyqtSignal()
    def __init__(self,store,settings):
        super().__init__();self.store=store;self.settings=settings;self._loading=False;self._busy=False
        self.setObjectName("ManagerPage");self.build_ui();self.refresh()

    def build_ui(self):
        root=QVBoxLayout(self);root.setContentsMargins(24,20,24,16);root.setSpacing(13)

        actions=QHBoxLayout();actions.setSpacing(8)
        self.add_btn=QPushButton("添加 ID");self.add_btn.setObjectName("PrimaryButton");self.add_btn.clicked.connect(self._request_add)
        self.batch_btn=QPushButton("批量设置");self.batch_btn.setObjectName("BatchActionButton");self.batch_btn.clicked.connect(self.batch_settings)
        self.delete_btn=QPushButton("批量删除");self.delete_btn.setObjectName("DangerButton");self.delete_btn.clicked.connect(self.delete_selected)
        for btn in (self.add_btn,self.batch_btn,self.delete_btn):
            btn.setFixedHeight(38);actions.addWidget(btn)
        actions.addStretch();root.addLayout(actions)
        tools=QHBoxLayout();tools.setSpacing(10)
        self.select_all=QCheckBox("全选当前结果");self.select_all.toggled.connect(self.select_visible);tools.addWidget(self.select_all)
        self.summary=QLabel();self.summary.setObjectName("SmallMuted");tools.addWidget(self.summary);tools.addStretch()
        self.filter=MenuButton((("全部模块","all"),("粉丝监控","growth"),("发帖监控","posts"),("两者都关闭","off")),"all")
        self.filter.changed.connect(lambda:self.refresh());tools.addWidget(self.filter)
        self.search=QLineEdit();self.search.setPlaceholderText("搜索名称、ID 或备注");self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(150);self.search.setMaximumWidth(270)
        self.search.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.search.textChanged.connect(lambda _:self.refresh());tools.addWidget(self.search)
        root.addLayout(tools)
        self.module_banner=QFrame();self.module_banner.setObjectName("SettingsCard")
        banner_lay=QHBoxLayout(self.module_banner);banner_lay.setContentsMargins(14,9,14,9);banner_lay.setSpacing(8)
        banner_text=QLabel("发帖监控未启用 — 表格已隐藏发帖相关列，看板和通知里也不显示发帖内容。已保存的发帖标准保留，在设置中开启后立即恢复。")
        banner_text.setObjectName("SmallMuted");banner_text.setWordWrap(True);banner_lay.addWidget(banner_text,1)
        banner_btn=QPushButton("去设置 →");banner_btn.setObjectName("LinkButton");banner_btn.clicked.connect(self.open_settings_requested.emit);banner_lay.addWidget(banner_btn)
        root.addWidget(self.module_banner)
        self.table=QTableWidget(0,9);self.table.setObjectName("IdManagerTable")
        self.table.setHorizontalHeaderLabels(("选择","头像","专业名称","专业 ID","粉丝监控","发帖监控","发帖标准（h）","备注","资料状态"))
        self.table.setIconSize(QSize(34,34));self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False);self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked|QAbstractItemView.EditTrigger.EditKeyPressed)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setSortingEnabled(True);self.table.sortItems(2,Qt.SortOrder.AscendingOrder)
        widths={0:47,1:57,2:190,3:177,4:88,5:88,6:118,7:170,8:150}
        for col,width in widths.items():
            self.table.setColumnWidth(col,width)
            self.table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(7,QHeaderView.ResizeMode.Stretch)
        for col in (0,4,5):self.table.setItemDelegateForColumn(col,CheckDelegate(self.table))
        self.table.itemChanged.connect(self._item_changed)
        self.table.cellClicked.connect(self._clicked)
        self.table.cellDoubleClicked.connect(self._double_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.table.viewport().installEventFilter(self)
        root.addWidget(self.table,1)
        hint=QLabel("点击“专业名称”表头可按名称升序 / 降序切换排序。名称和头像会在正常巡检时自动更新；未获取资料不会伪造。")
        hint.setObjectName("SmallMuted");hint.setWordWrap(True);root.addWidget(hint)
        self.filter.setCurrentData(str(self.settings.value("manager/filter","all")),emit=False)
        self.search.blockSignals(True);self.search.setText(str(self.settings.value("manager/search","")));self.search.blockSignals(False)
        state=self.settings.value("manager/header")
        if state:
            try:self.table.horizontalHeader().restoreState(state)
            except (TypeError,ValueError):pass
        # Old saved state pointed at the removed sort-order column (7); point it at the name column.
        if self.table.horizontalHeader().sortIndicatorSection() == 7:
            self.table.horizontalHeader().setSortIndicator(2,Qt.SortOrder.AscendingOrder)
        self.filter.changed.connect(self._remember)
        self.search.textChanged.connect(self._remember)
        self.table.horizontalHeader().sectionResized.connect(self._remember)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self._remember)

    def eventFilter(self,obj,event):
        if obj is self.table.viewport():
            if event.type()==QEvent.Type.ContextMenu:return True
            if event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonRelease) and event.button()==Qt.MouseButton.RightButton:return True
        return super().eventFilter(obj,event)

    def _remember(self,*_):
        if self._loading:return
        self.settings.setValue("manager/filter",self.filter.currentData())
        self.settings.setValue("manager/search",self.search.text())
        self.settings.setValue("manager/header",self.table.horizontalHeader().saveState())
        self.settings.sync()

    def set_busy(self,busy):
        self._busy=bool(busy)
        # Keep action buttons clickable during collection so the user gets an immediate
        # bottom toast explaining why an edit cannot run yet.
        for b in (self.add_btn,self.batch_btn,self.delete_btn):b.setEnabled(True)
        # Selection/copying is harmless during collection. Disabling the whole table made
        # single checkbox clicks fail while the external Select All checkbox still worked.
        self.table.setEnabled(True)
        blocked=self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                for col in range(self.table.columnCount()):
                    item=self.table.item(row,col)
                    if item is None:continue
                    flags=Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable
                    if col==0 or (col in (4,5) and not busy):flags|=Qt.ItemFlag.ItemIsUserCheckable
                    if col in (6,7,8) and not busy:flags|=Qt.ItemFlag.ItemIsEditable
                    item.setFlags(flags)
        finally:self.table.blockSignals(blocked)
        self.table.viewport().update()
        if busy:self.summary.setText("正在巡检 · 可查看和复制 ID，修改操作将在本轮结束后恢复")

    def _busy_notice(self):
        show_hint(self,"正在巡检，请等待本轮巡检结束后再修改专业 ID。",kind="warning")

    def _request_add(self):
        if self._busy:
            self._busy_notice();return
        self.add_requested.emit()

    def ids(self):
        checked=[]
        for r in range(self.table.rowCount()):
            item=self.table.item(r,0)
            if item and item.checkState()==Qt.CheckState.Checked:checked.append(str(item.data(Qt.ItemDataRole.UserRole)))
        if checked:return list(dict.fromkeys(checked))
        return list(dict.fromkeys(str(self.table.item(idx.row(),0).data(Qt.ItemDataRole.UserRole))
                                 for idx in self.table.selectionModel().selectedRows()))

    def select_visible(self,checked):
        self.table.blockSignals(True)
        try:
            for r in range(self.table.rowCount()):
                item=self.table.item(r,0)
                if item:item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        finally:self.table.blockSignals(False)
        self._sync_selection_header()

    def _sync_selection_header(self):
        count=self.table.rowCount()
        chosen=sum(1 for r in range(count) if self.table.item(r,0) and self.table.item(r,0).checkState()==Qt.CheckState.Checked)
        self.select_all.blockSignals(True)
        self.select_all.setChecked(count>0 and chosen==count)
        self.select_all.blockSignals(False)
        self.select_all.setToolTip("\u5df2\u52fe\u9009 %s / %s \u4e2a" % (chosen,count))

    def _clicked(self,row,col):
        if self._busy and col in (2,4,5,6,7,8,9):
            self._busy_notice();return
        if col==3:
            text=self.table.item(row,col).text()
            QApplication.clipboard().setText(text)
            show_hint(self,"已复制 ID："+text,kind="success")

    def _double_clicked(self,row,col):
        if col==2:
            if self._busy:
                self._busy_notice();return
            pid=self.table.item(row,0).data(Qt.ItemDataRole.UserRole);self.edit_id(pid)

    def edit_id(self,pid):
        if self._busy:
            self._busy_notice();return
        row=self.store.page(pid)
        if not row:return
        dlg=PageEditDialog(row,self,modules_posts_enabled(self.settings))
        if dlg.exec()==QDialog.DialogCode.Accepted:
            try:self.store.update_config([pid],**dlg.values())
            except (ValueError,TypeError) as exc:QMessageBox.warning(self,"未保存",str(exc));return
            self.refresh();self.config_changed.emit()



    def delete_selected(self):
        if self._busy:
            self._busy_notice();return
        ids=self.ids()
        if not ids:show_hint(self,"请选择需要删除的专业 ID。",kind="warning");return
        self.delete_requested.emit(ids)

    def batch_settings(self):
        if self._busy:
            self._busy_notice();return
        ids=self.ids()
        if not ids:show_hint(self,"请选择一个或多个专业 ID。",kind="warning");return
        dlg=QDialog(self);dlg.setWindowTitle(f"批量设置 {len(ids)} 个专业 ID");dlg.resize(440,316)
        root=QVBoxLayout(dlg);root.setContentsMargins(24,20,24,18);root.setSpacing(10)
        _title=QLabel("批量设置");_title.setObjectName("DialogTitle");root.addWidget(_title)
        _sub=QLabel(f"已选 {len(ids)} 个专业 ID · 不改的项保持原设置");_sub.setObjectName("SmallMuted");root.addWidget(_sub)
        _line=QFrame();_line.setFrameShape(QFrame.Shape.HLine);_line.setObjectName("HeaderDivider");root.addWidget(_line)
        selects={}
        for name,key in (("粉丝监控","monitor_growth"),("发帖监控","monitor_posts")):
            combo=MenuButton((("保持原设置",None),("开启",True),("关闭",False)),None)
            combo.setFixedWidth(190)
            _row=QHBoxLayout();_row.addWidget(QLabel(name));_row.addStretch();_row.addWidget(combo)
            root.addLayout(_row);selects[key]=combo
        if not modules_posts_enabled(self.settings):
            selects["monitor_posts"].setEnabled(False)
        _line2=QFrame();_line2.setFrameShape(QFrame.Shape.HLine);_line2.setObjectName("HeaderDivider");root.addWidget(_line2)
        limit_flag=QCheckBox("修改发帖超时标准");limit_flag.setChecked(True)
        hours=QSpinBox();hours.setRange(1,8760);hours.setValue(24);hours.setSuffix(" 小时");hours.setFixedWidth(130)
        if not modules_posts_enabled(self.settings):
            limit_flag.setEnabled(False);hours.setEnabled(False)
        _lim=QHBoxLayout();_lim.addWidget(limit_flag);_lim.addStretch();_lim.addWidget(hours);root.addLayout(_lim)
        _note=QLabel("发帖超时标准默认已勾选，不想改时取消勾选即可。");_note.setObjectName("SmallMuted");root.addWidget(_note)
        root.addStretch()
        row=QHBoxLayout();row.addStretch();cancel=QPushButton("取消");save=QPushButton("保存")
        cancel.clicked.connect(dlg.reject);save.clicked.connect(dlg.accept);save.setObjectName("PrimaryButton")
        cancel.setFixedWidth(86);save.setFixedWidth(86)
        row.addWidget(cancel);row.addWidget(save);root.addLayout(row)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        fields={key:combo.currentData() for key,combo in selects.items() if combo.currentData() is not None}
        if limit_flag.isChecked():fields["post_limit_hours"]=hours.value()
        if fields:
            self.store.update_config(ids,**fields);self.refresh();self.config_changed.emit()

    def _item_changed(self,item):
        if self._loading:return
        col=item.column()
        if col==0:
            self._sync_selection_header();return
        marker=self.table.item(item.row(),0)
        if not marker:return
        pid=str(marker.data(Qt.ItemDataRole.UserRole))
        if self._busy:self.refresh();return
        try:
            if col in (4,5):
                key="monitor_growth" if col==4 else "monitor_posts"
                self.store.update_config([pid],**{key:item.checkState()==Qt.CheckState.Checked})
                item.sort_key=int(item.checkState()==Qt.CheckState.Checked)
            elif col==6:
                value=int(item.text().strip())
                self.store.update_config([pid],post_limit_hours=value)
                item.sort_key=value
            elif col==7:self.store.update_config([pid],notes=item.text())
            else:return
        except (ValueError,TypeError) as exc:
            QMessageBox.warning(self,"输入无效",str(exc));self.refresh();return
        count=self.table.rowCount()
        growth=sum(self.table.item(r,4).checkState()==Qt.CheckState.Checked for r in range(count))
        posts=sum(self.table.item(r,5).checkState()==Qt.CheckState.Checked for r in range(count))
        self.summary.setText(f"{count} 个 ID · 粉丝监控 {growth} · 发帖监控 {posts}")
        self.config_changed.emit()

    def focus_id(self,pid):
        self.search.clear();self.filter.setCurrentData("all",emit=False);self.refresh()
        for r in range(self.table.rowCount()):
            if self.table.item(r,0).data(Qt.ItemDataRole.UserRole)==pid:
                self.table.selectRow(r);self.table.scrollToItem(self.table.item(r,2));return

    def refresh(self):
        checked=set()
        for r in range(self.table.rowCount()):
            item=self.table.item(r,0)
            if item and item.checkState()==Qt.CheckState.Checked:checked.add(item.data(Qt.ItemDataRole.UserRole))
        selected=set(self.ids()) if self.table.rowCount() else set()
        scroll=self.table.verticalScrollBar().value()
        sort_col=self.table.horizontalHeader().sortIndicatorSection();sort_order=self.table.horizontalHeader().sortIndicatorOrder()
        posts_on=modules_posts_enabled(self.settings)
        self.module_banner.setVisible(not posts_on)
        self.table.setColumnHidden(5,not posts_on);self.table.setColumnHidden(6,not posts_on)
        needle=self.search.text().casefold().strip();mode=self.filter.currentData()
        if mode=="posts" and not posts_on:mode="all"
        rows=[]
        for row in self.store.list_pages():
            if needle and needle not in (display_name(row)+" "+row["page_id"]+" "+row["notes"]).casefold():continue
            if mode=="growth" and not row["monitor_growth"]:continue
            if mode=="posts" and not row["monitor_posts"]:continue
            if mode=="off" and (row["monitor_growth"] or row["monitor_posts"]):continue
            rows.append(row)
        self._loading=True;self.table.blockSignals(True);self.table.setSortingEnabled(False)
        self.table.clearContents();self.table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            pid=row["page_id"]
            for col in range(9):
                item=SortItem("")
                flags=Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable
                if col in (0,4,5):flags|=Qt.ItemFlag.ItemIsUserCheckable
                if col in (6,7):flags|=Qt.ItemFlag.ItemIsEditable
                item.setFlags(flags);item.setTextAlignment(Qt.AlignmentFlag.AlignCenter);self.table.setItem(i,col,item)
            self.table.item(i,0).setData(Qt.ItemDataRole.UserRole,pid)
            self.table.item(i,0).setCheckState(Qt.CheckState.Checked if pid in checked else Qt.CheckState.Unchecked)
            wrapper=QWidget();avatar_layout=QHBoxLayout(wrapper);avatar_layout.setContentsMargins(0,0,0,0)
            avatar_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar_layout.addWidget(AvatarWidget(display_name(row),row["avatar_path"],36,page_id=pid))
            self.table.setCellWidget(i,1,wrapper)
            for col,text in ((2,display_name(row)),(3,pid),(6,str(row["post_limit_hours"])),(7,row["notes"])):
                item=self.table.item(i,col);item.setText(text);item.sort_key=int(text) if col==6 else text.casefold()
            self.table.item(i,2).setToolTip(html.escape("真实名称："+(normalize_name(row["page_name"],pid) or "未获取"))+"\n双击编辑自定义名称与配置")
            self.table.item(i,3).setToolTip("点击复制完整 ID："+pid)
            for col,key in ((4,"monitor_growth"),(5,"monitor_posts")):
                item=self.table.item(i,col);item.setCheckState(Qt.CheckState.Checked if row[key] else Qt.CheckState.Unchecked);item.sort_key=int(row[key])
            if row.get("diagnosis_code")=="page_unavailable":state="主页不可用"
            elif row.get("diagnosis_code")=="login":state="需登录验证"
            elif row.get("growth_error") or (posts_on and row.get("post_error")):state="读取失败"
            elif row.get("name_error"):state="待核实"
            elif normalize_name(row["page_name"],pid):state="已同步"
            else:state="名称待获取"
            _diag_parts=[str(row.get("diagnosis_detail") or ""),str(row.get("name_error") or ""),str(row.get("growth_error") or "")]
            if posts_on:_diag_parts.append(str(row.get("post_error") or ""))
            _diag_tip="；".join(x for x in _diag_parts if x)
            item=self.table.item(i,8);item.setText(state);item.setToolTip(html.escape(_diag_tip or str(row.get("metadata_checked_at") or "巡检时同步资料")))
            self.table.setRowHeight(i,58)
        self.table.setSortingEnabled(True);self.table.sortItems(sort_col,sort_order)
        self.table.blockSignals(False);self._loading=False
        for r in range(self.table.rowCount()):
            if self.table.item(r,0).data(Qt.ItemDataRole.UserRole) in selected:
                for c in range(self.table.columnCount()):self.table.item(r,c).setSelected(True)
        self.table.verticalScrollBar().setValue(scroll)
        self._sync_selection_header()
        g=sum(r["monitor_growth"] for r in rows);p=sum(r["monitor_posts"] for r in rows)
        self.summary.setText(f"{len(rows)} 个 ID · 粉丝监控 {g}"+(f" · 发帖监控 {p}" if posts_on else ""))
        self.set_busy(self._busy)


class SettingsPage(QWidget):
    login_requested=pyqtSignal()
    save_requested=pyqtSignal(bool)
    export_requested=pyqtSignal()
    backup_requested=pyqtSignal()
    data_dir_requested=pyqtSignal()
    theme_requested=pyqtSignal(str)
    ui_scale_requested=pyqtSignal(int)
    toast_position_requested=pyqtSignal(str)

    def __init__(self,store:Store,settings:QSettings):
        super().__init__();self.store=store;self.settings=settings
        self.build_ui();self.load_settings()
        self.autosave=QTimer(self);self.autosave.setSingleShot(True)
        self.autosave.timeout.connect(self._request_autosave)
        for widget in self.findChildren(QSpinBox):
            widget.setKeyboardTracking(isinstance(widget,DirectNumberSpinBox))
            widget.valueChanged.connect(lambda *_:self.autosave.start(260))
            widget.editingFinished.connect(lambda:self.autosave.start(1))
        for widget in self.findChildren(QCheckBox):
            widget.toggled.connect(lambda *_:self.autosave.start(120))
        for widget in self.findChildren(SwitchToggle):
            widget.toggled.connect(self._module_switch_changed)

    def _refresh_module_statuses(self):
        self.module_growth_status.setText("已开启" if self.module_growth_switch.isChecked() else "未开启")
        self.module_posts_status.setText("已开启" if self.module_posts_switch.isChecked() else "未开启")

    def _module_switch_changed(self):
        if not self.module_growth_switch.isChecked() and not self.module_posts_switch.isChecked():
            show_hint(self,"至少保留一个监控模块",kind="warning")
            sender=self.sender()
            if isinstance(sender,SwitchToggle):
                sender.blockSignals(True);sender.setChecked(True);sender.blockSignals(False)
            return
        self._refresh_module_statuses()
        self.autosave.start(120)

    def set_selected_theme(self,name):
        for key,card in getattr(self,"theme_cards",{}).items():
            card.setSelected(key==name)

    def set_ui_scale_label(self,scale):
        if hasattr(self,"zoom_label"):self.zoom_label.setText(f"{int(scale)}%")

    def _on_toast_position_changed(self):
        # Save first (synchronous emit), then show the real toast so it
        # appears at the position just selected.
        self.toast_position_requested.emit(self.toast_position_choice.currentData())
        show_hint(self,"提示会显示在这里",kind="success")

    @staticmethod
    def card():
        card=QFrame();card.setObjectName("SettingsCard")
        layout=QVBoxLayout(card);layout.setContentsMargins(20,18,20,18);layout.setSpacing(13)
        return card,layout

    def build_ui(self):
        root=QVBoxLayout(self);root.setContentsMargins(30,24,30,20);root.setSpacing(16)
        tabs=QTabWidget();tabs.setObjectName("SettingsTabs");root.addWidget(tabs,1)
        self.settings_tabs=tabs
        def make_tab(label):
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
            body=QWidget();layout=QVBoxLayout(body);layout.setContentsMargins(8,10,12,8);layout.setSpacing(14)
            scroll.setWidget(body);tabs.addTab(scroll,label);return layout

        modules_layout=make_tab("监控模块")
        modules,modl=self.card()
        def _module_row(name,desc):
            row=QHBoxLayout();row.setSpacing(12)
            texts=QVBoxLayout();texts.setSpacing(1)
            n=QLabel(name);n.setObjectName("SettingsTitle");texts.addWidget(n)
            d=QLabel(desc);d.setObjectName("SmallMuted");d.setWordWrap(True);texts.addWidget(d)
            row.addLayout(texts,1)
            sw=SwitchToggle();row.addWidget(sw)
            st=QLabel("");st.setMinimumWidth(44);st.setAlignment(Qt.AlignmentFlag.AlignRight);row.addWidget(st)
            modl.addLayout(row);return sw,st
        self.module_growth_switch,self.module_growth_status=_module_row("粉丝增长监控","粉丝数、每日新增、增长提醒")
        self.module_posts_switch,self.module_posts_status=_module_row("发帖时间监控","距上次发帖、超时提醒、发帖标准")
        modules_layout.addWidget(modules);modules_layout.addStretch()

        themes_layout=make_tab("外观")
        themes,thel=self.card()
        theme_row=QHBoxLayout();theme_row.setSpacing(12)
        self.theme_cards={}
        _theme_descs={"云白":"暖白底色，深蓝点缀","护眼绿":"淡绿底色，深绿点缀（微信绿系）","曜石黑":"深灰底色，柔和浅蓝"}
        for _name in THEME_PRESETS:
            _preset=THEME_PRESETS[_name]
            card=OptionCard(_name,_theme_descs.get(_name,""))
            card.setFixedHeight(132)
            _preview=QFrame();_preview.setFixedHeight(56)
            _preview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
            _preview.setStyleSheet(f"background:{_preset['bg']};border:1px solid {_preset['border']};border-radius:8px;")
            _pl=QHBoxLayout(_preview);_pl.setContentsMargins(5,5,5,5);_pl.setSpacing(5)
            _strip=QFrame();_strip.setFixedWidth(26)
            _strip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
            _strip.setStyleSheet(f"background:{_preset['sidebar']};border:1px solid {_preset['border']};border-radius:4px;")
            _pl.addWidget(_strip)
            _bars=QVBoxLayout();_bars.setSpacing(4)
            _bar1=QFrame();_bar1.setFixedHeight(12)
            _bar1.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
            _bar1.setStyleSheet(f"background:{_preset['accent']};border-radius:3px;")
            _bar2=QFrame();_bar2.setFixedHeight(12)
            _bar2.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
            _bar2.setStyleSheet(f"background:{_preset['panel_2']};border:1px solid {_preset['border']};border-radius:3px;")
            _bars.addWidget(_bar1);_bars.addWidget(_bar2);_bars.addStretch();_pl.addLayout(_bars,1)
            card.layout().insertWidget(0,_preview)
            card.clicked.connect(lambda _=False,n=_name:self.theme_requested.emit(n))
            theme_row.addWidget(card,1);self.theme_cards[_name]=card
        thel.addLayout(theme_row)
        _zoom_title=QLabel("界面缩放");_zoom_title.setObjectName("SettingsTitle");thel.addWidget(_zoom_title)
        _zoom_row=QHBoxLayout();_zoom_row.setSpacing(8)
        self.zoom_out_btn=QPushButton("−");self.zoom_out_btn.setFixedSize(38,36)
        self.zoom_label=QLabel("100%");self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter);self.zoom_label.setFixedWidth(64)
        self.zoom_in_btn=QPushButton("+");self.zoom_in_btn.setFixedSize(38,36)
        self.zoom_out_btn.clicked.connect(lambda:self.ui_scale_requested.emit(ui_scale_percent(self.settings)-10))
        self.zoom_in_btn.clicked.connect(lambda:self.ui_scale_requested.emit(ui_scale_percent(self.settings)+10))
        _zoom_row.addWidget(self.zoom_out_btn);_zoom_row.addWidget(self.zoom_label);_zoom_row.addWidget(self.zoom_in_btn)
        _zoom_note=QLabel("80% – 130%，每次 10%，立即生效");_zoom_note.setObjectName("SmallMuted");_zoom_row.addWidget(_zoom_note)
        _zoom_row.addStretch();thel.addLayout(_zoom_row)
        _toast_title=QLabel("消息提示位置");_toast_title.setObjectName("SettingsTitle");thel.addWidget(_toast_title)
        _toast_note=QLabel("点选立即弹出一条真实提示");_toast_note.setObjectName("SmallMuted");thel.addWidget(_toast_note)
        self.toast_position_choice=SegmentedChoice(TOAST_POSITIONS,"bottom_center")
        self.toast_position_choice.changed.connect(self._on_toast_position_changed)
        thel.addWidget(self.toast_position_choice)
        themes_layout.addWidget(themes);themes_layout.addStretch()

        merged_layout=make_tab("连接与更新")
        browser,bl=self.card()
        _conn_title=QLabel("浏览器连接器");_conn_title.setObjectName("SettingsTitle");bl.addWidget(_conn_title)
        row=QHBoxLayout();row.setSpacing(10)
        self.login_button=QPushButton("浏览器连接");self.login_button.setObjectName("PrimaryButton")
        self.login_button.clicked.connect(self.login_requested.emit);row.addWidget(self.login_button)
        self.connector_package_button=QPushButton(f"获取连接器 v{BUNDLED_CONNECTOR_VERSION}");self.connector_package_button.setObjectName("SecondaryButton")
        self.connector_package_button.setToolTip("将软件内置的浏览器连接器 ZIP 保存到你选择的位置")
        self.connector_package_button.clicked.connect(lambda:save_bundled_connector(self));row.addWidget(self.connector_package_button)
        row.addStretch();bl.addLayout(row)
        self.connector_summary=QLabel("等待浏览器连接");self.connector_summary.setWordWrap(True)
        self.connector_summary.setTextFormat(Qt.TextFormat.PlainText);bl.addWidget(self.connector_summary)
        _div=QFrame();_div.setFrameShape(QFrame.Shape.HLine);_div.setObjectName("HeaderDivider");bl.addWidget(_div)
        _upd_title=QLabel("版本更新");_upd_title.setObjectName("SettingsTitle");bl.addWidget(_upd_title)
        _ver_label=QLabel(f"当前版本：v{APP_VERSION}");_ver_label.setTextFormat(Qt.TextFormat.PlainText);_ver_label.setObjectName("SmallMuted");bl.addWidget(_ver_label)
        self.auto_update=QCheckBox("启动后自动检查新版本，并在发现新版时提示")
        bl.addWidget(self.auto_update)
        self.auto_install=QCheckBox("下载完成后自动安装更新")
        self.auto_install.setChecked(True)
        bl.addWidget(self.auto_install)
        merged_layout.addWidget(browser);merged_layout.addStretch()

        collect_layout=make_tab("巡检与提醒")
        collect,cl=self.card()
        form=QGridLayout();form.setHorizontalSpacing(18);form.setVerticalSpacing(13)
        self.interval=DirectNumberSpinBox();self.interval.setRange(5,1440)
        self.jitter_min=DirectNumberSpinBox();self.jitter_min.setRange(0,1439)
        self.jitter_max=DirectNumberSpinBox();self.jitter_max.setRange(0,1439)
        self.gap_min=DirectNumberSpinBox();self.gap_min.setRange(0,120)
        self.gap_max=DirectNumberSpinBox();self.gap_max.setRange(0,120)
        form.addWidget(QLabel("每轮间隔（分钟）"),0,0);form.addWidget(self.interval,0,1)
        float_label=QLabel("浮动范围（分钟）");form.addWidget(float_label,0,2)
        float_box=QWidget();float_layout=QHBoxLayout(float_box);float_layout.setContentsMargins(0,0,0,0);float_layout.setSpacing(6)
        float_layout.addWidget(self.jitter_min);float_layout.addWidget(QLabel("–"));float_layout.addWidget(self.jitter_max);float_layout.addStretch();form.addWidget(float_box,0,3)
        form.addWidget(QLabel("主页间隔（秒）"),1,0)
        gap_box=QWidget();gap_layout=QHBoxLayout(gap_box);gap_layout.setContentsMargins(0,0,0,0);gap_layout.setSpacing(6)
        gap_layout.addWidget(self.gap_min);gap_layout.addWidget(QLabel("–"));gap_layout.addWidget(self.gap_max);gap_layout.addStretch();form.addWidget(gap_box,1,1,1,3)
        for widget in (self.interval,self.jitter_min,self.jitter_max,self.gap_min,self.gap_max):widget.setFixedWidth(86)
        self.start_auto=QCheckBox("启动时自动巡检")
        self.start_auto.setToolTip("只有在此明确开启，下次启动才自动巡检。主界面的按钮仅控制本次运行。")
        self.silent_to_tray=QCheckBox("静默收起到托盘")
        self.silent_to_tray.setToolTip("开启：关闭窗口不提示。关闭：收起时提示仍在后台运行。两种情况都保持托盘巡检，完全退出请用托盘菜单。")
        form.addWidget(self.start_auto,2,0,1,4);form.addWidget(self.silent_to_tray,3,0,1,4)
        form.setColumnStretch(1,1);form.setColumnStretch(3,1);cl.addLayout(form)
        _div=QFrame();_div.setFrameShape(QFrame.Shape.HLine);_div.setObjectName("HeaderDivider");cl.addWidget(_div)
        _gt=QLabel("增长提醒");_gt.setObjectName("SettingsTitle");cl.addWidget(_gt)
        self.alert_enabled=QCheckBox("开启桌面增长提醒")
        cl.addWidget(self.alert_enabled)
        _tr=QHBoxLayout();_tr.setSpacing(8)
        _tr.addWidget(QLabel("当日增长阈值"))
        self.threshold=DirectNumberSpinBox();self.threshold.setRange(1,100_000_000);self.threshold.setSingleStep(100)
        self.threshold.setFixedWidth(110)
        _tr.addWidget(self.threshold);_tr.addStretch()
        cl.addLayout(_tr)
        collect_layout.addWidget(collect);collect_layout.addStretch()

        data_layout=make_tab("数据管理")
        data,dl=self.card()
        self.data_path_label=QLabel(str(DATA_DIR));self.data_path_label.setTextFormat(Qt.TextFormat.PlainText);self.data_path_label.setObjectName("PathLabel");self.data_path_label.setWordWrap(True);dl.addWidget(self.data_path_label)
        buttons=QHBoxLayout()
        self.choose_data_dir=QPushButton("更改保存目录并迁移数据");self.choose_data_dir.setObjectName("PrimaryButton")
        self.choose_data_dir.clicked.connect(self.data_dir_requested.emit);buttons.addWidget(self.choose_data_dir)
        folder=QPushButton("打开数据目录");folder.setObjectName("SecondaryButton")
        folder.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR))));buttons.addWidget(folder)
        backup=QPushButton("备份数据库");backup.setObjectName("SecondaryButton");backup.clicked.connect(self.backup_requested.emit)
        buttons.addWidget(backup);buttons.addStretch();dl.addLayout(buttons)
        data_layout.addWidget(data);data_layout.addStretch()

        self.save_note=QLabel("所有设置修改后自动保存，下次启动继续使用");self.save_note.setObjectName("SmallMuted")
        root.addWidget(self.save_note)


    def refresh_data_path(self):
        self.data_path_label.setText(str(DATA_DIR))

    def open_monitor_directory(self):
        self.login_requested.emit()

    def load_settings(self):
        minutes,j0,j1,g0,g1=random_inspection_timing(self.settings)
        pairs=((self.interval,minutes),(self.jitter_min,j0),(self.jitter_max,j1),(self.gap_min,g0),(self.gap_max,g1),
               (self.threshold,_bounded_int(self.settings.value("alert_threshold",500),500,1,100_000_000)))
        for widget,value in pairs:
            widget.blockSignals(True);widget.setValue(value);widget.blockSignals(False)
        for widget,key,default in ((self.start_auto,"start_auto",False),(self.silent_to_tray,"silent_to_tray",True),
                (self.alert_enabled,"alert_enabled",True),
                (self.auto_update,"auto_check_updates",True),
                (self.auto_install,"update/auto_install",True)):
            widget.blockSignals(True);widget.setChecked(is_true(self.settings.value(key,default),default));widget.blockSignals(False)
        for widget,key,default in ((self.module_growth_switch,MODULE_GROWTH_KEY,True),(self.module_posts_switch,MODULE_POSTS_KEY,False)):
            widget.blockSignals(True);widget.setChecked(is_true(self.settings.value(key,default),default));widget.blockSignals(False)
        self._refresh_module_statuses()
        self.set_selected_theme(migrate_theme_name(self.settings.value("ui_theme","云白")))
        _pos=str(self.settings.value("toast_position","bottom_center"))
        if _pos in [k for _,k in TOAST_POSITIONS]:self.toast_position_choice.setCurrentData(_pos,emit=False)
        self.set_ui_scale_label(ui_scale_percent(self.settings))

    def save_settings(self):
        timing=save_random_timing(self.settings,(self.interval.value(),self.jitter_min.value(),self.jitter_max.value(),self.gap_min.value(),self.gap_max.value()))
        for widget,value in zip((self.interval,self.jitter_min,self.jitter_max,self.gap_min,self.gap_max),timing):
            widget.blockSignals(True);widget.setValue(value);widget.blockSignals(False)
        values={
            "start_auto":int(self.start_auto.isChecked()),
            "min_to_tray":1,"silent_to_tray":int(self.silent_to_tray.isChecked()),"alert_enabled":int(self.alert_enabled.isChecked()),
            "alert_threshold":self.threshold.value(),
            "auto_check_updates":int(self.auto_update.isChecked()),
            "update/auto_install":int(self.auto_install.isChecked()),
            MODULE_GROWTH_KEY:int(self.module_growth_switch.isChecked()),MODULE_POSTS_KEY:int(self.module_posts_switch.isChecked()),
        }
        for key,value in values.items():self.settings.setValue(key,value)
        self.settings.sync()
        if self.settings.status()!=QSettings.Status.NoError:
            raise OSError("无法写入配置文件："+self.settings.fileName())

    def _request_autosave(self):
        self.save_requested.emit(False)

    def flush_pending(self):
        if self.autosave.isActive():
            self.autosave.stop()
            # Keep MainWindow's runtime schedule and quick controls in sync, too.
            self.save_requested.emit(False)
        # Flush all controls even if a last click has not yet scheduled the debounce timer.
        self.save_settings()




class QuickToolTipStyle(QProxyStyle):
    def styleHint(self,hint,option=None,widget=None,returnData=None):
        if hint==QStyle.StyleHint.SH_ToolTip_WakeUpDelay:return 60
        if hint==QStyle.StyleHint.SH_ToolTip_FallAsleepDelay:return 0
        return super().styleHint(hint,option,widget,returnData)

class UpdateWorker(QObject):
    done=pyqtSignal(dict)
    progress=pyqtSignal(object,object)
    def __init__(self,operation,info=None,folder=None):
        super().__init__();self.operation=operation;self.info=info or {};self.folder=folder;self.cancel_event=threading.Event()
    def cancel(self):self.cancel_event.set()
    def run(self):
        try:
            if self.operation=="check":
                result=query_latest_release()
            elif self.operation=="download":
                path=download_release_asset(self.info["asset"],self.folder,
                    progress=lambda a,b:self.progress.emit(a,b),cancel=self.cancel_event)
                result={"status":"ready","path":path,"info":self.info}
            else:
                path=validate_staged_update(self.info["asset"],self.info["path"],self.folder)
                result={"status":"ready","path":str(path),"info":self.info}
        except Exception as exc:
            result={"status":"cancelled" if self.cancel_event.is_set() else "error","message":str(exc)[:600]}
        self.done.emit(result)

class UpdateDialog(QDialog):
    download_requested=pyqtSignal()
    install_requested=pyqtSignal()
    later_requested=pyqtSignal()
    cancel_requested=pyqtSignal()
    def __init__(self,info,parent=None):
        super().__init__(parent);self.info=info;self.ready_path=""
        self.setWindowTitle("发现新版本 · "+APP_TITLE);self.resize(630,530)
        root=QVBoxLayout(self);root.setContentsMargins(24,22,24,20);root.setSpacing(13)
        head_row=QHBoxLayout();head_row.setSpacing(13)
        head_row.addWidget(BrandMark(40))
        head_text=QVBoxLayout();head_text.setSpacing(2)
        heading_row=QHBoxLayout();heading_row.setSpacing(8)
        heading=QLabel("发现新版本");heading.setObjectName("PageTitle");heading_row.addWidget(heading)
        pill=QLabel("V"+str(info.get("version","")));pill.setObjectName("UpdatePill");heading_row.addWidget(pill);heading_row.addStretch()
        head_text.addLayout(heading_row)
        repo=QLabel("当前 V"+APP_VERSION+"   →   V"+str(info.get("version","")));repo.setObjectName("SmallMuted");head_text.addWidget(repo)
        head_row.addLayout(head_text,1);root.addLayout(head_row)
        title=QLabel(str(info.get("title") or "版本更新"));title.setTextFormat(Qt.TextFormat.PlainText);title.setWordWrap(True);root.addWidget(title)
        self.notes=QPlainTextEdit();self.notes.setReadOnly(True);self.notes.setPlainText(str(info.get("notes") or "暂无更新日志"))
        root.addWidget(self.notes,1)
        self.status=QLabel();self.status.setTextFormat(Qt.TextFormat.PlainText);self.status.setWordWrap(True);self.status.setObjectName("SmallMuted");root.addWidget(self.status)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0);self.progress.hide();root.addWidget(self.progress)
        row=QHBoxLayout();row.addStretch()
        self.cancel_btn=QPushButton();self.cancel_btn.hide()
        self.later=QPushButton("以后再说");self.later.clicked.connect(self._later);row.addWidget(self.later)
        self.action=QPushButton("升级");self.action.setObjectName("PrimaryButton");self.action.clicked.connect(self._action);row.addWidget(self.action)
        root.addLayout(row)
        asset=info.get("asset")
        if not asset:
            self.action.setEnabled(False);self.status.setText("此版本尚未上传适合当前系统的更新包。")
        elif not asset.get("sha256"):
            self.action.setEnabled(False);self.status.setText("发布包缺少 SHA-256，自动下载暂不可用，请发布者完善 Release 资产校验信息。")
        else:
            self.status.setText("下载将在后台进行；不会在下载后未经确认就退出或安装。"+
                ("\n当前为源码运行方式：下载的新文件不会自动覆盖正在执行的 Python 文件。" if asset.get("source_mode") else ""))
    def _action(self):
        if self.ready_path:self.install_requested.emit()
        else:self.download_requested.emit()
    def _later(self):
        self.later_requested.emit();self.hide()
    def downloading(self):
        self.action.setEnabled(False);self.progress.show()
        self.status.setText("正在后台下载。可以选择“以后再说”关闭窗口，下载会继续。")
    def set_progress(self,done,total):
        self.progress.setValue(int(100*int(done)/max(1,int(total))))
        self.status.setText(f"已下载 {int(done)/1048576:.1f} / {int(total)/1048576:.1f} MB，完成后校验 SHA-256。")
    def ready(self,path):
        self.ready_path=str(path);self.progress.show();self.progress.setValue(100);self.action.setEnabled(True)
        allowed,reason=signed_install_available(self.info.get("asset") or {})
        self.action.setText("现在更新" if allowed else "打开下载目录")
        self.status.setText("下载和完整性校验完成。\n"+("下载完成，是否现在更新？点击“现在更新”会安全结束巡检并重启；也可以选择“以后再说”。" if allowed else reason))
    def error(self,text):
        self.status.setText(str(text));self.action.setEnabled(bool((self.info.get("asset") or {}).get("sha256")))


class WindowResizeHandle(QWidget):
    """Transparent native resize edge for the frameless main window."""
    def __init__(self,edges,cursor,parent=None):
        super().__init__(parent);self.edges=edges;self.setCursor(cursor);self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,False)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and not self.window().isMaximized():
            handle=self.window().windowHandle()
            try:
                if handle and handle.startSystemResize(self.edges):
                    event.accept();return
            except Exception:pass
        super().mousePressEvent(event)


class FirstRunDialog(QDialog):
    """Ask once which modules to monitor. Default: follower growth only."""

    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle("第一次运行");self.resize(560,470)
        self.choice="growth"
        root=QVBoxLayout(self);root.setContentsMargins(26,24,26,20);root.setSpacing(12)
        mark=BrandMark(46);root.addWidget(mark)
        title=QLabel("第一次运行：先选要监测什么");title.setObjectName("DialogTitle");root.addWidget(title)
        sub=QLabel("这个软件有两个监测板块。默认只开粉丝增长；发帖时间监测会多读页面内容、巡检稍慢一点，不需要的话可以先不开，以后随时在设置里打开，已保存的发帖标准不会丢。")
        sub.setWordWrap(True);sub.setObjectName("SmallMuted");root.addWidget(sub)
        self.opt_growth=OptionCard("只监测粉丝增长","看板只显示粉丝数和每日新增，界面最干净。适合只关心涨粉的用户。")
        self.opt_both=OptionCard("同时监测粉丝增长和发帖时间","多一个“距上次发帖”和超时提醒。适合要盯更新频率、怕停更的用户。")
        for card,choice in ((self.opt_growth,"growth"),(self.opt_both,"both")):
            card.clicked.connect(lambda _=False,c=choice:self._select(c));root.addWidget(card)
        self._select("growth")
        actions=QHBoxLayout();actions.setSpacing(10)
        ok=QPushButton("确认，开始使用");ok.setObjectName("PrimaryButton");ok.clicked.connect(self.accept);actions.addWidget(ok)
        skip=QPushButton("以后再说");skip.setObjectName("LinkButton");skip.clicked.connect(self.accept);actions.addWidget(skip)
        actions.addStretch();root.addLayout(actions)
        note=QLabel("只问这一次。以后改主意：设置 → 监控模块，随时开关，开关后看板和卡片会跟着变。")
        note.setObjectName("SmallMuted");note.setWordWrap(True);root.addWidget(note)

    def _select(self,choice):
        self.choice=choice
        self.opt_growth.setSelected(choice=="growth");self.opt_both.setSelected(choice=="both")


class MainWindow(QMainWindow):
    # Cross-thread jump request: the Windows toast callback runs on a WinRT
    # background thread, so it must not touch widgets directly. Emitting this
    # signal from any thread queues the jump onto the GUI thread.
    open_alert_requested = pyqtSignal(object)

    def __init__(self):
        super().__init__();self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        self._ui_restoring=True
        self.open_alert_requested.connect(self.open_alert_notification)
        legacy=QSettings("GrowthRadar","FBGrowthRadar")
        directory=read_settings_location(DATA_DIR,str(legacy.value("data_directory","") or ""))
        self._set_paths(directory)
        ini=DATA_DIR/"settings.ini";first_local=not ini.exists()
        self.settings=QSettings(str(ini),QSettings.Format.IniFormat);self.settings.setFallbacksEnabled(False)
        if first_local and not os.environ.get("FBPM_DATA_DIR"):
            for key in legacy.allKeys():self.settings.setValue(key,legacy.value(key))
        self._preferences_migrated=migrate_runtime_preferences(self.settings)
        migrate_random_preferences(self.settings)
        self._settings_timing=random_inspection_timing(self.settings)
        self.settings.setValue("data_directory",str(DATA_DIR));self.settings.sync()
        if self.settings.status()!=QSettings.Status.NoError:raise RuntimeError("无法写入本地配置文件："+str(ini))
        write_settings_location(DATA_DIR)
        self._update_thread=None;self._update_worker=None;self._update_dialog=None;self._update_info=None
        self._update_manual=False;self._install_command=None
        self._ui_save_timer=QTimer(self);self._ui_save_timer.setSingleShot(True);self._ui_save_timer.timeout.connect(self.save_ui_state)
        self._updates_timer=QTimer(self);self._updates_timer.setInterval(6*60*60*1000)
        self._updates_timer.timeout.connect(lambda:self.check_for_updates(False))
        self.store=Store(DB_PATH)
        def old_json(key,fallback):
            try:return json.loads(str(self.settings.value(key,json.dumps(fallback))))
            except (ValueError,TypeError):return fallback
        self.store.migrate_legacy_settings(old_json("post_monitor_rules",[]),old_json("post_monitor_data",{}))
        self.worker=None;self.worker_thread=None;self.login_worker=None;self.login_thread=None
        self._closing=False;self._maintenance=False;self._tray_hint_shown=False
        self.auto_enabled=False;self.next_run_at=None;self.active_run_id=None
        self.run_started_at=None;self.run_ok=0;self.run_fail=0;self.current_purpose="monitor"
        self._tick=0;self._popup=None;self._notice_queue=[];self._toast=None
        self.auto_timer=QTimer(self);self.auto_timer.setSingleShot(True)
        self.auto_timer.timeout.connect(lambda:self.start_collection(False))
        self.count_timer=QTimer(self);self.count_timer.setInterval(1000);self.count_timer.timeout.connect(self.update_countdown)
        self.paint_timer=QTimer(self);self.paint_timer.setSingleShot(True);self.paint_timer.timeout.connect(self.refresh_all)
        self.notice_timer=QTimer(self);self.notice_timer.setSingleShot(True);self.notice_timer.timeout.connect(self.flush_notices)
        self.apply_theme(str(self.settings.value("ui_theme","云白")),refresh=False)
        app_icon=make_app_icon()
        QApplication.instance().setWindowIcon(app_icon)
        self.setWindowIcon(app_icon);self.setWindowTitle(APP_TITLE+" · "+APP_VERSION)
        self.resize(1536,1024);self.setMinimumSize(1200,800)
        self.tray=QSystemTrayIcon(make_app_icon(),self);self.tray.setToolTip(APP_TITLE)
        self.tray_menu=QMenu(self)
        self.tray_menu.addAction("打开监控看板",self.show_dashboard)
        self.tray_menu.addAction("立即巡检",self.dashboard_run_button)
        self.tray_menu.addAction("启用 / 暂停自动巡检",self.toggle_auto)
        self.tray_menu.addSeparator();self.tray_menu.addAction("完全退出",self.exit_application)
        self.tray.setContextMenu(self.tray_menu);self.tray.activated.connect(self.on_tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():self.tray.show()
        self.connector=ConnectorBridge(DATA_DIR/"connector_registry.json",CONNECTOR_PORT)
        if not os.environ.get("FBPM_TEST_MODE"):
            try:self.connector.start()
            except ConnectorError as exc:log_exception(str(exc))
        self._connector_dialog=None
        self._pending_dialogs=set();self._pending_dismissed={};self._approval_dialog_open=False
        self._connector_timer=QTimer(self);self._connector_timer.setInterval(1000)
        self._connector_timer.timeout.connect(self.refresh_connector_summary)
        self.build_ui();self.apply_style();self.refresh_all();self.count_timer.start()
        self._connector_timer.start();self.refresh_connector_summary()
        self.size_grip=QSizeGrip(self);self.size_grip.setFixedSize(16,16)
        self.size_grip.move(self.width()-18,self.height()-18);self.size_grip.raise_()
        self._create_resize_handles()
        self.restore_ui_state()
        if not os.environ.get("FBPM_TEST_MODE") and "--diagnose" not in sys.argv:
            QTimer.singleShot(1800,self.startup_update_check);self._updates_timer.start()
        if self.store.upgrade_backup:self.dashboard.status.setText("升级前安全备份已保存："+self.store.upgrade_backup)
        if is_true(self.settings.value("start_auto","0")) and not os.environ.get("FBPM_TEST_MODE") and "--diagnose" not in sys.argv:
            QTimer.singleShot(900,self.start_auto)
        if not os.environ.get("FBPM_TEST_MODE"):
            QTimer.singleShot(500,self._ask_first_run_modules)

    def _ask_first_run_modules(self):
        if self._closing:return
        if self.settings.value(MODULES_ASKED_KEY) is not None:return
        dlg=FirstRunDialog(self)
        dlg.exec()
        self.settings.setValue(MODULE_GROWTH_KEY,1)
        self.settings.setValue(MODULE_POSTS_KEY,1 if dlg.choice=="both" else 0)
        self.settings.setValue(MODULES_ASKED_KEY,1)
        self.settings.sync()
        self.settings_page.load_settings()
        self.refresh_all()

    @staticmethod
    def _set_paths(path):
        global DATA_DIR,DB_PATH,BROWSER_PROFILE_DIR,AVATAR_DIR
        DATA_DIR=ensure_private_directory(Path(path))
        DB_PATH=DATA_DIR/"fb_growth_radar_v1.db";BROWSER_PROFILE_DIR=DATA_DIR/"browser_profile";AVATAR_DIR=DATA_DIR/"avatars"

    def build_ui(self):
        root=QWidget();root.setObjectName("Root");self.setCentralWidget(root)
        self._root_layout=QVBoxLayout(root);self._root_layout.setContentsMargins(1,1,1,1);self._root_layout.setSpacing(0)
        shell=QHBoxLayout();shell.setContentsMargins(0,0,0,0);shell.setSpacing(0)
        self.sidebar=QWidget();self.sidebar.setObjectName("Sidebar");self.sidebar.setFixedWidth(240)
        side=QVBoxLayout(self.sidebar);side.setContentsMargins(14,12,14,10);side.setSpacing(0)
        brand=DraggableHeader();brand.setObjectName("BrandRow")
        brand_lay=QHBoxLayout(brand);brand_lay.setContentsMargins(6,2,6,8);brand_lay.setSpacing(10)
        self.brand_mark=BrandMark(34);brand_lay.addWidget(self.brand_mark)
        brand_text=QVBoxLayout();brand_text.setSpacing(1)
        self.brand_name=QLabel(APP_TITLE);self.brand_name.setObjectName("BrandName")
        self.brand_name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True);brand_text.addWidget(self.brand_name)
        tagline=QLabel("Facebook 主页监控");tagline.setObjectName("BrandSub")
        tagline.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True);brand_text.addWidget(tagline)
        brand_lay.addLayout(brand_text,1);side.addWidget(brand)
        self.brand_caption=tagline
        nav_label=QLabel("监控");nav_label.setObjectName("NavLabel");side.addWidget(nav_label)
        self.nav_buttons={}
        for index,kind,text in ((0,"home","监控看板"),(2,"bell","通知"),(3,"pages","ID管理")):
            row=QHBoxLayout();row.setContentsMargins(0,0,0,0);row.setSpacing(0)
            btn=QPushButton(text);btn.setObjectName("SideNav");btn.setProperty("iconKind",kind)
            btn.setIcon(ui_icon(kind,MUTED));btn.setIconSize(QSize(22,22));btn.setFixedHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False,i=index:self.switch_page(i))
            row.addWidget(btn,1)
            if index==2:
                self.notification_badge=QLabel(btn);self.notification_badge.setObjectName("NotificationBadge")
                self.notification_badge.setFixedSize(19,17);self.notification_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.notification_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
            wrap=QWidget();wrap.setLayout(row);side.addWidget(wrap);self.nav_buttons[index]=btn
            side.addSpacing(1)
        nav_label2=QLabel("系统");nav_label2.setObjectName("NavLabel");side.addWidget(nav_label2)
        btn=QPushButton("设置");btn.setObjectName("SideNav");btn.setProperty("iconKind","settings")
        btn.setIcon(ui_icon("settings",MUTED));btn.setIconSize(QSize(22,22));btn.setFixedHeight(40)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda:self.switch_page(4));side.addWidget(btn);self.nav_buttons[4]=btn
        self.page_nav_buttons=dict(self.nav_buttons)
        side.addStretch(1)
        self.connector_card=ClickableFrame();self.connector_card.setObjectName("ConnCard")
        conn_lay=QVBoxLayout(self.connector_card);conn_lay.setContentsMargins(12,9,12,9);conn_lay.setSpacing(3)
        title_row=QHBoxLayout();title_row.setSpacing(7)
        self.connector_dot=QLabel();self.connector_dot.setObjectName("ConnectorDot");self.connector_dot.setFixedSize(10,10)
        self.connector_dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        title_row.addWidget(self.connector_dot)
        self.connector_title=QLabel("浏览器连接");self.connector_title.setObjectName("ConnTitle");title_row.addWidget(self.connector_title,1)
        self.connector_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        conn_lay.addLayout(title_row)
        self.connector_sub=QLabel("连接器 v"+BUNDLED_CONNECTOR_VERSION+" · 点击查看");self.connector_sub.setObjectName("SmallMuted");self.connector_sub.setWordWrap(True);conn_lay.addWidget(self.connector_sub)
        self.connector_sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        self.connector_card.clicked.connect(self.open_login_browser);side.addWidget(self.connector_card)
        side.addSpacing(10)
        theme_row=QHBoxLayout();theme_row.setContentsMargins(4,0,4,0)
        theme_label=QLabel("外观");theme_label.setObjectName("SmallMuted");theme_row.addWidget(theme_label)
        self.theme_name_label=QLabel(self.theme_name);self.theme_name_label.setObjectName("SmallMuted");theme_row.addWidget(self.theme_name_label)
        theme_row.addStretch()
        self.theme_swatches={}
        for name in THEME_PRESETS:
            sw=QPushButton();sw.setFixedSize(20,20);sw.setCursor(Qt.CursorShape.PointingHandCursor)
            sw.clicked.connect(lambda _=False,n=name:self.apply_theme(n));theme_row.addWidget(sw);self.theme_swatches[name]=sw
        side.addLayout(theme_row)
        self._refresh_theme_swatches(self.theme_name)
        foot=QLabel("V "+APP_VERSION+" · Windows 版");foot.setObjectName("SideFoot");side.addWidget(foot)
        shell.addWidget(self.sidebar)
        center=QWidget();center_layout=QVBoxLayout(center);center_layout.setContentsMargins(0,0,0,0);center_layout.setSpacing(0)
        self.topbar=DraggableHeader();self.topbar.setObjectName("TopBar");self.topbar.setFixedHeight(64)
        bar=QHBoxLayout(self.topbar);bar.setContentsMargins(24,8,12,8);bar.setSpacing(8)
        titles=QVBoxLayout();titles.setSpacing(1)
        self.page_title=QLabel("监控看板");self.page_title.setObjectName("PageTitleTop");titles.addWidget(self.page_title)
        self.page_sub=QLabel("粉丝与发帖监控 · 数据保存在本地");self.page_sub.setObjectName("Subtitle");titles.addWidget(self.page_sub)
        self.page_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        self.page_sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        bar.addLayout(titles,1)
        bar.addStretch()
        self._caption_hover=CaptionHoverFilter(self)
        minimum=icon_button("min","",self,34);minimum.setAccessibleName("最小化");minimum.clicked.connect(self.showMinimized);bar.addWidget(minimum)
        self.max_btn=icon_button("max","",self,34);self.max_btn.setAccessibleName("最大化");self.max_btn.clicked.connect(self.toggle_maximized);bar.addWidget(self.max_btn)
        close=icon_button("close","",self,34);close.setObjectName("CloseWindowButton");close.setAccessibleName("关闭");close.installEventFilter(self._caption_hover);close.clicked.connect(self.close);bar.addWidget(close)
        center_layout.addWidget(self.topbar)
        self.stack=QStackedWidget();self.stack.setObjectName("MainStack")
        self.dashboard=DashboardPage(self.store,self.settings)
        reserved_slot=QWidget()
        self.alerts=AlertsPage(self.store,self.settings)
        self.page_manager=PageManagementPage(self.store,self.settings)
        self.settings_page=SettingsPage(self.store,self.settings)
        for page in (self.dashboard,reserved_slot,self.alerts,self.page_manager,self.settings_page):self.stack.addWidget(page)
        if hasattr(self.dashboard,"rail_widget"):
            # Fixed in the sidebar: no scroll area of its own, so the recent
            # alerts / overview cards never scroll away with the main content
            # and never grow their own scrollbar.
            self.dashboard.rail_widget.setStyleSheet("background:transparent;")
            self.dashboard.rail_widget.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Fixed)
            side.insertWidget(side.indexOf(self.connector_card),self.dashboard.rail_widget)
            side.insertSpacing(side.indexOf(self.connector_card),12)
        center_layout.addWidget(self.stack,1)
        if hasattr(self.dashboard,"action_bar"):
            bar.insertWidget(2,self.dashboard.action_bar)
        self.statusbar=QFrame();self.statusbar.setObjectName("StatusBar");self.statusbar.setFixedHeight(30)
        status_lay=QHBoxLayout(self.statusbar);status_lay.setContentsMargins(24,0,24,0);status_lay.setSpacing(10)
        if hasattr(self.dashboard,"status"):status_lay.addWidget(self.dashboard.status,1)
        if hasattr(self.dashboard,"next_run"):
            self.dashboard.next_run.setParent(self.statusbar);self.dashboard.next_run.hide()
        center_layout.addWidget(self.statusbar)
        shell.addWidget(center,1)
        self._root_layout.addLayout(shell,1)
        self.wire_signals();self.switch_page(0);self._update_window_shape()

    def wire_signals(self):
        d=self.dashboard;d.collect_once.connect(self.dashboard_run_button);d.toggle_auto.connect(self.toggle_auto)
        d.view_alerts.connect(lambda:self.switch_page(2));d.open_manager.connect(self.open_manager)
        d.delete_page.connect(lambda pid:self.delete_ids([pid]))
        d.open_page.connect(self.open_page);d.open_settings_requested.connect(lambda:self.switch_page(4))
        d.collect_subset_requested.connect(self.start_subset_collection)
        d.inspect_page.connect(self.inspect_single_page);d.sync_page.connect(lambda pid:self.sync_profiles([pid]))
        m=self.page_manager;m.add_requested.connect(self.open_batch_dialog)
        m.delete_requested.connect(self.delete_ids)
        m.config_changed.connect(self.refresh_dashboard)
        m.inspect_requested.connect(self.inspect_pages)
        m.open_settings_requested.connect(lambda:self.switch_page(4))
        self.alerts.ack_requested.connect(self.ack_alerts);self.alerts.clear_history_requested.connect(self.clear_read_history);self.alerts.read_changed.connect(self.refresh_dashboard)
        settings=self.settings_page;settings.login_requested.connect(self.open_login_browser)
        settings.save_requested.connect(self.save_settings)
        settings.theme_requested.connect(self.apply_theme)
        settings.ui_scale_requested.connect(self.set_ui_scale)
        settings.toast_position_requested.connect(self.set_toast_position)
        settings.export_requested.connect(self.export_csv);settings.backup_requested.connect(self.backup_db)
        settings.data_dir_requested.connect(self.move_data_directory)

    def switch_page(self,index):
        if index not in (0,2,3,4):index=0
        self.stack.setCurrentIndex(index)
        if not self._ui_restoring:
            self.settings.setValue("ui/page",index);self.settings.sync()
        for idx,button in self.page_nav_buttons.items():
            _new_active=(idx==index)
            if button.property("active")!=_new_active:
                button.setProperty("active",_new_active);button.style().unpolish(button);button.style().polish(button)
        if hasattr(self,"dashboard") and hasattr(self.dashboard,"action_bar"):
            self.dashboard.action_bar.setVisible(index==0)
        titles={0:("监控看板","粉丝与发帖监控 · 数据保存在本地"),2:("通知","未读通知与历史记录"),3:("ID管理","一次添加，多模块共用"),4:("设置","浏览器连接、巡检、提醒与数据")}
        title,sub=titles[index]
        if index==0 and not modules_posts_enabled(self.settings):sub="仅粉丝监控 · 数据保存在本地"
        if hasattr(self,"page_title"):self.page_title.setText(title)
        if hasattr(self,"page_sub"):self.page_sub.setText(sub)
        if index==0:self.refresh_dashboard()
        elif index==2:self.alerts.open_current()
        elif index==3:self.page_manager.refresh()
        elif index==4:self.settings_page.refresh_data_path()

    def open_manager(self,pid=""):
        self.switch_page(3)
        if pid:self.page_manager.focus_id(pid);self.page_manager.edit_id(pid)

    def _position_notification_badge(self):
        if not hasattr(self,"notification_badge"):return
        btn=self.nav_buttons.get(2)
        if btn is None:return
        self.notification_badge.move(max(0,btn.width()-27),(btn.height()-17)//2)

    def _update_header_icons(self,unread=None):
        if not hasattr(self,"page_nav_buttons"):return
        # Icon state changes rarely (unread count, connector presence, update
        # availability), but this runs on every refresh and every 1s connector
        # tick; redrawing every icon pixmap each time is pure repaint churn.
        # Skip the whole pass when the visible state is unchanged.
        try:_online=bool(self.selected_connectors())
        except Exception:_online=False
        _buttons=[b for b in self.findChildren(QPushButton) if b.property("iconKind")]
        _sig=((unread or 0)>0,_online,bool(getattr(self,"_update_available",False)),len(_buttons))
        if getattr(self,"_header_icon_signature",None)==_sig:return
        self._header_icon_signature=_sig
        colors={"pages":CYAN,"browser":GREEN,"theme":ACCENT,"settings":CYAN,"update":MUTED}
        for button in _buttons:
            kind=button.property("iconKind")
            if button.objectName()=="HomePill":color="#FFFFFF"
            elif kind=="bell":color=RED if (unread or 0)>0 else CYAN
            elif kind=="browser":color=GREEN if (hasattr(self,"connector") and self.selected_connectors()) else RED
            elif kind=="update" and getattr(self,"_update_available",False):color=AMBER
            else:color=colors.get(kind,MUTED)
            button.setIcon(ui_icon(kind,color))

    def set_update_attention(self,active,version=""):
        self._update_available=bool(active)
        self._update_header_icons(sum(self.store.unread_totals()) if hasattr(self,"store") else 0)

    def refresh_dashboard(self):
        self.dashboard.refresh();self.dashboard.set_running(self.auto_enabled,self.worker_thread is not None)
        g,p=self.store.unread_totals();n=g+p
        self.notification_badge.setText(str(n) if n<100 else "99+");self.notification_badge.setVisible(n>0)
        self.page_nav_buttons[2].setToolTip(f"通知 · {n} 条未读")
        self._update_header_icons(n)

    def refresh_all(self):
        self.refresh_dashboard()
        index=self.stack.currentIndex()
        if index==2:self.alerts.refresh()
        elif index==3:self.page_manager.refresh()

    def open_alert_notification(self,entry):
        # The Windows toast callback runs on a WinRT background thread, never
        # the Qt GUI thread. Touching widgets from there deadlocks the app,
        # so re-dispatch onto the GUI thread and return immediately.
        try:
            _app = QApplication.instance()
        except Exception:
            _app = None
        if _app is not None and QThread.currentThread() is not _app.thread():
            # Queued signal delivery: a bare QTimer.singleShot created on
            # the worker thread would never fire (no event loop there), and
            # PyQt6 singleShot has no (msec, receiver, callable) overload.
            self.open_alert_requested.emit(entry)
            return
        log_window_event("open_alert_notification","visible=%s minimized=%s"%(
            self.isVisible(),self.isMinimized()))
        if not self.isVisible() or self.isMinimized():
            if self.isMaximized():self.showMaximized()
            else:self.showNormal()
        self.raise_();self.activateWindow();self.switch_page(2)
        self.alerts.focus_alert(entry or {})

    def schedule_refresh(self):
        if not self.paint_timer.isActive():self.paint_timer.start(450)

    def open_batch_dialog(self):
        if self._tasks_busy():return
        dlg=BatchAddDialog(self,growth_enabled=modules_growth_enabled(self.settings),posts_enabled=modules_posts_enabled(self.settings))
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        parsed=normalize_page_ids(dlg.text())
        if dlg.mode()=="replace":
            old={p["page_id"] for p in self.store.list_pages()}
            removed=len(old-set(parsed.ids))
            answer=QMessageBox.question(self,"确认覆盖当前 ID 列表",
                f"当前 {len(old)} 个 ID，将移除不在新列表中的 {removed} 个 ID。\n只保留当前监控设置；新列表中已存在 ID 的配置也会保留。\n\n确认覆盖？",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
        try:
            result=self.store.import_ids(parsed.ids,dlg.mode(),dlg.growth.isChecked(),dlg.posts.isChecked(),dlg.hours.value())
        except Exception as exc:QMessageBox.warning(self,"导入失败",str(exc));return
        self.switch_page(3);self.refresh_all()
        msg=f"新增 {result['added']} 个 · 已存在跳过 {result['skipped']} 个 · 移除 {result['removed']} 个"
        self.dashboard.status.setText(msg);show_hint(self,msg+"\n\n名称和头像会在正常巡检时自动更新。")

    def delete_ids(self,ids):
        if self._tasks_busy():return
        ids=list(dict.fromkeys(ids))
        answer=QMessageBox.question(self,"确认批量删除",
            f"从当前列表移除 {len(ids)} 个专业 ID？\n\n对应的当前状态与今日基准会移除；已有通知保留。重新添加同一 ID 将重新建立基准。",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        self.store.delete_ids(ids,False);self.refresh_all()
        self.show_toast(f"已移除 {len(ids)} 个专业 ID",kind="success")

    def _tasks_busy(self):
        if self.worker_thread is not None or self.login_thread is not None or self._maintenance:
            show_hint(self,"请等待当前巡检或连接任务结束后再操作。暂停不会结束当前任务。",kind="warning")
            return True
        return False

    def dashboard_run_button(self):
        if self.worker is not None:self.toggle_pause_collection()
        else:self.start_collection(True)

    def toggle_pause_collection(self):
        if self.worker is None:return
        self.dashboard.paused=self.worker.toggle_pause()
        self.dashboard.set_running(self.auto_enabled,True)
        self.dashboard.status.setText("已请求暂停：当前主页处理完成后停止进入下一页" if self.dashboard.paused else "继续本轮巡检")

    def start_collection(self,once=True):
        if self._closing or self._maintenance:return
        if self.login_thread is not None:
            if once:show_hint(self,"请先关闭登录浏览器，再巡检。",kind="warning")
            elif self.auto_enabled:self.auto_timer.start(30000)
            return
        if self.worker_thread is not None:return
        pages=self.store.list_pages(enabled_only=True)
        if not pages:
            self.stop_auto()
            if once:show_hint(self,"请在 ID管理中添加 ID，并至少勾选一个监控模块。",kind="warning")
            return
        self._start_worker(pages,"monitor")

    def inspect_single_page(self,pid):
        if self._tasks_busy():return
        pages=[p for p in self.store.list_pages() if str(p["page_id"])==str(pid)]
        if not pages:show_hint(self,"找不到该主页。",kind="warning");return
        self._start_worker(pages,"monitor")

    def inspect_pages(self,ids):
        if self._tasks_busy():return
        chosen={str(x) for x in ids}
        pages=[p for p in self.store.list_pages() if str(p["page_id"]) in chosen]
        if not pages:show_hint(self,"请先选择要巡检的主页。",kind="warning");return
        self._start_worker(pages,"monitor")

    def start_subset_collection(self,mode):
        if self._tasks_busy():return
        pages=self.store.list_pages(enabled_only=True)
        if mode=="failed":
            pages=[p for p in pages if p.get("status") in ("采集失败","部分成功") or p.get("growth_error")
                   or (modules_posts_enabled(self.settings) and p.get("post_error")) or (p.get("name_error") and not normalize_name(p.get("page_name"),p.get("page_id")))]
        elif mode=="uninspected":
            pages=[p for p in pages if not p.get("last_inspected_at")]
        if not pages:
            show_hint(self,"没有符合条件的主页。",kind="warning");return
        self._start_worker(pages,"monitor")

    def sync_profiles(self,ids):
        if self._tasks_busy():return
        chosen=set(ids);pages=[p for p in self.store.list_pages() if p["page_id"] in chosen]
        if pages:self._start_worker(pages,"metadata")

    def _start_worker(self,pages,purpose):
        try:self.settings_page.flush_pending()
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"\u8bbe\u7f6e\u672a\u80fd\u4fdd\u5b58",str(exc));return
        if purpose=="monitor":
            pages=apply_module_gating(pages,self.settings)
            pages=[p for p in pages if p.get("monitor_growth") or p.get("monitor_posts")]
            if not pages:
                self.dashboard.status.setText("没有可巡检的主页：监控模块均未启用，请在设置 → 监控模块中至少开启一个")
                return
        cids=self.selected_connectors(require_all=False)
        if not cids:
            self.dashboard.status.setText("浏览器连接未就绪，请打开已安装连接器的 Chrome")
            if self.auto_enabled:self.stop_auto()
            else:self.show_toast("未检测到在线浏览器连接器，请先打开已安装连接器的 Chrome",kind="warning")
            return
        if len(pages)<len(cids):
            # Small rounds (single-page recheck) simply use fewer
            # connectors instead of refusing the whole round.
            cids=cids[:len(pages)]
        self.auto_timer.stop();self.next_run_at=None;self.current_purpose=purpose
        self.active_run_id=uuid.uuid4().hex;self.store.start_run(self.active_run_id,len(pages))
        self.run_started_at=time.time();self.run_ok=0;self.run_fail=0
        self.worker_thread=QThread(self);timing=random_inspection_timing(self.settings)
        self.worker=ConnectorCollectWorker(pages,self.connector,cids,purpose=purpose,gap_range=timing[3:])
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.result.connect(self.on_collect_result);self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_collection_finished)
        self.worker.finished.connect(self.worker.deleteLater);self.worker.finished.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.cleanup_worker)
        self.dashboard.paused=False;self.dashboard.set_running(self.auto_enabled,True);self.page_manager.set_busy(True)
        self.dashboard.status.setText(f"通过 {len(cids)} 个 Chrome 连接器并行开始任务 · {len(pages)} 个 ID")
        self.worker_thread.start()

    def on_progress(self,current,total,info):
        self.dashboard.status.setText(f"{info}  ·  {current}/{total}")

    def on_collect_result(self,data):
        options={key:self.settings.value(key,default) for key,default in
                 (("interval_minutes",DEFAULT_INTERVAL_MINUTES),("alert_threshold",500),("alert_enabled",1))}
        try:out=self.store.apply_collection(data,options,self.current_purpose)
        except Exception as exc:
            import traceback;log_exception(traceback.format_exc())
            self.run_fail+=1;self.dashboard.status.setText("记录保存失败："+str(exc)[:180]);return
        if out.get("ignored"):return
        if out["success"]:self.run_ok+=1
        else:self.run_fail+=1
        if out.get("error"):self.dashboard.status.setText(str(data.get("page_id"))+" · "+out["error"][:180])
        if out["alerts"]:
            self._notice_queue.extend(out["alerts"])
            if not self.notice_timer.isActive():self.notice_timer.start(500)
        self.schedule_refresh()

    def flush_notices(self):
        queued=self._notice_queue;self._notice_queue=[]
        if not queued:return
        fresh=self.store.combined_alerts(limit=300,unread_only=True);entries=[]
        for raw in queued:
            match=next((row for row in fresh if row.get("kind")==raw.get("kind") and row.get("page_id")==raw.get("page_id")
                        and (not raw.get("id") or int(row.get("id") or 0)==int(raw.get("id") or 0))),None)
            item=dict(match or raw)
            pid=str(item.get("page_id") or "")
            page=self.store.page(pid) or {}
            # Popup must use the same avatar cache as the dashboard. A queued/stale path
            # must never override the current valid page avatar.
            current_avatar=str(page.get("avatar_path") or "") if isinstance(page,dict) else ""
            cached=AVATAR_DIR/(pid+".png") if pid else None
            if current_avatar and Path(current_avatar).is_file():
                item["avatar_path"]=current_avatar
            elif cached is not None and cached.is_file():
                item["avatar_path"]=str(cached)
            elif not (item.get("avatar_path") and Path(str(item.get("avatar_path"))).is_file()):
                item["avatar_path"]=""
            if page:
                item["page_name"]=display_name(page)
                item.setdefault("name",item["page_name"])
            entries.append(item)
        # Native Windows toast only. No custom popup fallback (user
        # decision): the alert itself stays in the notification list and
        # the sidebar badge, so a failed toast never loses a warning.
        _ok,_detail=send_system_toast(entries,lambda:self.open_alert_notification(entries[0] if entries else {}),
                                      silent=False)
        self._last_toast_result=(_ok,_detail)
        if not _ok:
            log_exception("系统通知未发出："+str(_detail))

    def on_collection_finished(self,ok,message):
        if self.active_run_id:
            state="completed" if ok and self.run_fail==0 else "partial" if self.run_ok else "failed"
            self.store.finish_run(self.active_run_id,self.run_ok,self.run_fail,state)
        if self.current_purpose=="monitor" and self.run_ok+self.run_fail>0:
            stamp=now_iso();self.settings.setValue("last_inspection_at",stamp);self.settings.sync()
            self.dashboard._last_inspection_stamp=stamp
            self.dashboard.run_badge.setText("上次巡检时间："+inspection_stamp_label(stamp))
        if "连接器中断" in message and self.auto_enabled:
            self.stop_auto();self.dashboard.status.setText(message+" · 自动巡检已暂停，请恢复浏览器连接后重新开启")
        else:self.dashboard.status.setText(message)
        self.schedule_refresh()

    def cleanup_worker(self):
        thread=self.worker_thread
        self.worker=None;self.worker_thread=None;self.active_run_id=None
        if thread:thread.deleteLater()
        self.dashboard.paused=False;self.page_manager.set_busy(False)
        self.dashboard.set_running(self.auto_enabled,False)
        if self._closing:self.check_pending_exit();return
        if self.auto_enabled:self.schedule_next_round(self.run_started_at)
        self.refresh_all()

    def toggle_auto(self):
        if self.auto_enabled:self.stop_auto()
        else:self.start_auto()

    def start_auto(self):
        if self.auto_enabled:return
        cids=self.selected_connectors(require_all=False)
        if not cids:
            self.show_toast("未检测到在线浏览器连接器，请先打开已安装连接器的 Chrome",kind="warning")
            return
        try:self.settings_page.flush_pending()
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"设置未能保存",str(exc));return
        pages=self.store.list_pages(enabled_only=True)
        if not pages:
            self.show_toast("请先在 ID管理中选择粉丝监控或发帖监控。",kind="warning")
            return
        # Small rounds are trimmed to the available tasks in _start_worker.
        self.auto_enabled=True
        # Deliberately do NOT write start_auto or change the startup checkbox.
        if not self.worker_thread:self.start_collection(False)
        self.dashboard.set_running(True,self.worker_thread is not None)

    def stop_auto(self):
        # This only stops scheduling in this process; explicit startup preference is independent.
        self.auto_enabled=False;self.next_run_at=None;self.auto_timer.stop()
        self.dashboard.set_running(False,self.worker_thread is not None)
        self.dashboard.status.setText("已暂停自动巡检；当前任务可用巡检按钮暂停")

    def update_countdown(self):
        self._tick+=1
        if self.auto_enabled and self.next_run_at:
            secs=max(0,int(self.next_run_at-time.time()));mm,ss=divmod(secs,60)
            self.dashboard.next_run.setText(f"下次巡检 {mm:02d}:{ss:02d}")
        elif self.worker_thread:self.dashboard.next_run.setText("当前轮次进行中")
        elif self.auto_enabled:self.dashboard.next_run.setText("自动巡检等待中")
        else:self.dashboard.next_run.setText("自动巡检未开启")
        if self._tick%60==0 and not self._maintenance:self.refresh_dashboard()

    def open_login_browser(self):
        if self._connector_dialog is None:
            self._connector_dialog=BrowserConnectionsDialog(self)
        self._connector_dialog.refresh();self._connector_dialog.show()
        self._connector_dialog.raise_();self._connector_dialog.activateWindow()

    def connector_selection_initialized(self):
        return is_true(self.settings.value('connector/selection_initialized',0),False)

    def configured_connector_ids(self,include_offline=False):
        # Zero-configuration, no cap: every connected browser is used
        # automatically. Saved selections from the old checkbox UI are kept
        # on disk but no longer consulted.
        rows = self.connector.clients()
        if include_offline:
            return [r['instance_id'] for r in rows if not r.get('blocked')]
        return [r['instance_id'] for r in rows if r['online'] and not r.get('blocked')]

    def set_connector_selection(self,ids,initialized=True):
        ids=list(dict.fromkeys(str(x) for x in ids if x))
        self.settings.setValue('connector/selected_ids',json.dumps(ids,ensure_ascii=False));self.settings.setValue('connector/selection_initialized',1 if initialized else 0)
        self.settings.remove('connector/selected_id');self.settings.remove('connector/selection_mode');self.settings.sync();self.refresh_connector_summary()

    def selected_connectors(self,require_all=False):
        configured=self.configured_connector_ids(include_offline=True);active=self.configured_connector_ids(include_offline=False)
        if require_all and configured and len(active)!=len(configured):return []
        return active

    def selected_connector(self):
        active=self.selected_connectors();return active[0] if active else ''

    def _prompt_pending_approvals(self):
        if getattr(self,"_approval_dialog_open",False):return
        try:
            while True:
                cid=self.connector.pending_queue.get_nowait()
                if cid in self._pending_dialogs:continue
                if time.monotonic()-self._pending_dismissed.get(cid,0)<120:continue
                info=next((p for p in self.connector.pending_approvals() if p['instance_id']==cid),None)
                if not info:continue
                self._pending_dialogs.add(cid)
                self._approval_dialog_open=True
                try:
                    ident=info.get('identity') or {}
                    label=connector_display_name(ident,cid)
                    detail="\n".join(x for x in (
                        "浏览器备注："+label,
                        "浏览器："+str(ident.get('browser_brand') or '')+" "+str(ident.get('browser_version') or ''),
                        "频道："+str(ident.get('channel_label') or ''),
                        "资料目录："+str(ident.get('profile_directory') or ''),
                        "扩展版本："+str(ident.get('extension_version') or ''),
                    ) if x.split('：',1)[-1].strip())
                    box=QMessageBox(self)
                    box.setWindowTitle("新浏览器连接确认")
                    box.setText("检测到一个从未连接过的新浏览器，是否允许它连接本软件？")
                    box.setInformativeText(detail+"\n\n只确认一次。已连接过的浏览器不会再次询问。停用后该浏览器不会再自动注册。")
                    allow_btn=box.addButton("允许连接",QMessageBox.ButtonRole.AcceptRole)
                    block_btn=box.addButton("停用此浏览器",QMessageBox.ButtonRole.DestructiveRole)
                    box.addButton("稍后决定",QMessageBox.ButtonRole.RejectRole)
                    box.setDefaultButton(allow_btn)
                    box.exec()
                    clicked=box.clickedButton()
                    if clicked is allow_btn:
                        self.connector.approve_pending(cid)
                        self.show_toast("已允许新浏览器连接："+label,kind="success")
                    elif clicked is block_btn:
                        self.connector.block_pending(cid)
                        self.show_toast("已停用该浏览器连接",kind="success")
                    else:
                        self._pending_dismissed[cid]=time.monotonic()
                finally:
                    self._approval_dialog_open=False
                    self._pending_dialogs.discard(cid)
        except queue.Empty:
            pass

    def refresh_connector_summary(self):
        if self._closing:return
        self._prompt_pending_approvals()
        if not self.connector._running and not os.environ.get('FBPM_TEST_MODE'):
            now=time.monotonic()
            if now-getattr(self,'_connector_last_retry',0)>10:
                self._connector_last_retry=now
                try:self.connector.start()
                except Exception as exc:self.connector.error=str(exc)
        rows=self.connector.clients();online=[r for r in rows if r['online'] and not r.get('blocked')]
        active=self.configured_connector_ids(include_offline=False)
        outdated=[r for r in online if connector_needs_update(r.get('identity') or {})]
        offline=[r for r in rows if not r['online'] and not r.get('blocked')]
        # Usability, not tidiness, decides the state: any online browser can
        # run inspections right away. Outdated versions and offline browsers
        # are details in the long text, never a 'pending' state while the
        # software is usable.
        if self.connector.error:text='浏览器连接服务异常：'+self.connector.error;state='error'
        elif not online:text='未检测到在线浏览器连接器';state='error'
        else:
            state='ok'
            if len(online)==1:
                name=connector_display_name(online[0]['identity'],online[0]['instance_id']);text='已自动连接：'+name
            else:text=f'已连接 {len(active)} 个浏览器，任务将并行分配'
            extras=[]
            if outdated:extras.append(f'{len(outdated)} 个连接器版本较旧，可在设置中获取 v{BUNDLED_CONNECTOR_VERSION}')
            if offline:extras.append(f'{len(offline)} 个浏览器离线')
            if extras:text+=' · '+' · '.join(extras)
        try:self.settings_page.connector_summary.setText(text)
        except Exception:pass
        if hasattr(self,"connector_card"):self.connector_card.setToolTip(html.escape(text)+'\n点击查看浏览器连接')
        if hasattr(self,"connector_title"):
            if state=='ok' and len(online)==1:
                _nm=connector_display_name(online[0]['identity'],online[0]['instance_id']);_short='已连接：'+_nm
            elif state=='ok':_short=f'已连接 {len(active)} 个浏览器'
            else:_short='未检测到浏览器'
            self.connector_title.setText(_short)
        if hasattr(self,'connector_dot'):
            color={'ok':'#26C281','warn':'#F0A43A','error':'#E75768'}[state];self.connector_dot.setStyleSheet(f'background:{color};border:2px solid {BG};border-radius:6px;');self.connector_dot.setToolTip(html.escape(text))
        if self.auto_enabled and not active:
            if self.worker is not None:self.worker.stop()
            self.stop_auto();self.dashboard.status.setText('所有可用浏览器连接均已中断，自动巡检已暂停')

    def activate_existing_window(self):
        # Restore this window and the user's current page; do not start a task.
        # Never toggle window state when already visible: redundant
        # showNormal/showMaximized calls re-present the layered window
        # (DWM ghost frame). Only restore state when hidden/minimized, and
        # only raise when the window is actually in the background.
        log_window_event("activate","visible=%s active=%s minimized=%s maximized=%s"%(
            self.isVisible(),self.isActiveWindow(),self.isMinimized(),self.isMaximized()))
        if self.isVisible() and not self.isMinimized():
            if not self.isActiveWindow():
                self.raise_();self.activateWindow()
                if os.name=="nt":
                    try:
                        import ctypes
                        ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
                    except Exception:pass
            return
        if self.isMaximized():self.showMaximized()
        else:self.showNormal()
        self.raise_();self.activateWindow()
        if os.name=="nt":
            try:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
            except Exception:pass

    def on_login_finished(self,message):
        self.dashboard.status.setText(message)
        if message.startswith("登录浏览器失败"):QMessageBox.warning(self,"登录失败",message)

    def cleanup_login(self):
        if self.login_thread:self.login_thread.deleteLater()
        self.login_worker=None;self.login_thread=None;self.page_manager.set_busy(False)
        if self._closing:self.check_pending_exit()
        elif self.auto_enabled:self.next_run_at=time.time()+2;self.auto_timer.start(2000)

    def save_settings(self, show_hint=False):
        previous=self._settings_timing
        try:self.settings_page.save_settings()
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,"保存失败",str(exc));return
        self._apply_timing(previous)
        self.dashboard.status.setText("设置已保存")
        self.settings_page.save_note.setText("已自动保存 · 下次启动保留")
        self.refresh_all()
        if show_hint:self.show_toast("设置已保存",kind="success")

    def schedule_next_round(self, started_at=None):
        timing=random_inspection_timing(self.settings)
        minutes,deadline,delay_ms=plan_next_round(timing,started_at)
        self._next_round_minutes=minutes;self.next_run_at=deadline
        self.auto_timer.start(delay_ms)
        self.dashboard.next_run.setToolTip("\u672c\u6b21\u968f\u673a\u8f6e\u6b21\u95f4\u9694\uff1a%s \u5206\u949f" % minutes)

    def _apply_timing(self, previous):
        values=random_inspection_timing(self.settings)
        self._settings_timing=values
        self.dashboard.set_timing_values(*values)
        if self.worker is not None:self.worker.set_gap_range(*values[3:])
        if self.auto_enabled and self.worker_thread is None and values[:3]!=previous[:3]:
            self.schedule_next_round()
        self.update_countdown()

    def ack_alerts(self):
        self.store.acknowledge_notifications();self.alerts.refresh();self.refresh_dashboard()
        self.show_toast("通知已标记为已读",kind="success")

    def clear_read_history(self):
        answer=QMessageBox.question(self,"清空已读记录","确定要清空全部已读通知吗？此操作不可恢复。",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        self.store.clear_acknowledged_alerts();self.alerts.refresh();self.refresh_dashboard()
        self.show_toast("已清空已读历史记录",kind="success")

    def show_toast(self, text, duration_ms=3600, kind="info"):
        self.dashboard.status.setText(str(text))
        if not self.isVisible() or self.isMinimized():
            return
        if self._toast is None:
            self._toast=ToastNotice(self)
        self._toast.show_message(str(text),duration_ms,kind,position=str(self.settings.value("toast_position","bottom_center")))



    def _create_resize_handles(self):
        specs={
            "left":(Qt.Edge.LeftEdge,Qt.CursorShape.SizeHorCursor),
            "right":(Qt.Edge.RightEdge,Qt.CursorShape.SizeHorCursor),
            "top":(Qt.Edge.TopEdge,Qt.CursorShape.SizeVerCursor),
            "bottom":(Qt.Edge.BottomEdge,Qt.CursorShape.SizeVerCursor),
            "tl":(Qt.Edge.TopEdge|Qt.Edge.LeftEdge,Qt.CursorShape.SizeFDiagCursor),
            "tr":(Qt.Edge.TopEdge|Qt.Edge.RightEdge,Qt.CursorShape.SizeBDiagCursor),
            "bl":(Qt.Edge.BottomEdge|Qt.Edge.LeftEdge,Qt.CursorShape.SizeBDiagCursor),
            "br":(Qt.Edge.BottomEdge|Qt.Edge.RightEdge,Qt.CursorShape.SizeFDiagCursor),
        }
        self._resize_handles={}
        for key,(edges,cursor) in specs.items():
            handle=WindowResizeHandle(edges,cursor,self);self._resize_handles[key]=handle;handle.raise_()
        self._layout_resize_handles()

    def _layout_resize_handles(self):
        if not hasattr(self,"_resize_handles"):return
        w,h=self.width(),self.height();edge=7;corner=15
        geo={
            "left":QRect(0,corner,edge,max(0,h-2*corner)),
            "right":QRect(max(0,w-edge),corner,edge,max(0,h-2*corner)),
            "top":QRect(corner,0,max(0,w-2*corner),edge),
            "bottom":QRect(corner,max(0,h-edge),max(0,w-2*corner),edge),
            "tl":QRect(0,0,corner,corner),
            "tr":QRect(max(0,w-corner),0,corner,corner),
            "bl":QRect(0,max(0,h-corner),corner,corner),
            "br":QRect(max(0,w-corner),max(0,h-corner),corner,corner),
        }
        visible=not self.isMaximized()
        for key,handle in self._resize_handles.items():
            handle.setGeometry(geo[key]);handle.setVisible(visible);handle.raise_()
        if hasattr(self,"size_grip"):self.size_grip.raise_()

    def show_dashboard(self):
        log_window_event("show_dashboard","visible=%s minimized=%s"%(
            self.isVisible(),self.isMinimized()))
        if not self.isVisible() or self.isMinimized():
            if self.isMaximized():self.showMaximized()
            else:self.showNormal()
        self.raise_();self.activateWindow();self.switch_page(0)

    def reset_ui_layout(self):
        for key in ("ui/geometry","ui/maximized","ui/page","dashboard/scroll","manager/header","alerts/header"):
            self.settings.remove(key)
        self.settings.sync();self.showNormal();self.resize(1360,880)
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        if screen:
            area=screen.availableGeometry();self.move(area.center()-self.rect().center())
        self.switch_page(0);self.show_toast("窗口布局已恢复默认",kind="success")

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,"_ui_save_timer") and not self._ui_restoring:self._ui_save_timer.start(250)
        if getattr(self,"_toast",None) is not None:
            self._toast.reposition()
        if hasattr(self,"size_grip"):
            self.size_grip.move(self.width()-18,self.height()-18);self.size_grip.setVisible(not self.isMaximized())
        self._layout_resize_handles()
        self._position_notification_badge()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius=0 if self.isMaximized() else 20
        rect=QRectF(0.5,0.5,self.width()-1,self.height()-1)
        p.setBrush(QColor(BG))
        # Outer edge: a faint 20%-opacity line (black on light themes, white
        # on the dark theme) so the window edge stays visible against other
        # windows, instead of the near-invisible theme border colour.
        _preset=THEME_PRESETS.get(migrate_theme_name(getattr(self,"theme_name","云白")),THEME_PRESETS["云白"])
        _edge=QColor(255,255,255,51) if not _preset.get("light",True) else QColor(0,0,0,51)
        p.setPen(QPen(_edge,1))
        if radius:p.drawRoundedRect(rect,radius,radius)
        else:p.drawRect(rect)
        p.end()
        super().paintEvent(event)

    def _update_window_shape(self):
        flat=self.isMaximized()
        if getattr(self,"_shape_flat",None)==flat:return
        self._shape_flat=flat
        layout=getattr(self,"_root_layout",None)
        if layout is not None:
            layout.setContentsMargins(0,0,0,0) if flat else layout.setContentsMargins(1,1,1,1)
        for widget in (getattr(self,"sidebar",None),getattr(self,"topbar",None),getattr(self,"statusbar",None)):
            if widget is not None:
                widget.setProperty("flat",flat);widget.style().unpolish(widget);widget.style().polish(widget)
        self.update()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.WindowStateChange and hasattr(self,"max_btn"):
            QTimer.singleShot(0,self._layout_resize_handles)
            self._update_window_shape()

    def toggle_maximized(self):
        log_window_event("toggle_maximized","maximized=%s"%self.isMaximized())
        if self.isMaximized():self.showNormal()
        else:self.showMaximized()


    def check_for_updates(self,manual=True):
        if self._closing or self._maintenance:return
        if not manual and not is_true(self.settings.value("auto_check_updates",1)):return
        if self._update_thread is not None:
            if manual:
                if self._update_dialog:self._update_dialog.show();self._update_dialog.raise_()
                else:self.dashboard.status.setText("版本检查正在进行，请稍候")
            return
        self._update_manual=bool(manual)
        self.dashboard.status.setText("正在检查 GitHub 正式发布版本…")
        self._start_update_task("check")


    def move_data_directory(self):
        if self._tasks_busy():return
        if self._update_thread is not None:
            show_hint(self,"请等待版本检查或下载结束后再迁移目录。",kind="warning");return
        old=DATA_DIR.resolve()
        parent=QFileDialog.getExistingDirectory(self,"选择新数据文件夹的上级目录",str(old.parent))
        if not parent:return
        name,ok=QInputDialog.getText(self,"新文件夹名称","在所选位置创建的文件夹：",QLineEdit.EchoMode.Normal,"专业监控工具数据")
        if not ok:return
        name=name.strip()
        if not name or name in (".","..") or any(ch in name for ch in '/\\:*?"<>|'):
            QMessageBox.warning(self,"名称无效","请填写普通文件夹名称。");return
        target=Path(parent)/name
        if QMessageBox.question(self,"确认迁移",
            f"数据、设置、头像及浏览器资料将迁移到：\n{target}\n\n验证并切换成功后删除旧应用数据目录；如有无关文件，则保留原目录。",
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self.settings_page.flush_pending();self.save_ui_state();self.settings.sync()
        self._maintenance=True;self.auto_timer.stop();self.paint_timer.stop();self._ui_save_timer.stop()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        moved=None
        try:
            result=prepare_data_migration(self.store,target)
            new_settings=QSettings(str(result["target"]/"settings.ini"),QSettings.Format.IniFormat);new_settings.setFallbacksEnabled(False)
            new_settings.setValue("data_directory",str(result["target"]));new_settings.sync()
            if new_settings.status()!=QSettings.Status.NoError:raise RuntimeError("新目录配置不可写")
            # No commit to the new path until both copied DB and INI are usable.
            write_settings_location(result["target"])
            self._set_paths(result["target"]);self.store.path=result["database"];self.connector.relocate(DATA_DIR/"connector_registry.json")
            self.settings=new_settings
            for obj in (self.dashboard,self.dashboard.cards,self.page_manager,self.settings_page):obj.settings=new_settings
            self.settings_page.refresh_data_path();moved=result
        except Exception as exc:
            log_exception(str(exc));QMessageBox.critical(self,"迁移未完成",str(exc)+"\n原数据没有删除。")
        finally:
            QApplication.restoreOverrideCursor();self._maintenance=False
        if moved:
            if moved["can_delete"]:
                try:shutil.rmtree(moved["old"]);note="原应用数据目录已删除。"
                except OSError as exc:note="新目录已启用；原目录删除失败："+str(exc)
            else:note="旧目录存在非应用文件，未删除："+", ".join(moved["unrelated"][:6])
            self.refresh_all();QMessageBox.information(self,"迁移完成",str(moved["target"])+"\n\n"+note)
        if self.auto_enabled:self.next_run_at=time.time()+30;self.auto_timer.start(30000)


    def open_page(self,pid):
        QDesktopServices.openUrl(QUrl(f"https://www.facebook.com/{pid}"))


    def export_csv(self,kind=None):
        if kind not in ("current","alerts"):
            choice,ok=QInputDialog.getItem(self,"导出数据","内容：",["主页当前状态","通知"],0,False)
            if not ok:return
            kind="current" if choice=="主页当前状态" else "alerts"
        filename="pages.csv" if kind=="current" else "notifications.csv"
        path,_=QFileDialog.getSaveFileName(self,"导出",str(Path.home()/filename),"CSV (*.csv)")
        if not path:return
        try:self.store.export_csv(path,kind);show_hint(self,"已导出："+path,kind="success")
        except Exception as exc:QMessageBox.warning(self,"导出失败",str(exc))

    def backup_db(self):
        stamp=datetime.now().strftime("%Y%m%d_%H%M")
        path,_=QFileDialog.getSaveFileName(self,"备份数据库",str(Path.home()/f"ProfessionalMonitor_backup_{stamp}.db"),"本地数据库数据库 (*.db)")
        if not path:return
        try:
            self.store.backup(Path(path))
            show_hint(self,f"本地主页、当前状态与预警已备份（不含浏览器登录资料）：\n{path}",kind="success")
        except Exception as exc:
            QMessageBox.warning(self,"备份失败",str(exc))


    def on_tray_activated(self,reason):
        if reason==QSystemTrayIcon.ActivationReason.DoubleClick:self.show_dashboard()

    def on_tray_hint(self):
        if is_true(self.settings.value("silent_to_tray",1),True):return
        self.tray.showMessage(APP_TITLE,"窗口已收起到托盘，继续后台运行。双击托盘图标可打开；完全退出请使用托盘菜单。",QSystemTrayIcon.MessageIcon.Information,4000)

    def exit_application(self):
        self._closing=True;self.auto_enabled=False;self.auto_timer.stop();self.next_run_at=None
        self.close()

    def check_pending_exit(self):
        if self._closing and self.worker_thread is None and self.login_thread is None and self._update_thread is None:
            QTimer.singleShot(0,self.close)

    def closeEvent(self,event):
        log_window_event("close_event","closing=%s visible=%s"%(self._closing,self.isVisible()))
        try:
            self.settings_page.flush_pending();self.save_ui_state()
        except Exception as exc:
            log_exception("保存设置失败："+str(exc))
            QMessageBox.warning(self,"设置未能保存",str(exc)+"\n请检查数据目录写入权限。")
            event.ignore();self._closing=False;return
        if self._toast is not None:self._toast.hide()
        if not self._closing:
            event.ignore()
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray.show();self.hide();self.on_tray_hint()
            else:
                # Never hide the only recoverable window when the OS has no tray.
                self.showMinimized()
            return
        self._closing=True
        self.auto_enabled=False;self.auto_timer.stop();self.count_timer.stop();self._updates_timer.stop()
        if self.worker_thread is not None or self.login_thread is not None or self._update_thread is not None:
            if self.worker:self.worker.stop()
            if self.login_worker:self.login_worker.stop()
            if self._update_worker:self._update_worker.cancel()
            self.dashboard.status.setText("正在安全结束当前任务…")
            event.ignore();return
        if self._install_command:
            try:
                kwargs={"close_fds":True}
                if os.name=="nt":kwargs["creationflags"]=getattr(subprocess,"CREATE_NO_WINDOW",0)
                subprocess.Popen(self._install_command,**kwargs)
                self._install_command=None
            except OSError as exc:
                self._closing=False;self.count_timer.start();self._updates_timer.start()
                QMessageBox.warning(self,"无法启动安装器",str(exc));event.ignore();return
        self._connector_timer.stop();self.connector.stop()
        self.settings.sync();self.tray.hide();event.accept()
        QTimer.singleShot(0,QApplication.instance().quit)

    def _refresh_theme_swatches(self,name):
        if not hasattr(self,"theme_swatches"):return
        _sw_colors={"云白":"#F7F7F5","护眼绿":"#0B7A43","曜石黑":"#17181C"}
        for _n,_sw in self.theme_swatches.items():
            _sel=_n==name
            _sw.setStyleSheet(f"background:{_sw_colors.get(_n,'#FFFFFF')};border:{'2px' if _sel else '1px'} solid {ACCENT if _sel else '#C9C9C4'};border-radius:10px;")
        if hasattr(self,"theme_name_label"):self.theme_name_label.setText(name)

    def set_ui_scale(self,scale):
        scale=_bounded_int(scale,100,80,130)
        self.settings.setValue("ui_scale",scale);self.settings.sync()
        self._apply_ui_font();self.apply_style();self.update()
        try:self.settings_page.set_ui_scale_label(scale)
        except Exception:pass

    def _apply_ui_font(self):
        app=QApplication.instance()
        if app is None:return
        font=QFont(app.font());font.setPixelSize(max(8,round(13*ui_scale_percent(self.settings)/100)));app.setFont(font)

    def set_toast_position(self,position):
        position=str(position or "bottom_center")
        if position not in [k for _,k in TOAST_POSITIONS]:position="bottom_center"
        self.settings.setValue("toast_position",position);self.settings.sync()
        self.toast_position=position

    def apply_theme(self,theme_name=None,refresh=True):
        global BG,SIDEBAR,PANEL,PANEL_2,BORDER,TEXT,MUTED,ACCENT,ACCENT2,PILL,PILL_HOVER,GREEN,RED,AMBER,CYAN
        name=migrate_theme_name(str(theme_name or "云白"))
        if name not in THEME_PRESETS:name="云白"
        self.theme_name=name;p=THEME_PRESETS[name]
        self.toast_position=str(self.settings.value("toast_position","bottom_center"))
        for key,target in (("bg","BG"),("sidebar","SIDEBAR"),("panel","PANEL"),("panel_2","PANEL_2"),
                ("border","BORDER"),("text","TEXT"),("muted","MUTED"),("accent","ACCENT"),
                ("accent2","ACCENT2"),("pill","PILL"),("pill_hover","PILL_HOVER"),
                ("green","GREEN"),("red","RED"),("amber","AMBER"),("cyan","CYAN")):
            globals()[target]=p[key]
        self.settings.setValue("ui_theme",name);self.settings.sync()
        app=QApplication.instance()
        palette=QPalette()
        for role,color in ((QPalette.ColorRole.Window,BG),(QPalette.ColorRole.Base,p["input"]),
            (QPalette.ColorRole.AlternateBase,PANEL_2),(QPalette.ColorRole.WindowText,TEXT),
            (QPalette.ColorRole.Text,TEXT),(QPalette.ColorRole.Button,PANEL_2),(QPalette.ColorRole.ButtonText,TEXT),
            (QPalette.ColorRole.Highlight,ACCENT),(QPalette.ColorRole.HighlightedText,"#FFFFFF"),
            (QPalette.ColorRole.ToolTipBase,p.get("tooltip_bg",PANEL_2)),(QPalette.ColorRole.ToolTipText,p.get("tooltip_text",TEXT)),
            (QPalette.ColorRole.PlaceholderText,MUTED)):
            palette.setColor(role,QColor(color))
        app.setPalette(palette)
        try:
            families=set(QFontDatabase.families())
            family=next((f for f in ("Microsoft YaHei UI","Microsoft YaHei","Noto Sans CJK SC","WenQuanYi Zen Hei","PingFang SC","DejaVu Sans") if f in families),"Sans Serif")
        except Exception:family="Sans Serif"
        font=QFont(family);font.setPixelSize(max(8,round(13*ui_scale_percent(self.settings)/100)));app.setFont(font)
        self.apply_style()
        if hasattr(self,"brand_mark"):self.brand_mark.update()
        self._refresh_theme_swatches(name)
        if hasattr(self,"settings_page"):
            try:self.settings_page.set_selected_theme(name)
            except Exception:pass
        for _sw in self.findChildren(SwitchToggle):_sw.update()
        if hasattr(self,"dashboard"):
            self._update_header_icons(sum(self.store.unread_totals()) if hasattr(self,"store") else 0)
            if refresh:self.refresh_all()
        for avatar in self.findChildren(AvatarWidget):avatar.update()


    def apply_style(self):
        p=THEME_PRESETS.get(getattr(self,"theme_name","云白"),THEME_PRESETS["云白"])
        field=p["input"];hover=p["hover"];soft=p["soft"];light=bool(p.get("light"))
        accent2=p.get("accent2",ACCENT);pill=p.get("pill",ACCENT);pill_hover=p.get("pill_hover",ACCENT)
        status_ok_bg="#E8F5EC" if light else "#17301F"
        status_ok_border="#BFE3C9" if light else "#2C4A34"
        status_alert_bg="#FDECEC" if light else "#331B1B"
        status_alert_border="#F2C4C4" if light else "#5A2E2E"
        status_warn_bg="#FDF0E0" if light else "#33270F"
        status_warn_border="#F0D9AE" if light else "#5A4520"
        danger_bg="#FDECEC" if light else "#331B1B"
        danger_border="#F2C4C4" if light else "#5A2E2E"
        table_selection="#EAF0FE" if light else "#1E2A44"
        disabled_text="#A3A3A3" if light else "#667C95"
        _sheet=f"""
            QMainWindow, QWidget#Root {{ background:transparent; color:{TEXT}; }}
            QWidget {{ color:{TEXT}; font-size:13px; }}
            QLabel {{ background:transparent; border:0; }}
            QDialog, QMessageBox {{ background:{BG}; }}
            QWidget#Sidebar {{ background:{SIDEBAR}; border-right:1px solid {BORDER};
                border-top-left-radius:19px; border-bottom-left-radius:19px; }}
            QWidget#Sidebar[flat='true'] {{ border-radius:0px; }}
            QFrame#BrandRow {{ background:transparent; }}
            QLabel#BrandName {{ font-size:16px;font-weight:750;color:{TEXT}; }}
            QLabel#BrandSub {{ font-size:12px;color:{MUTED}; }}
            QLabel#NavLabel {{ color:{MUTED};font-size:12px;font-weight:700;padding:8px 10px 4px; }}
            QPushButton#SideNav {{ background:transparent;border:0;border-radius:10px;
                padding:0 10px;font-size:16px;font-weight:700;text-align:left;color:{TEXT}; }}
            QPushButton#SideNav:hover {{ background:{hover}; }}
            QPushButton#SideNav[active='true'] {{ background:{soft};color:{ACCENT};font-weight:700; }}
            QFrame#ConnCard {{ background:{PANEL_2};border:1px solid {BORDER};border-radius:14px; }}
            QFrame#ConnCard:hover {{ border-color:{ACCENT}; }}
            QLabel#ConnTitle {{ font-size:13px;font-weight:700;color:{TEXT}; }}
            QLabel#SideFoot {{ color:{MUTED};font-size:11px;padding:10px 8px 0; }}
            QFrame#TopBar {{ background:{BG};border-bottom:1px solid {BORDER};border-top-right-radius:19px; }}
            QFrame#TopBar[flat='true'] {{ border-radius:0px; }}
            QLabel#PageTitleTop {{ font-size:21px;font-weight:800;color:{TEXT}; }}
            QFrame#StatusBar {{ background:{BG};border-top:1px solid {BORDER};border-bottom-right-radius:19px; }}
            QFrame#StatusBar[flat='true'] {{ border-radius:0px; }}
            QFrame#HeaderDivider {{ background:{BORDER}; }}
            QPushButton#TopIconButton {{ background:{PANEL_2};border:1px solid {BORDER};border-radius:10px;padding:0; }}
            QPushButton#TopIconButton:hover {{ background:{hover};border-color:{BORDER}; }}
            QPushButton#TopIconButton[active='true'] {{ background:{soft};border-color:{ACCENT}; }}
            QPushButton#UpdateButton {{ background:{PANEL_2};border:1px solid {BORDER};border-radius:10px;padding:0; }}
            QPushButton#UpdateButton:hover {{ background:{hover};border-color:{ACCENT}; }}
            QPushButton#UpdateButton[hasUpdate='true'] {{ background:{status_warn_bg};border:1px solid {AMBER}; }}
            QProgressBar {{ border:1px solid {BORDER};border-radius:6px;background:{PANEL_2};height:18px;text-align:center; }}
            QProgressBar::chunk {{ background:{ACCENT};border-radius:5px; }}
            QPushButton#CloseWindowButton {{ background:transparent;border:0;border-radius:8px;padding:0; }}
            QPushButton#CloseWindowButton:hover {{ background:#E81123; }}
            QLabel#NotificationBadge {{ background:{RED};color:#FFFFFF;border-radius:8px;font-size:9px;font-weight:800; }}
            QLabel#PageTitle {{ font-size:24px;font-weight:800;color:{TEXT}; }}
            QLabel#DialogTitle {{ font-size:23px;font-weight:800; }}
            QLabel#SectionTitle {{ font-size:17px;font-weight:750; }}
            QLabel#SettingsTitle, QLabel#PanelTitle {{ font-size:15px;font-weight:750; }}
            QLabel#Subtitle, QLabel#SmallMuted, QLabel#FooterText {{ color:{MUTED};font-size:12px; }}
            QLabel#Eyebrow {{ color:{CYAN};font-size:11px;font-weight:700; }}
            QLabel#RunBadge {{ color:{TEXT};font-size:13px;font-weight:650;padding:7px 8px; }}
            QFrame#MetricCard, QFrame#PageCard, QFrame#SettingsCard, QFrame#EmptyState, QFrame#DetailStat, QFrame#RailCard {{
                background:{PANEL};border:1px solid {BORDER};border-radius:16px;
            }}
            QFrame#PageCard:hover {{ border:1px solid {ACCENT}; }}
            QFrame#AlertRow {{ background:transparent;border-left:2px solid {BORDER}; }}
            QLabel#AlertRowTitle {{ color:{AMBER};font-size:12px;font-weight:650; }}
            QLabel#MetricLabel {{ color:{MUTED};font-size:13px;font-weight:600; }}
            QLabel#MetricValue {{ color:{TEXT};font-size:32px;font-weight:750; }}
            QPushButton#MetricBadge {{ background:{RED};color:#FFFFFF;border:0;border-radius:10px;font-size:11px;font-weight:800;padding:0; }}
            QLabel#ChipBadge {{ background:{RED};color:#FFFFFF;border-radius:8px;font-size:10px;font-weight:800;padding:0; }}
            QLabel#CardTitle {{ font-size:16px;font-weight:750;color:{TEXT}; }}
            QLabel#CardId {{ color:{MUTED};font-size:13px; }}
            QLabel#BigNumber {{ color:{TEXT};font-weight:800; }}
            QLabel#GrowthUp {{ color:{GREEN};font-weight:750; }}
            QLabel#GrowthDown {{ color:{RED};font-weight:750; }}
            QLabel#GrowthSoon {{ color:{AMBER};font-weight:700; }}
            QLabel#GrowthFlat {{ color:{MUTED};font-weight:650; }}
            QLabel#StatusBadge {{ background:{status_ok_bg};color:{GREEN};border:1px solid {status_ok_border};border-radius:12px;
                padding:4px 11px;font-size:13px;font-weight:700; }}
            QLabel#StatusBadge[state='alert'] {{ background:{status_alert_bg};color:{RED};border-color:{status_alert_border}; }}
            QLabel#StatusBadge[state='warning'] {{ background:{status_warn_bg};color:{AMBER};border-color:{status_warn_border}; }}
            QLabel#StatusBadge[state='off'] {{ background:{PANEL_2};color:{MUTED};border-color:{BORDER}; }}
            QLabel#UpdatePill {{ background:{status_warn_bg};color:{AMBER};border:1px solid {status_warn_border};border-radius:11px;padding:3px 9px;font-size:12px;font-weight:700; }}
            QLabel#DetailNumber {{ color:{TEXT};font-size:20px;font-weight:800; }}
            QLabel#PathLabel {{ color:{CYAN};font-size:12px; }}
            QLabel#InfoBox {{ background:{PANEL_2};border-radius:10px;padding:12px;color:{MUTED}; }}
            QPushButton {{ background:{PANEL_2};border:1px solid {BORDER};border-radius:10px;padding:8px 13px;
                color:{TEXT};font-weight:650; }}
            QPushButton:hover {{ background:{hover};border-color:{ACCENT}; }}
            QPushButton:disabled {{ color:{disabled_text};border-color:{BORDER};background:{PANEL}; }}
            QPushButton#PrimaryButton {{ background:{ACCENT};border:1px solid {ACCENT};color:#FFFFFF; }}
            QPushButton#PrimaryButton:hover {{ background:{accent2};border-color:{accent2}; }}
            QPushButton#AutoButton {{ background:{PANEL_2};border:1px solid {BORDER}; }}
            QPushButton#AutoButton[autoEnabled='true'] {{ background:{soft};border-color:{ACCENT}; }}
            QPushButton#DangerButton {{ background:{danger_bg};color:{RED};border:1px solid {danger_border};font-size:14px;font-weight:700; }}
            QPushButton#BatchActionButton {{ font-size:14px;font-weight:700; }}
            QPushButton#LinkButton {{ background:transparent;border:0;color:{ACCENT};padding:4px 8px;font-size:12px;font-weight:600; }}
            QPushButton#FilterChip {{ background:{PANEL};border:1px solid {BORDER};border-radius:15px;padding:0 13px;font-size:13px;font-weight:600; }}
            QPushButton#FilterChip:hover {{ border-color:{ACCENT}; }}
            QPushButton#FilterChip[active='true'] {{ background:{ACCENT};color:#FFFFFF;border:2px solid {ACCENT};font-weight:750; }}
            QPushButton#NoticeModeButton, QPushButton#NoticeHistoryButton {{ background:{PANEL_2};border:1px solid {BORDER};padding:7px 12px; }}
            QPushButton#NoticeModeButton[active='true'] {{ background:{soft};border-color:{ACCENT};color:{TEXT}; }}
            QPushButton#NoticeHistoryButton {{ color:{MUTED}; }}
            QPushButton#NoticeHistoryButton[active='true'] {{ background:{soft};border-color:{BORDER};color:{TEXT}; }}
            QLabel#NoticeSummary {{ color:{TEXT};font-weight:650; }}
            QLabel#EmptyHint {{ color:{MUTED};font-size:14px; }}
            QFrame#OptionCard {{ background:{PANEL};border:1px solid {BORDER};border-radius:14px; }}
            QFrame#OptionCard[selected='true'] {{ border:2px solid {ACCENT};background:{soft}; }}
            QLabel#OptionCardTitle {{ font-size:14px;font-weight:700;color:{TEXT}; }}
            QLineEdit, QPlainTextEdit, QSpinBox, QComboBox {{
                background:{field};border:1px solid {BORDER};border-radius:10px;
                padding:7px 9px;color:{TEXT};selection-background-color:{ACCENT};
            }}
            QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color:{ACCENT}; }}
            QComboBox QAbstractItemView {{ background:{PANEL};border:1px solid {BORDER};color:{TEXT};selection-background-color:{soft}; }}
            QCheckBox {{ spacing:8px;color:{TEXT}; }}
            QCheckBox::indicator {{ width:17px;height:17px;border:1px solid {BORDER};border-radius:4px;background:{field}; }}
            QCheckBox::indicator:checked {{ background:{ACCENT};border:1px solid {ACCENT}; }}
            QScrollArea {{ background:transparent;border:0; }}
            QWidget#CardCanvas {{ background:transparent; }}
            QScrollBar:vertical {{ background:transparent;width:9px;margin:0; }}
            QScrollBar::handle:vertical {{ background:{BORDER};border-radius:4px;min-height:25px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
            QScrollBar:horizontal {{ background:transparent;height:9px;margin:0; }}
            QScrollBar::handle:horizontal {{ background:{BORDER};border-radius:4px;min-width:25px; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}
            QTableWidget {{ background:{PANEL};alternate-background-color:{PANEL_2};border:1px solid {BORDER};
                border-radius:16px;gridline-color:transparent;selection-background-color:{table_selection};selection-color:{TEXT}; }}
            QTableWidget::item {{ border-bottom:1px solid {PANEL_2};padding:6px; }}
            QHeaderView::section {{ background:{PANEL_2};border:0;border-bottom:1px solid {BORDER};color:{MUTED};padding:10px 6px;font-size:12px;font-weight:700; }}
            QTableWidget#IdManagerTable {{ font-size:12px; }}
            QTabWidget::pane {{ border:1px solid {BORDER};border-radius:16px;background:{BG}; }}
            QTabBar::tab {{ background:{PANEL_2};border:1px solid {BORDER};color:{MUTED};padding:10px 17px;
                border-top-left-radius:8px;border-top-right-radius:8px;margin-right:5px; }}
            QTabBar::tab:selected {{ background:{soft};color:{TEXT};border-bottom-color:{ACCENT}; }}
            QMenu {{ background:{PANEL};border:1px solid {BORDER};padding:6px;color:{TEXT};border-radius:12px; }}
            QMenu::item {{ padding:9px 20px;border-radius:8px;font-size:13.5px;font-weight:600; }}
            QMenu::item:selected {{ background:{soft}; }}
            QMenu::indicator {{ width:16px;height:16px; }}
            QPushButton#MenuButton {{ background:{PANEL};border:1px solid {BORDER};border-radius:10px;
                padding:0 13px;font-size:13.5px;font-weight:650;color:{TEXT};text-align:left; }}
            QPushButton#MenuButton:hover {{ border-color:{ACCENT};background:{soft}; }}
            QFrame#SegmentedChoice {{ background:{PANEL_2};border:1px solid {BORDER};border-radius:11px; }}
            QPushButton#SegmentedButton {{ background:transparent;border:0;border-radius:8px;
                padding:7px 14px;font-size:13.5px;font-weight:650;color:{MUTED}; }}
            QPushButton#SegmentedButton:checked {{ background:{PANEL};border:1px solid {BORDER};color:{TEXT}; }}
            QLabel#ConnectorDot {{ border-radius:5px; }}
            QFrame#MonitorAlertPopup {{ background:{PANEL};border:2px solid {AMBER};border-radius:18px; }}
            QLabel#MonitorAlertHeadline {{ font-size:18px;font-weight:850;color:{TEXT}; }}
            QLabel#MonitorAlertSymbol {{ background:{AMBER};color:#16110A;border-radius:17px;font-size:22px;font-weight:900; }}
            QFrame#MonitorAlertRow {{ background:{PANEL_2};border:1px solid {BORDER};border-left:4px solid {AMBER};border-radius:12px; }}
            QLabel#MonitorAlertName {{ font-size:15px;font-weight:850;color:{TEXT}; }}
            QLabel#MonitorAlertEvent {{ background:{soft};border:1px solid {BORDER};border-radius:7px;padding:3px 7px;font-size:11px;font-weight:800;color:{AMBER}; }}
            QLabel#MonitorAlertEvent[kind='growth'] {{ color:{RED};background:{danger_bg};border-color:{RED}; }}
            QLabel#MonitorAlertEvent[kind='post'] {{ color:{AMBER};background:{soft};border-color:{AMBER}; }}
            QLabel#MonitorAlertMessage {{ color:{TEXT};font-size:12px; }}
            QPushButton#AlertCloseButton {{ background:transparent;border:0;font-size:21px;padding:0;color:{MUTED}; }}
            QToolTip {{ background:{p["tooltip_bg"]};color:{p["tooltip_text"]};border:1px solid {p["tooltip_border"]};padding:6px 8px;font-size:13px; }}
            QSizeGrip {{ background:transparent; }}
        """
        self.setStyleSheet(_scaled_stylesheet(_sheet,ui_scale_percent(self.settings)))


    def restore_ui_state(self):
        self.alerts.filter.blockSignals(True)
        self.alerts.filter.setCurrentIndex(max(0,self.alerts.filter.findData(self.settings.value("alerts/filter","all"))))
        self.alerts.filter.blockSignals(False)
        header=self.settings.value("alerts/header")
        if header:
            try:self.alerts.table.horizontalHeader().restoreState(header)
            except (TypeError,ValueError):pass
        geometry=self.settings.value("ui/geometry")
        if geometry:
            try:self.restoreGeometry(geometry)
            except (TypeError,ValueError):pass
        screen=QApplication.primaryScreen()
        if screen:
            frame=self.frameGeometry()
            anchor=QPoint(frame.left()+60,frame.top()+12)
            _ok=False
            for sc in QApplication.screens():
                area=sc.availableGeometry()
                if area.contains(anchor) and frame.width()<=area.width()+80 and frame.height()<=area.height()+80:
                    _ok=True;break
            if not _ok:
                area=screen.availableGeometry()
                self.resize(min(max(1200,frame.width()),area.width()),min(max(800,frame.height()),area.height()))
                self.move(area.topLeft()+QPoint(25,25))
        if is_true(self.settings.value("ui/maximized",False)):self._start_maximized=True
        else:self._start_maximized=False
        log_window_event("restore","start_maximized=%s"%self._start_maximized)
        # 1.6.2: 启动始终打开监控看板，不恢复上次停留的页面；安装后第一屏
        # 必须是看板，而不是设置。
        self.switch_page(0);self._ui_restoring=False
        try:offset=int(self.settings.value("dashboard/scroll",0))
        except (ValueError,TypeError):offset=0
        QTimer.singleShot(0,lambda:self.dashboard.scroll.verticalScrollBar().setValue(offset))

    def save_ui_state(self):
        if self._ui_restoring or not hasattr(self,"stack"):return
        if not self.isMinimized():
            self.settings.setValue("ui/geometry",self.saveGeometry())
            self.settings.setValue("ui/maximized",self.isMaximized())
        self.settings.setValue("ui/page",self.stack.currentIndex())
        self.settings.setValue("dashboard/scroll",self.dashboard.scroll.verticalScrollBar().value())
        self.settings.setValue("alerts/filter",self.alerts.filter.currentData())
        self.settings.setValue("alerts/header",self.alerts.table.horizontalHeader().saveState())
        self.settings.sync()

    def moveEvent(self,event):
        super().moveEvent(event)
        if hasattr(self,"_ui_save_timer") and not self._ui_restoring:self._ui_save_timer.start(250)


    def startup_update_check(self):
        result_path=DATA_DIR/"updates/helper/install-result.json"
        if result_path.is_file():
            try:
                result=json.loads(result_path.read_text("utf-8-sig"))
                if result.get("status")=="failed":
                    QMessageBox.warning(self,"上次更新未安装",str(result.get("message") or "系统安装器或签名验证未通过。原数据保留，可重新检查版本。"))
                else:self.dashboard.status.setText("更新安装已完成 · 当前版本 "+APP_VERSION)
                result_path.unlink(missing_ok=True)
            except (OSError,ValueError):pass
        pending=DATA_DIR/"updates/pending.json"
        if pending.is_file():
            try:
                info=json.loads(pending.read_text("utf-8"))
                if release_version(info.get("version",""))>release_version(APP_VERSION):
                    self.set_update_attention(True,info.get("version",""))
                    self._update_manual=False;self._start_update_task("verify",info);return
                pending.unlink(missing_ok=True)
            except (ValueError,OSError,UpdateError):pass
        self.check_for_updates(False)

    def _start_update_task(self,operation,info=None):
        if self._update_thread is not None:return
        self._update_operation=operation
        thread=QThread(self);worker=UpdateWorker(operation,info,DATA_DIR/"updates")
        self._update_thread=thread;self._update_worker=worker
        worker.moveToThread(thread);thread.started.connect(worker.run)
        worker.progress.connect(self._update_progress)
        worker.done.connect(self._update_done)
        worker.done.connect(worker.deleteLater);worker.done.connect(thread.quit)
        thread.finished.connect(self._update_cleanup);thread.start()

    def _update_progress(self,done,total):
        if self._update_dialog:self._update_dialog.set_progress(done,total)

    def _show_update_dialog(self,info):
        if self._update_dialog:
            self._update_dialog.close();self._update_dialog.deleteLater()
        self._update_info=dict(info)
        dlg=UpdateDialog(info,self);self._update_dialog=dlg
        dlg.download_requested.connect(self._download_update);dlg.install_requested.connect(self._install_update)
        dlg.later_requested.connect(self._postpone_update)
        dlg.cancel_requested.connect(self._cancel_update_download)
        dlg.show();dlg.raise_();dlg.activateWindow()
        return dlg

    def _update_done(self,result):
        status=result.get("status")
        if self._closing:return
        if status=="new":
            self.set_update_attention(True,result.get("version",""))
            self.settings.setValue("update/last_checked",now_iso());self.settings.sync()
            version=result.get("version","")
            snoozed=str(self.settings.value("update/snooze_version",""))==version
            try:until=float(self.settings.value("update/snooze_until",0))
            except (ValueError,TypeError):until=0
            if not self._update_manual and snoozed and time.time()<until:
                self.dashboard.status.setText("发现新版 V"+version+" · 已设置稍后提醒")
            else:self._show_update_dialog(result)
        elif status=="ready":
            self.set_update_attention(True,(result.get("info") or {}).get("version",""))
            info=dict(result["info"]);info["path"]=result["path"]
            save_json_atomic(DATA_DIR/"updates/pending.json",info)
            if self._try_silent_install(result["path"],info):
                return
            dlg=self._show_update_dialog(info);dlg.ready(result["path"])
            self.dashboard.status.setText("新版已下载并校验，可选择更新或稍后安装")
        elif status in ("error","cancelled"):
            message=str(result.get("message") or "下载已取消")
            self.dashboard.status.setText(message)
            if self._update_dialog and self._update_operation!="check":
                self._update_dialog.error(message)
            elif self._update_manual:
                if status=="cancelled":self.show_toast("下载已取消")
                else:QMessageBox.warning(self,"版本检查未完成",message)
        elif status=="current":
            self.set_update_attention(False)
            self.settings.setValue("update/last_checked",now_iso());self.settings.sync()
            message="当前已是最新版本（V"+APP_VERSION+"）"
            self.dashboard.status.setText(message)
            if self._update_manual:self.show_toast(message)
        else:
            message=str(result.get("message") or "暂未获取到发布信息")
            self.dashboard.status.setText(message)
            if self._update_manual:self.show_toast(message)

    def _update_cleanup(self):
        if self._update_thread:self._update_thread.deleteLater()
        self._update_thread=None;self._update_worker=None
        if self._closing:self.check_pending_exit()

    def _download_update(self):
        if self._closing:return
        if self._update_thread is not None:
            QTimer.singleShot(150,self._download_update);return
        if not self._update_info or not self._update_info.get("asset"):return
        self._update_dialog.downloading()
        self._start_update_task("download",dict(self._update_info))

    def _cancel_update_download(self):
        if self._update_worker:self._update_worker.cancel()

    def _postpone_update(self):
        if self._update_info:
            self.settings.setValue("update/snooze_version",self._update_info.get("version",""))
            self.settings.setValue("update/snooze_until",time.time()+6*3600);self.settings.sync()

    def _try_silent_install(self,path,info):
        """Hash-verified silent install: only when idle and the user left auto-install on."""
        if not is_true(self.settings.value("update/auto_install",1),True):return False
        if self.worker is not None or self.login_thread is not None:return False
        try:
            plan=(info.get("asset") or {})
            validate_staged_update(plan,path,DATA_DIR/"updates")
            allowed,reason=signed_install_available(plan)
            if not allowed:return False
            self._install_command=prepare_install_helper(plan,path,DATA_DIR/"updates")
            if self._update_dialog:self._update_dialog.close()
            self.dashboard.status.setText("新版已校验，正在退出并自动安装…")
            log_exception("静默安装已启动：新版 "+str(info.get("version",""))+" 已通过 SHA-256 校验。")
            self.exit_application()
            return True
        except Exception as exc:
            log_exception("静默安装未启动："+str(exc));return False

    def _install_update(self):
        if not self._update_info or not self._update_dialog or not self._update_dialog.ready_path:return
        plan=self._update_info.get("asset") or {};path=self._update_dialog.ready_path
        try:
            validate_staged_update(plan,path,DATA_DIR/"updates")
            allowed,reason=signed_install_available(plan)
            if not allowed:
                QMessageBox.information(self,"已下载，待手动安装",reason+"\n\n文件："+path)
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)));return
            answer=QMessageBox.question(self,"确认退出并更新",
                "将安全结束当前巡检并退出应用，安装校验过的新版本后重启。\n系统可能请求安装权限；数据与设置不会删除。\n\n现在更新？",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
            self._install_command=prepare_install_helper(plan,path,DATA_DIR/"updates")
            self.exit_application()
        except Exception as exc:QMessageBox.warning(self,"未开始安装",str(exc))


class NoWheelSpinBoxFilter(QObject):
    """Prevent accidental numeric changes while scrolling settings pages."""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel and isinstance(obj, (QSpinBox, QComboBox)):
            event.ignore()
            return True
        return False


def main():
    configure_process_identity()
    app=QApplication(sys.argv)
    app.setWindowIcon(make_app_icon())
    app.setStyle(QuickToolTipStyle("Fusion"))
    app.setApplicationName(APP_TITLE);app.setOrganizationName("GrowthRadar")
    app.setQuitOnLastWindowClosed(False)
    wheel_filter=NoWheelSpinBoxFilter(app);app.installEventFilter(wheel_filter)
    # --uninstall runs before the single-instance guard: a second process
    # (from Settings/Geek) must be able to uninstall while the app runs.
    if "--uninstall" in sys.argv:
        _target_arg=""
        if "--target" in sys.argv:
            _ti=sys.argv.index("--target")
            if _ti+1<len(sys.argv):_target_arg=sys.argv[_ti+1]
        return _run_uninstall_cli(app,"--silent" in sys.argv,_target_arg)
    instance=SingleInstanceGuard()
    try:
        primary=instance.acquire()
    except Exception as exc:
        QMessageBox.warning(None,"\u542f\u52a8\u5931\u8d25",str(exc));return 1
    if not primary:
        if instance.activate_existing():return 0
        QMessageBox.warning(None,"\u8f6f\u4ef6\u5df2\u5728\u8fd0\u884c",
            "\u5df2\u68c0\u6d4b\u5230\u539f\u7a97\u53e3\uff0c\u4f46\u6682\u65f6\u672a\u6536\u5230\u5524\u56de\u54cd\u5e94\u3002\u8bf7\u7a0d\u5019\u6216\u4ece\u6258\u76d8\u6253\u5f00\uff1b\u672c\u6b21\u4e0d\u4f1a\u521b\u5efa\u7b2c\u4e8c\u4e2a\u8fdb\u7a0b\u3002")
        return 0
    def exception_hook(exc_type,exc,tb):
        import traceback
        text="".join(traceback.format_exception(exc_type,exc,tb));log_exception(text)
        if sys.stderr is not None:
            try:sys.stderr.write(text)
            except Exception:pass
        QMessageBox.critical(None,APP_TITLE + "发生错误",
            "详细信息已记录到当前数据目录的 error.log。\n\n"+str(exc)[:600])
    sys.excepthook=exception_hook
    try:window=MainWindow()
    except Exception:
        exception_hook(*sys.exc_info());instance.close();return 1
    # Single presentation: show once, already in the right state. Calling
    # showMaximized() inside restore_ui_state and then show() here used to
    # present the layered window twice at startup (DWM ghost frame).
    if getattr(window,"_start_maximized",False):window.showMaximized()
    else:window.show()
    _last_activation=[0.0]
    def _maybe_activate():
        if not instance.take_activation():return
        log_window_event("activation_request")
        now=time.monotonic()
        if now-_last_activation[0]<0.5:return
        _last_activation[0]=now
        window.activate_existing_window()
    activation_timer=QTimer(app);activation_timer.setInterval(100)
    activation_timer.timeout.connect(_maybe_activate)
    activation_timer.start()
    if "--diagnose" in sys.argv:
        def diagnostic():
            info={"version":APP_VERSION,"window":[window.width(),window.height()],
                  "cards":len(window.dashboard.cards.cards),"columns":window.dashboard.cards.columns,
                  "id_count":len(window.store.list_pages()),"background":window.theme_name,
                  "worker_running":window.worker_thread is not None}
            ensure_private_directory(DATA_DIR)
            (DATA_DIR/"ui_diagnostic.json").write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding="utf-8")
            window.grab().save(str(DATA_DIR/"ui_diagnostic.png"))
            window._closing=True;window.close()
        QTimer.singleShot(1000,diagnostic)
    try:
        return app.exec()
    finally:
        window.connector.stop()
        instance.close()


if __name__=="__main__":
    raise SystemExit(main())

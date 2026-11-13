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
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlsplit
import hashlib
import html
import json
from xml.sax.saxutils import escape as _xml_escape
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
APP_VERSION = "1.7.3"
APP_BUILD = "professional-portable-deployer-ui-v173-20261112-rev87"

# Update log, bundled in the code in Whitaker's wording and grouping:
# version header "vX.Y.Z (date)", groups 优化/新增/修复 (first release
# uses 首个版本), connector line on its own after the groups.
UPDATE_LOG_SHOWN_KEY = "update_log/shown_for"
CHANGELOG = [{'version': '1.7.3', 'date': '2026-11-12', 'groups': [{'title': '新增', 'items': ['左侧导航栏可以收起来，只留一列图标，点 ‹ 收起、点 › 展开。', '设置 → 外观里可以换导航栏样式：胶囊分组、清爽线条、深色导航三种。', '左侧导航栏新增「趋势」：上面是所有专业汇总趋势图，下面是每个专业的趋势图；点日期药丸可以选几号到几号。']}, {'title': '优化', 'items': ['启用自动巡检后，按钮变成深蓝色；点启用后等 5 秒再开始第一轮，5 秒内点取消就不立即巡检。', '窗口默认 1230×720，最小 1024×650；拉到 1200 以下侧栏自动收起，拖回自动展开；卡片按宽度排，最多 6 列；开发者模式最小 1080×560，开发者日志里可以输入尺寸测试、还原默认尺寸。', '通知、发帖超时、需处理、粉丝增长超标的数字，三个主题统一成正红色。', '更新完旧的安装包会自动清理，只留当前版本。', '浏览器连接窗口里，在线绿色、离线红色；状态和备注不再弹重复提示。', '关闭窗口改成新确认框，只有最小化到托盘和完全退出两个选项。', '左侧导航栏的「最近预警」板块删掉了。', '更新前会验证发布者的签名，签名不对就不会安装。']}, {'title': '修复', 'items': ['趋势日历下面三个快捷日期，现在只有点中的那一个有颜色；手动在日历上选日期后，三个都不亮了。', '头像不会再误抓成贴文里的图片。', '粉丝增长超标时，每录到一个就立刻放一次烟花。']}], 'connector': '浏览器连接器保持 1.4.7，已安装的无需重新安装。'}, {'version': '1.7.2', 'date': '2026-11-06', 'groups': [{'title': '新增', 'items': ['第一次打开会弹新手引导，带你走一遍装连接器、加主页、设自动巡检时间、跑巡检、看提醒；老用户也会弹一次，确认过就不再弹。', '自动巡检间隔设到 180 分钟以下时，设置里会出现提示，提醒你太短容易被 Facebook 临时限制。', '巡检跑起来之后，右键点「立即巡检」可以取消当前这一轮。']}, {'title': '优化', 'items': ['设置 → 巡检与提醒里的「巡检设置」改名「自动巡检设置」。']}, {'title': '修复', 'items': ['昨天超标、今天没超标的主页，不再一直留在「粉丝增长超标」里。']}], 'connector': '浏览器连接器保持 1.4.7，无需重新安装。'}, {'version': '1.7.1', 'date': '2026-11-06', 'groups': [{'title': '优化', 'items': ['主页小卡片改版：数值显示为「昨日新增 / 今日新增 / 距上次发帖」三列，当前粉丝单独一行（仅开启粉丝监控时显示）。', '昨日新增以红色、今日新增以绿色显示，无数据时为灰色；数值达 10000 以上以 W 为单位显示。', '点击「仅巡检本主页」后立即排入队列，无需等待上一轮结束；多个浏览器并行执行。', '发帖状态区分为「未见贴文」「读取不到」「待获取」三种。', '设置页重新整理：说明文字移至控件下方，「巡检与提醒」拆分为三节，粉丝增长提醒与发帖超时提醒可分别开关。', '精简设置项，移除「启动自动巡检」「静默收起到托盘」「备份数据库」。', '托盘右键菜单精简为「打开软件」「完全退出」。']}, {'title': '新增', 'items': ['筛选胶囊支持右键直接巡检该类主页。', '关闭窗口时可选择继续后台运行、等待本轮结束后退出或立即退出。']}, {'title': '修复', 'items': ['主页名称本轮未读取到时，不再判定为异常。']}], 'connector': '浏览器连接器保持 1.4.7，无需重新安装。'}, {'version': '1.7.0', 'date': '2026-11-04', 'groups': [{'title': '新增', 'items': ['浏览器连接器升级至 1.4.7（需手动更新），工具栏图标以角标显示离线 / 空闲 / 执行中状态。', '粉丝增长达标时播放烟花提示。', '自动复检：对仍无法确认的主页最多复检 5 遍，并优先更换浏览器重试。', '新增界面缩放（80%–130%）与消息提示位置设置。', '新增诊断日志窗口。']}, {'title': '优化', 'items': ['优化预警分类规则：粉丝增长超标、发帖超时、需处理三个维度独立统计。', '排序精简为三项，默认「增长预警优先」。', '卡片数值达 1000 以上以 k 为单位显示，悬停可查看精确值。', '设置页改为 5 个横向标签页。', '巡检间隔默认值调整为 240 分钟。', '通知历史支持清空已读记录。', '统一各类提示的显示样式。', '重写浏览器连接窗口，支持筛选、停用、删除与重新检测。', '并行巡检自动识别新上线的浏览器，不再限制数量。']}], 'connector': ''}, {'version': '1.6.2', 'date': '', 'groups': [{'title': '优化', 'items': ['优化已知问题，提升使用体验。']}], 'connector': ''}, {'version': '1.6.1', 'date': '2026-11-02', 'groups': [{'title': '新增', 'items': ['Windows 版改用标准安装程序，提供简体中文安装向导，可自选安装路径。', '新增绿色便携版，解压即用，数据保存在软件文件夹内。']}, {'title': '优化', 'items': ['优化已知问题，提升使用体验。']}], 'connector': ''}, {'version': '1.6.0', 'date': '2026-11-02', 'groups': [{'title': '新增', 'items': ['新增三套主题：云白（默认）、护眼绿、曜石黑。', '新增监控模块开关，首次运行时可选择启用的模块。', '支持静默升级：后台下载并校验新版本，空闲时自动安装并重启，可在「设置 → 更新」中关闭。', '提示气泡按类型区分图标：成功、警告、普通提示。', '主页卡片支持通过三点菜单删除。', '左侧栏新增预警头像行。', '接入 Windows 系统通知。']}, {'title': '优化', 'items': ['界面改为圆角风格，并新增左侧边栏。', '提示气泡按主题配色，宽度随内容自适应。', '主页不可用时直接给出判断。', 'ID 管理列表按专业名称排序。', '精简通知文案，不再显示 ID。']}, {'title': '修复', 'items': ['修复提示气泡偶尔被裁掉最后一个字的问题。']}], 'connector': '浏览器连接器保持 1.4.1，无需重新安装。'}, {'version': '1.5.0', 'date': '', 'groups': [{'title': '优化', 'items': ['软件名称统一为「专业监控工具」。', '「设置中心」更名为「设置」，移除「恢复默认巡检参数」「打开运行日志」「重置窗口布局」。', '专业 ID 管理入口统一为「FB专业ID管理」。', '更新提示改为「升级 / 以后再说」，下载并校验完成后再次确认安装。']}, {'title': '新增', 'items': ['设置新增「智能清理缓存」，扫描后经确认再清理，不影响 ID、通知、头像、设置、数据库及浏览器连接记录。']}], 'connector': ''}, {'version': '1.4.0', 'date': '2026-10-15', 'groups': [{'title': '新增', 'items': ['首页新增「昨日新增」指标。', '点击「查看通知」可直达通知界面并高亮对应预警。']}, {'title': '优化', 'items': ['通知界面默认仅显示未读及今日通知，较早的已读记录移至「历史记录」。', '预警弹窗头像与主页卡片保持一致。', '首页巡检参数布局更紧凑。', '数字输入框改为点击即选中、输入即保存。', '顶部图标按主题分层配色，有未读通知时显示红色。', '浏览器按钮增加状态灯：绿色可用、黄色部分连接、红色无连接。', '浏览器连接窗口简化；多个连接器可并行巡检，最多 10 个。', '浏览器连接器改为紧凑弹窗，可直接填写浏览器备注。']}], 'connector': ''}, {'version': '1.3.0', 'date': '2026-10-14', 'groups': [{'title': '新增', 'items': ['浏览器连接器改为同机自动发现、自动连接，无需手动输入配对码。', '检测到多个 Chrome 配置时可选择巡检所用浏览器，并记住上次选择。', '专业 ID 的粉丝监控与发帖监控可独立启用，支持批量管理。', '首页显示上次巡检时间，支持随机巡检间隔与随机主页间隔。', '关闭窗口后可留在系统托盘运行，再次启动时自动唤回已有窗口。', '最近预警增加主页头像。', '支持通过 GitHub Releases 检查并更新软件。']}], 'connector': ''}, {'version': '1.0.0', 'date': '2026-10-12', 'groups': [{'title': '首个版本', 'items': ['支持批量导入主页 ID，可直接粘贴谷歌表格内容并自动清洗。', '登录监控账号后，逐页采集粉丝数、主页名称与头像。', '首页展示当前粉丝与今日新增。', '支持粉丝增长桌面提醒。', '支持发帖时间监控与超时判断。', '提供专业 ID 管理：添加、编辑、批量设置、批量删除、导出清单。', '支持立即巡检与自动巡检。', '支持系统托盘、数据导出、数据目录迁移与数据库备份。', '支持检查新版本。']}], 'connector': ''}]
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
    # Reuse a previously encoded toast avatar when the source file is
    # unchanged: re-encoding with PIL on every toast is pure overhead.
    try:
        _rec = None
        if out.is_file() and out.stat().st_size > 0:
            _check = toast_avatar_dir() / "toast_check.json"
            if _check.is_file():
                _data = json.loads(_check.read_text("utf-8")) or {}
                _rec = (_data.get("avatars") or {}).get(str(pid)) or {}
        if _rec and _rec.get("path") == str(out):
            for _raw in (avatar_path, str(AVATAR_DIR / (pid + ".png"))):
                if not _raw:
                    continue
                _src = Path(str(_raw))
                if _src.is_file():
                    _st = _src.stat()
                    if _rec.get("src") == {"path": str(_src), "mtime": int(_st.st_mtime_ns), "size": int(_st.st_size)}:
                        return out, "avatar-cached"
                    break
    except Exception:
        pass
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
                try:
                    _fp = {"path": str(src), "mtime": int(src.stat().st_mtime_ns), "size": int(src.stat().st_size)}
                except OSError:
                    _fp = None
                _record_toast_avatar(pid, out, "avatar-reencoded", _fp)
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


def _record_toast_avatar(pid, path, source, fingerprint=None):
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
        _rec = {"path": str(path), "source": source, "bytes": size, "at": now_iso()}
        if fingerprint is not None:
            _rec["src"] = fingerprint
        avatars[str(pid)] = _rec
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
    return {"title": _xml_escape(title), "message": _xml_escape(message), "image_path": image,
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
    if abs(n) < 10000:
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
    # One decimal only while the value is a single digit; two-plus digits
    # drop it (the exact time stays in the hover tooltip). Keeps the card
    # post value at most 5 chars, so it fits its column.
    if hours < 10:
        return f"{mark}{hours:.1f}H"
    if hours < 100:
        return f"{mark}{int(hours)}H"
    days = hours / 24.0
    if days < 10:
        return f"{mark}{days:.1f}D"
    return f"{mark}{int(days)}D"


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
    text=re.sub(r"^[\(（]\d+\+?[\)）]\s*", "", text).strip()
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
                  ariaLabel: el.getAttribute('aria-label') || '',
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
        name = _clean_profile_alt((row or {}).get("ariaLabel", ""))
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
        if not checked:
            return dict(state="unknown", label="待获取", elapsed="待获取", elapsed_short="待获取",
                        tooltip=row.get("post_error") or "尚未成功读取主页贴文时间", overdue=False)
        if _post_diag_candidates(row.get("post_diag")) == 0:
            return dict(state="unknown", label="未见贴文", elapsed="未见贴文", elapsed_short="未见贴文",
                        tooltip="本次巡检没看到该主页的贴文；可能是从未发帖，也可能是帖子没加载出来", overdue=False)
        return dict(state="unknown", label="无法获取", elapsed="无法获取", elapsed_short="读取不到",
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
    # Facebook zh UI also renders "10月24日2024" (month/day, year trailing,
    # no 年). The year is required: a bare "10月24日" is never guessed.
    m = re.fullmatch(r"(\d{1,2})月\s*(\d{1,2})日[，,\s]*(\d{4})年?(?:\s*(上午|下午)?\s*(\d{1,2}):(\d\d))?", text)
    if m:
        month, day, year = map(int, m.group(1, 2, 3))
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
                "%Y-%m-%d %H:%M", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d",
                "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"):
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


def post_candidates_diag(candidates, now=None):
    """Short diagnostic for one post detection: counts + raw timestamp samples.

    Samples are timestamp labels only (time-node attributes / permalink
    labels from authored candidates), truncated to 48 chars, at most 3,
    unparsed ones first. Never post body text.
    """
    items = [c for c in (candidates or []) if isinstance(c, dict)]
    authored = [c for c in items if c.get("authored")]
    parsed = 0
    unparsed = []
    for c in authored:
        if parse_post_time(c.get("raw"), now) is not None:
            parsed += 1
        else:
            raw = re.sub(r"\s+", " ", str(c.get("raw") or "")).strip()
            if raw:
                unparsed.append(raw[:48])
    samples = []
    for raw in dict.fromkeys(unparsed):
        if len(samples) >= 3:
            break
        samples.append(raw)
    diag = f"候选 {len(items)} · 已认作者 {len(authored)} · 可解析 {parsed}"
    if samples:
        diag += " · 未解析原始：" + " / ".join(f"“{x}”" for x in samples)
    return diag


_diag_log_lines = []
_diag_log_listeners = []


def diag_log(line):
    """Append one diagnostic line; the log keeps every line (no cap).

    Delivery to listeners is best-effort: a dead listener must never break
    a collection round.
    """
    text = str(line)[:500]
    _diag_log_lines.append(text)
    for listener in list(_diag_log_listeners):
        try:
            listener(text)
        except Exception:
            pass


def _post_diag_candidates(diag):
    """How many post candidates the last check saw, or None if unknown.

    post_candidates_diag() writes "候选 N · 已认作者 M · 可解析 P"; a
    zero means the page showed no post elements at all, which post_view
    tells apart from "posts exist but their time could not be read".
    """
    m = re.search(r"候选\s*(\d+)", str(diag or ""))
    return int(m.group(1)) if m else None


def diag_log_snapshot():
    return list(_diag_log_lines)


def add_diag_log_listener(callback):
    if callback not in _diag_log_listeners:
        _diag_log_listeners.append(callback)


def remove_diag_log_listener(callback):
    try:
        _diag_log_listeners.remove(callback)
    except ValueError:
        pass


def _diag_ts(ts):
    if not ts:
        return "无"
    return datetime.fromtimestamp(float(ts)).astimezone().strftime("%m-%d %H:%M:%S")



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
                CREATE TABLE IF NOT EXISTS daily_followers (
                    page_id TEXT NOT NULL,day TEXT NOT NULL,followers INTEGER NOT NULL,
                    approx INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(page_id, day)
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
                "post_source":"TEXT NOT NULL DEFAULT ''","post_precision_seconds":"INTEGER NOT NULL DEFAULT 1","post_diag":"TEXT NOT NULL DEFAULT ''",
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
            self._backfill_daily_followers(c)
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

    def pages_map(self,pids):
        """One query for many pages (flush_notices batch path)."""
        ids=[str(p) for p in dict.fromkeys(str(p or "") for p in (pids or [])) if p]
        out={}
        if not ids:
            return out
        with self.lock,self._connect() as c:
            for i in range(0,len(ids),400):
                chunk=ids[i:i+400]
                q="SELECT * FROM pages WHERE page_id IN (%s)" % ",".join("?"*len(chunk))
                for r in c.execute(q,chunk):
                    out[str(r["page_id"])]=dict(r)
        return out

    def unread_alert_page_ids(self, since_ts=None):
        """Page ids with unread alerts, without the 500-row display cap.
        since_ts restricts to alerts created at/after that timestamp
        (pass the local midnight to count only today's alerts)."""
        with self.lock,self._connect() as c:
            if since_ts is None:
                return {str(r[0]) for r in c.execute("SELECT DISTINCT page_id FROM alerts WHERE acknowledged=0")}
            return {str(r[0]) for r in c.execute("SELECT DISTINCT page_id FROM alerts WHERE acknowledged=0 AND alerted_ts>=?", (float(since_ts),))}

    def follower_states(self):
        """All follower_state rows in one query (dashboard refresh path)."""
        with self.lock,self._connect() as c:
            return {str(r["page_id"]):dict(r) for r in c.execute("SELECT * FROM follower_state")}

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


    @staticmethod
    def _today_from_state(row,now,interval_seconds=DEFAULT_INTERVAL_MINUTES*60):
        now=float(now)
        local=datetime.fromtimestamp(now).astimezone()
        if not row or row["baseline_date"]!=local.date().isoformat():
            return {"delta":None,"partial":True,"note":"今天尚无成功采集记录"}
        if row["latest_ts"]>now+1 or row["latest_ts"]<=row["baseline_ts"]:
            return {"delta":None,"partial":True,"note":"今天首次检测已建立基准；再次巡检后显示新增"}
        partial=bool(row["partial"]);approx=bool(row["latest_approx"] or row["baseline_approx"])
        note=("自今日首次检测起" if partial else "以零点附近读数为基准")
        note+="（"+datetime.fromtimestamp(row["baseline_ts"]).astimezone().strftime("%H:%M")+"）"
        if approx:note+="；来源为缩写约值"
        return {"delta":row["latest_count"]-row["baseline_count"],"partial":partial,"approx":approx,"note":note}

    def today_change(self,pid,now=None,interval_seconds=DEFAULT_INTERVAL_MINUTES*60):
        now=time.time() if now is None else float(now)
        with self.lock,self._connect() as c:
            row=c.execute("SELECT * FROM follower_state WHERE page_id=?",(pid,)).fetchone()
        return self._today_from_state(dict(row) if row else None,now,interval_seconds)


    @staticmethod
    def _yesterday_from_state(row,now):
        """Return only yesterday's rolled-up delta; no historical time series is stored."""
        now=float(now)
        yesterday=(datetime.fromtimestamp(now).astimezone().date()-timedelta(days=1)).isoformat()
        if not row or row["yesterday_date"]!=yesterday or row["yesterday_delta"] is None:
            return {"delta":None,"partial":True,"approx":False,"note":"需要跨日的成功巡检记录后显示"}
        note="昨天从首次有效基准起计算" if row["yesterday_partial"] else "昨天完整基准"
        if row["yesterday_approx"]:note+="；来源为缩写约值"
        return {"delta":int(row["yesterday_delta"]),"partial":bool(row["yesterday_partial"]),
                "approx":bool(row["yesterday_approx"]),"note":note}

    def yesterday_change(self,pid,now=None):
        now=time.time() if now is None else float(now)
        with self.lock,self._connect() as c:
            row=c.execute("SELECT yesterday_date,yesterday_delta,yesterday_partial,yesterday_approx FROM follower_state WHERE page_id=?",(pid,)).fetchone()
        return self._yesterday_from_state(dict(row) if row else None,now)


    def record_posts(self,pid,result,now=None,notify=True):
        """Persist success/failure separately; only fresh, confirmed results can alert."""
        now=time.time() if now is None else float(now)
        with self.lock,self._connect() as c:
            row=c.execute("SELECT * FROM pages WHERE page_id=?",(pid,)).fetchone()
            if not row or not row["monitor_posts"]: return None
            ts=valid_post_ts(result.get("last_post_ts"),now) if result.get("posts_ok") else None
            seen_ts=ts
            error=str(result.get("posts_error") or "未读取到可确认的主页贴文时间")[:300]
            stored_ts=float(row["last_post_ts"] or 0)
            stored_precision=max(1,int(row["post_precision_seconds"] or 1))
            new_precision=max(1,int(result.get("post_precision_seconds") or 1))
            reuse_stored=False;decision="无可确认时间"
            delta_text=str(int(stored_ts-seen_ts)) if (seen_ts and stored_ts) else "—"
            if ts is not None and stored_ts:
                if ts < stored_ts-120:
                    tolerance=max(120,new_precision,stored_precision)
                    if stored_ts-ts<=tolerance:
                        # Coarse confirmation of the same episode (e.g. a
                        # "6天前" label against a precise stored time): keep
                        # the precise stored value, only refresh the check.
                        reuse_stored=True;ts=stored_ts;decision="沿用已存（约值确认）"
                    else:
                        ts=None;error="本次可见贴文早于历史最新记录，无法确认最新贴文";decision="丢弃：早于已存超容差"
                else:
                    decision="接受新值"
            elif ts is not None:
                decision="接受新值"
            if ts is None:
                c.execute("""UPDATE pages SET last_post_checked_ts=?,post_result='failed',
                    post_error=?,post_diag=?,last_inspected_at=?,updated_at=? WHERE page_id=?""",(now,error,str(result.get("post_diag") or "")[:300],now_iso(),now_iso(),pid))
                diag_log(f"[发帖] {display_name(dict(row))}（{pid}）本次={_diag_ts(seen_ts)} 精度={new_precision}s 已存={_diag_ts(stored_ts)} 精度={stored_precision}s 差={delta_text}s 判定={decision} 写入=failed")
                return None
            limit=int(row["post_limit_hours"] or 24)
            precision=stored_precision if reuse_stored else max(1,int(result.get("post_precision_seconds") or 1))
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
                if notify:
                    message=f"最近贴文 {_age_label(ts,now)} 前，标准 {limit} 小时"
                    cur=c.execute("""INSERT INTO post_alerts(page_id,alerted_at,alerted_ts,last_post_ts,limit_hours,message)
                        VALUES(?,?,?,?,?,?)""",(pid,datetime.fromtimestamp(now,timezone.utc).isoformat(),now,ts,limit,message))
                    new_alert={"id":cur.lastrowid,"page_id":pid,"name":display_name(dict(row)),"avatar_path":row["avatar_path"] or "","message":message,"kind":"post","last_post_ts":ts,"limit_hours":limit}
            write_source=str(row["post_source"] or result.get("post_source") or "主页可见贴文")[:180] if reuse_stored else str(result.get("post_source") or "主页可见贴文")[:180]
            write_url=str(row["post_url"] or "")[:1000] if reuse_stored else str(result.get("post_url") or "")[:1000]
            c.execute("""UPDATE pages SET last_post_ts=?,last_post_checked_ts=?,post_result='ok',post_error='',
                post_source=?,post_url=?,post_precision_seconds=?,post_alert_key=?,post_diag=?,last_inspected_at=?,updated_at=?
                WHERE page_id=?""",(ts,now,write_source,write_url,precision,key,str(result.get("post_diag") or "")[:300],now_iso(),now_iso(),pid))
            diag_log(f"[发帖] {display_name(dict(row))}（{pid}）本次={_diag_ts(seen_ts)} 精度={new_precision}s 已存={_diag_ts(stored_ts)} 精度={stored_precision}s 差={delta_text}s 判定={decision} 写入=ok 写入时间={_diag_ts(ts)}")
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
        _fail_parts=[]
        if row["monitor_growth"] and not result.get("growth_ok"):_fail_parts.append("粉丝")
        if _fail_parts:diag_log(f"[采集] {pid} " + "／".join(_fail_parts) + "失败：" + str(result.get("growth_error") or "")[:80])
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
            post_alert=self.record_posts(pid,result,notify=is_true(opts.get("notify_post_overdue"),True))
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
            c.execute("INSERT OR REPLACE INTO daily_followers(page_id,day,followers,approx) VALUES(?,?,?,?)",
                      (pid,day,count,approx))
        return prior

    def _backfill_daily_followers(self, c):
        """Seed yesterday + today from follower_state so the default view has 2 points.
        Also reconstruct the day before yesterday (baseline - yesterday_delta)
        when yesterday was fully recorded, so growth is computable for both
        days in the default view. The reconstructed row is marked approx=1:
        it is derived, not directly observed."""
        today = datetime.now().astimezone().date()
        yesterday = today - timedelta(days=1)
        day_before = yesterday - timedelta(days=1)
        for row in c.execute("SELECT * FROM follower_state").fetchall():
            pid = str(row["page_id"])
            if str(row["baseline_date"] or "") == today.isoformat():
                c.execute("INSERT OR IGNORE INTO daily_followers(page_id,day,followers,approx) VALUES(?,?,?,?)",
                          (pid, yesterday.isoformat(), int(row["baseline_count"]), int(row["baseline_approx"] or 0)))
                c.execute("INSERT OR IGNORE INTO daily_followers(page_id,day,followers,approx) VALUES(?,?,?,?)",
                          (pid, today.isoformat(), int(row["latest_count"]), int(row["latest_approx"] or 0)))
                y_delta = row["yesterday_delta"]
                if y_delta is not None and not int(row["yesterday_partial"] or 0):
                    before = int(row["baseline_count"]) - int(y_delta)
                    if before >= 0:
                        c.execute("INSERT OR IGNORE INTO daily_followers(page_id,day,followers,approx) VALUES(?,?,?,?)",
                                  (pid, day_before.isoformat(), before, 1))

    def daily_series(self, pid, start_day, end_day):
        """One page daily followers in [start_day, end_day]; only days with data."""
        with self.lock, self._connect() as c:
            rows = c.execute(
                "SELECT day,followers FROM daily_followers WHERE page_id=? AND day>=? AND day<=? ORDER BY day",
                (str(pid), str(start_day), str(end_day))).fetchall()
        return [(str(r["day"]), int(r["followers"])) for r in rows]

    def daily_total_series(self, start_day, end_day):
        """All pages summed daily followers; a day counts if any page has data."""
        with self.lock, self._connect() as c:
            rows = c.execute(
                "SELECT day,SUM(followers) AS total FROM daily_followers WHERE day>=? AND day<=? GROUP BY day ORDER BY day",
                (str(start_day), str(end_day))).fetchall()
        return [(str(r["day"]), int(r["total"])) for r in rows]

    def daily_growth_series(self, pid, start_day, end_day):
        """Daily follower growth for one page in [start_day, end_day].
        Growth on day D = followers(D) - followers(D-1); a day is skipped
        when either day has no recorded number."""
        start = start_day - timedelta(days=1)
        rows = dict(self.daily_series(pid, start, end_day))
        out = {}
        d = start_day
        while d <= end_day:
            prev = rows.get((d - timedelta(days=1)).isoformat())
            cur = rows.get(d.isoformat())
            if prev is not None and cur is not None:
                out[d.isoformat()] = int(cur) - int(prev)
            d += timedelta(days=1)
        return out

    def daily_total_growth_series(self, start_day, end_day):
        """All pages summed daily growth in [start_day, end_day].
        A page counts toward a day only when it has numbers for that day
        and the day before, so a missing day never inflates the total."""
        start = start_day - timedelta(days=1)
        with self.lock, self._connect() as c:
            rows = c.execute(
                "SELECT page_id,day,followers FROM daily_followers WHERE day>=? AND day<=? ORDER BY day",
                (str(start), str(end_day))).fetchall()
        by_page = {}
        for r in rows:
            by_page.setdefault(str(r["page_id"]), {})[str(r["day"])] = int(r["followers"])
        out = {}
        d = start_day
        while d <= end_day:
            prev_key = (d - timedelta(days=1)).isoformat()
            cur_key = d.isoformat()
            total = 0
            any_page = False
            for series in by_page.values():
                if prev_key in series and cur_key in series:
                    total += series[cur_key] - series[prev_key]
                    any_page = True
            if any_page:
                out[cur_key] = total
            d += timedelta(days=1)
        return out


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


def _bigger_avatar_url(url):
    """Ask Facebook's CDN for a bigger avatar: rewrite a /p168x168/ or
    /s160x160/ path segment to /p480x480/; otherwise bump width=/height=
    query params to 480. No size marker -> return the URL unchanged."""
    u = str(url or "")
    if not u:
        return u
    bigger = re.sub(r"/[ps]\d+x\d+/", "/p480x480/", u, count=1)
    if bigger != u:
        return bigger
    if "width=" in u or "height=" in u:
        bigger = re.sub(r"([?&](?:width|height)=)\d+", r"\g<1>480", u)
        if bigger != u:
            return bigger
    return u


_AVATAR_ALT_RE = re.compile(r"profile picture|profile photo|avatar|picture of|page picture|page profile|头像|大头贴|大頭貼|头像照片|照片墙|主页照片", re.IGNORECASE)


def _avatar_url_key(url):
    """Normalize a Facebook image URL to the photo it identifies: drop the
    scheme/host, query string and the size segment, so the same photo at
    different sizes compares equal (used to match candidates to og:image)."""
    u = str(url or "").strip()
    if u.startswith("//"):
        u = "https:" + u
    try:
        path = urlsplit(u).path
    except ValueError:
        path = u.split("?", 1)[0]
    return re.sub(r"/[ps]\d+x\d+/", "/", path)


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
            if(el.closest('article')||el.closest('[role="article"]'))score-=85;
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
                            candidates.append({"url":url,"selector":"","index":-1,"score":70,"avatar_signal":True})
                except Exception:
                    pass
        og_urls=[]
        for selector in ("meta[property='og:image']","meta[name='twitter:image']"):
            try:
                url=page.locator(selector).first.get_attribute('content',timeout=1100)
                if url:
                    og_urls.append(url)
                    candidates.append({"url":url,"selector":"","index":-1,"score":0})
            except Exception:
                continue
        # Cross-check against og:image (the page's own avatar): a visible
        # candidate showing the same photo wins over post images, even if a
        # post image scored higher; it also counts as an avatar signal.
        og_keys={_avatar_url_key(u) for u in og_urls}
        for candidate in candidates:
            _key=_avatar_url_key(candidate.get("url") or "")
            if _key and _key in og_keys:
                candidate["og_match"]=True
                candidate["score"]=float(candidate.get("score") or 0)+120
            if candidate.get("og_match") or _AVATAR_ALT_RE.search(str(candidate.get("alt") or "")):
                candidate["avatar_signal"]=True
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
            # Keep the downloaded size (up to 480): a 640px original stays
            # sharp at 480, a 168px original is stored as-is, never upscaled.
            side=min(480,max(im.width,im.height))
            avatar=ImageOps.fit(im.convert('RGB'),(side,side),method=Image.Resampling.LANCZOS)
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
            # Legacy 192x192 caches were upscaled from small thumbnails:
            # treat them as expired once so they get re-downloaded bigger.
            # A failed re-download still falls back to the old file below.
            _legacy=False
            try:
                from PIL import Image as _PilImage
                with _PilImage.open(old) as _im:
                    _legacy=(_im.width==192 and _im.height==192)
            except Exception:
                _legacy=False
            if not _legacy:
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
            if old_valid and not candidate.get("avatar_signal"):
                # No avatar signal (no avatar alt text, no og:image match):
                # keep the good old avatar instead of letting a post image
                # replace it. Without an old avatar, any candidate is tried.
                continue
            url=str(candidate.get('url') or '').strip()
            if url and url.startswith('//'):
                url='https:'+url
            if url and self._is_facebook_image_url(url) and not any(x in url.lower() for x in ('emoji.php','static.xx.fbcdn.net/rsrc.php')):
                _tries=[_bigger_avatar_url(url)]
                if _tries[0]!=url:
                    _tries.append(url)
                for _try_url in _tries:
                    if not self._is_facebook_image_url(_try_url):
                        continue
                    try:
                        resp=self.context.request.get(_try_url,timeout=min(3800,max(350,int(remaining*1000))))
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
                post=self._extract_post(page,pid,name or normalize_name(row.get("page_name"),pid)) or {}
                info["post_diag"]=str(post.get("post_diag") or "")
                if post.get("ts"):
                    info.update(posts_ok=True,last_post_ts=post["ts"],post_precision_seconds=post["precision"],
                                post_source=post["source"],post_url=post["url"])
                elif _post_diag_candidates(info["post_diag"]) == 0:info["posts_error"]="本次巡检没看到该主页的贴文"
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
        if not chosen:return {"post_diag": post_candidates_diag(candidates)}
        chosen["post_diag"]=post_candidates_diag(candidates)
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
# Update-manifest Ed25519 public key (base64 of the raw 32-byte public key,
# from ReleaseSigner; fingerprint 7012-CFB2-DCEC-4DC7). The public key may
# be public; the private key must never be put in code or committed.
UPDATE_MANIFEST_PUBKEY_B64 = "Bb3XUBVn7Qkbbrjzq7gWmnJiJI85UA2VaiSuekSIeqI="
UPDATE_MANIFEST_NAME = "update-manifest.json"
UPDATE_MANIFEST_SIG_NAME = "update-manifest.json.sig"
UPDATE_MANIFEST_FAIL = "更新清单签名验证失败，已停止更新"
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


def _manifest_public_key():
    """Ed25519 public key built into the program, or None.

    Only the public half is needed; verification needs nothing secret.
    cryptography is imported lazily so the program still starts when it
    is missing (update checks then fail closed, see below).
    """
    try:
        raw = base64.b64decode(UPDATE_MANIFEST_PUBKEY_B64.strip(), validate=True)
    except Exception:
        return None
    if len(raw) != 32:
        return None
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        return Ed25519PublicKey.from_public_bytes(raw)
    except Exception:
        return None


def _verify_manifest_bytes(manifest_bytes, sig_bytes):
    """Verify raw manifest bytes against the signature.

    Runs on the downloaded bytes BEFORE any JSON parsing, never on
    re-serialized content. Any failure (no key, bad signature, bad
    input) means rejection, never a fallback to the GitHub digest.
    """
    pub = _manifest_public_key()
    if pub is None:
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        pub.verify(bytes(sig_bytes), bytes(manifest_bytes))
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False


def _load_update_bytes(url, open_fn=None, limit=MAX_UPDATE_JSON_BYTES):
    """Raw bytes from a trusted update URL, with a size cap."""
    with (open_fn or open_update_url)(url) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise UpdateError("更新清单过大，已停止")
    return raw


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
    if not manifest_item or not str(manifest_item.get("sha256") or ""):
        # No sha256 for this package in the verified manifest: reject the
        # update instead of falling back to the GitHub digest.
        raise UpdateError(UPDATE_MANIFEST_FAIL)
    sha=_asset_digest(asset,manifest_item)
    return {"name":name,"url":url,"size":size,"sha256":sha,"installer":"platform-bundle","platform":key,
            "version":version,"source_mode":not frozen}

def _rate_limit_wait_seconds(exc):
    """Seconds until a GitHub 403/429 rate limit resets, or None.

    429 prefers Retry-After; 403 prefers the x-ratelimit-reset epoch.
    A missing or unparsable header means 'limited, unknown wait' (None),
    which keeps the old generic message instead of inventing minutes.
    """
    try:
        _headers = exc.headers or {}
    except AttributeError:
        return None
    try:
        _retry = _headers.get("Retry-After")
    except Exception:
        _retry = None
    if _retry:
        try:
            _secs = int(str(_retry).strip())
            if _secs > 0:
                return _secs
        except (ValueError, TypeError):
            pass
    try:
        _reset = _headers.get("x-ratelimit-reset")
    except Exception:
        _reset = None
    if _reset:
        try:
            _secs = int(float(str(_reset).strip())) - int(time.time())
            if _secs > 0:
                return _secs
        except (ValueError, TypeError):
            pass
    return None


def query_latest_release(open_fn=None,system=None,machine=None,frozen=None):
    try:
        release=load_update_json(RELEASES_API,open_fn)
    except urllib.error.HTTPError as exc:
        if exc.code==404:return {"status":"unavailable","message":"暂未找到可公开访问的正式 Release（可能尚未发布或仓库暂不可访问）"}
        if exc.code in (403,429):
            _secs=_rate_limit_wait_seconds(exc)
            if _secs:
                _mins=max(1,-(-int(_secs)//60))
                _err=UpdateError(f"GitHub 请求受限，约 {_mins} 分钟后恢复")
                _err.retry_after_seconds=_secs
                raise _err from exc
            raise UpdateError("GitHub 请求受限，请稍后再检查") from exc
        raise UpdateError(f"GitHub 返回 HTTP {exc.code}") from exc
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        raise UpdateError("无法连接 GitHub，请检查网络后重试；没有把本次检查当作已是最新版") from exc
    if release.get("draft") or release.get("prerelease"):return {"status":"unavailable","message":"没有正式发布的稳定版本"}
    tag=str(release.get("tag_name") or "")
    if release_version(tag)<=release_version(APP_VERSION):return {"status":"current","version":tag}
    # A signed manifest is mandatory once the program carries a public
    # key: download the manifest AND its signature, verify the raw bytes
    # first, and only then parse. Missing .sig, bad signature, missing
    # manifest, or a version that does not match the Release tag all reject
    # the update; there is no fallback to the GitHub digest.
    assets_by_name={}
    for asset in release.get("assets",[]):
        if isinstance(asset,dict) and isinstance(asset.get("name"),str):
            assets_by_name[asset["name"]]=asset
    manifest_asset=assets_by_name.get(UPDATE_MANIFEST_NAME)
    sig_asset=assets_by_name.get(UPDATE_MANIFEST_SIG_NAME)
    if not manifest_asset or not sig_asset:
        raise UpdateError(UPDATE_MANIFEST_FAIL)
    manifest_url=str(manifest_asset.get("browser_download_url") or "")
    sig_url=str(sig_asset.get("browser_download_url") or "")
    if not _trusted_update_url(manifest_url,asset=True) or not _trusted_update_url(sig_url,asset=True):
        raise UpdateError(UPDATE_MANIFEST_FAIL)
    try:
        manifest_bytes=_load_update_bytes(manifest_url,open_fn)
        sig_raw=_load_update_bytes(sig_url,open_fn,limit=4096)
        sig_bytes=base64.b64decode(sig_raw.strip(),validate=True)
    except UpdateError:
        raise
    except Exception:
        raise UpdateError(UPDATE_MANIFEST_FAIL) from None
    if not _verify_manifest_bytes(manifest_bytes,sig_bytes):
        raise UpdateError(UPDATE_MANIFEST_FAIL)
    try:
        manifest=json.loads(manifest_bytes.decode("utf-8-sig"))
    except (UnicodeError,ValueError):
        raise UpdateError(UPDATE_MANIFEST_FAIL) from None
    if not isinstance(manifest,dict) or manifest.get("schema")!=1 or not isinstance(manifest.get("assets"),dict):
        raise UpdateError(UPDATE_MANIFEST_FAIL)
    if str(manifest.get("version") or "")!=str(tag).lstrip("vV"):
        raise UpdateError(UPDATE_MANIFEST_FAIL)
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

def cleanup_old_updates(updates_dir,keep_versions,keep_paths=()):
    """Remove update files from older versions; keep only the given ones.

    keep_versions: version strings to keep (current version, plus a failed
    install's version so it can be retried). keep_paths: exact file paths
    to keep (a pending update's downloaded file). Only files whose name
    carries a version number are touched, and only version folders under
    updates/extracted/; helper/, pending.json and anything unrecognised
    are left alone. Returns (removed_files, removed_dirs, freed_bytes).
    Never raises: a failed delete is skipped and the rest still runs.
    """
    keep_versions={str(v) for v in keep_versions if v}
    keep_paths={str(Path(p).resolve()) for p in keep_paths if p}
    removed_files=[];removed_dirs=[];freed=0
    try:
        base=Path(updates_dir)
        if not base.is_dir():return ([],[],0)
        _ver_re=re.compile(r"(\d+\.\d+\.\d+(?:\.\d+)?)")
        for entry in list(base.iterdir()):
            try:
                if entry.is_symlink() or not entry.is_file():continue
                if entry.suffix.lower() not in (".zip",".exe",".msi",".pkg",".dmg"):continue
                m=_ver_re.search(entry.name)
                if not m:continue
                if m.group(1) in keep_versions:continue
                if str(entry.resolve()) in keep_paths:continue
                size=entry.stat().st_size
                entry.unlink()
                removed_files.append(entry.name);freed+=size
            except OSError:
                continue
        extracted=base/"extracted"
        if extracted.is_dir() and not extracted.is_symlink():
            for sub in list(extracted.iterdir()):
                try:
                    if sub.is_symlink() or not sub.is_dir():continue
                    if not _ver_re.fullmatch(sub.name):continue
                    if sub.name in keep_versions:continue
                    size=sum(p.stat().st_size for p in sub.rglob("*") if p.is_file())
                    shutil.rmtree(sub)
                    removed_dirs.append(sub.name);freed+=size
                except OSError:
                    continue
    except OSError:
        pass
    return (removed_files,removed_dirs,freed)

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
    path = Path(tempfile.gettempdir()) / ("pmt-uninstall-%s.ps1" % secrets.token_hex(8))
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

CONNECTOR_VERSION = '1.4.7'
CONNECTOR_PROTOCOL = 1
CONNECTOR_PORT = 17831
CONNECTOR_EXTENSION_ID = 'lpjmbcclokpbgfogjhjepmnpoplgheoh'
CONNECTOR_ORIGIN = 'chrome-extension://' + CONNECTOR_EXTENSION_ID

# BEGIN BUNDLED CONNECTOR PACKAGE
# IMPORTANT: Connector version is independent from the desktop app version.
# Do not change this package/version unless the browser connector itself is intentionally updated.
BUNDLED_CONNECTOR_VERSION = '1.4.7'
BUNDLED_CONNECTOR_FILENAME = '专业监控工具-浏览器连接器-1.4.7.zip'
BUNDLED_CONNECTOR_SHA256 = '111802b2c60aae4580a1fedc0bc2fb89cc354a8988947c6c20a67b05cbc551fb'
BUNDLED_CONNECTOR_ZIP_B64 = (
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
                               'source':'主页贴文悬停提示' if '悬停' in str(item.get('source') or '') else '连接器读取的主页自发贴文'})
        chosen=choose_post_candidate(candidates,now=stamp)
        result['post_diag']=post_candidates_diag(candidates,now=stamp)
        if isinstance(payload.get('hover_checked'), int):
            result['post_diag'] += f" · 悬停 {int(payload.get('hover_found') or 0)}/{payload['hover_checked']}"
        if chosen:
            result.update(posts_ok=True,last_post_ts=chosen['ts'],post_precision_seconds=chosen['precision'],
                          post_source=chosen['source'],post_url=chosen['url'])
        elif not error and _post_diag_candidates(result['post_diag']) == 0:result['posts_error']='本次巡检没看到该主页的贴文'
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
    # A retry must never downgrade a successful first pass: the narrowed
    # retry row only reflects one browser's transient state, but the
    # dashboard treats 'login'/'page_unavailable' as page-level states
    # (login badge, needs-only classification). Keep the first diagnosis
    # when it is 'ok'; otherwise the retry's diagnosis is newer info.
    if first.get('diagnosis_code')=='ok':
        out['diagnosis_code']='ok'
        out['diagnosis_detail']=first.get('diagnosis_detail') or ''
    else:
        out['diagnosis_code']=second.get('diagnosis_code') or first.get('diagnosis_code') or 'unknown'
        out['diagnosis_detail']=second.get('diagnosis_detail') or first.get('diagnosis_detail') or ''
    out['name_candidates_count']=max(int(first.get('name_candidates_count') or 0),int(second.get('name_candidates_count') or 0))
    out['follower_text_present']=bool(first.get('follower_text_present') or second.get('follower_text_present'))

    if purpose=='monitor' and row.get('monitor_posts'):
        if second.get('posts_ok'):
            for key in ('posts_ok','last_post_ts','post_precision_seconds','post_source','post_url','post_diag'):
                if key in second:out[key]=second[key]
            out['posts_error']=''
        elif first.get('posts_ok'):
            for key in ('posts_ok','last_post_ts','post_precision_seconds','post_source','post_url','post_diag','posts_error'):
                if key in first:out[key]=first[key]
        else:
            out['posts_ok']=False
            detail=str(second.get('posts_error') or first.get('posts_error') or '未读取到可确认的主页自发贴文时间')
            _suffix='；已自动复检一次仍无法确认'
            if not detail.endswith('已自动复检一次仍无法确认'):detail+=_suffix
            out['posts_error']=detail[:300]
            out['post_diag']=str(second.get('post_diag') or first.get('post_diag') or '')[:300]
    out['rechecked']=True
    out['recheck_ok']=not record_needs_recheck(row,out,purpose)
    # The snapshot timestamp must be the time of the sample whose count
    # is stored, not the merge time: growth is kept from the first pass
    # when it succeeded, so stamping merge time inflates the elapsed
    # interval in should_alert (window max(300, 2.5*interval)) and can
    # drop an alert when rechecks run long on a small interval.
    if first.get('growth_ok'):
        out['collected_ts']=float(first.get('collected_ts') or 0) or time.time()
    elif second.get('growth_ok'):
        out['collected_ts']=float(second.get('collected_ts') or 0) or time.time()
    else:
        out['collected_ts']=max(float(first.get('collected_ts') or 0),float(second.get('collected_ts') or 0),time.time())
    out['collected_at']=now_iso()
    if out.get('recheck_ok'):
        out.pop('error',None)
    _fixed=[]
    if second_name and not first_name:_fixed.append("名称已确认")
    if not first.get("growth_ok") and second.get("growth_ok"):_fixed.append("粉丝已补")
    if _fixed:diag_log(f"[复检] {pid} " + "、".join(_fixed))
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
    QObject, QDate, QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QSettings, QRunnable, QThread, QThreadPool, QTimer, QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QImage, QLinearGradient, QPainter, QPalette,
    QPainterPath, QPen, QPixmap, QPolygonF, QRegion,
)
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDateEdit, QDialog, QLayout, QLayoutItem,
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
TOAST_POSITIONS = (("下居中", "bottom_center"), ("右上", "top_right"),
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
    elif kind=="tray":
        # inbox/tray: open box with a lid line and a handle notch.
        path=QPainterPath();path.moveTo(12,16);path.lineTo(12,46);path.lineTo(52,46);path.lineTo(52,16);p.drawPath(path)
        line(12,26,52,26)
        path=QPainterPath();path.moveTo(25,26);path.lineTo(29,34);path.lineTo(35,34);path.lineTo(39,26);p.drawPath(path)
    elif kind=="power":
        # power: circle open at the top + a vertical line through the gap.
        p.drawArc(QRectF(14,18,36,36),45*16,270*16);line(32,8,32,26)
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
            if p.fontMetrics().horizontalAdvance(self.text())<=self.contentsRect().width()-2:break
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


# Automatic recheck passes for ambiguous name/post results: keep
# retrying (rotating browsers in the connector worker) until the
# record is confirmed or this many passes are used up.
RECHECK_MAX_PASSES = 5


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
                    _reattempt=0
                    while record_needs_recheck(row,record,self.purpose) and _reattempt<RECHECK_MAX_PASSES and not self._stop.is_set():
                        _reattempt+=1
                        self.progress.emit(index,total,f"自动复检第 {_reattempt} 遍 "+display_name(row))
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

    A name/post result that cannot be confirmed is retried up to five times,
    each pass running in parallel across browsers (one lane per target).  When
    another selected browser is online the recheck rotates to a browser not yet tried
    for that page; with only one browser it retries the same connector.  A successful
    first-pass follower observation is preserved so the
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

    def _recheck_connector(self,source_cid,record=None,tried=()):
        online=self._live_online()
        others=[cid for cid in online if cid!=source_cid]
        diag=str((record or {}).get('diagnosis_code') or '')
        # Login/offline: another profile cannot fix this account's login
        # state, and switching accounts mid-round would be surprising.
        # Layout/parse failures: another browser may render differently,
        # so rotate to one not yet tried for this page.
        if diag in ('login',):
            return source_cid if source_cid in online else (online[0] if online else '')
        untried=[cid for cid in others if cid not in set(tried)]
        if untried:
            return untried[0]
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

        # Recheck the ambiguous subset up to 5 passes, in parallel across
        # browsers: each pass plans targets first (same rotation rule as
        # before: prefer a browser not yet tried for that page, same
        # connector repeats when alone), then runs one lane per target
        # browser so no connector ever handles two fetches at once. A
        # later pass can confirm the post time and move the page to
        # overdue/normal.
        _pending=list(rechecks);_tried={}
        for _cid0,_row0,_first0 in rechecks:
            _tried.setdefault(str(_row0["page_id"]),set()).add(_cid0)
        _attempt=0
        while _pending and _attempt<RECHECK_MAX_PASSES and not self._stop.is_set():
            _attempt+=1
            _planned=[]
            for _source_cid,_row,_first in _pending:
                _pid=str(_row["page_id"])
                _target=self._recheck_connector(_source_cid,_first,_tried.get(_pid,()))
                if _target:_tried.setdefault(_pid,set()).add(_target)
                _planned.append((_source_cid,_row,_first,_target))
            _by_target={}
            _still=[]
            for _source_cid,_row,_first,_target in _planned:
                if _target:
                    _by_target.setdefault(_target,[]).append((_source_cid,_row,_first,_target))
                    continue
                _second={'page_id':_row['page_id'],'metadata_ok':False,'growth_ok':False,'posts_ok':False}
                _merged=merge_recheck_record(_first,_second,_row,self.purpose)
                _merged['recheck_connector_changed']=False
                if record_needs_recheck(_row,_merged,self.purpose) and _attempt<RECHECK_MAX_PASSES:
                    _still.append((_source_cid,_row,_merged));continue
                _good=self._record_good(_row,_merged);_merged['ok']=_good;_merged['purpose']=self.purpose
                self.result.emit(_merged);finalized+=1
                if _good:success+=1
                else:failure+=1
            _outq=queue.Queue()
            def _recheck_lane(_cid,_items):
                for _source_cid,_row,_first,_target in _items:
                    if self._stop.is_set():break
                    _retry_row=dict(_row)
                    _retry_purpose='metadata'
                    if self.purpose=='monitor' and _row.get('monitor_posts') and not _first.get('posts_ok'):
                        _retry_purpose='monitor';_retry_row['monitor_growth']=False;_retry_row['monitor_posts']=True
                    elif self.purpose=='monitor' and _row.get('monitor_growth') and not _first.get('growth_ok'):
                        _retry_purpose='monitor';_retry_row['monitor_growth']=True;_retry_row['monitor_posts']=False
                    _second={'page_id':_row['page_id'],'metadata_ok':False,'growth_ok':False,'posts_ok':False}
                    try:
                        payload=self.bridge.request(_cid,_retry_row,_retry_purpose,self._stop,timeout=120,retry=True)
                        _second=connector_record(_retry_row,payload,_retry_purpose)
                    except ConnectorError as exc:
                        _second.update(error=str(exc),name_error=str(exc),posts_error=str(exc))
                    _merged=merge_recheck_record(_first,_second,_row,self.purpose)
                    _merged['recheck_connector_changed']=bool(_target!=_source_cid)
                    _outq.put((_cid,_row,_merged,_target,_source_cid))
            _lanes=[]
            for _cid,_items in _by_target.items():
                _t=threading.Thread(target=_recheck_lane,args=(_cid,_items),name='POM-recheck-'+_cid[:8],daemon=True)
                _lanes.append(_t);_t.start()
            _need=sum(len(_v) for _v in _by_target.values());_got=0
            while _got<_need and not self._stop.is_set():
                try:_cid,_row,_merged,_target,_source_cid=_outq.get(timeout=.25)
                except queue.Empty:
                    if not any(_t.is_alive() for _t in _lanes):break
                    continue
                _got+=1
                self.progress.emit(finalized+1,total,f'自动复检第 {_attempt} 遍 '+display_name(_row)+(' · 换浏览器' if _target!=_source_cid else ' · 当前浏览器'))
                if record_needs_recheck(_row,_merged,self.purpose) and _attempt<RECHECK_MAX_PASSES:
                    _still.append((_cid,_row,_merged));continue
                _good=self._record_good(_row,_merged);_merged['ok']=_good;_merged['purpose']=self.purpose
                self.result.emit(_merged);finalized+=1
                if _good:success+=1
                else:failure+=1
            for _t in _lanes:_t.join(timeout=1)
            if self._stop.is_set():break
            _pending=_still
        if not self._stop.is_set():
            for source_cid,row,first in _pending:
                good=self._record_good(row,first);first['ok']=good;first['purpose']=self.purpose
                self.result.emit(first);finalized+=1
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
        if rechecks:extra+=f' · 自动复检 {len(rechecks)} 个主页（最多 {RECHECK_MAX_PASSES} 遍）'
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
        self.chips = None; self._filter = "all"; self._chip_counts = None; self._growth_alert_ids = set()
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
            if status == '在线':
                scell.setForeground(QColor(THEME_PRESETS.get(getattr(self.owner, "theme_name", "云白"), THEME_PRESETS["云白"])["green"]))
            elif status == '离线':
                scell.setForeground(QColor("#EA580C"))
            self.table.setItem(i, 4, scell)
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


PROGRESS_STYLES = (
    ("fill", "填充式", "白色从左往右漫过按钮，写已处理 / 总数"),
    ("strip", "底边细条", "按钮底部一条细线走进度，写百分比"),
    ("ring", "圆环", "图标外套一个圆环，走完一圈就是跑完"),
    ("badge", "角标", "右上角小角标写已处理 / 总数，按钮不变宽"),
)
PROGRESS_BUTTON_WIDTHS = {"fill": 190, "strip": 140, "ring": 170, "badge": 150}


CARD_LAYOUTS = (
    ("oneline", "一行四列", "当前粉丝、昨日、今日、发帖时间放一排，数字自动缩小。"),
    ("standard", "三列带粉丝", "昨日、今日、发帖时间三列，下面一行当前粉丝。"),
    ("nofans", "三列无粉丝", "只有昨日、今日、发帖时间三列，不显示当前粉丝数。"),
    ("hero", "大粉丝数", "当前粉丝放大显示，下面是昨日、今日、发帖时间。"),
)
CARD_LAYOUT_KEYS = frozenset(k for k, _, _ in CARD_LAYOUTS)

# Sidebar (navigation bar) looks, chosen in 设置 → 外观. First entry is the default.
NAV_STYLES = (
    ("capsule", "胶囊分组", "入口分组放进圆角卡片，选中项是实心主色胶囊。"),
    ("line", "清爽线条", "细字重、浅色底加主色文字，最安静，信息最密。"),
    ("dark", "深色导航", "导航栏始终是深色，和浅色内容区对比最强。"),
)
NAV_STYLE_KEYS = frozenset(k for k, _, _ in NAV_STYLES)
NAV_DEFAULT_STYLE = "capsule"
# Colours for the "dark" sidebar, one set per theme (solid hex: no alpha needed).
NAV_DARK_PALETTES = {
    "云白": dict(bg="#0F1C3F", border="#24335C", text="#E8ECF8", muted="#A3AECB", accent="#8FB1FF", hover="#1B2A52", active="#27386A", glass="#16254B"),
    "护眼绿": dict(bg="#0E2A1D", border="#1F4A35", text="#E6F4EB", muted="#9DB8A8", accent="#6EE7A0", hover="#17392A", active="#1F4A35", glass="#13301F"),
    "曜石黑": dict(bg="#0B0C0F", border="#23242A", text="#ECECEC", muted="#9AA0A6", accent="#7AA2F7", hover="#1A1B20", active="#1E2A44", glass="#131418"),
}


def nav_dark_palette(theme_name):
    return NAV_DARK_PALETTES.get(theme_name, NAV_DARK_PALETTES["云白"])


def paint_progress_button(p, rect, style, frac, current, total, paused, font):
    """Paint the face of a patrol-progress button: icon + text + progress.
    The blue button background is painted by the caller (the real button's
    stylesheet, or the settings preview). rect is the button's own rect;
    the badge style draws a pill that sticks out above rect's top edge,
    so the caller must leave ~12px of room above it."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    frac = max(0.0, min(1.0, float(frac or 0)))
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    verb = "继续巡检" if paused else "暂停巡检"
    if total and total > 0:
        if style == "fill":
            text = f"{verb} {int(current)}/{int(total)}"
        elif style == "badge":
            text = verb
        else:
            text = f"{verb} · {int(round(frac * 100))}%"
    else:
        text = verb
    bf = QFont(font); bf.setBold(True); p.setFont(bf)
    tw = p.fontMetrics().horizontalAdvance(text)
    gw = 16 + 6 + tw
    gx = x + (w - gw) // 2
    iy = y + (h - 16) // 2
    p.setPen(Qt.PenStyle.NoPen)
    if style == "fill":
        fw = int(w * frac)
        if fw > 0:
            p.setBrush(QColor(255, 255, 255, 90))
            p.drawRoundedRect(QRectF(x, y, fw, h), 8, 8)
    elif style == "strip":
        track = QRectF(x + 7, y + h - 8, w - 14, 4)
        p.setBrush(QColor(255, 255, 255, 70)); p.drawRoundedRect(track, 2, 2)
        fw = (w - 14) * frac
        if fw > 0:
            p.setBrush(QColor(255, 255, 255, 235))
            p.drawRoundedRect(QRectF(track.x(), track.y(), fw, 4), 2, 2)
    if style == "ring":
        cx, cy, r = gx + 8, iy + 8, 11
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 70), 3))
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 0, 360 * 16)
        p.setPen(QPen(QColor(255, 255, 255, 240), 3))
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 90 * 16, -int(frac * 360 * 16))
    p.drawPixmap(gx, iy, ui_icon("play" if paused else "pause", "#FFFFFF").pixmap(16, 16))
    p.setPen(QColor("#FFFFFF"))
    p.drawText(gx + 22, y, w - 22, h, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
    if style == "badge" and total and total > 0:
        bf2 = QFont(font); bf2.setBold(True)
        if font.pixelSize() > 0:
            bf2.setPixelSize(max(10, font.pixelSize() - 2))
        else:
            bf2.setPointSize(max(8, font.pointSize() - 1))
        p.setFont(bf2)
        badge = f"{int(current)}/{int(total)}"
        bw = p.fontMetrics().horizontalAdvance(badge) + 14
        bx, by = x + w - bw - 5, y - 9
        p.setPen(QPen(QColor(ACCENT), 1))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(QRectF(bx, by, bw, 18), 9, 9)
        p.setPen(QColor(ACCENT))
        p.drawText(QRectF(bx, by, bw, 18), Qt.AlignmentFlag.AlignCenter, badge)


class ProgressStylePreview(QWidget):
    """Live miniature of the patrol button in one progress style (40%)."""
    def __init__(self, style, parent=None):
        super().__init__(parent)
        self._style = style
        self.setFixedHeight(48)
    def paintEvent(self, event):
        p = QPainter(self)
        w = PROGRESS_BUTTON_WIDTHS[self._style]
        btn = QRect((self.width() - w) // 2, 10, w, 36)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ACCENT))
        p.drawRoundedRect(QRectF(btn), 8, 8)
        paint_progress_button(p, btn, self._style, 0.4, 12, 30, False, self.font())
        p.end()


class CardLayoutPreview(QWidget):
    """Wireframe miniature of one card layout (for the settings picker)."""
    def __init__(self, layout_key, parent=None):
        super().__init__(parent)
        self._key = layout_key
        self.setFixedHeight(118)
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        def _bar(x, y, w, h, color, alpha=255, r=2):
            c = QColor(color); c.setAlpha(alpha)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(c)
            p.drawRoundedRect(QRectF(x, y, w, h), r, r)
        p.setPen(QPen(QColor(BORDER), 1)); p.setBrush(QColor(PANEL))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 8, 8)
        _bar(10, 10, 20, 20, ACCENT, 255, 5)
        _bar(36, 12, 52, 6, TEXT, 200)
        _bar(36, 23, 74, 5, MUTED, 160)
        def _cell(x, y, w, v_h=8):
            _bar(x, y, 24, 4, MUTED, 160)
            _bar(x, y + 8, min(w, 34), v_h, TEXT, 210)
        _cw = (W - 20) / 3
        if self._key == "oneline":
            for _i in range(4):
                _cell(10 + _i * (W - 20) / 4, 52, 26)
        elif self._key == "nofans":
            for _i in range(3):
                _cell(10 + _i * _cw, 52, 34)
        elif self._key == "hero":
            _bar(10, 40, 30, 4, MUTED, 160)
            _bar(10, 48, 40, 12, TEXT, 210)
            for _i in range(3):
                _cell(10 + _i * _cw, 68, 34)
        else:  # standard
            for _i in range(3):
                _cell(10 + _i * _cw, 40, 34)
            _bar(10, 66, 30, 4, MUTED, 160)
            _bar(44, 65, 36, 7, TEXT, 210)
        _bar(10, 94, 3, 8, AMBER, 255, 1)
        _bar(17, 94, W - 44, 6, MUTED, 160)
        _bar(10, 106, 46, 6, MUTED, 160)
        _bar(W - 40, 103, 30, 10, GREEN, 255, 5)
        p.end()


class NavStylePreview(QWidget):
    """Wireframe miniature of one sidebar look (for the settings picker)."""
    def __init__(self, style_key, theme_name="云白", parent=None):
        super().__init__(parent)
        self._key = style_key
        self._theme = theme_name
        self.setFixedHeight(118)
    def set_theme(self, theme_name):
        self._theme = theme_name
        self.update()
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        def _bar(x, y, w, h, color, alpha=255, r=2):
            c = QColor(color); c.setAlpha(alpha)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(c)
            p.drawRoundedRect(QRectF(x, y, w, h), r, r)
        # window + content area
        p.setPen(QPen(QColor(BORDER), 1)); p.setBrush(QColor(BG))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 8, 8)
        sw = 58  # sidebar width in the miniature
        for _i in range(3):
            _bar(sw + 14, 12 + _i * 32, W - sw - 26, 24, PANEL_2, 255, 5)
            _bar(sw + 20, 18 + _i * 32, 26, 4, MUTED, 160)
            _bar(sw + 20, 26 + _i * 32, 38, 6, TEXT, 200)
        if self._key == "dark":
            d = nav_dark_palette(self._theme)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(d["bg"]))
            p.drawRoundedRect(QRectF(5, 5, sw, H - 10), 6, 6)
            _bar(11, 11, 14, 14, d["accent"], 255, 4)
            _bar(29, 14, 24, 5, d["text"], 220)
            _bar(10, 34, sw - 10, 15, d["active"], 255, 4)
            _bar(15, 39, 22, 5, d["text"], 240)
            _bar(15, 56, 26, 5, d["muted"], 200)
            _bar(15, 70, 22, 5, d["muted"], 200)
            _bar(10, H - 30, sw - 10, 18, d["glass"], 255, 5)
        elif self._key == "line":
            p.setPen(QPen(QColor(BORDER), 1)); p.setBrush(QColor(PANEL))
            p.drawRoundedRect(QRectF(5, 5, sw, H - 10), 6, 6)
            _bar(11, 11, 14, 14, ACCENT, 255, 4)
            _bar(29, 14, 24, 5, TEXT, 200)
            _bar(10, 34, sw - 10, 15, ACCENT, 40, 4)
            _bar(10, 36, 2, 11, ACCENT, 255, 1)
            _bar(15, 39, 22, 5, ACCENT, 255)
            _bar(15, 56, 26, 5, MUTED, 170)
            _bar(15, 70, 22, 5, MUTED, 170)
            _bar(10, H - 28, sw - 10, 14, MUTED, 60, 4)
        else:  # capsule
            p.setPen(QPen(QColor(BORDER), 1)); p.setBrush(QColor(BG))
            p.drawRoundedRect(QRectF(5, 5, sw, H - 10), 6, 6)
            _bar(11, 11, 14, 14, ACCENT, 255, 4)
            _bar(29, 14, 24, 5, TEXT, 200)
            p.setPen(QPen(QColor(BORDER), 1)); p.setBrush(QColor(PANEL))
            p.drawRoundedRect(QRectF(9, 31, sw - 8, 40), 7, 7)
            p.drawRoundedRect(QRectF(9, 76, sw - 8, 16), 7, 7)
            _bar(12, 34, sw - 14, 11, ACCENT, 255, 5)
            _bar(17, 37, 20, 5, "#FFFFFF", 255)
            _bar(17, 52, 24, 5, MUTED, 170)
            _bar(17, 61, 18, 5, MUTED, 170)
            _bar(17, 82, 20, 5, MUTED, 170)
        p.end()


class OnceProgressOverlay(QWidget):
    """Transparent face over the patrol button while a patrol runs: icon +
    text + progress in the chosen style. Mouse-transparent, so the button
    still gets clicks and its right-click menu."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._style = "fill"; self._frac = 0.0; self._current = 0; self._total = 0; self._paused = False
        self.hide()
    def set_state(self, style, frac, current, total, paused):
        self._style = style; self._frac = frac; self._current = current; self._total = total; self._paused = paused
        self.update()
    def paintEvent(self, event):
        p = QPainter(self)
        paint_progress_button(p, QRect(0, 12, self.width(), self.height() - 12),
                              self._style, self._frac, self._current, self._total, self._paused, self.font())
        p.end()


class BrandMark(QWidget):
    def __init__(self,size=40,parent=None):
        super().__init__(parent);self.setFixedSize(size,size)
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


_AVATAR_SOURCE_CACHE = {}


def _avatar_source_pixmap(path):
    """Decode an avatar source pixmap once; cache by path+mtime+size (GUI thread only)."""
    if not path:
        return QPixmap()
    try:
        st = Path(str(path)).stat()
        key = (str(path), int(st.st_mtime_ns), int(st.st_size))
    except OSError:
        return QPixmap(str(path))
    pm = _AVATAR_SOURCE_CACHE.get(key)
    if pm is None or pm.isNull():
        pm = QPixmap(str(path))
        if len(_AVATAR_SOURCE_CACHE) > 512:
            _AVATAR_SOURCE_CACHE.clear()
        _AVATAR_SOURCE_CACHE[key] = pm
    return pm


def _avatar_source_cached(path):
    """Lookup only: return the cached pixmap, or None without decoding."""
    if not path:
        return None
    try:
        st = Path(str(path)).stat()
        key = (str(path), int(st.st_mtime_ns), int(st.st_size))
    except OSError:
        return None
    pm = _AVATAR_SOURCE_CACHE.get(key)
    return pm if pm is not None and not pm.isNull() else None


class _AvatarLoadSignals(QObject):
    loaded = pyqtSignal(int, str, object)  # token, path, QImage-or-None


_AVATAR_LOAD_SIGNALS = _AvatarLoadSignals()


class _AvatarLoadTask(QRunnable):
    """Decode an avatar off the GUI thread; QImage is thread-safe, QPixmap is not."""

    def __init__(self, token, path):
        super().__init__()
        self._token = token
        self._path = path

    def run(self):
        try:
            img = QImage(self._path)
            if img.isNull():
                img = None
        except Exception:
            img = None
        _AVATAR_LOAD_SIGNALS.loaded.emit(self._token, self._path, img)


class AvatarWidget(QWidget):
    def __init__(self, name="", path="", size=52, parent=None, page_id=""):
        super().__init__(parent)
        self.name = name or "P"
        self.page_id = page_id
        self.path = resolve_avatar_path(page_id,path)
        self.setFixedSize(size,size)
        self._scaled_cache = None
        self._avatar_token = 0
        self.image = _avatar_source_pixmap(self.path) if self.path else QPixmap()
        if self.image.isNull():
            self.setToolTip("头像与 ID管理共用同一缓存；正常巡检时自动更新。")
        else:
            self.setToolTip("")
        _AVATAR_LOAD_SIGNALS.loaded.connect(self._on_avatar_loaded)

    def set_image(self, name, path):
        """Swap the avatar without blocking the GUI thread on a fresh decode."""
        _new = resolve_avatar_path(self.page_id, path)
        _name = name or "P"
        if _new == self.path and _name == self.name:
            return
        self.name = _name
        self.path = _new
        _cached = _avatar_source_cached(self.path)
        if _cached is not None:
            self.image = _cached
            self._scaled_cache = None
            self.setToolTip("")
            self.update()
            return
        self.image = QPixmap()
        self._scaled_cache = None
        self.setToolTip("头像与 ID管理共用同一缓存；正常巡检时自动更新。")
        self._avatar_token += 1
        if self.path:
            QThreadPool.globalInstance().start(_AvatarLoadTask(self._avatar_token, self.path))
        self.update()

    def _on_avatar_loaded(self, token, path, image):
        if token != self._avatar_token or path != self.path or image is None:
            return
        _pm = QPixmap.fromImage(image)
        if _pm.isNull():
            return
        try:
            _st = Path(path).stat()
            _key = (str(path), int(_st.st_mtime_ns), int(_st.st_size))
            if len(_AVATAR_SOURCE_CACHE) > 512:
                _AVATAR_SOURCE_CACHE.clear()
            _AVATAR_SOURCE_CACHE[_key] = _pm
        except OSError:
            pass
        self.image = _pm
        self._scaled_cache = None
        self.setToolTip("")
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0,0,self.width(),self.height())
        clip = QPainterPath(); clip.addRoundedRect(r.adjusted(1,1,-1,-1), self.width()*.28, self.height()*.28); p.setClipPath(clip)
        if not self.image.isNull():
            # The widget size is fixed, so the smooth-scaled pixmap never
            # changes between paints; rescaling it on every paintEvent
            # was the largest share of resize-drag cost. Scale once.
            if self._scaled_cache is None or self._scaled_cache[0] != self.size():
                scaled = self.image.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                           Qt.TransformationMode.SmoothTransformation)
                self._scaled_cache = (self.size(), scaled)
            scaled = self._scaled_cache[1]
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
        self._hfw_cache={}
        self.setContentsMargins(0,0,0,0)

    def invalidate(self):
        self._hfw_cache.clear()
        super().invalidate()
    def addItem(self,item):self._items.append(item);self._hfw_cache.clear()
    def count(self):return len(self._items)
    def itemAt(self,index):return self._items[index] if 0<=index<len(self._items) else None
    def takeAt(self,index):
        self._hfw_cache.clear()
        return self._items.pop(index) if 0<=index<len(self._items) else None
    def expandingDirections(self):return Qt.Orientation(0)
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):
        # Qt queries heightForWidth several times per layout pass; the
        # result only depends on width + items, so cache it per width.
        if width in self._hfw_cache:
            return self._hfw_cache[width]
        h = self._do_layout(QRect(0,0,width,0),True)
        if len(self._hfw_cache) > 64:
            self._hfw_cache.clear()
        self._hfw_cache[width] = h
        return h
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
        self.value.setProperty("tone",kind)
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
        _tone=self.kind if str(value)!="—" else ""
        if self.value.property("tone")!=_tone:
            self.value.setProperty("tone",_tone)
            self.value.style().unpolish(self.value);self.value.style().polish(self.value)



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

def _growth_delta_objectname(row, delta, is_today):
    """Delta number color, by day: yesterday red, today green.
    No data / monitoring off stays muted. The over-threshold alert
    still shows on the card's left stripe and the 超标 chip."""
    if not row.get("monitor_growth") or delta is None:
        return "GrowthFlat"
    return "GrowthUp" if is_today else "GrowthAlert"


def _page_card_specs(row, post):
    """(label, text, objectname, tip) columns; mirrors PageCard.__init__."""
    today = row.get("today") or {"delta": None, "partial": True, "note": "暂无记录"}
    yesterday = row.get("yesterday") or {"delta": None, "partial": True, "note": "暂无记录"}
    _delta_y_full = format_delta(yesterday["delta"])
    _delta_y_compact = format_delta_compact(yesterday["delta"])
    _delta_y_tip = yesterday.get("note", "")
    if row.get("monitor_growth") and _delta_y_compact != _delta_y_full:
        _delta_y_tip = "实际昨日新增：" + _delta_y_full + (("\n" + _delta_y_tip) if _delta_y_tip else "")
    _delta_full = format_delta(today["delta"])
    _delta_compact = format_delta_compact(today["delta"])
    _delta_tip = today.get("note", "")
    if row.get("monitor_growth") and _delta_compact != _delta_full:
        _delta_tip = "实际今日新增：" + _delta_full + (("\n" + _delta_tip) if _delta_tip else "")
    specs = [
        ("昨日新增", ("未监控" if not row.get("monitor_growth") else
          (("≈" if yesterday.get("approx") else "") + _delta_y_compact)),
         _growth_delta_objectname(row, yesterday.get("delta"), False), _delta_y_tip),
        ("今日新增", ("未监控" if not row.get("monitor_growth") else
          (("≈" if today.get("approx") else "") + _delta_compact)),
         _growth_delta_objectname(row, today.get("delta"), True), _delta_tip),
        ("距上次发帖", post.get("elapsed_short", post["elapsed"]),
         "GrowthDown" if post["state"] == "overdue" else "GrowthSoon" if post["state"] in ("soon", "unknown", "unverified")
         else "GrowthUp" if post["state"] == "ok" else "GrowthFlat", post["tooltip"]),
    ]
    if not row.get("monitor_posts"):
        specs = specs[:2]
    if not row.get("monitor_growth"):
        specs = specs[2:]
    if not specs:
        specs = [("监控状态", "未开启", "GrowthFlat", "")]
    return specs


def _page_card_badges(row, post, checked):
    """(status, state) footer badges; mirrors PageCard.__init__."""
    badges = []
    if not row.get("monitor_growth") and not row.get("monitor_posts"):
        badges = [("未选择模块", "off")]
    elif row.get("diagnosis_code") == "page_unavailable":
        badges = [("主页不可用", "alert")]
    else:
        if row.get("diagnosis_code") == "login":
            badges.append(("需登录验证", "warning"))
        elif post["state"] == "overdue":
            badges.append(("发帖超时", "alert"))
        elif post["state"] == "soon":
            badges.append(("即将超时", "warning"))
        elif row.get("monitor_growth") and row.get("growth_error") and row.get("monitor_posts") and row.get("post_error"):
            badges.append(("读取失败", "alert"))
        elif post["state"] in ("unknown", "unverified"):
            badges.append(("发帖待核实", "warning"))
        elif row.get("monitor_growth") and row.get("growth_error"):
            badges.append(("粉丝读取失败", "warning"))
        elif row.get("monitor_posts") and row.get("post_error"):
            badges.append(("发帖读取失败", "warning"))
        elif not checked:
            badges.append(("待巡检", "off"))
        if row.get("is_growth_alert"):
            badges.append(("增长超标", "good"))
    if not badges:
        badges = [("正常", "normal")]
    return badges


def _diag_stripe_severity(badges):
    """Stripe severity follows badge severity: alert red, warning amber,
    good (growth over threshold only) green, plain diagnostic text grey.
    The color comes from the theme stylesheet (DiagStripe rules), so it
    follows theme switches."""
    states = [state for _, state in badges]
    if "alert" in states:
        return "alert"
    if "warning" in states:
        return "warning"
    if "good" in states:
        return "good"
    return "plain"


def _page_card_diag_text(row):
    """Diagnosis line; mirrors PageCard.__init__."""
    diag_parts = []
    if row.get("monitor_growth") and row.get("growth_error"):
        diag_parts.append("粉丝：" + str(row.get("growth_error"))[:90])
    if row.get("monitor_posts") and row.get("post_error"):
        diag_parts.append("发帖：" + str(row.get("post_error"))[:90])
    if not diag_parts and row.get("diagnosis_detail") and row.get("diagnosis_code") not in ("", "ok"):
        diag_parts.append("诊断：" + str(row.get("diagnosis_detail"))[:110])
    return (row.get("diagnosis_detail") or PAGE_UNAVAILABLE_DETAIL) if row.get("diagnosis_code") == "page_unavailable" else " · ".join(diag_parts)


class PageCard(QFrame):
    open_requested=pyqtSignal(str)
    manage_requested=pyqtSignal(str)
    inspect_requested=pyqtSignal(str)
    sync_requested=pyqtSignal(str)
    delete_requested=pyqtSignal(str)
    def __init__(self,row,rank=0,window_label="",layout_key="oneline"):
        super().__init__();self.row=dict(row);self.setObjectName("PageCard")
        self._layout_key=layout_key if layout_key in CARD_LAYOUT_KEYS else 'oneline'

        self.setMinimumWidth(0);self.setFixedHeight(216)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        pid=str(row["page_id"]);name=display_name(row);post=row.get("post_view") or post_view(row)
        layout=QVBoxLayout(self);layout.setContentsMargins(16,10,16,8);layout.setSpacing(6)
        header=QHBoxLayout();header.setSpacing(9)
        self._avatar=AvatarWidget(name,row.get("avatar_path",""),60,page_id=pid);header.addWidget(self._avatar,0,Qt.AlignmentFlag.AlignTop)
        identity=QVBoxLayout();identity.setSpacing(2)
        title=CopyLabel(name);title.setObjectName("CardTitle");title.setMinimumHeight(22);self._title=title
        title.setToolTip(html.escape("专业名称："+(normalize_name(row.get("page_name"),pid) or name or "尚未获取"))+"\n点击复制名称")
        ident=CopyLabel("ID  "+pid,pid);ident.setObjectName("CardId");ident.setMinimumHeight(18)
        ident.setToolTip("公共主页编号："+pid+"\n点击复制完整 ID")
        identity.addWidget(title);identity.addWidget(ident);header.addLayout(identity,1)
        menu=icon_button("more","主页操作",self,26);menu.setIconSize(QSize(18,18));menu.clicked.connect(self.show_menu)
        header.addWidget(menu,0,Qt.AlignmentFlag.AlignTop);layout.addLayout(header)

        self._build_numbers(row,post,layout)
        diag_parts=[]
        if row.get("monitor_growth") and row.get("growth_error"):diag_parts.append("粉丝："+str(row.get("growth_error"))[:90])
        if row.get("monitor_posts") and row.get("post_error"):diag_parts.append("发帖："+str(row.get("post_error"))[:90])
        if not diag_parts and row.get("diagnosis_detail") and row.get("diagnosis_code") not in ("","ok"):
            diag_parts.append("诊断："+str(row.get("diagnosis_detail"))[:110])
        diag_text=(row.get("diagnosis_detail") or PAGE_UNAVAILABLE_DETAIL) if row.get("diagnosis_code")=="page_unavailable" else " · ".join(diag_parts)
        diag_label=QLineEdit(diag_text);diag_label.setObjectName("DiagLine");diag_label.setReadOnly(True);diag_label.setFrame(False);diag_label.setMinimumHeight(18);diag_label.setCursor(Qt.CursorShape.IBeamCursor);diag_label.setCursorPosition(0);self._diag_label=diag_label
        diag_label.setToolTip(html.escape(diag_text))
        # Parent first, show second: setVisible(True) on a still-parentless
        # label opens it as its own tiny top-level window (the title-bar-only flash).
        diag_row=QWidget();diag_row_layout=QHBoxLayout(diag_row);diag_row_layout.setContentsMargins(0,0,0,0);diag_row_layout.setSpacing(8)
        diag_stripe=QWidget();diag_stripe.setFixedWidth(4);diag_stripe.setObjectName("DiagStripe");diag_stripe.setProperty("severity","plain")
        diag_row_layout.addWidget(diag_stripe);diag_row_layout.addWidget(diag_label,1)
        self._diag_row=diag_row;self._diag_stripe=diag_stripe
        layout.addWidget(diag_row);diag_row.setVisible(bool(diag_text))
        layout.addStretch(1)

        footer=QHBoxLayout();footer.setSpacing(4);self._footer=footer
        checked=row.get("last_inspected_at") or row.get("last_collected_at") or ""
        label=ElideLabel("最近检查 "+local_time_label(checked,False));label.setMinimumHeight(22)
        label.setToolTip(local_time_label(checked));label.setObjectName("SmallMuted");footer.addWidget(label,1);self._checked_label=label
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
            if row.get("is_growth_alert"):badges.append(("增长超标","good"))
        if not badges:badges=[("正常","normal")]
        self._badges=[]
        for status,state in badges:
            badge=QLabel(status);badge.setObjectName("StatusBadge");badge.setProperty("state",state)
            badge.setMinimumHeight(23);badge.setAlignment(Qt.AlignmentFlag.AlignCenter);footer.addWidget(badge);self._badges.append(badge)
        self._diag_stripe.setProperty("severity",_diag_stripe_severity(badges))
        layout.addLayout(footer)

    def _build_numbers(self,row,post,card_layout):
        """Numbers area per the chosen card layout. Sets _spec_heads/_spec_values/_post_value/_fans_value/_fans_holder/_shows_fans."""
        specs=_page_card_specs(row,post)
        self._spec_heads=[];self._spec_values=[];self._post_value=None;self._post_state=post["state"]
        self._fans_value=None;self._fans_holder=None;self._shows_fans=False
        _fans_text=format_compact_count(row.get("last_followers"))
        _fans_tip="实际粉丝数："+format_count(row.get("last_followers"))+("（约值）" if row.get("approx") else "")
        def _cell(label,text,objectname,tip,large=22,head_name="SmallMuted",value_min=28):
            cell=QWidget();col=QVBoxLayout(cell);col.setContentsMargins(0,0,0,0);col.setSpacing(1)
            heading=ElideLabel(label);heading.setMinimumHeight(17);heading.setObjectName(head_name)
            value=ValueLabel(text,large);value.setObjectName(objectname);value.setToolTip(tip);value.setMinimumHeight(value_min)
            col.addWidget(heading);col.addWidget(value)
            return cell,heading,value
        def _specs_into(numbers,large=22,head_name="SmallMuted",value_min=28,weights=None):
            for _i,(label,text,objectname,tip) in enumerate(specs):
                _c,_h,_v=_cell(label,text,objectname,tip,large,head_name,value_min)
                self._spec_heads.append(_h);self._spec_values.append(_v)
                if label=="距上次发帖":self._post_value=_v
                numbers.addWidget(_c,weights[_i] if weights else 1)
        _key=self._layout_key
        if _key=="oneline":
            numbers=QHBoxLayout();numbers.setSpacing(8)
            if row.get("monitor_growth"):
                _fc,_fh,_fv=_cell("当前粉丝",_fans_text,"FansValue",_fans_tip,22,"CardHeadSmall")
                self._fans_value=_fv;self._fans_holder=_fc;self._shows_fans=True
                numbers.addWidget(_fc,1)
            _specs_into(numbers,22,"CardHeadSmall")
            card_layout.addLayout(numbers)
        elif _key=="nofans":
            numbers=QHBoxLayout();numbers.setSpacing(8)
            _specs_into(numbers,22,"SmallMuted",28,(12,11,10))
            card_layout.addLayout(numbers)
        elif _key=="hero":
            box=QWidget();box_lay=QVBoxLayout(box);box_lay.setContentsMargins(0,0,0,0);box_lay.setSpacing(4)
            fans_line=QWidget();fans_lay=QHBoxLayout(fans_line);fans_lay.setContentsMargins(0,0,0,0);fans_lay.setSpacing(4)
            fans_label=QLabel("当前粉丝");fans_label.setObjectName("SmallMuted");fans_label.setMinimumHeight(22)
            fans_value=ValueLabel(_fans_text,28);fans_value.setObjectName("FansValue");fans_value.setToolTip(_fans_tip)
            fans_lay.addWidget(fans_label);fans_lay.addWidget(fans_value,1)
            self._fans_value=fans_value;self._fans_holder=fans_line;self._shows_fans=True
            box_lay.addWidget(fans_line)
            numbers=QHBoxLayout();numbers.setSpacing(8)
            _specs_into(numbers,22,"SmallMuted",28,(12,11,10))
            box_lay.addLayout(numbers)
            card_layout.addWidget(box)
        else:  # standard
            numbers=QHBoxLayout();numbers.setSpacing(8)
            _specs_into(numbers,22,"SmallMuted",28,(12,11,10))
            card_layout.addLayout(numbers)
            fans_row=QWidget();fans_layout=QHBoxLayout(fans_row);fans_layout.setContentsMargins(0,0,0,0);fans_layout.setSpacing(4)
            fans_label=QLabel("当前粉丝");fans_label.setObjectName("SmallMuted");fans_label.setMinimumHeight(22)
            fans_value=QLabel(_fans_text);fans_value.setObjectName("FansValue");fans_value.setMinimumHeight(22)
            fans_value.setToolTip(_fans_tip)
            fans_layout.addWidget(fans_label);fans_layout.addWidget(fans_value,1)
            self._fans_value=fans_value;self._fans_holder=fans_row;self._shows_fans=True
            card_layout.addWidget(fans_row);fans_row.setVisible(bool(row.get("monitor_growth")))

    @property
    def structure_key(self):
        return (bool(self.row.get("monitor_growth")), bool(self.row.get("monitor_posts")), self._layout_key)

    def refresh_values(self, row):
        """Update an existing card in place (card reuse); same output as a fresh PageCard."""
        self.row = dict(row)
        pid = str(row["page_id"])
        name = display_name(row)
        post = row.get("post_view") or post_view(row)
        if self._avatar is not None:
            self._avatar.set_image(name, row.get("avatar_path", ""))
        self._title.setText(name)
        self._title.setToolTip(html.escape("专业名称：" + (normalize_name(row.get("page_name"), pid) or name or "尚未获取")) + "\n点击复制名称")
        for (_label, _text, _obj, _tip), _head, _val in zip(_page_card_specs(row, post), self._spec_heads, self._spec_values):
            _head.setText(_label)
            _val.setText(_text)
            if _val.objectName() != _obj:
                _val.setObjectName(_obj)
                _val.style().unpolish(_val)
                _val.style().polish(_val)
            _val.setToolTip(_tip)
        if self._fans_value is not None:
            self._fans_value.setText(format_compact_count(row.get("last_followers")))
            self._fans_value.setToolTip("实际粉丝数：" + format_count(row.get("last_followers")) + ("（约值）" if row.get("approx") else ""))
        if self._fans_holder is not None:
            self._fans_holder.setVisible(bool(row.get("monitor_growth")) and self._shows_fans)
        _diag = _page_card_diag_text(row)
        self._diag_label.setText(_diag)
        self._diag_label.setCursorPosition(0)
        self._diag_label.setToolTip(html.escape(_diag))
        self._diag_row.setVisible(bool(_diag))
        checked = row.get("last_inspected_at") or row.get("last_collected_at") or ""
        self._checked_label.setText("最近检查 " + local_time_label(checked, False))
        self._checked_label.setToolTip(local_time_label(checked))
        for _b in self._badges:
            _b.hide()
            _b.deleteLater()
        self._badges = []
        _new_badges = _page_card_badges(row, post, checked)
        self._diag_stripe.setProperty("severity", _diag_stripe_severity(_new_badges))
        self._diag_stripe.style().unpolish(self._diag_stripe)
        self._diag_stripe.style().polish(self._diag_stripe)
        for _status, _state in _new_badges:
            badge = QLabel(_status)
            badge.setObjectName("StatusBadge")
            badge.setProperty("state", _state)
            badge.setMinimumHeight(23)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._footer.addWidget(badge)
            self._badges.append(badge)
        self._post_state = post["state"]
        self.update()

    def refresh_clock(self, now, interval):
        """Update only the time-driven post text. True = post state changed, full refresh needed."""
        if self._post_value is None:
            return False
        post = post_view(self.row, now, interval)
        if post["state"] != self._post_state:
            return True
        self._post_value.setText(post.get("elapsed_short", post["elapsed"]))
        self._post_value.setToolTip(post["tooltip"])
        return False

    def mouseDoubleClickEvent(self,event):
        self.manage_requested.emit(self.row["page_id"]);event.accept()

    def show_menu(self):
        pid=self.row["page_id"]
        menu=QMenu(self)
        menu.addAction("编辑监控模块 / 发帖标准",lambda:self.manage_requested.emit(pid))
        menu.addAction("仅巡检本主页",lambda:self.inspect_requested.emit(pid))
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
        self.cards=[];self.columns=0;self._last_reflow_visible=False
    def set_cards(self,cards):
        while self.grid.count():
            item=self.grid.takeAt(0)
            if item.widget():
                # Hide first: deleteLater() only runs on the next event-loop
                # turn, and a stale card left visible would paint over the
                # new one until then.
                item.widget().hide();item.widget().deleteLater()
        self.cards=list(cards);self.columns=0;self.reflow()
    def arrange(self,cards):
        """Lay out cards in order without deleting any (card reuse)."""
        while self.grid.count():
            item=self.grid.takeAt(0)
            if item.widget():item.widget().hide()
        self.cards=list(cards);self.columns=0;self.reflow()

    def reflow(self):
        available=max(220,self.width()-4)
        columns=max(1,min(6,int((available+10)//(255+10))))
        _was_visible=self._last_reflow_visible
        self._last_reflow_visible=self.isVisible()
        if columns==self.columns:return
        if self.columns and _was_visible:
            # Hysteresis: don't flip the column count back and forth
            # while a drag hovers on a threshold; require 30px beyond it.
            # A reflow that follows a hidden one (startup, page return) is
            # not a drag: it takes the computed count outright, so the
            # first visible layout can never get stuck one band below a
            # threshold the way a slow drag can.
            if columns>self.columns and available<(265*columns-10)+30:return
            if columns<self.columns and available>=(265*self.columns-10)-30:return
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
        super().__init__(parent)
        # Fixed card, not a movable window: no title bar to drag, no
        # close (X) and no minimise. The only way out is the bottom
        # 取消 / 确认导入 buttons. Applies in the tour and in normal use.
        self.setObjectName("BatchAddDialog")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QDialog#BatchAddDialog{background:%s;border:1px solid %s;border-radius:16px;}" % (PANEL, BORDER))
        self.setWindowTitle("添加专业 ID");self.resize(620,600)
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
        self._preview_timer=QTimer(self);self._preview_timer.setSingleShot(True);self._preview_timer.timeout.connect(self.update_preview)
        self.edit.textChanged.connect(lambda:self._preview_timer.start(300));self.update_preview()
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
    An unread growth alert from today also counts (via is_growth_alert
    in refresh); an unread alert from a previous day does not.
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
    - growth_alert: unread growth alert from today for the page, or
      today's accumulated growth (今日新增) reaching the existing threshold
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
             or bool(posts_on and row.get("post_error")))
    needs = bool(pending_review or uncertain or other) and not overdue
    return (growth, overdue, needs)


TOUR_DONE_KEY = "tour/done_1_7_2"


class TourWelcomeCard(QWidget):
    """The tour's first screen, as a fixed card inside the main window
    (not a separate window): no close button, no minimise, cannot be
    dragged -- the user only chooses 跳过 or 开始新手引导."""
    skip_requested = pyqtSignal()
    start_requested = pyqtSignal()

    def __init__(self, parent, main):
        super().__init__(parent)
        self.setObjectName("TourWelcomeCard")
        self.setFixedWidth(520)
        # A plain QWidget only paints its stylesheet background when
        # WA_StyledBackground is set; without it the card stays transparent.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Scope the card style to the card itself only (#id selector):
        # an unscoped background/border would leak onto every child
        # label and button and turn each of them into a white pill.
        self.setStyleSheet("#TourWelcomeCard{background:#FFFFFF;border:1px solid #E8E8E3;border-radius:16px;}")
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(12)
        icon = main.windowIcon()
        if not icon.isNull():
            lab = QLabel()
            lab.setPixmap(icon.pixmap(46, 46))
            root.addWidget(lab)
        title = QLabel("你是第一次使用吗？")
        title.setObjectName("DialogTitle")
        root.addWidget(title)
        body = QLabel("第一次用的话，我带你走一遍：先装浏览器连接器、加主页，设好自动巡检时间，再跑一轮巡检，最后看一眼提醒。几分钟就学会，不用看说明书。")
        body.setWordWrap(True)
        root.addWidget(body)
        root.addStretch()
        actions = QHBoxLayout()
        actions.addStretch()
        skip = QPushButton("跳过")
        skip.clicked.connect(self.skip_requested.emit)
        actions.addWidget(skip)
        start = QPushButton("开始新手引导")
        start.setObjectName("PrimaryButton")
        start.clicked.connect(self.start_requested.emit)
        actions.addWidget(start)
        root.addLayout(actions)
        self.hide()



class TourRingOverlay(QWidget):
    """Amber ring only, drawn over a dialog step's target. Fully
    click-through (WA_TransparentForMouseEvents) and never dims: the
    dialog stays bright and fully usable, the ring just points at the
    control the step is about."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._target = QRect()
        self.hide()

    def show_target(self, rect):
        self._target = QRect(rect)
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, event):
        if not self._target.isValid():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(245, 158, 11, 64), 7))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self._target.adjusted(-3, -3, 3, 3), 10, 10)
        p.setPen(QPen(QColor("#F59E0B"), 3))
        p.drawRoundedRect(self._target, 10, 10)


class TourOverlay(QWidget):
    """Spotlight overlay for the onboarding tour.

    A child of the main window (or of the dialog a step opens), so it only
    ever covers the app itself -- never the whole screen. It dims everything
    except the highlighted target, which stays fully clickable: the overlay
    mask cuts a hole at the target, so the user can click the highlighted
    control to actually use it, then advance with 下一步. Clicks on the
    dimmed area are swallowed; the bubble stays clickable.
    """
    next_requested = pyqtSignal()
    prev_requested = pyqtSignal()
    skip_requested = pyqtSignal()
    done_requested = pyqtSignal()

    def __init__(self, main):
        super().__init__(main)
        self._main = main
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._targets = []
        self._target = QRect()
        self._has_target = False
        self._is_last = False
        self._dialog = None
        self._ring = None
        self._welcome = TourWelcomeCard(self, main)
        self._bubble = QWidget(self)
        self._bubble.setStyleSheet("background:#FFFFFF;border:1px solid #E8E8E3;border-radius:12px;")
        bl = QVBoxLayout(self._bubble)
        bl.setContentsMargins(16, 14, 16, 14)
        bl.setSpacing(6)
        self._step_lab = QLabel()
        self._step_lab.setStyleSheet("color:#1D4ED8;font-size:11.5px;font-weight:bold;border:none;")
        bl.addWidget(self._step_lab)
        self._title_lab = QLabel()
        self._title_lab.setStyleSheet("font-size:15.5px;font-weight:bold;border:none;")
        bl.addWidget(self._title_lab)
        self._body_lab = QLabel()
        self._body_lab.setWordWrap(True)
        self._body_lab.setStyleSheet("font-size:13px;color:#3A3A3A;border:none;")
        bl.addWidget(self._body_lab)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._skip_btn = QPushButton("跳过引导")
        self._skip_btn.setStyleSheet("color:#6E6E6E;border:none;font-size:12.5px;")
        self._skip_btn.clicked.connect(self.skip_requested.emit)
        btns.addWidget(self._skip_btn)
        btns.addStretch()
        self._prev_btn = QPushButton("上一步")
        self._prev_btn.clicked.connect(self.prev_requested.emit)
        btns.addWidget(self._prev_btn)
        self._next_btn = QPushButton("下一步")
        self._next_btn.setStyleSheet("background:#1D4ED8;color:#FFFFFF;border:none;border-radius:8px;padding:8px 16px;font-size:13px;")
        self._next_btn.clicked.connect(self._on_next_clicked)
        btns.addWidget(self._next_btn)
        bl.addLayout(btns)
        self._bubble.setFixedWidth(320)
        self._bubble.hide()
        self.hide()

    def _on_next_clicked(self):
        if self._is_last:
            self.done_requested.emit()
        else:
            self.next_requested.emit()

    def _window_control_rects(self):
        # Only the three window buttons (minimise / maximise / close) in
        # overlay coordinates. Everything else in the top bar -- page
        # title, 立即巡检, 启用自动巡检 -- is dimmed and blocked like
        # the rest of the window.
        if not hasattr(self, "_win_ctl_btns"):
            self._win_ctl_btns = []
            for name in ("最小化", "最大化", "关闭"):
                for b in self._main.findChildren(QPushButton):
                    if b.accessibleName() == name:
                        self._win_ctl_btns.append(b)
                        break
        rects = []
        for b in self._win_ctl_btns:
            try:
                if b.isVisible():
                    rects.append(QRect(b.mapTo(self._main, QPoint(0, 0)), b.rect().size()))
            except Exception:
                pass
        return rects

    def show_welcome(self):
        """Dim the main window and show the fixed welcome card, centred."""
        self._set_overlay_parent(self._main)
        self._dialog = None
        self._has_target = False
        self._target = QRect()
        if self._ring is not None:
            self._ring.hide()
        self._bubble.hide()
        self._welcome.adjustSize()
        w, h = self._welcome.width(), self._welcome.height()
        self._welcome.move((self.width() - w) // 2, (self.height() - h) // 2)
        self._update_mask()
        self._welcome.show()
        self._welcome.raise_()
        self.show()
        self.raise_()
        self.update()

    def hide_welcome(self):
        self._welcome.hide()

    def _parent_for(self, targets):
        # The top-level window holding the first target; the overlay lives
        # there so it can cover a dialog step too.
        for w in targets:
            if w is not None:
                top = w.window()
                if top is not None:
                    return top
        return self._main

    def _set_overlay_parent(self, parent):
        old = self.parentWidget()
        if old is not None and old is not parent:
            try:
                old.removeEventFilter(self)
            except Exception:
                pass
        if self.parentWidget() is not parent:
            self.setParent(parent)
        try:
            parent.installEventFilter(self)
        except Exception:
            pass
        self.setGeometry(parent.rect())

    def _position_dialog_right(self):
        # Shift the dialog right so its left edge clears the bubble that
        # sits on the left (margin 16 + bubble 320 + gap 24 = 360). The
        # dialog is a top-level window, so move it in screen coordinates.
        dlg = self._dialog
        main = self._main
        dw, dh = dlg.width(), dlg.height()
        W, H = main.width(), main.height()
        left_needed = 16 + 320 + 24
        cx = (W - dw) // 2
        cy = (H - dh) // 2
        left = max(cx, left_needed)
        left = max(16, min(left, max(16, W - dw - 16)))
        top = max(16, min(cy, max(16, H - dh - 16)))
        dlg.move(main.mapToGlobal(QPoint(left, top)))

    def _dialog_target_rect(self):
        # Union of the target widgets, in the dialog's coordinates.
        rect = None
        if self._dialog is None:
            return None
        for w in self._targets:
            if w is None:
                continue
            try:
                r = QRect(w.mapTo(self._dialog, QPoint(0, 0)), w.rect().size())
            except Exception:
                continue
            rect = r if rect is None else rect.united(r)
        return rect

    def _target_rect(self):
        # Union of the target widgets, in overlay (== parent) coordinates.
        rect = None
        parent = self.parentWidget()
        if parent is None:
            return None
        for w in self._targets:
            if w is None:
                continue
            try:
                r = QRect(w.mapTo(parent, QPoint(0, 0)), w.rect().size())
            except Exception:
                continue
            rect = r if rect is None else rect.united(r)
        return rect

    def show_step(self, targets, step_no, total, title, text, has_prev, is_last):
        if isinstance(targets, QWidget):
            targets = [targets]
        self._targets = [w for w in (targets or []) if w is not None]
        # Dialog step: the target lives in a dialog, not in the main
        # window. Dim + block the main window only; the dialog stays
        # bright and fully clickable, with just a ring on the target.
        top = self._parent_for(self._targets)
        self._dialog = top if (top is not None and top is not self._main) else None
        self._set_overlay_parent(self._main)
        if self._dialog is not None:
            self._has_target = False
            self._target = QRect()
            self._position_dialog_right()
            if self._ring is None or self._ring.parentWidget() is not self._dialog:
                self._ring = TourRingOverlay(self._dialog)
            drect = self._dialog_target_rect()
            if drect is not None:
                self._ring.show_target(drect)
        else:
            if self._ring is not None:
                self._ring.hide()
            self._has_target = bool(self._targets)
            self._target = self._target_rect() or QRect()
        self._is_last = bool(is_last)
        self._step_lab.setText("第 %d 步 / 共 %d 步" % (step_no, total))
        self._title_lab.setText(title)
        self._body_lab.setText(text)
        self._prev_btn.setVisible(bool(has_prev))
        self._next_btn.setText("完成" if is_last else "下一步")
        self._skip_btn.setVisible(not is_last)
        # Size the bubble from the wrapped body text: a word-wrapped label
        # reports a wrong sizeHint before it is laid out, so measure the
        # text explicitly and give the label that minimum height.
        fm = self._body_lab.fontMetrics()
        avail = 320 - 32
        need = fm.boundingRect(0, 0, avail, 100000, Qt.TextFlag.TextWordWrap, text).height()
        self._body_lab.setMinimumHeight(need)
        self._bubble.adjustSize()
        self._place_bubble()
        self._update_mask()
        self._bubble.show()
        self.show()
        self.raise_()
        self.update()

    def _place_bubble_dialog(self):
        # Bubble on the left, clear of the dialog (the dialog was shifted
        # right so its left edge is at least 360). Align with the target's
        # height so it sits next to what the step is about.
        bw = 320
        bh = self._bubble.height()
        W, H = self.width(), self.height()
        t = None
        for w in self._targets:
            if w is None:
                continue
            try:
                r = QRect(w.mapTo(self._main, QPoint(0, 0)), w.rect().size())
            except Exception:
                continue
            t = r if t is None else t.united(r)
        y = t.top() if t is not None else (H - bh) // 2
        y = max(0, min(int(y), max(0, H - bh)))
        self._bubble.move(16, int(y))
        self._bubble.resize(bw, int(bh))

    def _update_mask(self):
        # Dialog mode: the target lives in the dialog, so the main-window
        # dim has no hole -- it blocks the whole main window, and the
        # bubble stays clickable. Main-window mode: click-through hole at
        # the target (inset keeps the amber ring itself inside the mask,
        # so it stays painted and visible). In every mode the main
        # window's own title bar is cut out, so minimise / maximise /
        # close keep working.
        region = QRegion(self.rect())
        for cr in self._window_control_rects():
            region = region.subtracted(QRegion(cr))
        if self._dialog is None and self._has_target and self._target.isValid():
            region = region.subtracted(QRegion(self._target.adjusted(2, 2, -2, -2)))
        region = region.united(QRegion(self._bubble.geometry()))
        if self._welcome.isVisible():
            region = region.united(QRegion(self._welcome.geometry()))
        self.setMask(region)

    def _place_bubble(self):
        # Dialog step: the bubble lives in the main window, outside the
        # dialog (the dialog would cover it), next to the target's height.
        if self._dialog is not None:
            self._place_bubble_dialog()
            return
        # Pick the placement whose (clamped) rect overlaps the highlighted
        # target least, so the bubble never sits on top of the control the
        # user needs to click. Right/left/below/above first, then the
        # corners, then centred.
        bw = 320
        bh = self._bubble.height()
        W, H = self.width(), self.height()
        if self._has_target:
            t = self._target
            cands = [
                (t.right() + 16, t.top()),
                (t.left() - bw - 16, t.top()),
                (t.left(), t.bottom() + 16),
                (t.left(), t.top() - bh - 16),
                (max(0, min(t.left(), W - bw)), max(0, H - bh - 12)),
                (max(0, min(t.left(), W - bw)), 0),
                ((W - bw) // 2, (H - bh) // 2),
            ]
        else:
            cands = [((W - bw) // 2, (H - bh) // 2)]
        best = None
        best_score = None
        for x, y in cands:
            x = max(0, min(int(x), max(0, W - bw)))
            y = max(0, min(int(y), max(0, H - bh)))
            r = QRect(x, y, bw, int(bh))
            overlap = 0
            if self._has_target:
                inter = r.intersected(self._target)
                if inter.isValid():
                    overlap = inter.width() * inter.height()
            if best_score is None or overlap < best_score:
                best_score = overlap
                best = r
        self._bubble.move(best.topLeft())
        self._bubble.resize(bw, int(bh))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ctl = self._window_control_rects()
        if self._dialog is not None:
            # Plain full dim, except the three window buttons stay bright:
            # the ring lives in the dialog, not here.
            path = QPainterPath()
            path.setFillRule(Qt.FillRule.OddEvenFill)
            path.addRect(QRectF(self.rect()))
            for cr in ctl:
                path.addRect(QRectF(cr))
            p.fillPath(path, QColor(15, 15, 15, 140))
            return
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addRect(QRectF(self.rect()))
        for cr in ctl:
            path.addRect(QRectF(cr))
        if self._has_target:
            path.addRoundedRect(QRectF(self._target), 10, 10)
        p.fillPath(path, QColor(15, 15, 15, 140))
        if self._has_target:
            p.setPen(QPen(QColor(245, 158, 11, 64), 7))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(self._target.adjusted(-3, -3, 3, 3), 10, 10)
            p.setPen(QPen(QColor("#F59E0B"), 3))
            p.drawRoundedRect(self._target, 10, 10)

    def mousePressEvent(self, event):
        # Swallow clicks on the dimmed area. Clicks on the target never
        # reach us (the mask cuts a hole there); the bubble handles itself.
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            if self._welcome.isVisible():
                w, h = self._welcome.width(), self._welcome.height()
                self._welcome.move((self.width() - w) // 2, (self.height() - h) // 2)
            if self._dialog is not None:
                drect = self._dialog_target_rect()
                if drect is not None and self._ring is not None:
                    self._ring.show_target(drect)
            else:
                self._target = self._target_rect() or QRect()
            self._place_bubble()
            self._update_mask()
            self.update()

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parentWidget().rect())
            if self.isVisible():
                self._target = self._target_rect() or QRect()
                self._place_bubble()
                self._update_mask()
                self.update()
        return super().eventFilter(watched, event)



class OnboardingTour(QObject):
    """Seven-step guided tour. Each step prepares its context (page/tab/
    dialog) and returns the target widget(s); the overlay highlights them
    and leaves them clickable, so the user can use the control and then
    advance with 下一步."""
    def __init__(self, main):
        super().__init__(main)
        self._main = main
        self._overlay = TourOverlay(main)
        self._overlay.next_requested.connect(self.next_step)
        self._overlay.prev_requested.connect(self.prev_step)
        self._overlay.skip_requested.connect(self.stop)
        self._overlay.done_requested.connect(self.stop)
        self._overlay._welcome.skip_requested.connect(self._on_welcome_skip)
        self._overlay._welcome.start_requested.connect(self._on_welcome_start)
        self._idx = -1
        self._dlg = None
        self._tour_closing_dialog = False
        self._steps = [
            {"key": "connector", "title": "先装浏览器连接器",
             "text": "点「获取连接器」，按提示在 Chrome 里加载好，软件才能读到主页。软件里导出的插件和发布包里附带是一样的，装一个地方的就行，不用两边都装。",
             "prepare": self._prep_connector},
            {"key": "idman", "title": "去 ID 管理加主页",
             "text": "点左边这个「ID管理」，准备加要监控的主页。",
             "prepare": self._prep_idman},
            {"key": "paste", "title": "粘贴主页 ID",
             "text": "把主页 ID 粘贴到这个框里，一行一个，点「确认导入」。一次可以粘贴很多个。",
             "prepare": self._prep_paste},
            {"key": "modules", "title": "选要监测什么",
             "text": "只看粉丝增长，还是连发帖时间一起盯？点一个，点「确定」。以后随时能在设置里改。",
             "prepare": self._prep_modules},
            {"key": "time", "title": "设自动巡检隔多久跑一轮",
             "text": "在这里改「每轮间隔」，建议 180 分钟以上。太短容易被 Facebook 临时限制，被限制的那个浏览器读不到主页。这个时间你自己改，改完自动保存。",
             "prepare": self._prep_time},
            {"key": "patrol", "title": "选一种巡检方式",
             "text": "想现在就跑一轮，点「立即巡检」；想以后按时间自动跑，点「启用自动巡检」。选一个就行，不用两个都点，两个都点会跑两轮。",
             "prepare": self._prep_patrol},
            {"key": "alerts", "title": "看提醒",
             "text": "有超标或超时，这里会提醒你：点「通知」看全部历史，左侧「最近预警」和卡片上的徽章也能看到。引导完了，开始用吧。",
             "prepare": self._prep_alerts},
        ]

    def show_welcome(self):
        self._overlay.show_welcome()

    def _mark_tour_done(self):
        try:
            self._main.settings.setValue(TOUR_DONE_KEY, 1)
            self._main.settings.sync()
        except Exception:
            pass

    def _on_welcome_skip(self):
        self._overlay.hide_welcome()
        self._overlay.hide()
        self._mark_tour_done()

    def _on_welcome_start(self):
        self._overlay.hide_welcome()
        self._mark_tour_done()
        self.start()

    def start(self):
        self._idx = 0
        self._show_current()

    def stop(self):
        self._close_step_dialog()
        self._overlay.hide_welcome()
        self._overlay.hide()
        if self._overlay._ring is not None:
            self._overlay._ring.hide()
        self._idx = -1

    def next_step(self):
        self._close_step_dialog()
        self._idx += 1
        if self._idx >= len(self._steps):
            self.stop()
            return
        self._show_current()

    def prev_step(self):
        self._close_step_dialog()
        self._idx = max(0, self._idx - 1)
        self._show_current()

    def _close_step_dialog(self):
        if self._dlg is not None:
            # Guard: closing it here fires its finished signal; the tour
            # itself is moving, so the handler must not advance again.
            self._tour_closing_dialog = True
            try:
                self._dlg.close()
            except Exception:
                pass
            self._tour_closing_dialog = False
            self._dlg = None

    def _on_step_dialog_finished(self, result):
        # The user dismissed the step's dialog (confirm / cancel / X).
        # That counts as finishing the step: move on by itself.
        if self._tour_closing_dialog:
            return
        if self._idx < 0 or self._idx >= len(self._steps):
            return
        if self._dlg is None:
            return
        self._dlg = None
        self.next_step()

    def _show_current(self):
        step = self._steps[self._idx]
        try:
            targets = step["prepare"]()
        except Exception:
            targets = None
        QApplication.processEvents()
        self._overlay.show_step(targets, self._idx + 1, len(self._steps),
                                step["title"], step["text"],
                                self._idx > 0, self._idx == len(self._steps) - 1)

    def _prep_connector(self):
        m = self._main
        m.switch_page(4)
        m.settings_page.settings_tabs.setCurrentIndex(2)
        QApplication.processEvents()
        return m.settings_page.connector_package_button

    def _prep_idman(self):
        m = self._main
        m.switch_page(0)
        QApplication.processEvents()
        return m.page_nav_buttons.get(3)

    def _prep_paste(self):
        m = self._main
        dlg = BatchAddDialog(m, growth_enabled=modules_growth_enabled(m.settings),
                             posts_enabled=modules_posts_enabled(m.settings))
        self._dlg = dlg
        dlg.finished.connect(self._on_step_dialog_finished)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        QApplication.processEvents()
        return dlg.edit

    def _prep_modules(self):
        m = self._main
        dlg = FirstRunDialog(m)
        self._dlg = dlg
        dlg.finished.connect(self._on_step_dialog_finished)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        QApplication.processEvents()
        return [dlg.opt_growth, dlg.opt_both]

    def _prep_time(self):
        m = self._main
        m.switch_page(4)
        m.settings_page.settings_tabs.setCurrentIndex(3)
        QApplication.processEvents()
        return m.settings_page.interval

    def _prep_patrol(self):
        m = self._main
        m.switch_page(0)
        QApplication.processEvents()
        return [m.dashboard.once_btn, m.dashboard.auto_btn]

    def _prep_alerts(self):
        m = self._main
        m.switch_page(0)
        QApplication.processEvents()
        return m.page_nav_buttons.get(2)



class DashboardPage(QWidget):
    collect_once=pyqtSignal()
    collect_subset_requested=pyqtSignal(str)
    cancel_patrol_requested=pyqtSignal()
    grace_cancel_requested=pyqtSignal()
    inspect_page=pyqtSignal(str)
    inspect_requested=pyqtSignal(list)
    sync_page=pyqtSignal(str)
    toggle_auto=pyqtSignal()
    view_alerts=pyqtSignal()
    open_manager=pyqtSignal(str)
    open_page=pyqtSignal(str)
    open_settings_requested=pyqtSignal()
    delete_page=pyqtSignal(str)

    def __init__(self,store,settings):
        super().__init__();self.setObjectName("DashboardPage");self.store=store;self.settings=settings
        self.paused=False;self._active=False;self._auto=False;self._card_cache={};self._empty_frame=None
        _ps=str(self.settings.value("progress_style","fill") or "fill")
        self._prog_style=_ps if _ps in PROGRESS_BUTTON_WIDTHS else "fill";self._prog_current=0;self._prog_total=0
        _cl=str(self.settings.value("card_layout","oneline") or "oneline")
        self._card_layout=_cl if _cl in CARD_LAYOUT_KEYS else 'oneline'

        self.build_ui();self.refresh()

    def build_ui(self):
        root=QVBoxLayout(self);root.setContentsMargins(20,16,20,10);root.setSpacing(12)
        self.action_bar=QWidget();action_lay=QHBoxLayout(self.action_bar);action_lay.setContentsMargins(0,0,0,0);action_lay.setSpacing(10)
        self.run_badge=QLabel("上次巡检时间：—");self.run_badge.setObjectName("RunBadge");action_lay.addWidget(self.run_badge)
        self.once_btn=QPushButton("立即巡检");self.once_btn.setIcon(ui_icon("play","#FFFFFF"))
        self.once_btn.setIconSize(QSize(16,16));self.once_btn.setObjectName("PrimaryButton");self.once_btn.setFixedSize(140,40)
        self._once_menu=QMenu(self.once_btn)
        self._once_menu.addAction("仅巡检失败主页",lambda:self.collect_subset_requested.emit("failed"))
        self._once_menu.addAction("仅巡检未巡检主页",lambda:self.collect_subset_requested.emit("uninspected"))
        self._once_menu.addSeparator()
        self._once_cancel_action=self._once_menu.addAction("取消当前巡检",lambda:self.cancel_patrol_requested.emit())
        self._once_cancel_action.setVisible(False)
        self.once_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.once_btn.customContextMenuRequested.connect(lambda _pos: self._once_menu.popup(self.once_btn.mapToGlobal(QPoint(0, self.once_btn.height()))))
        self.once_btn.clicked.connect(self.collect_once.emit);action_lay.addWidget(self.once_btn)
        self._grace_remaining=0
        self._grace_cancel_btn=QPushButton("取消");self._grace_cancel_btn.setObjectName("SecondaryButton");self._grace_cancel_btn.setFixedSize(72,40);self._grace_cancel_btn.setVisible(False)
        self._grace_cancel_btn.clicked.connect(self.grace_cancel_requested.emit);action_lay.addWidget(self._grace_cancel_btn)
        self._once_overlay=OnceProgressOverlay(self.action_bar)
        self.once_btn.installEventFilter(self);self._sync_once_overlay()
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
        self.metric_yesterday=MetricCard("昨日新增",RED,"history")
        self.metric_today=MetricCard("今日新增数",GREEN,"bell")
        self.metric_today.badge_clicked.connect(lambda:self._set_filter_mode("needs"))
        for metric in (self.metric_pages,self.metric_total,self.metric_yesterday,self.metric_today):metrics.addWidget(metric,1)
        root.addLayout(metrics)
        toolbar=QHBoxLayout();toolbar.setSpacing(8)
        self.search=QLineEdit();self.search.setPlaceholderText("搜索名称 / 专业 ID");self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(150);self.search.setMaximumWidth(300);self.search.setFixedHeight(36)
        self.search.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.search.textChanged.connect(lambda _:self._on_search_changed())
        toolbar.addWidget(self.search,0,Qt.AlignmentFlag.AlignTop)
        self._chip_row=ChipRow()
        self._filter_chips={}
        for name,mode in (("全部","all"),("粉丝监控","growth"),("发帖监控","posts"),("发帖超时","post_overdue"),("粉丝增长超标","growth_alert"),("需处理","needs")):
            chip=BadgeButton(name) if mode in ("needs","post_overdue","growth_alert") else QPushButton(name)
            chip.setObjectName("FilterChip");chip.setFixedHeight(30)
            if mode in ("needs","post_overdue","growth_alert"):chip.setMinimumWidth(chip.sizeHint().width()+20)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False,m=mode:self._set_filter_mode(m))
            chip.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            chip.customContextMenuRequested.connect(lambda pos,m=mode:self._on_chip_context_menu(m,pos))
            if mode=="growth_alert":chip.badge.setProperty("tone","good")
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

    def _on_search_changed(self):
        # Typing must not rebuild all cards per keystroke: wait until
        # input settles, then refresh once.
        if not hasattr(self, "_search_timer"):
            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.timeout.connect(self.refresh)
        self._search_timer.start(300)

    def filter_mode(self):
        return getattr(self,"_filter_mode","all")

    def _apply_filter_chips(self):
        posts_on=modules_posts_enabled(self.settings)
        growth_on=modules_growth_enabled(self.settings)
        _counts=getattr(self,"_chip_counts",None) or {}
        _all_dual=getattr(self,"_all_pages_dual",False)
        if getattr(self,"_filter_mode","all")=="needs" and _counts.get("needs",1)==0:self._filter_mode="all"
        if getattr(self,"_filter_mode","all")=="growth_alert" and _counts.get("growth_alert",1)==0:self._filter_mode="all"
        if not posts_on and getattr(self,"_filter_mode","all") in ("posts","post_overdue"):self._filter_mode="all"
        if not growth_on and getattr(self,"_filter_mode","all")=="growth_alert":self._filter_mode="all"
        if _all_dual and getattr(self,"_filter_mode","all") in ("growth","posts"):self._filter_mode="all"
        for mode,chip in self._filter_chips.items():
            if mode=="growth":visible=not _all_dual
            elif mode=="posts":visible=posts_on and not _all_dual
            elif mode=="post_overdue":visible=posts_on
            elif mode=="growth_alert":visible=growth_on and _counts.get("growth_alert",1)>0
            elif mode=="needs":visible=_counts.get("needs",1)>0
            else:visible=True
            chip.setVisible(visible)
            chip.setProperty("active",mode==self._filter_mode);chip.style().unpolish(chip);chip.style().polish(chip)

    def filter_ids(self,mode):
        """Page ids in one filter chip's scope, from the last refresh."""
        rows=getattr(self,"_last_rows",None) or []
        if mode=="growth":return [str(r["page_id"]) for r in rows if r.get("monitor_growth")]
        if mode=="posts":return [str(r["page_id"]) for r in rows if r.get("monitor_posts")]
        if mode=="needs":return [str(r["page_id"]) for r in rows if r.get("needs_attention")]
        if mode=="post_overdue":return [str(r["page_id"]) for r in rows if r.get("is_post_overdue")]
        if mode=="growth_alert":return [str(r["page_id"]) for r in rows if r.get("cat_growth")]
        return [str(r["page_id"]) for r in rows]

    def _on_chip_context_menu(self,mode,pos):
        ids=self.filter_ids(mode)
        if not ids:return
        _label="巡检全部主页" if mode=="all" else "巡检此类主页"
        menu=QMenu(self)
        menu.addAction(f"{_label}（{len(ids)} 个）",lambda:self.inspect_requested.emit(ids))
        chip=self._filter_chips.get(mode)
        menu.popup(chip.mapToGlobal(pos) if chip is not None else self.mapToGlobal(pos))

    def _set_filter_mode(self,mode):
        self._filter_mode=mode;self._apply_filter_chips();self._remember_view();self.refresh()

    def _on_sort_changed(self):
        self._sort_mode=self.sort_box.currentData();self._remember_view();self.refresh()

    def _refresh_auto_tooltip(self):
        # Floating tooltip on the auto-inspection button: current settings
        # only, read live from settings so a change in Settings shows up
        # on the next refresh without reopening anything. The jitter range
        # rides on the interval line itself (no separate line, no title).
        vals=getattr(self,"_timing_values",None) or random_inspection_timing(self.settings)
        self.auto_btn.setToolTip(
            f"每轮间隔：{vals[0]} 分钟（±{vals[1]}–{vals[2]}分钟）\n"
            "如需修改巡检参数，请前往设置中修改。")

    def set_timing_values(self,minutes,j0,j1,g0,g1):
        self._timing_values=(minutes,j0,j1,g0,g1)
        self._refresh_auto_tooltip()

    def _remember_view(self,*_):
        self.settings.setValue("dashboard/sort",getattr(self,"_sort_mode","growth"))
        self.settings.setValue("dashboard/filter",self._filter_mode)
        self.settings.setValue("dashboard/search",self.search.text())
        self.settings.sync()


    def eventFilter(self,obj,event):
        if obj is self.once_btn and event.type() in (QEvent.Type.Move,QEvent.Type.Resize,QEvent.Type.Show):
            self._sync_once_overlay()
        return super().eventFilter(obj,event)

    def _sync_once_overlay(self):
        if not hasattr(self,"_once_overlay"):return
        g=self.once_btn.geometry()
        self._once_overlay.setGeometry(g.x(),g.y()-12,g.width(),g.height()+12)

    def _frac(self):
        return (self._prog_current/self._prog_total) if self._prog_total>0 else 0.0

    def set_progress_style(self,style):
        if style not in PROGRESS_BUTTON_WIDTHS:return
        self._prog_style=style
        if self._active:
            self.once_btn.setFixedWidth(PROGRESS_BUTTON_WIDTHS[style])
            self._sync_once_overlay()
            self._once_overlay.set_state(style,self._frac(),self._prog_current,self._prog_total,self.paused)

    def set_card_layout(self,key):
        key=key if key in CARD_LAYOUT_KEYS else "oneline"
        if key==getattr(self,"_card_layout","oneline"):return
        self._card_layout=key
        self.refresh()

    def set_patrol_progress(self,current,total):
        self._prog_current=int(current or 0);self._prog_total=int(total or 0)
        if self._active:
            self._once_overlay.set_state(self._prog_style,self._frac(),self._prog_current,self._prog_total,self.paused)

    def set_grace_countdown(self,seconds):
        """Show the 5s grace countdown on the 立即巡检 button (or clear it)."""
        if seconds and int(seconds)>0:
            self._grace_remaining=int(seconds);self._apply_grace_display()
        else:
            self._grace_remaining=0;self._grace_cancel_btn.setVisible(False)
            self.once_btn.setProperty("graceCountdown",False);self.once_btn.style().unpolish(self.once_btn);self.once_btn.style().polish(self.once_btn)
            if not getattr(self,"_active",False):
                self.once_btn.setText("立即巡检");self.once_btn.setIcon(ui_icon("play","#FFFFFF"))

    def _apply_grace_display(self):
        self.once_btn.setText(f"⏱ {self._grace_remaining} 秒后巡检");self.once_btn.setIcon(QIcon())
        self.once_btn.setProperty("graceCountdown",True);self.once_btn.style().unpolish(self.once_btn);self.once_btn.style().polish(self.once_btn)
        self._grace_cancel_btn.setVisible(True)

    def set_running(self,auto,active):
        self._auto=auto;self._active=active
        label="暂停中" if active and self.paused else "巡检中" if active else "自动巡检已开启" if auto else "待巡检"
        self.run_badge.setToolTip("")
        if active:
            # The overlay paints the button face (icon + text + progress);
            # keep the button itself blank so nothing is drawn twice.
            if getattr(self,"_once_cancel_action",None) is not None:self._once_cancel_action.setVisible(True)
            self.once_btn.setText("");self.once_btn.setIcon(QIcon())
            self.once_btn.setFixedWidth(PROGRESS_BUTTON_WIDTHS.get(self._prog_style,140))
            self._sync_once_overlay()
            self._once_overlay.set_state(self._prog_style,self._frac(),self._prog_current,self._prog_total,self.paused)
            self._once_overlay.show();self._once_overlay.raise_()
        else:
            if getattr(self,"_once_cancel_action",None) is not None:self._once_cancel_action.setVisible(False)
            self._once_overlay.hide();self.once_btn.setFixedWidth(140)
            if getattr(self,"_grace_remaining",0)>0:self._apply_grace_display()
            else:self.once_btn.setText("立即巡检");self.once_btn.setIcon(ui_icon("play","#FFFFFF"))
            self._prog_current=0;self._prog_total=0
        self.once_btn.setToolTip("暂停在当前主页处理完成后生效；继续不会从头重跑" if active else "巡检所有已选择模块的专业 ID")
        self.auto_btn.setText("暂停自动巡检" if auto else "启用自动巡检")
        self.auto_btn.setProperty("autoEnabled",auto)
        self._refresh_auto_tooltip()
        self.auto_btn.style().unpolish(self.auto_btn);self.auto_btn.style().polish(self.auto_btn)

    def showEvent(self,event):
        super().showEvent(event)
        # The pre-show layout may still carry the hidden width; re-lay out
        # once the event loop has settled so the column count matches the
        # real width (startup 1-column bug).
        QTimer.singleShot(0,self._reflow_after_show)

    def _reflow_after_show(self):
        if not hasattr(self,"cards"):return
        self.cards.columns=0
        self.cards.reflow()

    def refresh(self):        self.auto_btn.style().unpolish(self.auto_btn);self.auto_btn.style().polish(self.auto_btn)

    def refresh(self):
        now=time.time()
        try:interval=int(self.settings.value("interval_minutes",DEFAULT_INTERVAL_MINUTES))*60
        except (ValueError,TypeError):interval=DEFAULT_INTERVAL_MINUTES*60
        rows=apply_module_gating(self.store.dashboard_rows(None,interval),self.settings)
        self._last_rows=rows
        self._all_pages_dual=bool(rows) and all(r.get("monitor_growth") and r.get("monitor_posts") for r in rows)
        posts_on=modules_posts_enabled(self.settings)
        self._apply_filter_chips()
        if not self._active or not hasattr(self,"_last_inspection_stamp"):
            self._last_inspection_stamp=latest_inspection_stamp(self.settings,rows)
        self.run_badge.setText("上次巡检时间："+inspection_stamp_label(self._last_inspection_stamp))
        _day_start=datetime.fromtimestamp(now).astimezone().replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        unread_pages=self.store.unread_alert_page_ids(_day_start)
        _threshold=_bounded_int(self.settings.value("alert_threshold",500),500,1,100_000_000)
        today_sum=0;covered=0;partial=0;yesterday_sum=0;yesterday_covered=0;yesterday_partial=0
        growth_rows=[r for r in rows if r["monitor_growth"]]
        post_rows=[r for r in rows if r["monitor_posts"]]
        states=self.store.follower_states()
        for row in rows:
            row["post_view"]=post_view(row,now,interval)
            if row["monitor_growth"]:
                _st=states.get(row["page_id"])
                row["today"]=self.store._today_from_state(_st,now,interval)
                row["yesterday"]=self.store._yesterday_from_state(_st,now)
                if row["today"]["delta"] is not None:
                    today_sum+=row["today"]["delta"];covered+=1
                    partial+=int(row["today"]["partial"])
                if row["yesterday"]["delta"] is not None:
                    yesterday_sum+=row["yesterday"]["delta"];yesterday_covered+=1
                    yesterday_partial+=int(row["yesterday"]["partial"])
            # Growth category is state-based, not unread-only: an alert row
            # is created on every over-threshold collection (should_alert
            # still applies its elapsed/approx guards), and it stops
            # counting once read. An unread alert only counts on the day
            # it was created: yesterday's unread alert must not keep the
            # page in the over-threshold category once today's patrol
            # shows growth below the threshold. A page whose today's
            # accumulated growth reached the threshold counts even with
            # no unread alert row left; a single-interval jump alone
            # does not count (see today_growth_over_threshold).
            row["is_growth_alert"]=row["monitor_growth"] and (row["page_id"] in unread_pages or today_growth_over_threshold(row,_threshold,(row.get("today") or {}).get("delta")))
            row["growth_threshold"]=_threshold
            _gf,_of,_nf=dashboard_row_flags(row,posts_on)
            row["cat_growth"]=_gf;row["is_post_overdue"]=_of;row["needs_attention"]=_nf
        total=sum(r["last_followers"] for r in growth_rows if r["last_followers"] is not None)
        sampled=sum(r["last_followers"] is not None for r in growth_rows)
        overdue=sum(r["post_view"]["state"]=="overdue" for r in rows)
        unverified=sum(r["post_view"]["state"] in ("unknown","unverified") for r in rows)
        g,p=self.store.unread_totals()
        unavailable=sum(1 for r in rows if r.get("diagnosis_code")=="page_unavailable")
        failed=sum(1 for r in rows if r.get("diagnosis_code")!="page_unavailable" and (r.get("status") in ("采集失败","部分成功") or r.get("growth_error") or (posts_on and r.get("post_error"))))
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
        self._chip_counts={"needs":_needs_count,"growth_alert":_growth_count}
        self._growth_alert_ids={r["page_id"] for r in rows if r.get("cat_growth")}
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
            _pid=str(r["page_id"]);_card=self._card_cache.get(_pid)
            _key=(bool(r.get("monitor_growth")),bool(r.get("monitor_posts")),self._card_layout)
            if _card is None or _card.structure_key!=_key:
                if _card is not None:_card.hide();_card.deleteLater()
                _card=PageCard(r,layout_key=self._card_layout)
                _card.open_requested.connect(self.open_page.emit)
                _card.manage_requested.connect(self.open_manager.emit)
                _card.inspect_requested.connect(self.inspect_page.emit)
                _card.sync_requested.connect(self.sync_page.emit)
                _card.delete_requested.connect(self.delete_page.emit)
                self._card_cache[_pid]=_card
            else:
                _card.refresh_values(r)
            cards.append(_card)
        _live={str(r["page_id"]) for r in rows}
        for _pid in list(self._card_cache):
            if _pid not in _live:
                _old=self._card_cache.pop(_pid);_old.hide();_old.deleteLater()
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
            if self._empty_frame is not None:self._empty_frame.hide();self._empty_frame.deleteLater()
            cards=[empty];self._empty_frame=empty
        scroll=self.scroll.verticalScrollBar().value()
        if self._empty_frame is not None and not (len(cards)==1 and cards[0] is self._empty_frame):
            self._empty_frame.hide();self._empty_frame.deleteLater();self._empty_frame=None
        self.cards.arrange(cards)
        self.scroll.verticalScrollBar().setValue(scroll)
        _tv=random_inspection_timing(self.settings);self.set_timing_values(*_tv)
    def refresh_clock(self):
        """Light time-only refresh. True if any post state changed (full refresh needed)."""
        try:
            interval = int(self.settings.value("interval_minutes", DEFAULT_INTERVAL_MINUTES)) * 60
        except (ValueError, TypeError):
            interval = DEFAULT_INTERVAL_MINUTES * 60
        now = time.time()
        try:
            for card in list(self._card_cache.values()):
                if card.refresh_clock(now, interval):
                    return True
        except Exception:
            return True
        return False

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




class RangeCalendar(QWidget):
    """One-month grid for picking a date range, painted to match the trend
    mockup: rounded start/end, light band in between, today has a red dot
    (white when today is the range start/end). Weeks start on Sunday."""
    picked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        today = datetime.now().astimezone().date()
        self._today = today
        self._year = today.year
        self._month = today.month
        self._start = None
        self._end = None
        self.setMinimumSize(320, 250)
        self.setFixedHeight(250)

    def set_month(self, year, month):
        self._year, self._month = int(year), int(month)
        self.update()

    def month(self):
        return (self._year, self._month)

    def set_range(self, start, end):
        self._start, self._end = start, end
        anchor = start or end
        if anchor is not None:
            self._year, self._month = anchor.year, anchor.month
        self.update()

    def range(self):
        return (self._start, self._end)

    def _cells(self):
        first = date(self._year, self._month, 1)
        start_col = (first.weekday() + 1) % 7
        start_day = first - timedelta(days=start_col)
        out = []
        for i in range(42):
            d = start_day + timedelta(days=i)
            out.append((d, i // 7, i % 7, d.month == self._month))
        return out

    def _cell_rect(self, row, col):
        w, h = self.width(), self.height()
        top = 26
        cw = w / 7.0
        ch = (h - top) / 6.0
        return QRectF(col * cw, top + row * ch, cw, ch)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        font = p.font()
        font.setPointSize(11)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(MUTED))
        for col, name in enumerate(["日", "一", "二", "三", "四", "五", "六"]):
            p.drawText(QRectF(col * w / 7.0, 0, w / 7.0, 26),
                       Qt.AlignmentFlag.AlignCenter, name)
        font.setBold(False)
        font.setPointSize(13)
        p.setFont(font)
        s, e = self._start, self._end
        if s is not None and e is not None and e < s:
            s, e = e, s
        band = QColor(ACCENT)
        band.setAlpha(28)
        for d, row, col, in_month in self._cells():
            r = self._cell_rect(row, col)
            cx, cy = r.center().x(), r.center().y()
            in_range = s is not None and e is not None and s <= d <= e
            if in_range:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(ACCENT))
                if s == e:
                    p.drawRoundedRect(QRectF(cx - 17, cy - 15, 34, 30), 9, 9)
                elif d == s:
                    p.drawRoundedRect(QRectF(r.left(), cy - 15, r.width(), 30), 9, 9)
                    p.drawRect(QRectF(cx, cy - 15, r.right() - cx, 30))
                elif d == e:
                    p.drawRoundedRect(QRectF(r.left(), cy - 15, r.width(), 30), 9, 9)
                    p.drawRect(QRectF(r.left(), cy - 15, cx - r.left(), 30))
                else:
                    p.setBrush(band)
                    p.drawRect(r)
            if in_range and (d == s or d == e or s == e):
                p.setPen(QColor("#FFFFFF"))
            elif in_range:
                p.setPen(QColor(ACCENT))
            elif in_month:
                p.setPen(QColor(TEXT))
            else:
                p.setPen(QColor(BORDER))
            p.drawText(QRectF(r.left(), cy - 10, r.width(), 20),
                       Qt.AlignmentFlag.AlignCenter, str(d.day))
            if d == self._today:
                on_accent = in_range and (d == s or d == e or s == e)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#FFFFFF") if on_accent else QColor(RED))
                p.drawEllipse(QPointF(cx, cy + 12), 2.5, 2.5)
        p.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        w, h = self.width(), self.height()
        top = 26
        col = int(event.position().x() // (w / 7.0))
        row = int((event.position().y() - top) // ((h - top) / 6.0))
        if not (0 <= col < 7 and 0 <= row < 6):
            return
        d = self._cells()[row * 7 + col][0]
        if self._start is None or (self._start is not None and self._end is not None):
            self._start, self._end = d, None
        elif d < self._start:
            self._start = d
        else:
            self._end = d
        self.update()
        self.picked.emit()
        event.accept()


class DateRangePopup(QDialog):
    """Custom date-range picker matching the trend mockup: rounded white
    card, blue range, today has a red dot, quick ranges, 取消 / 确定."""
    def __init__(self, parent, start_day, end_day):
        super().__init__(parent)
        self.setWindowTitle("选择日期")
        self.setModal(True)
        self.setObjectName("DateRangePopup")
        self._start = start_day
        self._end = end_day
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)
        head = QHBoxLayout()
        self.prev_btn = QPushButton("‹")
        self.prev_btn.setObjectName("CalNavButton")
        self.prev_btn.clicked.connect(self._prev_month)
        head.addWidget(self.prev_btn)
        self.month_label = QLabel()
        self.month_label.setObjectName("CalMonthLabel")
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.addWidget(self.month_label, 1)
        self.next_btn = QPushButton("›")
        self.next_btn.setObjectName("CalNavButton")
        self.next_btn.clicked.connect(self._next_month)
        head.addWidget(self.next_btn)
        root.addLayout(head)
        self.cal = RangeCalendar(self)
        self.cal.set_range(start_day, end_day)
        root.addWidget(self.cal)
        self._sync_month_label()
        quick = QHBoxLayout()
        quick.setSpacing(8)
        self._quick_group = QButtonGroup(self)
        self._quick_group.setExclusive(True)
        self._quick_btns = {}
        for label, days in (("昨天 - 今天", 2), ("最近 7 天", 7), ("最近 30 天", 30)):
            btn = QPushButton(label)
            btn.setObjectName("CalQuickButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, n=days: self._quick(n))
            self._quick_group.addButton(btn)
            self._quick_btns[days] = btn
            quick.addWidget(btn)
        root.addLayout(quick)
        self.cal.picked.connect(self._sync_quick)
        self._sync_quick()
        foot = QHBoxLayout()
        foot.setSpacing(10)
        cancel = QPushButton("取消")
        cancel.setObjectName("SecondaryButton")
        cancel.clicked.connect(self.reject)
        foot.addWidget(cancel)
        ok = QPushButton("确定")
        ok.setObjectName("PrimaryButton")
        ok.clicked.connect(self.accept)
        foot.addWidget(ok)
        root.addLayout(foot)
        self.setFixedWidth(360)

    def _sync_month_label(self):
        y, m = self.cal.month()
        self.month_label.setText(f"{y} 年 {m} 月")

    def _prev_month(self):
        y, m = self.cal.month()
        m -= 1
        if m < 1:
            y, m = y - 1, 12
        self.cal.set_month(y, m)
        self._sync_month_label()

    def _next_month(self):
        y, m = self.cal.month()
        m += 1
        if m > 12:
            y, m = y + 1, 1
        self.cal.set_month(y, m)
        self._sync_month_label()

    def _quick(self, days):
        today = datetime.now().astimezone().date()
        start = today - timedelta(days=days - 1)
        self.cal.set_range(start, today)
        self._sync_month_label()
        self._sync_quick()

    def _sync_quick(self):
        """Only the quick range matching the current selection is lit:
        the range must end today and span 2 / 7 / 30 days. A hand-picked
        range lights none of the three."""
        s, e = self.cal.range()
        today = datetime.now().astimezone().date()
        days = None
        if s is not None and e is not None and e == today:
            n = (e - s).days + 1
            if n in self._quick_btns:
                days = n
        self._quick_group.setExclusive(False)
        for n, btn in self._quick_btns.items():
            btn.setChecked(n == days)
        self._quick_group.setExclusive(True)

    def selected_range(self):
        s, e = self.cal.range()
        if s is None and e is None:
            return (self._start, self._end)
        if s is None:
            s = e
        if e is None:
            e = s
        if e < s:
            s, e = e, s
        return (s, e)


def _nice_axis_top(max_val):
    """Nice Y-axis top and tick step for a daily-growth chart (1-2-3-5
    series, ~4 ticks): 351 -> (400, 100), 9 -> (9, 3), 3 -> (3, 1)."""
    if max_val is None or max_val <= 0:
        return 3, 1
    rough = float(max_val) / 4.0
    mag = 10 ** int(math.floor(math.log10(rough))) if rough >= 1 else 1
    step = None
    for mult in (1, 2, 3, 5, 10):
        _s = mult * mag
        if _s >= rough:
            step = _s
            break
    if step is None:
        step = 10 * mag
    step = max(1, int(step))
    top = int(step * math.ceil(float(max_val) / step))
    return top, step


class TrendChart(QWidget):
    """Area chart of daily growth (how many new followers each day).
    Y starts at 0 and tops out at a nice number above the largest daily
    gain; the line is a smooth curve through the points; every point
    carries its value and every selected date sits on the X axis. A day
    with a recorded gain of 0 is a real point; a day with no data breaks
    the line. minimal=True is the smaller card chart (same axis, values
    and dates, just shorter)."""
    def __init__(self, parent=None, minimal=False):
        super().__init__(parent)
        self._minimal = bool(minimal)
        self._points = {}
        self._start = None
        self._end = None
        self.setMinimumHeight(150 if self._minimal else 240)

    def set_series(self, points, start_day, end_day):
        self._points = {str(k): int(v) for k, v in (points or {}).items()}
        self._start = start_day
        self._end = end_day
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if not self._points or self._start is None or self._end is None or w < 40 or h < 20:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "暂无数据")
            p.end()
            return
        days = []
        d = self._start
        while d <= self._end:
            days.append(d)
            d += timedelta(days=1)
        n = len(days)
        if n == 0:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "暂无数据")
            p.end()
            return
        vals = list(self._points.values())
        axis_top, axis_step = _nice_axis_top(max(vals) if vals else 0)
        y_lo = 0
        y_hi = axis_top
        left = 34 if self._minimal else 46
        right = 12
        top = 12 if self._minimal else 14
        bottom = 20 if self._minimal else 24
        plot_w = max(w - left - right, 1)
        plot_h = max(h - top - bottom, 1)

        def x_of(i):
            return left + plot_w / 2 if n == 1 else left + plot_w * i / (n - 1)

        def y_of(v):
            return top + plot_h * (1 - (v - y_lo) / (y_hi - y_lo))

        font = p.font()
        font.setPointSize(9 if self._minimal else 10)
        p.setFont(font)
        _t = 0
        while _t <= axis_top:
            y = y_of(_t)
            p.setPen(QColor(BORDER))
            p.drawLine(QPointF(left, y), QPointF(left + plot_w, y))
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(0, y - 8, left - 6, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       format_compact_count(int(_t)))
            _t += axis_step
        step = (max(1, n // 4) if self._minimal else (1 if n <= 14 else max(1, n // 10)))
        for i, d in enumerate(days):
            if i % step == 0 or i == n - 1:
                p.setPen(QColor(MUTED))
                lx = max(0, min(x_of(i) - 30, w - 60))
                lbl = str(d.day) if self._minimal else d.strftime("%m-%d")
                p.drawText(QRectF(lx, top + plot_h + 5, 60, 16),
                           Qt.AlignmentFlag.AlignCenter, lbl)
        def _smooth(pts):
            """Monotone cubic through pts -> QPainterPath: the line flows
            up and down like the reference curves, but never overshoots
            past the neighbouring values, so a flat stretch stays flat
            (Fritsch-Carlson tangents)."""
            path = QPainterPath()
            if not pts:
                return path
            path.moveTo(pts[0][0], pts[0][1])
            m = len(pts)
            if m < 2:
                return path
            d = []
            for i in range(m - 1):
                dx = pts[i + 1][0] - pts[i][0]
                d.append((pts[i + 1][1] - pts[i][1]) / dx if dx else 0.0)
            tan = [0.0] * m
            tan[0] = d[0]
            tan[m - 1] = d[m - 2]
            for i in range(1, m - 1):
                if d[i - 1] * d[i] <= 0:
                    tan[i] = 0.0
                else:
                    w1 = 2 * (pts[i + 1][0] - pts[i][0]) + (pts[i][0] - pts[i - 1][0])
                    w2 = (pts[i + 1][0] - pts[i][0]) + 2 * (pts[i][0] - pts[i - 1][0])
                    tan[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
            for i in range(m - 1):
                dx = pts[i + 1][0] - pts[i][0]
                c1 = (pts[i][0] + dx / 3.0, pts[i][1] + tan[i] * dx / 3.0)
                c2 = (pts[i + 1][0] - dx / 3.0, pts[i + 1][1] - tan[i + 1] * dx / 3.0)
                path.cubicTo(c1[0], c1[1], c2[0], c2[1], pts[i + 1][0], pts[i + 1][1])
            return path
            path.moveTo(pts[0][0], pts[0][1])
            m = len(pts)
            for i in range(m - 1):
                p0 = pts[max(i - 1, 0)]
                p1 = pts[i]
                p2 = pts[i + 1]
                p3 = pts[min(i + 2, m - 1)]
                c1 = (p1[0] + (p2[0] - p0[0]) / 6.0,
                      p1[1] + (p2[1] - p0[1]) / 6.0)
                c2 = (p2[0] - (p3[0] - p1[0]) / 6.0,
                      p2[1] - (p3[1] - p1[1]) / 6.0)
                path.cubicTo(c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])
            return path

        runs = []
        run = []
        for i, d in enumerate(days):
            v = self._points.get(d.isoformat())
            if v is None:
                if len(run) >= 2:
                    runs.append(run)
                run = []
            else:
                run.append((x_of(i), y_of(v)))
        if len(run) >= 2:
            runs.append(run)
        base_y = top + plot_h
        fill = QColor(ACCENT)
        fill.setAlpha(31)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        for run in runs:
            fp = _smooth(run)
            fp.lineTo(run[-1][0], base_y)
            fp.lineTo(run[0][0], base_y)
            fp.closeSubpath()
            p.drawPath(fp)
        p.setPen(QPen(QColor(ACCENT), 2.5, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for run in runs:
            p.drawPath(_smooth(run))
        for i, d in enumerate(days):
            v = self._points.get(d.isoformat())
            if v is None:
                continue
            x, y = x_of(i), y_of(v)
            p.setBrush(QColor(ACCENT))
            p.setPen(QColor(PANEL))
            p.drawEllipse(QPointF(x, y), 4, 4)
            if n <= 14:
                p.setPen(QColor(TEXT))
                lx = max(left, min(x - 34, left + plot_w - 68))
                ly = max(2, y - 20)
                p.drawText(QRectF(lx, ly, 68, 14),
                           Qt.AlignmentFlag.AlignCenter, format_compact_count(int(v)))
        p.end()


class TrendCard(QFrame):
    """One page in the trend overview grid: avatar, name, period total
    (+N, no label, no tooltip) and a small daily-growth area chart with
    its own axis, value labels and dates. View-only."""
    def __init__(self, store, page, growth, start_day, end_day, parent=None):
        super().__init__(parent)
        self._pid = str(page["page_id"])
        self.setObjectName("TrendCard")
        name = normalize_name(page.get("custom_name") or page.get("page_name"), self._pid)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(AvatarWidget(name, page.get("avatar_path", ""), 36, page_id=self._pid))
        nm = QLabel(name)
        nm.setObjectName("TrendCardName")
        nm.setWordWrap(True)
        head.addWidget(nm, 1)
        total = sum(growth.values()) if growth else None
        tot_txt = format_delta(total) if total is not None else "—"
        tot = QLabel(f'<b style="color:{RED};font-size:15px">{tot_txt}</b>')
        tot.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        head.addWidget(tot)
        lay.addLayout(head)
        spark = TrendChart(minimal=True)
        spark.set_series(growth, start_day, end_day)
        lay.addWidget(spark)


class TrendPage(QWidget):
    """增长趋势：上面是所有专业加起来的总趋势（每天一共长多少、这几天
    一共长多少、从哪天开始），下面是每个专业的小卡片。日期药丸点开是
    新做的圆角日历。"""
    def __init__(self, store, settings=None):
        super().__init__()
        self.store = store
        self.settings = settings
        self.setObjectName("TrendPage")
        today = datetime.now().astimezone().date()
        self._start = today - timedelta(days=1)
        self._end = today
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(12)
        self.total_card = QFrame()
        self.total_card.setObjectName("TrendChartCard")
        tl = QVBoxLayout(self.total_card)
        tl.setContentsMargins(16, 14, 16, 10)
        tl.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(10)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("全部专业总计")
        title.setObjectName("PanelTitle")
        title_box.addWidget(title)
        sub = QLabel("每天所有专业加起来")
        sub.setObjectName("SmallMuted")
        title_box.addWidget(sub)
        head.addLayout(title_box)
        head.addStretch(1)
        self.date_pill = QPushButton()
        self.date_pill.setObjectName("DatePill")
        self.date_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.date_pill.clicked.connect(self._show_date_popup)
        head.addWidget(self.date_pill)
        self.grand_total = QLabel()
        self.grand_total.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.grand_total)
        tl.addLayout(head)
        self.chart = TrendChart()
        tl.addWidget(self.chart)
        self.chart_note = QLabel()
        self.chart_note.setObjectName("SmallMuted")
        self.chart_note.setWordWrap(True)
        tl.addWidget(self.chart_note)
        root.addWidget(self.total_card)
        grid_head = QHBoxLayout()
        grid_title = QLabel("全部专业")
        grid_title.setObjectName("PanelTitle")
        grid_head.addWidget(grid_title)
        grid_head.addStretch(1)
        grid_hint = QLabel("每张卡片是这个专业这几天的增长")
        grid_hint.setObjectName("SmallMuted")
        grid_head.addWidget(grid_hint)
        root.addLayout(grid_head)
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setObjectName("CardScroll")
        self.grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid_wrap = QWidget()
        self.grid_lay = QGridLayout(self.grid_wrap)
        self.grid_lay.setSpacing(10)
        self.grid_lay.setContentsMargins(0, 0, 0, 0)
        self.grid_scroll.setWidget(self.grid_wrap)
        root.addWidget(self.grid_scroll, 1)
        self._empty = QLabel("尚无匹配主页，先去左侧「ID管理」添加。")
        self._empty.setObjectName("EmptyHint")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._empty)
        self.refresh()

    def _show_date_popup(self):
        dlg = DateRangePopup(self, self._start, self._end)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            s, e = dlg.selected_range()
            self._start, self._end = s, e
            self.refresh()

    def refresh(self):
        pages = self.store.list_pages()
        s, e = self._start, self._end
        if s > e:
            s, e = e, s
        self._start, self._end = s, e
        self.date_pill.setText(f"📅 {s.strftime('%m-%d')} 至 {e.strftime('%m-%d')} ▾")
        total_series = dict(self.store.daily_total_growth_series(s, e))
        grand = sum(total_series.values()) if total_series else None
        grand_txt = format_delta(grand) if grand is not None else "—"
        self.grand_total.setText(
            f'<b style="color:{RED};font-size:22px">{grand_txt}</b>')
        self.chart.set_series(total_series, s, e)
        if total_series:
            self.chart_note.setText("")
            self.chart_note.hide()
        else:
            self.chart_note.setText("这几天还没有每天的增长记录，巡检跑起来之后每天会记一个数。")
            self.chart_note.show()
        self._rebuild_grid(pages, s, e)
        self._empty.setVisible(not pages)
        self.grid_scroll.setVisible(bool(pages))

    def _rebuild_grid(self, pages, s, e):
        while self.grid_lay.count():
            item = self.grid_lay.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        if not pages:
            return
        cols = 3
        for i, page in enumerate(pages):
            pid = str(page["page_id"])
            growth = dict(self.store.daily_growth_series(pid, s, e))
            card = TrendCard(self.store, page, growth, s, e)
            self.grid_lay.addWidget(card, i // cols, i % cols)


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
        _hr=QWidget();_hl=QHBoxLayout(_hr);_hl.setContentsMargins(0,0,0,0);_hl.setSpacing(6)
        _hl.addWidget(self.hours);_hl.addStretch()
        form.addRow("发帖超时标准",_hr)
        form.addRow(_subtitle("主页超过这么久没发新贴，就进发帖超时。"))
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
            elif normalize_name(row["page_name"],pid):state="已同步"
            else:state="名称待获取"
            _diag_parts=[str(row.get("diagnosis_detail") or ""),str(row.get("growth_error") or "")]
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
    dev_mode_requested=pyqtSignal(bool)
    manual_update_check_requested=pyqtSignal()
    view_update_log_requested=pyqtSignal()
    fireworks_preview_requested=pyqtSignal()
    export_requested=pyqtSignal()
    data_dir_requested=pyqtSignal()
    theme_requested=pyqtSignal(str)
    ui_scale_requested=pyqtSignal(int)
    toast_position_requested=pyqtSignal(str)
    progress_style_requested=pyqtSignal(str)
    card_layout_requested=pyqtSignal(str)
    nav_style_requested=pyqtSignal(str)

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
        for prev in getattr(self,"nav_style_previews",{}).values():
            prev.set_theme(name)

    def set_selected_nav_style(self,name):
        for key,card in getattr(self,"nav_style_cards",{}).items():
            card.setSelected(key==name)

    def _on_nav_style_picked(self,key):
        if key not in NAV_STYLE_KEYS:return
        self._nav_style=key;self.set_selected_nav_style(key)
        self.settings.setValue("nav_style",key);self.settings.sync()
        self.nav_style_requested.emit(key)

    def set_ui_scale_label(self,scale):
        if hasattr(self,"zoom_label"):self.zoom_label.setText(f"{int(scale)}%")

    def _on_toast_position_changed(self):
        # Save first (synchronous emit), then show the real toast so it
        # appears at the position just selected.
        self.toast_position_requested.emit(self.toast_position_choice.currentData())
        show_hint(self,"提示会显示在这里",kind="success")

    def set_selected_progress_style(self,name):
        for key,card in getattr(self,"progress_cards",{}).items():
            card.setSelected(key==name)

    def _on_progress_style_picked(self,key):
        if key not in PROGRESS_BUTTON_WIDTHS:return
        self._progress_style=key;self.set_selected_progress_style(key)
        self.settings.setValue("progress_style",key);self.settings.sync()
        self.progress_style_requested.emit(key)

    def set_selected_card_layout(self,name):
        for key,card in getattr(self,"card_layout_cards",{}).items():
            card.setSelected(key==name)

    def _on_card_layout_picked(self,key):
        if key not in CARD_LAYOUT_KEYS:return
        self._card_layout=key;self.set_selected_card_layout(key)
        self.settings.setValue("card_layout",key);self.settings.sync()
        self.card_layout_requested.emit(key)

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
        _theme_title=QLabel("界面模式");_theme_title.setObjectName("SettingsTitle");thel.addWidget(_theme_title)
        _theme_note=QLabel("选择亮色或暗色界面风格。");_theme_note.setObjectName("SmallMuted");thel.addWidget(_theme_note)
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
        _div=QFrame();_div.setFrameShape(QFrame.Shape.HLine);_div.setObjectName("HeaderDivider");thel.addWidget(_div)
        _nav_title=QLabel("导航栏样式");_nav_title.setObjectName("SettingsTitle");thel.addWidget(_nav_title)
        _nav_note=QLabel("左侧导航栏的外观，点一张卡片就选中，立即生效。");_nav_note.setObjectName("SmallMuted");thel.addWidget(_nav_note)
        _nav_row=QHBoxLayout();_nav_row.setSpacing(12)
        self.nav_style_cards={};self.nav_style_previews={};self._nav_style=NAV_DEFAULT_STYLE
        for _key,_name,_desc in NAV_STYLES:
            _card=OptionCard(_name,_desc)
            _prev=NavStylePreview(_key,migrate_theme_name(self.settings.value("ui_theme","云白")));_prev.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
            _card.layout().insertWidget(0,_prev)
            _card.clicked.connect(lambda _=False,k=_key:self._on_nav_style_picked(k))
            _nav_row.addWidget(_card,1);self.nav_style_cards[_key]=_card;self.nav_style_previews[_key]=_prev
        thel.addLayout(_nav_row)
        _div=QFrame();_div.setFrameShape(QFrame.Shape.HLine);_div.setObjectName("HeaderDivider");thel.addWidget(_div)
        _zoom_title=QLabel("界面缩放");_zoom_title.setObjectName("SettingsTitle");thel.addWidget(_zoom_title)
        _zoom_row=QHBoxLayout();_zoom_row.setSpacing(8)
        _zoom_min=QLabel("80%");_zoom_min.setObjectName("SmallMuted");_zoom_row.addWidget(_zoom_min)
        self.zoom_out_btn=QPushButton("−");self.zoom_out_btn.setFixedSize(38,36)
        self.zoom_out_btn.setToolTip("缩小 10%")
        self.zoom_label=QLabel("100%");self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter);self.zoom_label.setFixedWidth(64)
        self.zoom_in_btn=QPushButton("+");self.zoom_in_btn.setFixedSize(38,36)
        self.zoom_in_btn.setToolTip("放大 10%")
        self.zoom_out_btn.clicked.connect(lambda:self.ui_scale_requested.emit(ui_scale_percent(self.settings)-10))
        self.zoom_in_btn.clicked.connect(lambda:self.ui_scale_requested.emit(ui_scale_percent(self.settings)+10))
        _zoom_row.addWidget(self.zoom_out_btn);_zoom_row.addWidget(self.zoom_label);_zoom_row.addWidget(self.zoom_in_btn)
        _zoom_max=QLabel("130%");_zoom_max.setObjectName("SmallMuted");_zoom_row.addWidget(_zoom_max)
        _zoom_row.addStretch();thel.addLayout(_zoom_row)
        _div=QFrame();_div.setFrameShape(QFrame.Shape.HLine);_div.setObjectName("HeaderDivider");thel.addWidget(_div)
        _toast_title=QLabel("消息提示位置");_toast_title.setObjectName("SettingsTitle");thel.addWidget(_toast_title)
        _toast_note=QLabel("点选立即弹出一条真实提示");_toast_note.setObjectName("SmallMuted");thel.addWidget(_toast_note)
        self.toast_position_choice=SegmentedChoice(TOAST_POSITIONS,"bottom_center")
        self.toast_position_choice.changed.connect(self._on_toast_position_changed)
        thel.addWidget(self.toast_position_choice)
        _div=QFrame();_div.setFrameShape(QFrame.Shape.HLine);_div.setObjectName("HeaderDivider");thel.addWidget(_div)
        _prog_title=QLabel("巡检进度条样式");_prog_title.setObjectName("SettingsTitle");thel.addWidget(_prog_title)
        _prog_note=QLabel("巡检进行时，「立即巡检」按钮上的进度显示方式，点一张卡片就选中。");_prog_note.setObjectName("SmallMuted");thel.addWidget(_prog_note)
        _prog_grid=QGridLayout();_prog_grid.setSpacing(12)
        _prog_grid.setColumnStretch(0,1);_prog_grid.setColumnStretch(1,1);_prog_grid.setColumnStretch(2,1);_prog_grid.setColumnStretch(3,1)
        self.progress_cards={};self._progress_style="fill"
        for _i,(_key,_name,_desc) in enumerate(PROGRESS_STYLES):
            _card=OptionCard(_name,_desc)
            _prev=ProgressStylePreview(_key);_prev.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
            _card.layout().insertWidget(0,_prev)
            _card.clicked.connect(lambda _=False,k=_key:self._on_progress_style_picked(k))
            _prog_grid.addWidget(_card,_i//4,_i%4);self.progress_cards[_key]=_card
        thel.addLayout(_prog_grid)
        _card_title=QLabel("卡片排版");_card_title.setObjectName("SettingsTitle");thel.addWidget(_card_title)
        _card_note=QLabel("小卡片上数字的排版方式，点一张卡片就选中，立即生效。");_card_note.setObjectName("SmallMuted");thel.addWidget(_card_note)
        _card_row=QHBoxLayout();_card_row.setSpacing(12)
        self.card_layout_cards={};self._card_layout="oneline"
        for _i,(_key,_name,_desc) in enumerate(CARD_LAYOUTS):
            _card=OptionCard(_name,_desc)
            _prev=CardLayoutPreview(_key);_prev.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
            _card.layout().insertWidget(0,_prev)
            _card.clicked.connect(lambda _=False,k=_key:self._on_card_layout_picked(k))
            _card_row.addWidget(_card,1);self.card_layout_cards[_key]=_card
        thel.addLayout(_card_row)
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
        self.auto_update=QCheckBox("启动时自动检查更新")
        bl.addWidget(self.auto_update)
        _mc=QHBoxLayout();_mc.setSpacing(8)
        self.manual_update_check_button=QPushButton("检查更新");self.manual_update_check_button.setObjectName("SecondaryButton")
        self.manual_update_check_button.clicked.connect(self.manual_update_check_requested.emit)
        _mc.addWidget(self.manual_update_check_button)
        self.view_update_log_button=QPushButton("查看更新日志");self.view_update_log_button.setObjectName("SecondaryButton")
        self.view_update_log_button.clicked.connect(self.view_update_log_requested.emit)
        _mc.addWidget(self.view_update_log_button);_mc.addStretch();bl.addLayout(_mc)
        merged_layout.addWidget(browser);merged_layout.addStretch()

        collect_layout=make_tab("巡检与提醒")
        collect,cl=self.card()
        _nt=QLabel("系统通知弹窗提醒");_nt.setObjectName("SettingsTitle");cl.addWidget(_nt)
        self.alert_enabled=QCheckBox("粉丝增长提醒")
        cl.addWidget(self.alert_enabled)
        self.notify_post_overdue=QCheckBox("发帖超时提醒")
        cl.addWidget(self.notify_post_overdue)
        _div=QFrame();_div.setFrameShape(QFrame.Shape.HLine);_div.setObjectName("HeaderDivider");cl.addWidget(_div)
        _pt=QLabel("自动巡检设置");_pt.setObjectName("SettingsTitle");cl.addWidget(_pt)
        def _block(row,note=None,indent=0):
            # One setting: its row + subtitle hugging right below it (3px),
            # so the note clearly belongs to the row above it; the card
            # layout keeps 13px between blocks.
            g=QWidget();gl=QVBoxLayout(g);gl.setContentsMargins(0,0,0,0);gl.setSpacing(3)
            gl.addLayout(row)
            if note:gl.addWidget(_subtitle(note, indent=indent))
            cl.addWidget(g)
        def _labeled(label_text,widgets):
            row=QHBoxLayout();row.setSpacing(8)
            _lab=QLabel(label_text);_lab.setFixedWidth(130);row.addWidget(_lab)
            for _w in widgets:row.addWidget(_w)
            row.addStretch();return row
        self.interval=DirectNumberSpinBox();self.interval.setRange(5,1440);self.interval.setFixedWidth(70)
        _block(_labeled("每轮间隔（分钟）",[self.interval]),"相邻两轮巡检之间隔多久。")
        self._interval_hint=QLabel("⚠ 间隔低于 180 分钟\n太短容易被 Facebook 临时限制，页面会提示「暂时被禁止使用此功能」，被限制的那个浏览器这段时间读不到主页，其他没受限的浏览器不受影响。隔几小时不访问会慢慢自动恢复。建议改到 180 分钟以上；坚持用更短的也可以，只是提醒你一下。")
        self._interval_hint.setWordWrap(True)
        self._interval_hint.setStyleSheet("background:#FFFBEB;border:1px solid #F59E0B;border-radius:8px;color:#92400E;padding:9px 12px;margin-left:138px;")
        self._interval_hint.setVisible(False)
        cl.addWidget(self._interval_hint)
        self.interval.valueChanged.connect(lambda v:self._interval_hint.setVisible(int(v)<180))
        self.jitter_min=DirectNumberSpinBox();self.jitter_min.setRange(0,1439);self.jitter_min.setFixedWidth(70)
        self.jitter_max=DirectNumberSpinBox();self.jitter_max.setRange(0,1439);self.jitter_max.setFixedWidth(70)
        _block(_labeled("浮动范围（分钟）",[self.jitter_min,QLabel("–"),self.jitter_max]),"每轮开始时间在间隔附近随机前后浮动，不固定在整点。")
        self.gap_min=DirectNumberSpinBox();self.gap_min.setRange(0,120);self.gap_min.setFixedWidth(70)
        self.gap_max=DirectNumberSpinBox();self.gap_max.setRange(0,120);self.gap_max.setFixedWidth(70)
        _block(_labeled("主页间隔（秒）",[self.gap_min,QLabel("–"),self.gap_max]),"同一轮里，每两个主页之间隔几秒再读。")
        _div=QFrame();_div.setFrameShape(QFrame.Shape.HLine);_div.setObjectName("HeaderDivider");cl.addWidget(_div)
        _gt=QLabel("粉丝增长");_gt.setObjectName("SettingsTitle");cl.addWidget(_gt)
        _tr=QHBoxLayout();_tr.setSpacing(8)
        _tr.addWidget(QLabel("当日粉丝增长阈值"))
        self.threshold=DirectNumberSpinBox();self.threshold.setRange(1,100_000_000);self.threshold.setSingleStep(100)
        self.threshold.setFixedWidth(90)
        _tr.addWidget(self.threshold);_tr.addStretch()
        _block(_tr,"当天粉丝累计新增达到这个数就提醒。")
        self.fireworks_enabled=QCheckBox("新超标时放烟花")
        self.fireworks_enabled.setToolTip("有主页新超标时，在屏幕上放一场烟花。关掉「粉丝增长提醒」后，烟花也不会触发。")
        self.alert_enabled.toggled.connect(lambda checked:self.fireworks_enabled.setEnabled(checked))
        _fw=QHBoxLayout();_fw.setSpacing(8)
        _fw.addWidget(self.fireworks_enabled)
        self.fireworks_preview_button=QPushButton("预览效果");self.fireworks_preview_button.setObjectName("SecondaryButton")
        self.fireworks_preview_button.clicked.connect(self.fireworks_preview_requested.emit)
        _fw.addWidget(self.fireworks_preview_button);_fw.addStretch()
        cl.addLayout(_fw)
        collect_layout.addWidget(collect);collect_layout.addStretch()

        data_layout=make_tab("数据管理")
        data,dl=self.card()
        self.data_path_label=QLabel(str(DATA_DIR));self.data_path_label.setTextFormat(Qt.TextFormat.PlainText);self.data_path_label.setObjectName("PathLabel");self.data_path_label.setWordWrap(True);dl.addWidget(self.data_path_label)
        buttons=QHBoxLayout()
        self.choose_data_dir=QPushButton("更改保存目录");self.choose_data_dir.setObjectName("PrimaryButton")
        self.choose_data_dir.clicked.connect(self.data_dir_requested.emit);buttons.addWidget(self.choose_data_dir)
        folder=QPushButton("打开数据目录");folder.setObjectName("SecondaryButton")
        folder.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR))));buttons.addWidget(folder)
        buttons.addStretch();dl.addLayout(buttons)
        dl.addWidget(_subtitle("选新目录后，现有数据会一起迁过去，不用手动搬。"))
        _div=QFrame();_div.setFrameShape(QFrame.Shape.HLine);_div.setObjectName("HeaderDivider");dl.addWidget(_div)
        _dev_title=QLabel("开发者模式");_dev_title.setObjectName("SettingsTitle");dl.addWidget(_dev_title)
        self.dev_mode=QCheckBox("开发者模式")
        self.dev_mode.setToolTip("开启后显示诊断日志窗口（只能在主窗口内移动），记录发帖检测、名称／粉丝采集、复检与更新检查的诊断信息。默认关闭。")
        self.dev_mode.toggled.connect(self.dev_mode_requested.emit)
        _dm=QWidget();_dl2=QHBoxLayout(_dm);_dl2.setContentsMargins(0,0,0,0);_dl2.setSpacing(6)
        _dl2.addWidget(self.dev_mode);_dl2.addStretch()
        dl.addWidget(_dm)
        dl.addWidget(_subtitle("打开诊断日志窗口，记录巡检每一步的判断，排查问题用。", indent=28))
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
        for widget,key,default in ((self.alert_enabled,"alert_enabled",True),(self.notify_post_overdue,"notify_post_overdue",True),
                (self.fireworks_enabled,"fireworks_enabled",True),
                (self.auto_update,"auto_check_updates",True),
                (self.dev_mode,"dev_mode",False)):
            widget.blockSignals(True);widget.setChecked(is_true(self.settings.value(key,default),default));widget.blockSignals(False)
        for widget,key,default in ((self.module_growth_switch,MODULE_GROWTH_KEY,True),(self.module_posts_switch,MODULE_POSTS_KEY,False)):
            widget.blockSignals(True);widget.setChecked(is_true(self.settings.value(key,default),default));widget.blockSignals(False)
        self._refresh_module_statuses()
        self.fireworks_enabled.setEnabled(self.alert_enabled.isChecked())
        _style=str(self.settings.value("progress_style","fill") or "fill")
        if _style not in PROGRESS_BUTTON_WIDTHS:_style="fill"
        self._progress_style=_style;self.set_selected_progress_style(_style)
        _cl=str(self.settings.value("card_layout","oneline") or "oneline")
        if _cl not in CARD_LAYOUT_KEYS:_cl="oneline"
        self._card_layout=_cl;self.set_selected_card_layout(_cl)
        _ns=str(self.settings.value("nav_style",NAV_DEFAULT_STYLE) or NAV_DEFAULT_STYLE)
        if _ns not in NAV_STYLE_KEYS:_ns=NAV_DEFAULT_STYLE
        self._nav_style=_ns;self.set_selected_nav_style(_ns)
        self.set_selected_theme(migrate_theme_name(self.settings.value("ui_theme","云白")))
        _pos=str(self.settings.value("toast_position","bottom_center"))
        if _pos in [k for _,k in TOAST_POSITIONS]:self.toast_position_choice.setCurrentData(_pos,emit=False)
        self.set_ui_scale_label(ui_scale_percent(self.settings))
        if hasattr(self,"_interval_hint"):self._interval_hint.setVisible(int(self.interval.value())<180)

    def save_settings(self):
        timing=save_random_timing(self.settings,(self.interval.value(),self.jitter_min.value(),self.jitter_max.value(),self.gap_min.value(),self.gap_max.value()))
        for widget,value in zip((self.interval,self.jitter_min,self.jitter_max,self.gap_min,self.gap_max),timing):
            widget.blockSignals(True);widget.setValue(value);widget.blockSignals(False)
        values={
            "min_to_tray":1,"alert_enabled":int(self.alert_enabled.isChecked()),
            "notify_post_overdue":int(self.notify_post_overdue.isChecked()),
            "fireworks_enabled":int(self.fireworks_enabled.isChecked()),"progress_style":getattr(self,"_progress_style","fill"),"card_layout":getattr(self,"_card_layout","oneline"),
            "alert_threshold":self.threshold.value(),
            "auto_check_updates":int(self.auto_update.isChecked()),"dev_mode":int(self.dev_mode.isChecked()),
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
            if getattr(exc,"retry_after_seconds",None):
                result["retry_after_seconds"]=exc.retry_after_seconds
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
        ok=QPushButton("确定");ok.setObjectName("PrimaryButton");ok.clicked.connect(self.accept);actions.addWidget(ok)
        skip=QPushButton("以后再说");skip.setObjectName("LinkButton");skip.clicked.connect(self.accept);actions.addWidget(skip)
        actions.addStretch();root.addLayout(actions)
        note=QLabel("只问这一次。以后改主意：设置 → 监控模块，随时开关，开关后看板和卡片会跟着变。")
        note.setObjectName("SmallMuted");note.setWordWrap(True);root.addWidget(note)

    def _select(self,choice):
        self.choice=choice
        self.opt_growth.setSelected(choice=="growth");self.opt_both.setSelected(choice=="both")



_FIREWORKS_PALETTES = [
    ("#F59E0B", "#EF4444", "#FDE68A"),
    ("#3B82F6", "#A855F7", "#93C5FD"),
    ("#22C55E", "#EC4899", "#A7F3D0"),
    ("#EF4444", "#F97316", "#FCA5A5"),
    ("#8B5CF6", "#06B6D4", "#C4B5FD"),
    ("#EC4899", "#F59E0B", "#FBCFE8"),
]
_FIREWORKS_STYLES = ("ring", "willow", "star", "rings", "rain", "chrysanthemum", "fountain", "spiral")


class FireworksOverlay(QWidget):
    """One-shot fireworks overlay covering the main window.

    Transparent to mouse clicks, paints only particles (no background
    fill), and hides itself when the animation ends. A play runs three
    waves over about 7 seconds (3 + 4 + 5 bursts, the last wave with a
    large finale burst); every burst picks a random style and palette,
    so no two plays look the same.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.hide()
        self._particles = []
        self._elapsed = 0
        self.duration_ms = 7000
        self.wave_offsets_ms = [0, 2200, 4500]
        self._waves_done = set()
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)
        if parent is not None:
            parent.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parent().rect())
        return super().eventFilter(obj, event)

    def play(self):
        if self.parent() is not None:
            self.setGeometry(self.parent().rect())
        self._particles = []
        self._elapsed = 0
        self._waves_done = {0}
        self._spawn_wave(0)
        self.show()
        self.raise_()
        self._timer.start()
        self.update()

    def _spawn_wave(self, wave_index):
        rnd = random.Random()
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            w, h = 1200, 800
        count = [3, 4, 5][wave_index] if wave_index < 3 else 3
        styles = rnd.sample(list(_FIREWORKS_STYLES), k=min(3, len(_FIREWORKS_STYLES)))
        for n in range(count):
            style = styles[n % len(styles)]
            palette = rnd.choice(_FIREWORKS_PALETTES)
            if wave_index == 2 and n == 0:
                self._make_burst(w * 0.5, h * 0.26, 240, style, palette, rnd)
                continue
            cy = h * 0.92 if style == "fountain" else rnd.uniform(h * 0.10, h * 0.55)
            self._make_burst(rnd.uniform(w * 0.12, w * 0.88), cy,
                             rnd.uniform(90, 190), style, palette, rnd)

    def _make_burst(self, cx, cy, radius, style, palette, rnd):
        def particle(angle, speed, life, gravity, size, color, spin=0.0):
            self._particles.append({
                "x": cx, "y": cy, "px": cx, "py": cy,
                "vx": speed * math.cos(angle), "vy": speed * math.sin(angle),
                "life": life, "maxlife": life, "gravity": gravity,
                "size": size, "color": color, "spin": spin,
            })

        if style == "ring":
            for k in range(48):
                ang = 2 * math.pi * k / 48
                particle(ang, radius * rnd.uniform(1.9, 2.4),
                         rnd.uniform(0.9, 1.3), 30, rnd.uniform(3.5, 5),
                         palette[k % len(palette)])
        elif style == "willow":
            for k in range(36):
                ang = 2 * math.pi * k / 36 + rnd.uniform(-0.05, 0.05)
                particle(ang, radius * rnd.uniform(1.5, 2.1),
                         rnd.uniform(1.5, 2.2), 300, rnd.uniform(3, 4.5),
                         palette[k % len(palette)])
        elif style == "star":
            for k in range(40):
                ang = 2 * math.pi * k / 40
                long_ray = (k % 2 == 0)
                particle(ang, radius * (2.6 if long_ray else 1.4) * rnd.uniform(0.9, 1.0),
                         rnd.uniform(1.0, 1.4), 40,
                         rnd.uniform(4, 5) if long_ray else rnd.uniform(2.5, 3.5),
                         palette[k % len(palette)])
        elif style == "rings":
            for k in range(36):
                ang = 2 * math.pi * k / 36
                particle(ang, radius * 2.4, rnd.uniform(1.0, 1.2), 30,
                         rnd.uniform(3.5, 5), palette[k % 2])
            for k in range(24):
                ang = 2 * math.pi * k / 24
                particle(ang, radius * 1.3, rnd.uniform(0.8, 1.0), 30,
                         rnd.uniform(3, 4), palette[2])
        elif style == "chrysanthemum":
            for k in range(72):
                ang = 2 * math.pi * k / 72
                particle(ang, radius * rnd.uniform(1.9, 2.3),
                         rnd.uniform(1.0, 1.4), 20, rnd.uniform(3, 4.5),
                         palette[k % 2])
        elif style == "fountain":
            for k in range(40):
                particle(rnd.uniform(-2.8, -0.35), rnd.uniform(380, 520),
                         rnd.uniform(1.6, 2.4), 520, rnd.uniform(3, 5),
                         palette[k % len(palette)])
        elif style == "spiral":
            for k in range(40):
                ang = 2 * math.pi * k / 40
                particle(ang, radius * 2.0, rnd.uniform(1.2, 1.8), 25,
                         rnd.uniform(3, 4.5), palette[k % len(palette)],
                         spin=rnd.choice([-1, 1]) * rnd.uniform(1.2, 2.0))
        else:  # rain
            for k in range(30):
                ang = rnd.uniform(0, 2 * math.pi)
                particle(ang, radius * rnd.uniform(1.2, 2.0),
                         rnd.uniform(1.1, 1.5), 120, rnd.uniform(3, 4.5),
                         rnd.choice(palette))
            for _ in range(46):
                ang = rnd.uniform(0, 2 * math.pi)
                particle(ang, radius * rnd.uniform(0.3, 0.8),
                         rnd.uniform(1.4, 1.9), 420, rnd.uniform(2, 3.5),
                         rnd.choice(palette))

    def _tick(self):
        dt = self._timer.interval() / 1000.0
        self._elapsed += self._timer.interval()
        for _i, _off in enumerate(self.wave_offsets_ms):
            if _off <= self._elapsed and _i not in self._waves_done:
                self._waves_done.add(_i)
                self._spawn_wave(_i)
        alive = []
        for pt in self._particles:
            pt["life"] -= dt
            if pt["life"] <= 0:
                continue
            pt["px"], pt["py"] = pt["x"], pt["y"]
            pt["vy"] += pt["gravity"] * dt
            _spin = pt.get("spin") or 0
            if _spin:
                _ca = math.cos(_spin * dt); _sa = math.sin(_spin * dt)
                pt["vx"], pt["vy"] = pt["vx"] * _ca - pt["vy"] * _sa, pt["vx"] * _sa + pt["vy"] * _ca
            pt["x"] += pt["vx"] * dt
            pt["y"] += pt["vy"] * dt
            alive.append(pt)
        self._particles = alive
        if self._elapsed >= self.duration_ms or (len(self._waves_done) >= len(self.wave_offsets_ms) and not self._particles):
            self._timer.stop()
            self.hide()
            return
        self.update()

    def paintEvent(self, event):
        if not self._particles:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for pt in self._particles:
            alpha = max(0.0, min(1.0, pt["life"] / pt["maxlife"]))
            col = QColor(pt["color"])
            col.setAlphaF(alpha)
            pen = QPen(col, 3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(pt["px"], pt["py"]), QPointF(pt["x"], pt["y"]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(col)
            painter.drawEllipse(QPointF(pt["x"], pt["y"]), pt["size"], pt["size"])


class DiagLogWindow(QDialog):
    """Floating diagnostic log, visible only in developer mode.

    Non-modal, movable, minimizable and closable; closing only hides it.
    Lines arrive through a queued signal so collection threads never
    touch widgets. Only timestamp labels and page ids are logged, never
    post body text.
    """
    append_requested = pyqtSignal(str)
    reset_tour_requested = pyqtSignal()
    restore_window_size_requested = pyqtSignal()
    apply_window_size_requested = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("诊断日志（开发者模式）")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self._placed = False
        self._clamping = False
        self._snap_timer = QTimer(self); self._snap_timer.setInterval(120)
        self._snap_timer.timeout.connect(self._snap_check)
        _parent = self.parentWidget()
        if _parent is not None:
            _parent.installEventFilter(self)
        self._listener = lambda text: self.append_requested.emit(text)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setPlaceholderText("暂无诊断记录；下一次巡检的发帖检测会显示在这里。")
        root = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        fw_btn = QPushButton("放烟花")
        fw_btn.setStyleSheet("QPushButton{background:#F59E0B;color:#FFFFFF;border:none;padding:7px 16px;} QPushButton:hover{background:#D97706;}")
        fw_btn.clicked.connect(self._test_fireworks)
        notify_btn = QPushButton("测试通知")
        notify_btn.clicked.connect(self._test_notification)
        bubble_btn = QPushButton("测试气泡")
        bubble_btn.clicked.connect(self._test_bubble)
        toolbar.addWidget(fw_btn)
        toolbar.addWidget(notify_btn)
        toolbar.addWidget(bubble_btn)
        _tdiv = QFrame()
        _tdiv.setFrameShape(QFrame.Shape.VLine)
        toolbar.addWidget(_tdiv)
        reset_btn = QPushButton("重设新手引导")
        reset_btn.clicked.connect(self.reset_tour_requested.emit)
        toolbar.addWidget(reset_btn)
        restore_btn = QPushButton("还原默认窗口尺寸")
        restore_btn.clicked.connect(self.restore_window_size_requested.emit)
        toolbar.addWidget(restore_btn)
        toolbar.addStretch()
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        toolbar.addWidget(divider)
        copy_btn = QPushButton("复制全部")
        copy_btn.clicked.connect(self._copy_all)
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self.view.clear)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.hide)
        toolbar.addWidget(copy_btn)
        toolbar.addWidget(clear_btn)
        toolbar.addWidget(close_btn)
        root.addLayout(toolbar)
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("窗口尺寸："))
        self._size_w = DirectNumberSpinBox()
        self._size_w.setRange(320, 3840)
        self._size_w.setFixedWidth(80)
        size_row.addWidget(self._size_w)
        size_row.addWidget(QLabel("×"))
        self._size_h = DirectNumberSpinBox()
        self._size_h.setRange(240, 2160)
        self._size_h.setFixedWidth(80)
        size_row.addWidget(self._size_h)
        _apply_size_btn = QPushButton("应用尺寸")
        _apply_size_btn.clicked.connect(self._apply_size)
        size_row.addWidget(_apply_size_btn)
        size_row.addStretch()
        root.addLayout(size_row)
        if _parent is not None:
            self._size_w.setValue(_parent.width())
            self._size_h.setValue(_parent.height())
        else:
            self._size_w.setValue(1230)
            self._size_h.setValue(720)
        status_row = QHBoxLayout()
        self._status_label = QLabel("共 0 行")
        self._status_label.setStyleSheet("color:#6B7280;")
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        live_label = QLabel("● 记录中")
        live_label.setStyleSheet("color:#16A34A;")
        status_row.addWidget(live_label)
        root.addLayout(status_row)
        root.addWidget(self.view, 1)
        footer = QLabel("关闭窗口仅隐藏，日志继续记录。")
        footer.setStyleSheet("color:#9CA3AF;")
        root.addWidget(footer)
        self.append_requested.connect(self._append)
        # Default to the smallest size the layout allows (the toolbar
        # row decides the width); dragging larger still works, and the
        # bottom-right dock on first show is unchanged.
        self.resize(self.minimumSizeHint())

    def _apply_size(self):
        self.apply_window_size_requested.emit(self._size_w.value(), self._size_h.value())

    def _refresh_status(self):
        self._status_label.setText("共 %d 行" % len(diag_log_snapshot()))

    def _test_fireworks(self):
        diag_log("[烟花] 手动测试播放一次")
        parent = self.parent()
        play = getattr(parent, "play_fireworks", None)
        if callable(play):
            play()

    def _test_notification(self):
        entries = [{"kind": "growth", "page_id": "0000000000000000",
                    "name": "测试主页", "growth": 600, "threshold": 500,
                    "window_seconds": 3600}]
        parent = self.parent()
        try:
            ok, detail = send_system_toast(
                entries, lambda: parent.switch_page(2) if parent is not None else None)
        except Exception as exc:
            ok, detail = False, str(exc)[:160]
        if ok:
            diag_log("[通知] 测试通知已发送")
        else:
            diag_log("[通知] 测试通知未发送：" + str(detail))
            show = getattr(parent, "show_toast", None)
            if callable(show):
                show("测试通知未发出：" + str(detail), kind="warning")

    def _test_bubble(self):
        parent = self.parent()
        show = getattr(parent, "show_toast", None)
        if callable(show):
            show("测试气泡：这是诊断日志窗口发出的测试提示。", kind="info")
        diag_log("[气泡] 测试气泡已显示")

    def _place_bottom_right(self):
        """First show only: dock at the main window's bottom-right with a
        margin, never flush against the edge. Later shows keep wherever
        the user moved the window."""
        if getattr(self, "_placed", False):
            return
        self._placed = True
        parent = self.parentWidget()
        if parent is None:
            return
        try:
            pg = parent.geometry()
            fw = self.frameGeometry()
            margin = 28
            x = pg.x() + pg.width() - fw.width() - margin
            y = pg.y() + pg.height() - fw.height() - margin
            screen = self.screen()
            if screen is not None:
                ag = screen.availableGeometry()
                x = max(ag.x() + 8, min(x, ag.x() + ag.width() - fw.width() - 8))
                y = max(ag.y() + 8, min(y, ag.y() + ag.height() - fw.height() - 8))
            self.move(x, y)
        except Exception:
            pass

    def _clamp_inside_parent(self):
        """Keep this floating window inside the main window: it can be
        dragged and resized, but never moved out of the main window.
        Clamping runs immediately, except mid-drag (see _defer_or_clamp):
        during a drag it snaps back once on release, so it never fights
        the window manager."""
        if getattr(self, "_clamping", False) or self.isMinimized():
            return
        parent = self.parentWidget()
        if parent is None or not self.isVisible():
            return
        try:
            pg = parent.frameGeometry()
            fg = self.frameGeometry()
            x = max(pg.x(), min(fg.x(), pg.x() + pg.width() - fg.width()))
            y = max(pg.y(), min(fg.y(), pg.y() + pg.height() - fg.height()))
            if (x, y) != (fg.x(), fg.y()):
                self._clamping = True
                try:
                    self.move(x, y)
                finally:
                    self._clamping = False
        except Exception:
            pass

    def _snap_check(self):
        # Dragging: wait until the mouse is released, then snap back once.
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            return
        self._snap_timer.stop()
        self._clamp_inside_parent()

    def _defer_or_clamp(self):
        # Clamping on every move event fights the window manager mid-drag
        # and flickers; wait for the release, then snap back once.
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            if not self._snap_timer.isActive():
                self._snap_timer.start()
        else:
            self._clamp_inside_parent()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._defer_or_clamp()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._defer_or_clamp()

    def eventFilter(self, watched, event):
        # The main window moved or resized: pull the log back inside.
        if watched is self.parentWidget() and event.type() in (QEvent.Type.Move, QEvent.Type.Resize):
            self._clamp_inside_parent()
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_placed", False):
            QTimer.singleShot(0, self._place_bottom_right)
        _pw = self.parentWidget()
        if _pw is not None:
            self._size_w.setValue(_pw.width())
            self._size_h.setValue(_pw.height())
        self.view.setPlainText("\n".join(diag_log_snapshot()))
        self._refresh_status()
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())
        add_diag_log_listener(self._listener)

    def hideEvent(self, event):
        self._snap_timer.stop()
        remove_diag_log_listener(self._listener)
        super().hideEvent(event)

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def _append(self, text):
        self.view.appendPlainText(text)
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())
        self._refresh_status()

    def _copy_all(self):
        QApplication.clipboard().setText(self.view.toPlainText())


def _subtitle(text, indent=0):
    lab = QLabel(text); lab.setObjectName("SmallMuted"); lab.setWordWrap(True)
    if indent:
        lab.setIndent(indent)
    return lab


class CloseChoiceDialog(QDialog):
    """Close-window confirmation, simple card style. One state, 2 cards
    (最小化到托盘 / 完全退出). A distinct floating window: the dialog
    itself is translucent and the content sits in an inner card with a
    2px theme-accent border and a drop shadow. The header is an inset
    rounded band in the theme's soft tint, with a red circular X
    button at its top-right. choice: background/stop/None. remember:
    the "记住我的选择" box."""

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setObjectName("CloseDialog")
        self.choice=None;self.remember=False
        preset=THEME_PRESETS.get(getattr(parent,"theme_name","云白"),THEME_PRESETS["云白"])
        panel=preset["panel"];panel2=preset["panel_2"];border=preset["border"]
        text=preset["text"];muted=preset["muted"];accent=preset["accent"]
        accent2=preset.get("accent2",accent);soft=preset["soft"]
        hover=preset["hover"]
        self._text=text
        self.setStyleSheet(
            "QDialog#CloseDialog{background:transparent;border:0;}"
            "QFrame#CloseDialogCard{background:%s;border:2px solid %s;border-radius:12px;}"
            "QFrame#CloseHeadBand{background:%s;border-radius:10px;}"
            "QLabel#CloseTitle{font-size:20px;font-weight:700;color:%s;}"
            "QLabel#CloseSub{font-size:14px;color:%s;}"
            "QPushButton#CloseX{background:#DC2626;border:0;border-radius:14px;color:#FFFFFF;font-size:20px;font-weight:700;padding:0;}"
            "QPushButton#CloseX:hover{background:#B91C1C;}"
            "QPushButton#CloseCard{background:%s;border:1px solid %s;border-radius:10px;padding:0;}"
            "QPushButton#CloseCard:hover{background:%s;border-color:%s;}"
            "QLabel#CloseTile{background:%s;border-radius:10px;}"
            "QLabel#CloseCardTitle{font-size:15px;font-weight:600;color:%s;}"
            "QLabel#CloseCardDesc{font-size:13px;color:%s;}"
            "QLabel#CloseChevron{color:%s;font-size:16px;}"
            "QCheckBox#CloseRemember{font-size:13px;color:%s;}"
            % (panel,accent,soft,text,muted,panel,border,hover,accent,
               panel2,text,muted,muted,text))
        # 548px wide: 500px card + 24px margins so the shadow is not clipped.
        self.setFixedWidth(548)
        outer=QVBoxLayout(self);outer.setContentsMargins(24,24,24,24)
        card=QFrame();card.setObjectName("CloseDialogCard")
        shadow=QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(22);shadow.setOffset(0,4);shadow.setColor(QColor(0,0,0,165))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)
        # Band is inset 16px from the card; the body is inset 8px further
        # (24px), so the band reads as a slightly wider block.
        root=QVBoxLayout(card);root.setContentsMargins(16,16,16,24);root.setSpacing(18)
        band=QFrame();band.setObjectName("CloseHeadBand")
        band_lay=QHBoxLayout(band);band_lay.setContentsMargins(18,16,18,16);band_lay.setSpacing(16)
        head_text=QVBoxLayout();head_text.setSpacing(6)
        title=QLabel("关闭程序");title.setObjectName("CloseTitle")
        sub=QLabel("请选择关闭窗口后的处理方式");sub.setObjectName("CloseSub")
        head_text.addWidget(title);head_text.addWidget(sub);band_lay.addLayout(head_text,1)
        xbtn=QPushButton("×");xbtn.setObjectName("CloseX");xbtn.setFixedSize(28,28)
        xbtn.setCursor(Qt.CursorShape.PointingHandCursor);xbtn.clicked.connect(self.reject)
        band_lay.addWidget(xbtn,0,Qt.AlignmentFlag.AlignTop)
        root.addWidget(band)
        body=QWidget()
        body_lay=QVBoxLayout(body);body_lay.setContentsMargins(8,0,8,0);body_lay.setSpacing(10)
        body_lay.addWidget(self._card("tray","最小化到托盘","窗口收起，程序继续在后台待命","background"))
        body_lay.addWidget(self._card("power","完全退出","停止任务立即退出","stop"))
        foot_wrap=QWidget()
        foot=QHBoxLayout(foot_wrap);foot.setContentsMargins(0,14,0,0)
        self._remember_box=QCheckBox("记住我的选择，下次不再询问")
        self._remember_box.setObjectName("CloseRemember");foot.addWidget(self._remember_box)
        foot.addStretch()
        body_lay.addWidget(foot_wrap)
        root.addWidget(body)

    def _card(self,icon,title,desc,choice):
        btn=QPushButton();btn.setObjectName("CloseCard")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # QPushButton's sizeHint ignores a custom layout (it is based on the
        # empty button text), so pin a minimum height: 40px tile / two text
        # lines (~44px) + 14px top/bottom margins = 72px. Without this the
        # button is 21px tall and the tile/title/desc are clipped to 0.
        btn.setMinimumHeight(72)
        lay=QHBoxLayout(btn);lay.setContentsMargins(16,14,16,14);lay.setSpacing(14)
        tile=QLabel();tile.setObjectName("CloseTile")
        tile.setFixedSize(40,40);tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setPixmap(ui_icon(icon,self._text).pixmap(QSize(20,20)))
        lay.addWidget(tile)
        text_lay=QVBoxLayout();text_lay.setSpacing(3)
        t=QLabel(title);t.setObjectName("CloseCardTitle");text_lay.addWidget(t)
        d=QLabel(desc);d.setObjectName("CloseCardDesc");d.setWordWrap(True);text_lay.addWidget(d)
        lay.addLayout(text_lay,1)
        chev=QLabel("›");chev.setObjectName("CloseChevron");lay.addWidget(chev)
        btn.clicked.connect(lambda _=False:self._pick(choice))
        return btn

    def _pick(self,choice):
        self.choice=choice;self.remember=self._remember_box.isChecked();self.accept()

    def exec_choice(self):
        self.exec();return self.choice,self.remember




class UpdateLogPanel(QWidget):
    """Right-side update log panel (400px). An OVERLAY: it covers the right
    side of the main window without resizing it. The same panel whether it
    is opened from Settings or auto-shown once after an update. Its colours
    come from the app stylesheet, so all three themes work."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UpdateLogPanel")
        self.setFixedWidth(400)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        head = QWidget()
        head_lay = QHBoxLayout(head)
        head_lay.setContentsMargins(20, 18, 20, 14)
        head_lay.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel("更新日志")
        tf = title.font(); tf.setBold(True); tf.setPointSize(17); title.setFont(tf)
        titles.addWidget(title)
        sub = QLabel("当前版本 v%s · 连接器 v%s" % (APP_VERSION, BUNDLED_CONNECTOR_VERSION))
        sub.setObjectName("SmallMuted")
        titles.addWidget(sub)
        head_lay.addLayout(titles, 1)
        close_btn = QPushButton("×")
        close_btn.setObjectName("UpdateLogClose")
        close_btn.setFixedSize(32, 32)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        head_lay.addWidget(close_btn)
        root.addWidget(head)
        div = QFrame(); div.setFrameShape(QFrame.Shape.HLine); div.setObjectName("HeaderDivider")
        root.addWidget(div)
        # Amber note: only when auto-shown right after an update.
        self._note_box = QWidget()
        note_wrap = QVBoxLayout(self._note_box)
        note_wrap.setContentsMargins(20, 14, 20, 0)
        self._note = QLabel("更新到 v%s 已完成，这次更新了下面这些内容。" % APP_VERSION)
        self._note.setWordWrap(True)
        self._note.setStyleSheet("QLabel{background:#FFFBEB;border:1px solid #F59E0B;border-radius:10px;color:#92400E;padding:10px 12px;font-size:12.5px;}")
        note_wrap.addWidget(self._note)
        self._log_wrap_labels = [self._note]
        self._note_box.hide()
        root.addWidget(self._note_box)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:0;background:transparent;} QScrollArea QWidget{background:transparent;}")
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 16, 20, 20)
        bl.setSpacing(0)
        for vi, entry in enumerate(CHANGELOG):
            hrow = QHBoxLayout()
            hrow.setSpacing(6)
            vlab = QLabel("v" + entry["version"])
            vlab.setObjectName("UpdateLogVersion")
            hrow.addWidget(vlab)
            if entry["date"]:
                dlab = QLabel(entry["date"])
                dlab.setObjectName("SmallMuted")
                hrow.addWidget(dlab)
            hrow.addStretch()
            bl.addLayout(hrow)
            for grp in entry["groups"]:
                glab = QLabel(grp["title"])
                glab.setObjectName("UpdateLogGroup")
                bl.addSpacing(10)
                bl.addWidget(glab)
                for item in grp["items"]:
                    row = QHBoxLayout()
                    row.setContentsMargins(0, 0, 0, 0)
                    row.setSpacing(8)
                    dot = QLabel("•")
                    dot.setObjectName("UpdateLogDot")
                    row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
                    lab = QLabel(item)
                    lab.setWordWrap(True)
                    lab.setTextFormat(Qt.TextFormat.PlainText)
                    row.addWidget(lab, 1)
                    self._log_wrap_labels.append(lab)
                    bl.addLayout(row)
                    bl.addSpacing(5)
            if entry["connector"]:
                conn = QLabel(entry["connector"])
                conn.setObjectName("SmallMuted")
                conn.setWordWrap(True)
                conn.setTextFormat(Qt.TextFormat.PlainText)
                bl.addSpacing(10)
                bl.addWidget(conn)
                self._log_wrap_labels.append(conn)
            # Clear separation between versions: a divider line.
            if vi < len(CHANGELOG) - 1:
                bl.addSpacing(16)
                vdiv = QFrame(); vdiv.setFrameShape(QFrame.Shape.HLine); vdiv.setObjectName("HeaderDivider")
                bl.addWidget(vdiv)
                bl.addSpacing(16)
        bl.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def show_log(self, just_updated=False):
        self._note_box.setVisible(bool(just_updated))
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.width() - 400, 0, 400, parent.height())
        self.show()
        self.raise_()
        self._fit_log_rows()
        QTimer.singleShot(0, self._fit_log_rows)

    def _fit_log_rows(self):
        """Pin every word-wrapped log label to the height its wrapped text
        actually needs at its real width. Qt lays the rows out before the
        labels know their final width inside the scroll area, so items that
        wrap to 3 lines only get ~44px instead of 57px and the last line is
        cut (this hit 1.7.1+ because those entries first grew 3-line items;
        shorter entries never showed it). Measuring here, after the panel
        has its width, fixes every version at once."""
        for lab in getattr(self, "_log_wrap_labels", []):
            w = lab.width()
            if w <= 0:
                continue
            need = lab.fontMetrics().boundingRect(
                QRect(0, 0, w, 100000), Qt.TextFlag.TextWordWrap,
                lab.text()).height()
            lab.setMinimumHeight(need)

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
        self._patrol_queue=[];self._patrol_running=[]
        self._closing=False;self._maintenance=False;self._tray_hint_shown=False;self._exit_after_round=False
        self.auto_enabled=False;self.next_run_at=None;self.active_run_id=None
        self.run_started_at=None;self.run_ok=0;self.run_fail=0;self.current_purpose="monitor"
        self._tick=0;self._popup=None;self._notice_queue=[];self._toast=None;self._diag_window=None;self._fireworks_overlay=None;self._growth_alert_seen=None;self._fireworks_pending=0;self._fireworks_queue=0
        self._grace_timer=QTimer(self);self._grace_timer.setInterval(1000);self._grace_timer.timeout.connect(self._on_grace_tick);self._grace_remaining=0
        self._badge_show_next=False
        self._badge_timer=QTimer(self);self._badge_timer.setInterval(20000);self._badge_timer.timeout.connect(self._on_badge_timer)
        self.auto_timer=QTimer(self);self.auto_timer.setSingleShot(True)
        self.auto_timer.timeout.connect(lambda:self.start_collection(False))
        self.count_timer=QTimer(self);self.count_timer.setInterval(1000);self.count_timer.timeout.connect(self.update_countdown)
        self.paint_timer=QTimer(self);self.paint_timer.setSingleShot(True);self.paint_timer.timeout.connect(self.refresh_all)
        self.notice_timer=QTimer(self);self.notice_timer.setSingleShot(True);self.notice_timer.timeout.connect(self.flush_notices)
        self.apply_theme(str(self.settings.value("ui_theme","云白")),refresh=False)
        app_icon=make_app_icon()
        QApplication.instance().setWindowIcon(app_icon)
        self.setWindowIcon(app_icon);self.setWindowTitle(APP_TITLE+" · "+APP_VERSION)
        self.resize(1230,720);self.setMinimumSize(1024,650)
        self.tray=QSystemTrayIcon(make_app_icon(),self);self.tray.setToolTip(APP_TITLE)
        self.tray_menu=QMenu(self)
        self.tray_menu.addAction("打开软件",self.show_dashboard)
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
        if self.settings.value(MODULES_ASKED_KEY) is not None:
            QTimer.singleShot(400,self._maybe_show_tour);return
        dlg=FirstRunDialog(self)
        dlg.exec()
        self.settings.setValue(MODULE_GROWTH_KEY,1)
        self.settings.setValue(MODULE_POSTS_KEY,1 if dlg.choice=="both" else 0)
        self.settings.setValue(MODULES_ASKED_KEY,1)
        self.settings.sync()
        self.settings_page.load_settings()
        self.refresh_all()
        QTimer.singleShot(400,self._maybe_show_tour)

    def _get_tour(self):
        if getattr(self,"_tour",None) is None:
            self._tour=OnboardingTour(self)
        return self._tour

    def _maybe_show_tour(self):
        """Show the tour welcome once per version, to old and new users."""
        if self._closing:return
        if self.settings.value(TOUR_DONE_KEY) is not None:return
        if self.worker is not None:return
        self._get_tour().show_welcome()

    def reset_tour(self):
        """Developer-mode reset: treat the app as first-time use again."""
        self.settings.remove(TOUR_DONE_KEY);self.settings.sync()
        if self._closing:return
        if self.worker is not None:return
        self._get_tour().show_welcome()
        # The developer log window closes once the tour is reset, so it
        # does not sit on top of the welcome.
        if self._diag_window is not None:
            try:
                self._diag_window.close()
            except Exception:
                pass

    def show_update_log(self, just_updated=False):
        """Open the update log panel on the right (same panel from
        Settings and after an update)."""
        if getattr(self, "_update_log_panel", None) is None:
            return
        self._update_log_panel.show_log(just_updated=just_updated)

    def hide_update_log(self):
        if getattr(self, "_update_log_panel", None) is not None:
            self._update_log_panel.hide()

    @staticmethod
    def _set_paths(path):
        global DATA_DIR,DB_PATH,BROWSER_PROFILE_DIR,AVATAR_DIR
        DATA_DIR=ensure_private_directory(Path(path))
        DB_PATH=DATA_DIR/"fb_growth_radar_v1.db";BROWSER_PROFILE_DIR=DATA_DIR/"browser_profile";AVATAR_DIR=DATA_DIR/"avatars"

    def build_ui(self):
        root=QWidget();root.setObjectName("Root");self.setCentralWidget(root)
        self._root_layout=QVBoxLayout(root);self._root_layout.setContentsMargins(1,1,1,1);self._root_layout.setSpacing(0)
        self._version_corner = QLabel("V " + APP_VERSION + " · Windows 版", root)
        self._version_corner.setObjectName("SmallMuted")
        self._version_corner.hide()
        shell=QHBoxLayout();shell.setContentsMargins(0,0,0,0);shell.setSpacing(0)
        self.sidebar=QWidget();self.sidebar.setObjectName("Sidebar");self.sidebar.setFixedWidth(240)
        side=QVBoxLayout(self.sidebar);side.setContentsMargins(14,12,14,10);side.setSpacing(0)
        self._sidebar_collapsed=False;self._nav_button_texts={}
        self._sidebar_auto_collapsed=False;self._last_width=None
        brand=DraggableHeader();brand.setObjectName("BrandRow");self._brand_row=brand
        brand_lay=QHBoxLayout(brand);brand_lay.setContentsMargins(6,2,6,8);brand_lay.setSpacing(10)
        self.brand_mark=BrandMark(48);brand_lay.addWidget(self.brand_mark)
        brand_text=QVBoxLayout();brand_text.setSpacing(1)
        self.brand_name=QLabel(APP_TITLE);self.brand_name.setObjectName("BrandName")
        self.brand_name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True);brand_text.addWidget(self.brand_name)
        tagline=QLabel("Facebook 主页监控");tagline.setObjectName("BrandSub")
        tagline.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True);brand_text.addWidget(tagline)
        brand_lay.addLayout(brand_text,1);side.addWidget(brand)
        self.brand_caption=tagline
        self.nav_style=self._read_nav_style();self.sidebar.setProperty("navStyle",self.nav_style)
        self._nav_group_1=QFrame();self._nav_group_1.setObjectName("NavGroup")
        _g1=QVBoxLayout(self._nav_group_1);_g1.setContentsMargins(0,0,0,0);_g1.setSpacing(1);side.addWidget(self._nav_group_1)
        nav_label=QLabel("监控");nav_label.setObjectName("NavLabel");_g1.addWidget(nav_label);self._nav_label_monitor=nav_label
        self.nav_buttons={}
        for index,kind,text in ((0,"home","监控看板"),(1,"trend","趋势"),(2,"bell","通知"),(3,"pages","ID管理")):
            row=QHBoxLayout();row.setContentsMargins(0,0,0,0);row.setSpacing(0)
            btn=QPushButton(text);btn.setObjectName("SideNav");btn.setProperty("iconKind",kind);self._nav_button_texts[index]=text
            btn.setIcon(ui_icon(kind,MUTED));btn.setIconSize(QSize(22,22));btn.setFixedHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False,i=index:self.switch_page(i))
            row.addWidget(btn,1)
            if index==2:
                self.notification_badge=QLabel(btn);self.notification_badge.setObjectName("NotificationBadge")
                self.notification_badge.setFixedSize(19,17);self.notification_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.notification_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
            wrap=QWidget();wrap.setLayout(row);_g1.addWidget(wrap);self.nav_buttons[index]=btn
        self._nav_gap_w=QWidget();self._nav_gap_w.setFixedHeight(0);side.addWidget(self._nav_gap_w)
        self._nav_group_2=QFrame();self._nav_group_2.setObjectName("NavGroup")
        _g2=QVBoxLayout(self._nav_group_2);_g2.setContentsMargins(0,0,0,0);_g2.setSpacing(1);side.addWidget(self._nav_group_2)
        nav_label2=QLabel("系统");nav_label2.setObjectName("NavLabel");_g2.addWidget(nav_label2);self._nav_label_system=nav_label2
        btn=QPushButton("设置");btn.setObjectName("SideNav");btn.setProperty("iconKind","settings");self._nav_button_texts[4]="设置"
        btn.setIcon(ui_icon("settings",MUTED));btn.setIconSize(QSize(22,22));btn.setFixedHeight(40)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda:self.switch_page(4));_g2.addWidget(btn);self.nav_buttons[4]=btn
        self.page_nav_buttons=dict(self.nav_buttons)
        side.addStretch(1)
        self.connector_card=ClickableFrame();self.connector_card.setObjectName("ConnCard")
        conn_lay=QVBoxLayout(self.connector_card);conn_lay.setContentsMargins(12,9,12,9);conn_lay.setSpacing(3)
        title_row=QHBoxLayout();title_row.setSpacing(7);self._connector_title_row=title_row
        self.connector_dot=QLabel();self.connector_dot.setObjectName("ConnectorDot");self.connector_dot.setFixedSize(10,10)
        self.connector_dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        title_row.addWidget(self.connector_dot)
        self.connector_title=QLabel("浏览器连接");self.connector_title.setObjectName("ConnTitle");title_row.addWidget(self.connector_title,1)
        self.connector_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        conn_lay.addLayout(title_row)
        self.connector_sub=QLabel("连接器 v"+BUNDLED_CONNECTOR_VERSION+" · 点击查看");self.connector_sub.setObjectName("SmallMuted");self.connector_sub.setWordWrap(True);conn_lay.addWidget(self.connector_sub)
        _collapsed_box=QWidget();_cl=QVBoxLayout(_collapsed_box);_cl.setContentsMargins(0,2,0,2);_cl.setSpacing(2);_cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._conn_collapsed_icon=QLabel();self._conn_collapsed_icon.setFixedSize(22,22);_cl.addWidget(self._conn_collapsed_icon,0,Qt.AlignmentFlag.AlignCenter)
        self._conn_collapsed_count=QLabel("0 个");self._conn_collapsed_count.setObjectName("SmallMuted");_cl.addWidget(self._conn_collapsed_count,0,Qt.AlignmentFlag.AlignCenter)
        conn_lay.addWidget(_collapsed_box);self._conn_collapsed_box=_collapsed_box;_collapsed_box.hide()
        self.connector_sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        self.connector_card.clicked.connect(self.open_login_browser);side.addWidget(self.connector_card)
        side.addSpacing(10)
        theme_row=QHBoxLayout();theme_row.setContentsMargins(4,0,4,0)
        theme_label=QLabel("外观");theme_label.setObjectName("SmallMuted");theme_row.addWidget(theme_label);self._theme_label=theme_label
        self.theme_name_label=QLabel(self.theme_name);self.theme_name_label.setObjectName("SmallMuted");theme_row.addWidget(self.theme_name_label)
        theme_row.addStretch()
        self.theme_swatches={}
        for name in THEME_PRESETS:
            sw=QPushButton();sw.setFixedSize(20,20);sw.setCursor(Qt.CursorShape.PointingHandCursor)
            sw.clicked.connect(lambda _=False,n=name:self.apply_theme(n));theme_row.addWidget(sw);self.theme_swatches[name]=sw
        side.addLayout(theme_row)
        self._refresh_theme_swatches(self.theme_name)
        foot=QLabel("V "+APP_VERSION+" · Windows 版");foot.setObjectName("SideFoot");side.addWidget(foot);self._sidebar_foot=foot
        _collapsed_theme_box=QWidget();_ctb_lay=QHBoxLayout(_collapsed_theme_box);_ctb_lay.setContentsMargins(0,4,0,0);_ctb_lay.setSpacing(4);_ctb_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._collapsed_theme_swatches={}
        for _name in THEME_PRESETS:
            _sw=QPushButton();_sw.setFixedSize(14,14);_sw.setCursor(Qt.CursorShape.PointingHandCursor)
            _sw.clicked.connect(lambda _=False,n=_name:self.apply_theme(n));_ctb_lay.addWidget(_sw);self._collapsed_theme_swatches[_name]=_sw
        side.addWidget(_collapsed_theme_box);self._collapsed_theme_box=_collapsed_theme_box;_collapsed_theme_box.hide()
        self._refresh_theme_swatches(self.theme_name)
        _toggle_row=QHBoxLayout();_toggle_row.setContentsMargins(0,6,0,0);self._toggle_row=_toggle_row
        self._sidebar_toggle=QPushButton("‹ 收起导航栏");self._sidebar_toggle.setObjectName("SideCollapse");self._sidebar_toggle.setFixedHeight(28);self._sidebar_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sidebar_toggle.setToolTip("收起导航栏");self._sidebar_toggle.clicked.connect(self.toggle_sidebar_collapsed)
        _toggle_row.addWidget(self._sidebar_toggle);side.addLayout(_toggle_row)
        self._apply_nav_metrics()
        if is_true(self.settings.value("sidebar/collapsed",0)):self.set_sidebar_collapsed(True)
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
        self.trend=TrendPage(self.store,self.settings)
        self.alerts=AlertsPage(self.store,self.settings)
        self.page_manager=PageManagementPage(self.store,self.settings)
        self.settings_page=SettingsPage(self.store,self.settings)
        for page in (self.dashboard,self.trend,self.alerts,self.page_manager,self.settings_page):self.stack.addWidget(page)
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
        self._update_log_panel=UpdateLogPanel(self);self._update_log_panel.hide()
        self._root_layout.addLayout(shell,1)
        self.wire_signals();self.switch_page(0);self._update_window_shape()

    def restore_default_window_size(self):
        """Developer-mode helper: put the main window back to 1536x800."""
        try:
            if self.isMaximized():self.showNormal()
            self.resize(1230,720)
            diag_log("[窗口] 已还原默认尺寸 1230x720")
        except Exception as exc:
            diag_log(f"[窗口] 还原默认尺寸失败：{exc}")

    def apply_window_size(self, width, height):
        """Developer-mode helper: resize the main window to the given size."""
        try:
            if self.isMaximized():self.showNormal()
            w = max(int(width), self.minimumWidth())
            h = max(int(height), self.minimumHeight())
            self.resize(w, h)
            diag_log(f"[窗口] 已应用尺寸 {w}x{h}")
        except Exception as exc:
            diag_log(f"[窗口] 应用尺寸失败：{exc}")

    def toggle_sidebar_collapsed(self):
        _was=getattr(self,"_sidebar_collapsed",False)
        self.set_sidebar_collapsed(not _was)
        # Manual choice from here on: never auto-expand a sidebar the user
        # collapsed by hand, and never auto-collapse one they expanded.
        self._sidebar_auto_collapsed=False
        if _was and not getattr(self,"_sidebar_collapsed",False) and self.width()<1200:
            # Manual expand in a narrow window: grow the window by the
            # sidebar width difference so the content area does not shrink.
            # Clamp to the screen so it never grows off the right edge.
            _max_w=self.width()+176
            _scr=QApplication.primaryScreen()
            if _scr is not None:
                _avail=_scr.availableGeometry()
                _max_w=min(_max_w,_avail.right()-self.x()+1)
            if _max_w>self.width():self.resize(_max_w,self.height())

    def set_sidebar_collapsed(self,collapsed):
        """Collapse the left nav to a 64px icon-only column (Teams style)."""
        collapsed=bool(collapsed);self._sidebar_collapsed=collapsed
        try:self.settings.setValue("sidebar/collapsed",1 if collapsed else 0)
        except Exception:pass
        self.sidebar.setFixedWidth(64 if collapsed else 240)
        _lay=self.sidebar.layout()
        if collapsed:_lay.setContentsMargins(6,12,6,10)
        else:_lay.setContentsMargins(14,12,14,10)
        self.brand_name.setVisible(not collapsed);self.brand_caption.setVisible(not collapsed)
        self._brand_row.layout().setAlignment(Qt.AlignmentFlag.AlignCenter if collapsed else Qt.AlignmentFlag.AlignLeft)
        # Collapsed rail is 64px: sidebar margins 6+6 leave 52px, so the
        # brand row's 6+6 margins clipped the 48px mark (6+48+6=60>52).
        # 2px margins fit exactly (2+48+2=52) and keep the mark centered.
        self._brand_row.layout().setContentsMargins(*((2,2,2,8) if collapsed else (6,2,6,8)))
        self._nav_label_monitor.setVisible(not collapsed);self._nav_label_system.setVisible(not collapsed)
        for _idx,_btn in self.nav_buttons.items():
            _txt=self._nav_button_texts.get(_idx,"")
            if collapsed:_btn.setText("");_btn.setToolTip(_txt)
            else:_btn.setText(_txt);_btn.setToolTip("")
        self.connector_title.setVisible(not collapsed);self.connector_sub.setVisible(not collapsed)
        self.connector_dot.setVisible(not collapsed)
        if hasattr(self,"_conn_collapsed_box"):self._conn_collapsed_box.setVisible(collapsed)
        self.connector_card.setToolTip("浏览器连接 v"+BUNDLED_CONNECTOR_VERSION+" · 点击查看" if collapsed else "")
        self._connector_title_row.setAlignment(Qt.AlignmentFlag.AlignCenter if collapsed else Qt.AlignmentFlag.AlignLeft)
        self._theme_label.setVisible(not collapsed);self.theme_name_label.setVisible(not collapsed)
        for _name,_sw in self.theme_swatches.items():_sw.setVisible(not collapsed)
        self._sidebar_foot.setVisible(not collapsed)
        if hasattr(self, "_version_corner"):
            self._version_corner.setVisible(collapsed)
            if collapsed:
                self._position_version_corner()
        if hasattr(self,"_collapsed_theme_box"):self._collapsed_theme_box.setVisible(collapsed)
        if collapsed:
            self._sidebar_toggle.setText("›");self._sidebar_toggle.setFixedSize(24,28)
            self._toggle_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self._sidebar_toggle.setText("‹ 收起导航栏");self._sidebar_toggle.setMinimumSize(0,28);self._sidebar_toggle.setMaximumSize(16777215,28)
            self._toggle_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._sidebar_toggle.setToolTip("展开导航栏" if collapsed else "收起导航栏")
        self._apply_nav_metrics()
        QTimer.singleShot(0,self._position_notification_badge)

    def _position_version_corner(self):
        """Keep the collapsed-state version label pinned to the
        bottom-right corner of the whole window."""
        lab = getattr(self, "_version_corner", None)
        if lab is None or not lab.isVisible():
            return
        cw = self.centralWidget()
        if cw is None:
            return
        lab.adjustSize()
        lab.move(max(0, cw.width() - lab.width() - 12),
                 max(0, cw.height() - lab.height() - 8))
        lab.raise_()

    # ---- sidebar look (设置 → 外观 → 导航栏样式) -------------------------
    def _read_nav_style(self):
        key=str(self.settings.value("nav_style",NAV_DEFAULT_STYLE) or NAV_DEFAULT_STYLE)
        return key if key in NAV_STYLE_KEYS else NAV_DEFAULT_STYLE

    def _repolish_tree(self,widget):
        for w in [widget]+widget.findChildren(QWidget):
            w.style().unpolish(w);w.style().polish(w)

    def _nav_dot_ring(self):
        """Ring colour of the connector status dot = background of its card."""
        st=getattr(self,"nav_style","")
        if st=="dark":return nav_dark_palette(getattr(self,"theme_name","云白"))["glass"]
        return PANEL if st=="capsule" else (SIDEBAR if st=="line" else BG)

    def _nav_pad(self):
        """Left padding of a nav button (used to place the unread badge)."""
        if getattr(self,"_sidebar_collapsed",False):return 10
        return 14 if getattr(self,"nav_style","")=="capsule" else 10

    def _apply_nav_metrics(self):
        """Sizes/margins that QSS cannot express, then re-polish the sidebar."""
        if not hasattr(self,"_nav_group_1") or not hasattr(self,"_nav_group_2"):return
        st=getattr(self,"nav_style",NAV_DEFAULT_STYLE);col=bool(getattr(self,"_sidebar_collapsed",False))
        self.sidebar.setProperty("navStyle",st);self.sidebar.setProperty("navCollapsed",col)
        if st=="capsule":margins=(4,2,4,4) if col else (6,4,6,6);height=42;gap=10
        else:margins=(0,0,0,0);height=40 if st=="dark" else 38;gap=0
        for group in (self._nav_group_1,self._nav_group_2):group.layout().setContentsMargins(*margins)
        self._nav_gap_w.setFixedHeight(gap)
        for btn in self.nav_buttons.values():btn.setFixedHeight(height)
        self._repolish_tree(self.sidebar)
        self._refresh_nav_icons()
        QTimer.singleShot(0,self._position_notification_badge)

    def _refresh_nav_icons(self,unread=None):
        """Colour the sidebar icons for the active look and the active page."""
        if not hasattr(self,"page_nav_buttons"):return
        if unread is not None:self._nav_unread=int(unread or 0)
        st=getattr(self,"nav_style",NAV_DEFAULT_STYLE)
        d=nav_dark_palette(getattr(self,"theme_name","云白"))
        for btn in self.page_nav_buttons.values():
            kind=btn.property("iconKind");active=bool(btn.property("active"))
            if st=="capsule":color="#FFFFFF" if active else MUTED
            elif st=="dark":color=d["accent"] if active else d["muted"]
            else:color=ACCENT if active else MUTED
            if kind=="bell" and getattr(self,"_nav_unread",0)>0 and not (active and st=="capsule"):
                color="#F87171" if st=="dark" else RED
            btn.setIcon(ui_icon(kind,color))

    def apply_nav_style(self,key):
        self.nav_style=key if key in NAV_STYLE_KEYS else NAV_DEFAULT_STYLE
        self._apply_nav_metrics()
        self.sidebar.update()

    def _nav_style_sheet(self,hover,soft):
        d=nav_dark_palette(getattr(self,"theme_name","云白"))
        c="QWidget#Sidebar[navStyle='capsule']";l="QWidget#Sidebar[navStyle='line']";k="QWidget#Sidebar[navStyle='dark']"
        return f"""
            QFrame#NavGroup {{ background:transparent;border:0; }}
            {c} {{ background:{BG}; }}
            {c} QFrame#NavGroup {{ background:{PANEL};border:1px solid {BORDER};border-radius:14px; }}
            {c} QLabel#NavLabel {{ font-size:11px;font-weight:700;padding:6px 10px 4px; }}
            {c} QPushButton#SideNav {{ border-radius:21px;padding:0 14px;font-size:14px;font-weight:600; }}
            {c} QPushButton#SideNav:hover {{ background:{hover}; }}
            {c} QPushButton#SideNav[active='true'] {{ background:{ACCENT};color:#FFFFFF;font-weight:700; }}
            {c}[navCollapsed='true'] QPushButton#SideNav {{ padding:0px;text-align:center; }}
            {c} QFrame#ConnCard {{ background:{PANEL};border-radius:18px; }}
            {c} QPushButton#SideCollapse {{ font-size:13px;font-weight:600;border-radius:14px; }}
            {l} QLabel#NavLabel {{ font-size:11px;font-weight:600;padding:10px 10px 4px; }}
            {l} QPushButton#SideNav {{ border-radius:8px;padding:0 10px;font-size:14px;font-weight:500; }}
            {l} QPushButton#SideNav:hover {{ background:{hover}; }}
            {l} QPushButton#SideNav[active='true'] {{ background:{soft};color:{ACCENT};font-weight:700;border-left:3px solid {ACCENT};border-top-left-radius:0px;border-bottom-left-radius:0px;padding-left:7px; }}
            {l}[navCollapsed='true'] QPushButton#SideNav {{ padding:0px;text-align:center; }}
            {l}[navCollapsed='true'] QPushButton#SideNav[active='true'] {{ border-left:0;border-radius:8px;padding:0px;text-align:center; }}
            {l} QFrame#ConnCard {{ background:transparent;border-radius:8px; }}
            {l} QPushButton#SideCollapse {{ font-size:13px;font-weight:600; }}
            {k} {{ background:{d['bg']};border-right:1px solid {d['border']}; }}
            {k} QLabel {{ color:{d['text']}; }}
            {k} QLabel#BrandName, {k} QLabel#ConnTitle, {k} QLabel#NotificationBadge {{ color:#FFFFFF; }}
            {k} QLabel#BrandSub, {k} QLabel#NavLabel, {k} QLabel#SmallMuted, {k} QLabel#SideFoot {{ color:{d['muted']}; }}
            {k} QLabel#NavLabel {{ font-size:11px;font-weight:600;padding:10px 10px 4px; }}
            {k} QPushButton#SideNav {{ border-radius:8px;padding:0 12px;font-size:14px;font-weight:500;color:{d['text']}; }}
            {k} QPushButton#SideNav:hover {{ background:{d['hover']}; }}
            {k} QPushButton#SideNav[active='true'] {{ background:{d['active']};color:#FFFFFF;font-weight:700; }}
            {k}[navCollapsed='true'] QPushButton#SideNav {{ padding:0px;text-align:center; }}
            {k} QFrame#ConnCard {{ background:{d['glass']};border:1px solid {d['border']};border-radius:12px; }}
            {k} QFrame#ConnCard:hover {{ border-color:{d['accent']}; }}
            {k} QPushButton#SideCollapse {{ color:{d['muted']};font-size:13px;font-weight:600; }}
            {k} QPushButton#SideCollapse:hover {{ color:#FFFFFF;background:{d['hover']}; }}
        """

    def wire_signals(self):
        d=self.dashboard;d.collect_once.connect(self.dashboard_run_button);d.toggle_auto.connect(self.toggle_auto);d.grace_cancel_requested.connect(self._on_grace_cancel)
        d.view_alerts.connect(lambda:self.switch_page(2));d.open_manager.connect(self.open_manager)
        d.delete_page.connect(lambda pid:self.delete_ids([pid]))
        d.open_page.connect(self.open_page);d.open_settings_requested.connect(lambda:self.switch_page(4))
        d.collect_subset_requested.connect(self.start_subset_collection)
        d.cancel_patrol_requested.connect(self.cancel_current_patrol)
        d.inspect_page.connect(self.inspect_single_page);d.sync_page.connect(lambda pid:self.sync_profiles([pid]))
        d.inspect_requested.connect(self.inspect_pages)
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
        settings.progress_style_requested.connect(self._on_progress_style_changed)
        settings.card_layout_requested.connect(self._on_card_layout_changed)
        settings.nav_style_requested.connect(self.apply_nav_style)
        settings.export_requested.connect(self.export_csv)
        settings.data_dir_requested.connect(self.move_data_directory)
        settings.dev_mode_requested.connect(self.set_dev_mode)
        settings.manual_update_check_requested.connect(lambda:self.check_for_updates(manual=True))
        settings.view_update_log_requested.connect(lambda:self.show_update_log(just_updated=False))
        settings.fireworks_preview_requested.connect(self.play_fireworks)
        self.set_dev_mode(is_true(self.settings.value("dev_mode", False), False))

    def _on_progress_style_changed(self, style):
        self.dashboard.set_progress_style(style)

    def _on_card_layout_changed(self, key):
        self.dashboard.set_card_layout(key)

    def _request_fireworks(self,count=1):
        """Queue `count` firework plays; each plays in turn (one play ~7s)."""
        if count<=0:return
        self._fireworks_queue+=int(count);self._drain_fireworks_queue()

    def _drain_fireworks_queue(self):
        if getattr(self,"_fireworks_queue",0)<=0:return
        _ov=self._fireworks_overlay
        if _ov is not None and _ov._timer.isActive():
            QTimer.singleShot(1000,self._drain_fireworks_queue);return
        self._fireworks_queue-=1;self.play_fireworks()
        QTimer.singleShot(7100,self._drain_fireworks_queue)

    def play_fireworks(self):
        if self._fireworks_overlay is None:
            self._fireworks_overlay = FireworksOverlay(self)
        self._fireworks_overlay.play()
        QTimer.singleShot(300, self._fireworks_visibility_check)

    def _fireworks_visibility_check(self):
        """Fallback: if the overlay failed to appear on a visible window,
        say so in the log and fall back to the universal bubble, so the
        event itself is never silently lost."""
        ov = self._fireworks_overlay
        if ov is None or not ov._timer.isActive():
            return
        if self.isVisible() and not self.isMinimized() and not ov.isVisible():
            diag_log("[烟花] 覆层未能显示，已改用气泡提示")
            self.show_toast("发现粉丝增长超标（烟花特效未能显示）", kind="info")

    def _check_fireworks(self):
        """Play once when a patrol surfaces over-threshold pages.

        Fallbacks, so a real celebration is never silently swallowed:
        the first patrol of the session fires when it collected readings
        and anything is over the threshold (no silent baseline); later
        patrols fire for newly over-threshold pages and for pages with
        a growth alert created by this run. If the dashboard is not the
        visible page, the play is deferred until the user switches back.
        """
        if not modules_growth_enabled(self.settings):
            return
        if not is_true(self.settings.value("fireworks_enabled", True), True):
            return
        current = set(getattr(self.dashboard, "_growth_alert_ids", None) or set())
        fresh = set()
        started = getattr(self, "run_started_at", None)
        if started:
            try:
                for _a in self.store.alert_rows(500):
                    if float(_a.get("alerted_ts") or 0) >= float(started) and not _a.get("acknowledged"):
                        fresh.add(str(_a.get("page_id") or ""))
            except Exception:
                fresh = set()
        previous = self._growth_alert_seen
        if previous is None:
            self._growth_alert_seen = set(current)
            collected = (getattr(self, "run_ok", 0) + getattr(self, "run_fail", 0)) > 0
            new = set(current) if (current and collected) else set()
            if not new:
                diag_log("[烟花] 首次巡检，已记录基线 %d 个" % len(current))
                return
        else:
            new = (current - previous) | (fresh & current)
            self._growth_alert_seen = set(current)
        if not new:
            return
        if self.stack.currentIndex() == 0 and self.isVisible() and not self.isMinimized():
            diag_log("[烟花] 本轮新增超标 %d 个，逐个播放" % len(new))
            self._request_fireworks(len(new))
        else:
            diag_log("[烟花] 本轮新增超标 %d 个，切回看板时播放" % len(new))
            self._fireworks_pending += len(new)

    def set_dev_mode(self, on):
        on = bool(on)
        # Developer mode minimum is 1080x560 (user-set test size);
        # turning it off restores the normal 1024x650.
        # The sidebar keeps its fixed width; only the centre is allowed to
        # shrink, so the smaller floor is reachable without the sidebar
        # being squeezed away.
        self.setMinimumSize(1080, 560) if on else self.setMinimumSize(1024, 650)
        _center = self.stack.parentWidget() if hasattr(self, "stack") else None
        if on:
            self.sidebar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
            if _center is not None:
                _center.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        else:
            self.sidebar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            if _center is not None:
                _center.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self.set_sidebar_collapsed(getattr(self, "_sidebar_collapsed", False))
        self.updateGeometry()
        _lay = self.layout()
        if _lay is not None:
            _lay.activate()
        if on:
            if self._diag_window is None:
                self._diag_window = DiagLogWindow(self)
                self._diag_window.reset_tour_requested.connect(self.reset_tour)
                self._diag_window.restore_window_size_requested.connect(self.restore_default_window_size)
                self._diag_window.apply_window_size_requested.connect(self.apply_window_size)
            self._diag_window.show()
            self._diag_window.raise_()
            self._diag_window.activateWindow()
        elif self._diag_window is not None:
            self._diag_window.hide()

    def switch_page(self,index):
        if index not in (0,1,2,3,4):index=0
        self.stack.setCurrentIndex(index)
        if not self._ui_restoring:
            self.settings.setValue("ui/page",index);self.settings.sync()
        for idx,button in self.page_nav_buttons.items():
            _new_active=(idx==index)
            if button.property("active")!=_new_active:
                button.setProperty("active",_new_active);button.style().unpolish(button);button.style().polish(button)
        self._refresh_nav_icons()
        if hasattr(self,"dashboard") and hasattr(self.dashboard,"action_bar"):
            self.dashboard.action_bar.setVisible(index==0)
        titles={0:("监控看板","粉丝与发帖监控 · 数据保存在本地"),1:("增长趋势","每天粉丝变化曲线"),2:("通知","未读通知与历史记录"),3:("ID管理","一次添加，多模块共用"),4:("设置","浏览器连接、巡检、提醒与数据")}
        title,sub=titles[index]
        if index==0:
            _posts_on=modules_posts_enabled(self.settings);_growth_on=modules_growth_enabled(self.settings)
            sub=("粉丝与发帖监控 · 数据保存在本地" if _posts_on and _growth_on else
                 "仅粉丝监控 · 数据保存在本地" if not _posts_on else "仅发帖监控 · 数据保存在本地")
        if hasattr(self,"page_title"):self.page_title.setText(title)
        if hasattr(self,"page_sub"):self.page_sub.setText(sub)
        if index==0:self.refresh_dashboard()
        if index==0 and getattr(self,"_fireworks_pending",0):_n=self._fireworks_pending;self._fireworks_pending=0;self._request_fireworks(_n)
        elif index==1:self.trend.refresh()
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
        # The count hugs the label it belongs to, not the far right edge
        # of the row: expanded -> top-right of the "通知" text; collapsed
        # -> top-right of the bell icon. (The old code pinned it to the
        # row's right edge, which left it far from the word.)
        _y=2
        if getattr(self,"_sidebar_collapsed",False):
            _icon_w=btn.iconSize().width() or 22
            _x=(btn.width()-_icon_w)//2+_icon_w-3
        else:
            _tw=btn.fontMetrics().horizontalAdvance(btn.text() or "通知")
            _x=self._nav_pad()+btn.iconSize().width()+4+_tw-3
        self.notification_badge.move(max(0,_x),_y)

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
            if button.objectName()=="SideNav":continue  # sidebar icons: see _refresh_nav_icons
            if button.objectName()=="HomePill":color="#FFFFFF"
            elif kind=="bell":color=RED if (unread or 0)>0 else CYAN
            elif kind=="browser":color=GREEN if (hasattr(self,"connector") and self.selected_connectors()) else RED
            elif kind=="update" and getattr(self,"_update_available",False):color=AMBER
            else:color=colors.get(kind,MUTED)
            button.setIcon(ui_icon(kind,color))
        self._refresh_nav_icons(unread)

    def set_update_attention(self,active,version=""):
        self._update_available=bool(active)
        self._update_header_icons(sum(self.store.unread_totals()) if hasattr(self,"store") else 0)

    def refresh_dashboard(self):
        self.dashboard.refresh();self.dashboard.set_running(self.auto_enabled,self.worker_thread is not None)
        if self.worker_thread is not None and self.current_purpose=="monitor":self._check_fireworks()
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
        if self.paint_timer.isActive():return
        # During an active collection round results arrive steadily;
        # refreshing every 450ms means rebuilding the dashboard for the
        # whole round. Throttle to 5s mid-round; cleanup_worker already
        # does a final refresh_all when the round ends.
        _ms=5000 if self.worker_thread is not None else 450
        self.paint_timer.start(_ms)

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

    def cancel_current_patrol(self):
        """Cancel the running patrol (once-button right-click menu).

        The worker finishes the current page, then stops; the queued
        next batch is dropped so it does not auto-start. Already
        collected pages keep their data.
        """
        if self.worker is None:return
        self._patrol_queue.clear()
        self.worker.stop()
        self.dashboard.status.setText("正在取消当前巡检：当前主页处理完成后停止")

    def toggle_pause_collection(self):
        if self.worker is None:return
        self.dashboard.paused=self.worker.toggle_pause()
        self.dashboard.set_running(self.auto_enabled,True)
        self.dashboard.status.setText("已请求暂停：当前主页处理完成后停止进入下一页" if self.dashboard.paused else "继续本轮巡检")

    def _enqueue_patrol(self,pages):
        """Add pages to the patrol queue; start a round at once when idle.

        A single-page patrol no longer waits for the current round to end:
        it joins the queue, and the next batch starts automatically when
        the running round finishes. Pages already queued or running are
        skipped instead of being added twice.
        """
        queued={pid for pid,_ in self._patrol_queue}
        running={pid for pid,_ in self._patrol_running}
        fresh=[p for p in pages if str(p["page_id"]) not in queued and str(p["page_id"]) not in running]
        if not fresh:
            show_hint(self,"已在巡检队列中。",kind="info");return
        for p in fresh:self._patrol_queue.append((str(p["page_id"]),display_name(p)))
        if self._maybe_start_queued_round():return
        if any(str(p["page_id"]) in {pid for pid,_ in self._patrol_queue} for p in fresh):
            show_hint(self,"已加入巡检队列，本轮跑完就巡检。",kind="info")
        # Otherwise the pages were dropped by _start_worker (for example no
        # module enabled); it already explained why in the status bar.

    def _maybe_start_queued_round(self):
        """Start one round from the patrol queue. True if a round started."""
        if self.worker_thread is not None or self.login_thread is not None or self._maintenance or self._closing:
            return False
        if not self._patrol_queue:return False
        if not self.selected_connectors(require_all=False):
            # Browsers offline: keep the queue; the next patrol action
            # (or the next round's cleanup) tries again.
            return False
        queued=list(self._patrol_queue);self._patrol_queue=[]
        chosen={pid for pid,_ in queued}
        pages=[p for p in self.store.list_pages() if str(p["page_id"]) in chosen]
        if not pages:
            return False
        self._start_worker(pages,"monitor")
        return self.worker_thread is not None

    def start_collection(self,once=True):
        if self._closing or self._maintenance:return
        if getattr(self,"_grace_remaining",0)>0:self._clear_grace()
        if self.login_thread is not None:
            if once:show_hint(self,"请先关闭登录浏览器，再巡检。",kind="warning")
            elif self.auto_enabled:self.auto_timer.start(30000)
            return
        if self.worker_thread is not None:
            if once:
                pages=self.store.list_pages(enabled_only=True)
                if pages:self._enqueue_patrol(pages)
            return
        if self._maybe_start_queued_round():return
        pages=self.store.list_pages(enabled_only=True)
        if not pages:
            self.stop_auto()
            if once:show_hint(self,"请在 ID管理中添加 ID，并至少勾选一个监控模块。",kind="warning")
            return
        self._start_worker(pages,"monitor")

    def inspect_single_page(self,pid):
        if self.login_thread is not None or self._maintenance:
            show_hint(self,"请等待当前巡检或连接任务结束后再操作。暂停不会结束当前任务。",kind="warning");return
        pages=[p for p in self.store.list_pages() if str(p["page_id"])==str(pid)]
        if not pages:show_hint(self,"找不到该主页。",kind="warning");return
        self._enqueue_patrol(pages)

    def inspect_pages(self,ids):
        if self.login_thread is not None or self._maintenance:
            show_hint(self,"请等待当前巡检或连接任务结束后再操作。暂停不会结束当前任务。",kind="warning");return
        chosen={str(x) for x in ids}
        pages=[p for p in self.store.list_pages() if str(p["page_id"]) in chosen]
        if not pages:show_hint(self,"请先选择要巡检的主页。",kind="warning");return
        self._enqueue_patrol(pages)

    def start_subset_collection(self,mode):
        if self.login_thread is not None or self._maintenance:
            show_hint(self,"请等待当前巡检或连接任务结束后再操作。暂停不会结束当前任务。",kind="warning");return
        pages=self.store.list_pages(enabled_only=True)
        if mode=="failed":
            pages=[p for p in pages if p.get("status") in ("采集失败","部分成功") or p.get("growth_error")
                   or (modules_posts_enabled(self.settings) and p.get("post_error"))]
        elif mode=="uninspected":
            pages=[p for p in pages if not p.get("last_inspected_at")]
        if not pages:
            show_hint(self,"没有符合条件的主页。",kind="warning");return
        self._enqueue_patrol(pages)

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
            # connectors instead of refusing the whole round. Pick them
            # at random so consecutive small rounds spread across
            # browsers instead of always using the first ones.
            cids=random.sample(cids,len(pages))
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
        if purpose=="monitor":
            self._patrol_running=[(str(p["page_id"]),display_name(p)) for p in pages]
        self.worker_thread.start()

    def on_progress(self,current,total,info):
        self.dashboard.status.setText(f"{info}  ·  {current}/{total}")
        self.dashboard.set_patrol_progress(current,total)

    def on_collect_result(self,data):
        options={key:self.settings.value(key,default) for key,default in
                 (("interval_minutes",DEFAULT_INTERVAL_MINUTES),("alert_threshold",500),("alert_enabled",1),("notify_post_overdue",1))}
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
        pages=self.store.pages_map([r.get("page_id") for r in queued])
        for raw in queued:
            match=next((row for row in fresh if row.get("kind")==raw.get("kind") and row.get("page_id")==raw.get("page_id")
                        and (not raw.get("id") or int(row.get("id") or 0)==int(raw.get("id") or 0))),None)
            item=dict(match or raw)
            pid=str(item.get("page_id") or "")
            page=pages.get(pid) or {}
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
            self._refresh_run_badge()
        if "连接器中断" in message and self.auto_enabled:
            self.stop_auto();self.dashboard.status.setText(message+" · 自动巡检已暂停，请恢复浏览器连接后重新开启")
        else:self.dashboard.status.setText(message)
        self.schedule_refresh()

    def cleanup_worker(self):
        _finished_purpose=self.current_purpose
        thread=self.worker_thread
        self.worker=None;self.worker_thread=None;self.active_run_id=None
        if thread:thread.deleteLater()
        self.dashboard.paused=False;self.page_manager.set_busy(False)
        self.dashboard.set_running(self.auto_enabled,False)
        if self._closing:self.check_pending_exit();return
        if getattr(self,"_exit_after_round",False):
            self._exit_after_round=False;self.exit_application();return
        if _finished_purpose=="monitor":
            self._patrol_running=[]
        _started=self._maybe_start_queued_round()
        if not _started and self.auto_enabled:self.schedule_next_round(self.run_started_at)
        self.refresh_all()
        if _finished_purpose=="monitor":self._check_fireworks()

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
        self._badge_show_next=False;self._refresh_run_badge();self._badge_timer.start()
        # Deliberately do NOT write start_auto or change the startup checkbox.
        # 5s grace: show the countdown on 立即巡检; the first round starts
        # when it runs out, unless the user cancels it first.
        if not self.worker_thread:
            self._grace_remaining=5;self.dashboard.set_grace_countdown(5);self._grace_timer.start()
        self.dashboard.set_running(True,self.worker_thread is not None)

    def stop_auto(self):
        # This only stops scheduling in this process; explicit startup preference is independent.
        self._clear_grace()
        self.auto_enabled=False;self.next_run_at=None;self.auto_timer.stop()
        self._badge_timer.stop();self._badge_show_next=False;self._refresh_run_badge()
        self.dashboard.set_running(False,self.worker_thread is not None)
        self.dashboard.status.setText("已暂停自动巡检；当前任务可用巡检按钮暂停")

    def _clear_grace(self):
        self._grace_timer.stop();self._grace_remaining=0
        try:self.dashboard.set_grace_countdown(0)
        except Exception:pass

    def _on_grace_tick(self):
        self._grace_remaining-=1
        if self._grace_remaining<=0:
            self._clear_grace()
            if self.auto_enabled and not self.worker_thread:self.start_collection(False)
            return
        self.dashboard.set_grace_countdown(self._grace_remaining)

    def _on_grace_cancel(self):
        """User cancelled the immediate first round: wait for the scheduled time."""
        self._clear_grace()
        if self.auto_enabled:self.schedule_next_round()

    def _on_badge_timer(self):
        """Independent 10s switch: last <-> next, both sides exactly 10s,
        whatever the patrol is doing. Auto off: no rotation (badge shows
        last only, see _refresh_run_badge)."""
        if not self.auto_enabled:return
        self._badge_show_next=not self._badge_show_next
        self._refresh_run_badge()

    def _refresh_run_badge(self):
        """One line, one time, never two. Auto on: alternate every 10s between
        last patrol time and next patrol time (estimated). Auto off: last only."""
        _stamp=getattr(self.dashboard,"_last_inspection_stamp",None)
        _last="上次巡检时间："+inspection_stamp_label(_stamp)
        if not self.auto_enabled or not self._badge_show_next or not self.next_run_at or self.next_run_at<=time.time():
            self.dashboard.run_badge.setText(_last);return
        _when=datetime.fromtimestamp(self.next_run_at).astimezone().strftime("%m/%d %H:%M")
        self.dashboard.run_badge.setText(f"下次巡检时间，预计 {_when}")

    def update_countdown(self):
        self._tick+=1
        self._refresh_run_badge()
        if self.auto_enabled and self.next_run_at:
            secs=max(0,int(self.next_run_at-time.time()));mm,ss=divmod(secs,60)
            self.dashboard.next_run.setText(f"下次巡检 {mm:02d}:{ss:02d}")
        elif self.worker_thread:self.dashboard.next_run.setText("当前轮次进行中")
        elif self.auto_enabled:self.dashboard.next_run.setText("自动巡检等待中")
        else:self.dashboard.next_run.setText("自动巡检未开启")
        # The 60s tick used to rebuild the whole dashboard even with no
        # new data. Now only time-driven post text is refreshed; a full
        # refresh runs only if some post actually changed state.
        if self._tick%60==0 and not self._maintenance and self.dashboard.refresh_clock():self.refresh_dashboard()

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
            color={'ok':'#26C281','warn':'#F0A43A','error':'#E75768'}[state];self.connector_dot.setStyleSheet(f'background:{color};border:2px solid {self._nav_dot_ring()};border-radius:6px;');self.connector_dot.setToolTip(html.escape(text))
        if hasattr(self,"_conn_collapsed_icon"):
            self._conn_collapsed_icon.setPixmap(ui_icon("browser",color).pixmap(QSize(22,22)))
        if hasattr(self,"_conn_collapsed_count"):
            self._conn_collapsed_count.setText(f"{len(active)} 个")
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
        self._position_version_corner()
        # Log the current size once a drag settles, so the user can read
        # it from the diagnostic log and report it back. Debounced: the
        # timer restarts on every resize event and only fires after 500ms
        # with no further resize, so a drag writes exactly one line.
        if not hasattr(self,"_size_log_timer"):
            self._size_log_timer=QTimer(self);self._size_log_timer.setSingleShot(True)
            self._size_log_timer.timeout.connect(lambda:diag_log(f"[窗口] 当前尺寸 {self.width()}x{self.height()}"))
        self._size_log_timer.start(500)
        if getattr(self,"_update_log_panel",None) is not None and not self._update_log_panel.isHidden():
            self._update_log_panel.setGeometry(self.width()-400,0,400,self.height());self._update_log_panel.raise_()
        # Auto-collapse / auto-expand on width crossing 1200 while dragging.
        # Only a crossing counts, so a startup restore to a narrow width
        # keeps the saved sidebar state instead of overriding it.
        _w=self.width();_prev=getattr(self,"_last_width",None)
        if _prev is not None and _w!=_prev:
            if _prev>=1200 and _w<1200 and not getattr(self,"_sidebar_collapsed",False):
                self._sidebar_auto_collapsed=True;self.set_sidebar_collapsed(True)
            elif _prev<1200 and _w>=1200 and getattr(self,"_sidebar_collapsed",False) and getattr(self,"_sidebar_auto_collapsed",False):
                self._sidebar_auto_collapsed=False;self.set_sidebar_collapsed(False)
        self._last_width=_w

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius=0 if self.isMaximized() else 20
        rect=QRectF(0.5,0.5,self.width()-1,self.height()-1)
        # Outer edge: a faint 20%-opacity line (black on light themes, white
        # on the dark theme) so the window edge stays visible against other
        # windows, instead of the near-invisible theme border colour.
        _preset=THEME_PRESETS.get(migrate_theme_name(getattr(self,"theme_name","云白")),THEME_PRESETS["云白"])
        _edge=QColor(255,255,255,51) if not _preset.get("light",True) else QColor(0,0,0,51)
        # Cache the rasterized background: re-rasterizing the antialiased
        # rounded rect on every paint frame is a large share of resize
        # cost. The pixmap is rebuilt only when size/radius/theme change.
        _key=(self.width(),self.height(),radius,str(BG),_edge.rgba())
        _cached=getattr(self,"_bg_cache",None)
        if _cached is None or _cached[0]!=_key:
            _pm=QPixmap(max(1,self.width()),max(1,self.height()));_pm.fill(Qt.GlobalColor.transparent)
            _pp=QPainter(_pm);_pp.setRenderHint(QPainter.RenderHint.Antialiasing)
            _pp.setBrush(QColor(BG));_pp.setPen(QPen(_edge,1))
            if radius:_pp.drawRoundedRect(rect,radius,radius)
            else:_pp.drawRect(rect)
            _pp.end();self._bg_cache=(_key,_pm)
        p.drawPixmap(0,0,self._bg_cache[1])
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
        try:_backoff_until=float(self.settings.value("update/backoff_until",0))
        except (ValueError,TypeError):_backoff_until=0
        if _backoff_until>time.time():
            _mins=max(1,-(-int(_backoff_until-time.time())//60))
            _msg=f"GitHub 请求受限，约 {_mins} 分钟后恢复"
            self.dashboard.status.setText(_msg)
            if manual:self.show_toast(_msg)
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

    def on_tray_activated(self,reason):
        if reason==QSystemTrayIcon.ActivationReason.DoubleClick:self.show_dashboard()


    def exit_application(self):
        self._closing=True;self.auto_enabled=False;self.auto_timer.stop();self.next_run_at=None
        self.close()

    def check_pending_exit(self):
        if self._closing and self.worker_thread is None and self.login_thread is None and self._update_thread is None:
            QTimer.singleShot(0,self.close)

    def _finish_close(self,event):
        """Closing branch shared by closeEvent and the close dialog.

        close() called from inside closeEvent is swallowed by Qt (proven
        offscreen: a nested close() never re-enters closeEvent), so the
        dialog must not go through exit_application()->close(); it calls
        this directly with the outer event instead.
        """
        self._closing=True
        self.auto_enabled=False;self.auto_timer.stop();self.count_timer.stop();self._updates_timer.stop()
        if self.worker_thread is not None or self.login_thread is not None or self._update_thread is not None:
            if self.worker:self.worker.stop()
            if self.login_worker:self.login_worker.stop()
            if self._update_worker:self._update_worker.cancel()
            self.dashboard.status.setText("正在安全结束当前任务…")
            if not getattr(self,"_exit_timeout_armed",False):
                # Backstop: a hung page load must not trap the process in
                # "正在安全结束当前任务…" forever; 10s is past any single
                # page timeout, and settings were already flushed above.
                self._exit_timeout_armed=True
                QTimer.singleShot(10000,self._force_exit_after_timeout)
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

    def _close_tasks(self):
        """Running tasks for the close dialog: list of (name, current, total).
        total is None when there is no progress to show."""
        tasks=[]
        if self.worker_thread is not None:
            cur=int(getattr(self.dashboard,"_prog_current",0) or 0)
            tot=int(getattr(self.dashboard,"_prog_total",0) or 0)
            name="同步资料" if getattr(self,"current_purpose","monitor")=="metadata" else "本轮巡检"
            tasks.append((name,cur,tot if tot>0 else None))
        if self.login_thread is not None:
            tasks.append(("浏览器登录",None,None))
        if self._update_thread is not None:
            tasks.append(("正在更新",None,None))
        return tasks

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
            tasks=self._close_tasks()
            # A remembered choice (from the dialog's "记住我的选择") is applied
            # without asking. "立即退出" is never remembered. The old
            # silent_to_tray skip is retired: the dialog is the entry point,
            # and remembering "最小化到托盘" restores the silent behaviour.
            remembered=str(self.settings.value("close/remembered","") or "")
            if remembered=="background":
                self._exit_after_round=False
                if QSystemTrayIcon.isSystemTrayAvailable():
                    self.tray.show();self.hide()
                else:
                    self.showMinimized()
                return
            if remembered=="wait":
                if tasks:
                    self.auto_enabled=False;self.auto_timer.stop();self.next_run_at=None
                    self._exit_after_round=True
                    if self.worker_thread is None:
                        self._exit_after_round=False
                        self._finish_close(event)
                    elif QSystemTrayIcon.isSystemTrayAvailable():
                        self.tray.show();self.hide()
                    else:
                        self.showMinimized()
                else:
                    self._finish_close(event)
                return
            if remembered=="exit":
                self._finish_close(event);return
            # The dialog shows whether or not a tray exists: "stop" does
            # not need one, and "background" without a tray just minimises
            # instead of hiding (so the window stays recoverable).
            choice,remember=CloseChoiceDialog(self).exec_choice()
            if choice is None:
                return
            if remember:
                if choice=="background":
                    self.settings.setValue("close/remembered","background")
                    self.settings.setValue("silent_to_tray",1)
                elif choice=="wait":
                    self.settings.setValue("close/remembered","wait")
                elif choice=="stop" and not tasks:
                    self.settings.setValue("close/remembered","exit")
            if choice=="background":
                self._exit_after_round=False
                if QSystemTrayIcon.isSystemTrayAvailable():
                    self.tray.show();self.hide()
                else:
                    self.showMinimized()
                return
            if choice=="wait":
                self.auto_enabled=False;self.auto_timer.stop();self.next_run_at=None
                self._exit_after_round=True
                if self.worker_thread is None:
                    self._exit_after_round=False
                    self._finish_close(event)
                elif QSystemTrayIcon.isSystemTrayAvailable():
                    self.tray.show();self.hide()
                else:
                    self.showMinimized()
                return
            if choice=="stop":
                self._finish_close(event);return
            return
        self._finish_close(event)

    def _force_exit_after_timeout(self):
        if getattr(self, "_closing", False):
            try:
                log_window_event("force_exit", "close wait exceeded 10s")
            except Exception:
                pass
            os._exit(0)

    def _refresh_theme_swatches(self,name):
        if not hasattr(self,"theme_swatches"):return
        _sw_colors={"云白":"#F7F7F5","护眼绿":"#0B7A43","曜石黑":"#17181C"}
        for _n,_sw in self.theme_swatches.items():
            _sel=_n==name
            _sw.setStyleSheet(f"background:{_sw_colors.get(_n,'#FFFFFF')};border:{'2px' if _sel else '1px'} solid {ACCENT if _sel else '#C9C9C4'};border-radius:10px;")
        for _n,_sw in getattr(self,"_collapsed_theme_swatches",{}).items():
            _sel=_n==name
            _sw.setStyleSheet(f"background:{_sw_colors.get(_n,'#FFFFFF')};border:{'2px' if _sel else '1px'} solid {ACCENT if _sel else '#C9C9C4'};border-radius:7px;")
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
        self._refresh_nav_icons()
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
            QWidget#UpdateLogPanel {{ background:{PANEL}; border-left:1px solid {BORDER}; }}
            QLabel#UpdateLogVersion {{ font-weight:700; font-size:17px; }}
            QLabel#UpdateLogGroup {{ color:{ACCENT}; font-weight:700; font-size:13px; }}
            QLabel#UpdateLogDot {{ color:{ACCENT}; }}
            QPushButton#UpdateLogClose {{ background:transparent; border:1px solid {BORDER}; border-radius:8px; color:{MUTED}; font-size:16px; }}
            QWidget {{ color:{TEXT}; font-size:13px; }}
            QLabel {{ background:transparent; border:0; }}
            QDialog, QMessageBox {{ background:{BG}; }}
            QPushButton#SideCollapse {{ background:transparent;border:0;color:{MUTED};font-size:16px;font-weight:700;padding:0; }}
            QPushButton#SideCollapse:hover {{ color:{ACCENT};background:{hover};border-radius:6px; }}
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
            QLabel#NotificationBadge {{ background:#EA580C;color:#FFFFFF;border-radius:8px;font-size:9px;font-weight:800; }}
            QLabel#PageTitle {{ font-size:24px;font-weight:800;color:{TEXT}; }}
            QLabel#DialogTitle {{ font-size:23px;font-weight:800; }}
            QLabel#SectionTitle {{ font-size:17px;font-weight:750; }}
            QLabel#SettingsTitle, QLabel#PanelTitle {{ font-size:15px;font-weight:750; }}
            QLabel#Subtitle, QLabel#SmallMuted, QLabel#FooterText {{ color:{MUTED};font-size:12px; }}
            QLabel#CardHeadSmall {{ color:{MUTED};font-size:11px; }}
            QLineEdit#DiagLine {{ background:transparent;border:0;color:{MUTED};font-size:12px;padding:0; }}
            QLineEdit#DiagLine:focus {{ background:transparent;border:0; }}
            QLabel#FansValue {{ color:{TEXT};font-size:12px; }}
            QLabel#Eyebrow {{ color:{CYAN};font-size:11px;font-weight:700; }}
            QLabel#RunBadge {{ color:{TEXT};font-size:13px;font-weight:650;padding:7px 8px; }}
            QFrame#MetricCard, QFrame#PageCard, QFrame#SettingsCard, QFrame#EmptyState, QFrame#DetailStat, QFrame#TrendChartCard, QFrame#TrendCard {{
                background:{PANEL};border:1px solid {BORDER};border-radius:16px;
            }}
            QFrame#PageCard:hover {{ border:1px solid {ACCENT}; }}
            QFrame#TrendCard:hover {{ border:1px solid {ACCENT}; }}
            QLabel#TrendCardName {{ font-size:13px;font-weight:700; }}
            QPushButton#DatePill {{ background:{PANEL};border:1px solid {BORDER};border-radius:12px;padding:9px 14px;font-size:14px;font-weight:600;color:{TEXT}; }}
            QPushButton#DatePill:hover {{ border-color:{ACCENT}; }}
            QLabel#CalMonthLabel {{ font-size:15px;font-weight:750;color:{TEXT}; }}
            QPushButton#CalNavButton {{ background:{PANEL_2};border:1px solid {BORDER};border-radius:8px;padding:4px 12px;font-size:15px;font-weight:700; }}
            QPushButton#CalQuickButton {{ background:{PANEL};border:1px solid {BORDER};border-radius:9px;padding:8px 0;font-size:13px;font-weight:600;color:{TEXT}; }}
            QPushButton#CalQuickButton:checked {{ background:{ACCENT};border-color:{ACCENT};color:#FFFFFF; }}
            QDialog#DateRangePopup {{ background:{PANEL};border:1px solid {BORDER};border-radius:14px; }}
            QFrame#AlertRow {{ background:transparent;border-left:2px solid {BORDER}; }}
            QLabel#AlertRowTitle {{ color:{AMBER};font-size:12px;font-weight:650; }}
            QLabel#MetricLabel {{ color:{MUTED};font-size:13px;font-weight:600; }}
            QLabel#MetricValue {{ color:{TEXT};font-size:32px;font-weight:750; }}
            QLabel#MetricValue[tone="history"] {{ color:{RED}; }}
            QLabel#MetricValue[tone="bell"] {{ color:{GREEN}; }}
            QPushButton#MetricBadge {{ background:{RED};color:#FFFFFF;border:0;border-radius:10px;font-size:11px;font-weight:800;padding:0; }}
            QLabel#ChipBadge {{ background:#EA580C;color:#FFFFFF;border-radius:8px;font-size:10px;font-weight:800;padding:0; }}
            QLabel#ChipBadge[tone="good"] {{ background:#EA580C;color:#FFFFFF;border-radius:8px;font-size:10px;font-weight:800;padding:0; }}
            QLabel#CardTitle {{ font-size:16px;font-weight:750;color:{TEXT}; }}
            QLabel#CardId {{ color:{MUTED};font-size:13px; }}
            QLabel#BigNumber {{ color:{TEXT};font-weight:800; }}
            QLabel#GrowthUp {{ color:{GREEN};font-weight:750; }}
            QLabel#GrowthDown {{ color:{RED};font-weight:750; }}
            QLabel#GrowthSoon {{ color:{AMBER};font-weight:700; }}
            QLabel#GrowthFlat {{ color:{MUTED};font-weight:650; }}
            QLabel#GrowthAlert {{ color:{RED};font-weight:750; }}
            QWidget#DiagStripe[severity="alert"] {{ background:{RED};border-radius:2px; }}
            QWidget#DiagStripe[severity="warning"] {{ background:{AMBER};border-radius:2px; }}
            QWidget#DiagStripe[severity="plain"] {{ background:{MUTED};border-radius:2px; }}
            QWidget#DiagStripe[severity="good"] {{ background:{GREEN};border-radius:2px; }}
            QLabel#StatusBadge {{ background:{status_ok_bg};color:{GREEN};border:1px solid {status_ok_border};border-radius:12px;
                padding:4px 11px;font-size:13px;font-weight:700; }}
            QLabel#StatusBadge[state='alert'] {{ background:{status_alert_bg};color:{RED};border-color:{status_alert_border}; }}
            QLabel#StatusBadge[state='warning'] {{ background:{status_warn_bg};color:{AMBER};border-color:{status_warn_border}; }}
            QLabel#StatusBadge[state='off'] {{ background:{PANEL_2};color:{MUTED};border-color:{BORDER}; }}
            QLabel#StatusBadge[state='good'] {{ background:{status_ok_bg};color:{GREEN};border-color:{status_ok_border}; }}
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
            QPushButton#PrimaryButton[graceCountdown='true'] {{ background:#FEF3C7;border:1px solid #F59E0B;color:#92400E; }}
            QPushButton#AutoButton {{ background:{PANEL_2};border:1px solid {BORDER}; }}
            QPushButton#AutoButton[autoEnabled='true'] {{ background:{ACCENT};border-color:{ACCENT};color:#FFFFFF; }}
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
            QMenu::item {{ padding:6px 14px;border-radius:8px;font-size:12px;font-weight:500; }}
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
        _sheet+=self._nav_style_sheet(hover,soft)
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
        failed_version=""
        if result_path.is_file():
            try:
                result=json.loads(result_path.read_text("utf-8-sig"))
                if result.get("status")=="failed":
                    failed_version=str(result.get("version") or "")
                    QMessageBox.warning(self,"上次更新未安装",str(result.get("message") or "系统安装器或签名验证未通过。原数据保留，可重新检查版本。"))
                else:
                    self.dashboard.status.setText("更新安装已完成 · 当前版本 "+APP_VERSION)
                    if self.settings.value(UPDATE_LOG_SHOWN_KEY) != APP_VERSION:
                        self.settings.setValue(UPDATE_LOG_SHOWN_KEY, APP_VERSION);self.settings.sync()
                        self.show_update_log(just_updated=True)
                result_path.unlink(missing_ok=True)
            except (OSError,ValueError):pass
        pending=DATA_DIR/"updates/pending.json"
        pending_path=""
        if pending.is_file():
            try:
                info=json.loads(pending.read_text("utf-8"))
                if release_version(info.get("version",""))>release_version(APP_VERSION):
                    pending_path=str(info.get("path") or "")
                    self.set_update_attention(True,info.get("version",""))
                    self._update_manual=False;self._start_update_task("verify",info)
                    self._cleanup_old_updates(failed_version,pending_path);return
                pending.unlink(missing_ok=True)
            except (ValueError,OSError,UpdateError):pass
        self._cleanup_old_updates(failed_version,pending_path)
        self.check_for_updates(False)

    def _cleanup_old_updates(self,failed_version="",pending_path=""):
        """Startup cleanup: drop update files from older versions, keeping
        only the current version (plus a failed install's version so it can
        be retried, and a pending update's file)."""
        try:
            keep={APP_VERSION}
            if failed_version:keep.add(failed_version)
            files,dirs,freed=cleanup_old_updates(DATA_DIR/"updates",keep,(pending_path,) if pending_path else ())
            if files or dirs:
                diag_log(f"[更新] 已清理旧版本文件：{len(files)} 个安装包、{len(dirs)} 个解压文件夹，共释放约 {freed//(1024*1024)} MB")
        except Exception:
            pass

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
        diag_log(f"[更新] 检查结果：{status} " + str(result.get("version") or result.get("message") or "")[:80])
        if status=="new":
            self.set_update_attention(True,result.get("version",""))
            self.settings.setValue("update/last_checked",now_iso());self.settings.remove("update/backoff_until");self.settings.sync()
            version=result.get("version","")
            snoozed=str(self.settings.value("update/snooze_version",""))==version
            try:until=float(self.settings.value("update/snooze_until",0))
            except (ValueError,TypeError):until=0
            if not self._update_manual and snoozed and time.time()<until:
                self.dashboard.status.setText("发现新版 V"+version+" · 已设置稍后提醒")
            else:self._show_update_dialog(result)
        elif status=="ready":
            self.set_update_attention(True,(result.get("info") or {}).get("version",""))
            self.settings.remove("update/backoff_until")
            info=dict(result["info"]);info["path"]=result["path"]
            save_json_atomic(DATA_DIR/"updates/pending.json",info)
            if self._try_silent_install(result["path"],info):
                return
            dlg=self._show_update_dialog(info);dlg.ready(result["path"])
            self.dashboard.status.setText("新版已下载并校验，可选择更新或稍后安装")
        elif status in ("error","cancelled"):
            message=str(result.get("message") or "下载已取消")
            if result.get("retry_after_seconds"):
                try:self.settings.setValue("update/backoff_until",time.time()+float(result["retry_after_seconds"]));self.settings.sync()
                except (ValueError,TypeError):pass
            self.dashboard.status.setText(message)
            if self._update_dialog and self._update_operation!="check":
                self._update_dialog.error(message)
            elif self._update_manual:
                if status=="cancelled":self.show_toast("下载已取消")
                else:QMessageBox.warning(self,"版本检查未完成",message)
        elif status=="current":
            self.set_update_attention(False)
            self.settings.setValue("update/last_checked",now_iso());self.settings.remove("update/backoff_until");self.settings.sync()
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

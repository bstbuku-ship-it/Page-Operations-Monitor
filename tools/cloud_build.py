# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, base64, glob, json, os, platform, re, secrets, shutil, subprocess, sys
from pathlib import Path

def _ensure_utf8_output():
    # Windows runner stdout/stderr default to cp1252, which cannot encode the
    # Chinese warning text printed below (UnicodeEncodeError before PyInstaller
    # even starts). Force UTF-8 so the build script works on any runner locale.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
_ensure_utf8_output()

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'Page_Operations_Monitor.py';ICON_WIN=ROOT/'PageOperationsMonitor.ico';ICON_MAC=ROOT/'PageOperationsMonitor.icns';ISS_SCRIPT=ROOT/'tools/windows_setup.iss'
BUILD=ROOT/'build';DIST=ROOT/'dist';OUT=ROOT/'cloud-release';PORTABLE_OUT=ROOT/'cloud-release-portable';PORTABLE_MARKER='portable.mode';APP_ID='ProfessionalMonitorTool';BUNDLE_ID='com.bstbuku.pageoperationsmonitor';DEFAULT_TIMESTAMP_URL='http://timestamp.digicert.com'

def truthy(v):return str(v or '').strip().lower() in {'1','true','yes','on'}
def require_signing():return truthy(os.environ.get('REQUIRE_SIGNING'))
def run(args,cwd=None,secret_values=()):
    shown=[]
    for raw in map(str,args):
        masked=raw
        for s in secret_values:
            if s:masked=masked.replace(s,'***')
        shown.append(masked)
    print('\n>',' '.join(shown),flush=True)
    try:
        subprocess.run(args,cwd=cwd or ROOT,check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"构建命令失败（退出码 {exc.returncode}）：{' '.join(shown)}") from None
def version():
    t=SOURCE.read_text(encoding='utf-8-sig');m=re.search(r'APP_VERSION\s*=\s*["\']v?(\d+\.\d+\.\d+)["\']',t)
    if not m:raise RuntimeError('主程序找不到 APP_VERSION')
    return m.group(1)
def clean():
    shutil.rmtree(BUILD,ignore_errors=True);shutil.rmtree(DIST,ignore_errors=True);shutil.rmtree(OUT,ignore_errors=True);shutil.rmtree(PORTABLE_OUT,ignore_errors=True)
    for p in (BUILD, BUILD/'spec', DIST, OUT, PORTABLE_OUT):
        p.mkdir(parents=True,exist_ok=True)
def common(icon=None):
    cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir','--name',APP_ID,'--workpath',str(BUILD/'pyinstaller'),'--distpath',str(DIST),'--specpath',str(BUILD/'spec'),'--collect-all','playwright']
    if icon and icon.exists():cmd+=['--icon',str(icon)]
    return cmd

def decode_secret(env_name,target):
    data=''.join(str(os.environ.get(env_name,'') or '').split())
    if not data:return None
    try:raw=base64.b64decode(data,validate=True)
    except Exception as e:raise RuntimeError(f'{env_name} 不是有效 Base64') from e
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(raw)
    if os.name!='nt':
        try:target.chmod(0o600)
        except OSError:pass
    return target

def find_signtool():
    direct=shutil.which('signtool.exe') or shutil.which('signtool')
    if direct:return Path(direct)
    matches=[]
    for pattern in (r'C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe',r'C:\Program Files\Windows Kits\10\bin\*\x64\signtool.exe'):
        matches.extend(Path(x) for x in glob.glob(pattern))
    if not matches:raise RuntimeError('找不到 Windows SDK signtool.exe')
    return sorted(matches,key=lambda p:p.as_posix(),reverse=True)[0]
def windows_material():
    b64=str(os.environ.get('WINDOWS_CERT_PFX_B64','') or '').strip();password=str(os.environ.get('WINDOWS_CERT_PASSWORD','') or '')
    complete=bool(b64) and bool(password)
    partial=bool(b64)!=bool(password)
    if require_signing():
        if not complete:
            missing=[]
            if not b64:missing.append('WINDOWS_CERT_PFX_B64')
            if not password:missing.append('WINDOWS_CERT_PASSWORD')
            raise RuntimeError('正式签名发布缺少 Windows Secrets：'+', '.join(missing))
    if partial:
        print('::warning::Windows 签名 Secrets 配置不完整；普通构建将忽略签名配置并继续。')
        return None
    if not complete:
        print('::warning::未配置 Windows 签名证书；普通构建将生成未签名测试包。')
        return None
    cert=decode_secret('WINDOWS_CERT_PFX_B64',BUILD/'signing/windows.pfx');return cert,password
def pfx_thumbprint(cert,password):
    env=dict(os.environ);env['POM_PFX_PASSWORD']=password
    # Keep this compatible with Python 3.10/3.11 too: do not use nested same-quote
    # expressions inside an f-string (PEP 701 changed parsing in Python 3.12).
    cert_ps=str(cert).replace("'","''")
    ps=("$p=ConvertTo-SecureString $env:POM_PFX_PASSWORD -AsPlainText -Force; "
        + "$d=Get-PfxData -FilePath '" + cert_ps + "' -Password $p; "
        + "$c=$d.EndEntityCertificates | Select-Object -First 1; if(-not $c){exit 2}; $c.Thumbprint")
    p=subprocess.run(['powershell.exe','-NoProfile','-Command',ps],capture_output=True,text=True,encoding='utf-8',errors='replace',env=env)
    thumb=(p.stdout or '').strip().replace(' ','')
    if p.returncode!=0 or not re.fullmatch(r'[0-9A-Fa-f]{40,64}',thumb):raise RuntimeError('无法读取 Windows 代码签名证书指纹')
    return thumb.upper()
def patch_update_identity(win_thumb='',mac_team=''):
    t=SOURCE.read_text(encoding='utf-8-sig')
    t=re.sub(r'UPDATE_WINDOWS_PUBLISHER_THUMBPRINT\s*=\s*["\'][^"\']*["\']',f'UPDATE_WINDOWS_PUBLISHER_THUMBPRINT = "{win_thumb}"',t,count=1)
    t=re.sub(r'UPDATE_MACOS_TEAM_ID\s*=\s*["\'][^"\']*["\']',f'UPDATE_MACOS_TEAM_ID = "{mac_team}"',t,count=1)
    SOURCE.write_text(t,encoding='utf-8-sig')
def sign_windows(path,material):
    if not material:return
    cert,password=material;tool=find_signtool();timestamp=str(os.environ.get('WINDOWS_TIMESTAMP_URL') or DEFAULT_TIMESTAMP_URL)
    run([str(tool),'sign','/fd','SHA256','/td','SHA256','/tr',timestamp,'/f',str(cert),'/p',password,str(path)],secret_values=(password,))
    run([str(tool),'verify','/pa','/v',str(path)])
def _inno_install_roots():
    """Program Files roots where a real Inno Setup install lives (deduped,
    order preserved). The Chocolatey shim dir is deliberately NOT here:
    the shim forwards to the real compiler, but the language files live
    next to the real compiler, not next to the shim."""
    roots = []
    for key in ('ProgramFiles(x86)', 'ProgramFiles'):
        value = os.environ.get(key)
        if value:
            roots.append(Path(value))
    roots += [Path(r'C:\Program Files (x86)'), Path(r'C:\Program Files')]
    seen = set()
    out = []
    for r in roots:
        key = str(r).lower()
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def find_iscc():
    """Locate ISCC.exe (Inno Setup 6 compiler). Prefer the real install dir
    over a Chocolatey shim: the shim compiles fine, but the language files
    live next to the real compiler. Fail loudly if absent."""
    seen = set()
    for root in _inno_install_roots():
        candidates = [root / 'Inno Setup 6' / 'ISCC.exe']
        try:
            candidates += sorted(root.glob('Inno Setup */ISCC.exe'))
        except OSError:
            pass
        for cand in candidates:
            key = str(cand).lower()
            if key in seen:
                continue
            seen.add(key)
            if cand.is_file():
                return cand
    direct = shutil.which('ISCC.exe') or shutil.which('iscc')
    if direct:
        return Path(direct)
    raise RuntimeError('找不到 Inno Setup 的 ISCC.exe，请先安装 Inno Setup 6（choco install innosetup -y）')

def find_inno_language(iscc_path):
    """Official Simplified Chinese language file. Fail loudly if missing:
    never silently fall back to an English wizard.

    The compiler path may be a Chocolatey shim
    (C:\\ProgramData\\chocolatey\\bin\\ISCC.exe), whose directory holds
    no Languages folder, so search every known install dir too instead of
    only looking next to the given path."""
    checked = []
    dirs = [Path(iscc_path).resolve().parent]
    for root in _inno_install_roots():
        dirs.append(root / 'Inno Setup 6')
        try:
            dirs += sorted(root.glob('Inno Setup *'))
        except OSError:
            pass
    seen = set()
    for d in dirs:
        key = str(d).lower()
        if key in seen:
            continue
        seen.add(key)
        lang = d / 'Languages' / 'ChineseSimplified.isl'
        checked.append(str(lang))
        if lang.is_file():
            return lang
    raise RuntimeError('找不到 Inno Setup 官方简体中文语言文件（已查：' + '；'.join(checked) + '）；拒绝静默回退英文界面。')

def build_windows(ver):
    if not ICON_WIN.exists() or not ISS_SCRIPT.exists():raise RuntimeError('缺少 Windows 图标或 Inno Setup 脚本')
    material=windows_material()
    try:
        thumb=pfx_thumbprint(*material) if material else ''
        patch_update_identity(win_thumb=thumb)
        run(common(ICON_WIN)+[str(SOURCE)])
        app_dir=DIST/APP_ID;exe=app_dir/(APP_ID+'.exe')
        if not exe.exists():raise RuntimeError('主程序 EXE 未生成')
        sign_windows(exe,material)
        # Stage the exact file set the installer ships. No portable.mode here:
        # a standard install must never be detected as portable.
        stage=BUILD/'inno-stage'
        shutil.rmtree(stage,ignore_errors=True)
        shutil.copytree(app_dir,stage)
        if not (stage/(APP_ID+'.exe')).is_file():raise RuntimeError('安装文件 staging 不完整')
        # Portable artifact: same app files + portable.mode marker (exact
        # format the retired deployer wrote; the app detects portable mode
        # by the marker file next to its exe).
        shutil.rmtree(PORTABLE_OUT,ignore_errors=True)
        shutil.copytree(app_dir,PORTABLE_OUT)
        (PORTABLE_OUT/PORTABLE_MARKER).write_text(
            json.dumps({"mode":"portable","version":ver},ensure_ascii=False),encoding="utf-8")
        # Compile the Chinese Inno Setup installer. ISCC and the official
        # Simplified Chinese language file must both exist; both helpers
        # fail loudly instead of producing an English installer.
        iscc=find_iscc();find_inno_language(iscc)
        OUT.mkdir(parents=True,exist_ok=True)
        name=f'ProfessionalMonitorTool-{ver}-windows-x64-deployer'
        run([str(iscc),
             f'/DAppVersion={ver}',
             f'/DStageDir={stage}',
             f'/DOutputDir={OUT}',
             f'/DOutputName={name}',
             f'/DAppIcon={ICON_WIN}',
             str(ISS_SCRIPT)])
        result=OUT/(name+'.exe')
        if not result.exists():raise RuntimeError('Inno Setup 安装程序未生成')
        sign_windows(result,material)
        return result,PORTABLE_OUT
    finally:
        if material:
            try:material[0].unlink(missing_ok=True)
            except OSError:pass

def mac_config():
    cert_names=('APPLE_APP_CERT_P12_B64','APPLE_APP_CERT_PASSWORD','APPLE_INSTALLER_CERT_P12_B64','APPLE_INSTALLER_CERT_PASSWORD','APPLE_APP_SIGN_IDENTITY','APPLE_INSTALLER_SIGN_IDENTITY')
    cfg={n:str(os.environ.get(n,'') or '').strip() for n in cert_names}
    cert_complete=all(cfg.values())
    cert_partial=any(cfg.values()) and not cert_complete
    if require_signing():
        if not cert_complete:
            missing=[n for n in cert_names if not cfg[n]]
            raise RuntimeError('正式签名发布缺少 macOS Secrets：'+', '.join(missing))
    elif cert_partial:
        print('::warning::macOS 签名 Secrets 配置不完整；普通构建将忽略签名配置并继续。')
        return None
    elif not cert_complete:
        print('::warning::未配置 macOS 签名证书；普通构建将生成未签名测试包。')
        return None
    for n in ('APPLE_ID','APPLE_TEAM_ID','APPLE_APP_PASSWORD'):
        cfg[n]=str(os.environ.get(n,'') or '').strip()
    notarization_complete=all(cfg[n] for n in ('APPLE_ID','APPLE_TEAM_ID','APPLE_APP_PASSWORD'))
    if require_signing() and not notarization_complete:
        missing=[n for n in ('APPLE_ID','APPLE_TEAM_ID','APPLE_APP_PASSWORD') if not cfg[n]]
        raise RuntimeError('正式签名发布缺少 Apple 公证 Secrets：'+', '.join(missing))
    if not require_signing() and not notarization_complete:
        print('::warning::Apple 公证凭据不完整；普通构建只做代码签名，不执行公证。')
        cfg['APPLE_ID']=cfg['APPLE_TEAM_ID']=cfg['APPLE_APP_PASSWORD']=''
    return cfg
def prepare_keychain(cfg):
    sd=BUILD/'signing';sd.mkdir(parents=True,exist_ok=True);a=decode_secret('APPLE_APP_CERT_P12_B64',sd/'app.p12');i=decode_secret('APPLE_INSTALLER_CERT_P12_B64',sd/'installer.p12');key=sd/'sign.keychain-db';pwd=secrets.token_urlsafe(24)
    run(['security','create-keychain','-p',pwd,str(key)],secret_values=(pwd,));run(['security','unlock-keychain','-p',pwd,str(key)],secret_values=(pwd,))
    run(['security','import',str(a),'-k',str(key),'-P',cfg['APPLE_APP_CERT_PASSWORD'],'-T','/usr/bin/codesign'],secret_values=(cfg['APPLE_APP_CERT_PASSWORD'],))
    run(['security','import',str(i),'-k',str(key),'-P',cfg['APPLE_INSTALLER_CERT_PASSWORD'],'-T','/usr/bin/pkgbuild'],secret_values=(cfg['APPLE_INSTALLER_CERT_PASSWORD'],))
    run(['security','set-key-partition-list','-S','apple-tool:,apple:,codesign:','-s','-k',pwd,str(key)],secret_values=(pwd,));run(['security','default-keychain','-s',str(key)]);return key
def notarize(pkg,cfg):
    if not all(cfg.get(n) for n in ('APPLE_ID','APPLE_TEAM_ID','APPLE_APP_PASSWORD')):return
    pw=cfg['APPLE_APP_PASSWORD'];run(['xcrun','notarytool','submit',str(pkg),'--apple-id',cfg['APPLE_ID'],'--team-id',cfg['APPLE_TEAM_ID'],'--password',pw,'--wait'],secret_values=(pw,));run(['xcrun','stapler','staple',str(pkg)]);run(['xcrun','stapler','validate',str(pkg)])
def build_mac(ver,arch):
    if not ICON_MAC.exists():raise RuntimeError('缺少 macOS ICNS')
    cfg=mac_config();key=None;patch_update_identity(mac_team=(cfg or {}).get('APPLE_TEAM_ID',''))
    try:
        if cfg:key=prepare_keychain(cfg)
        cmd=common(ICON_MAC)+['--osx-bundle-identifier',BUNDLE_ID]
        if cfg:cmd+=['--codesign-identity',cfg['APPLE_APP_SIGN_IDENTITY']]
        cmd+=[str(SOURCE)];run(cmd);app=DIST/(APP_ID+'.app')
        if not app.exists():raise RuntimeError('macOS .app 未生成')
        if cfg:
            run(['codesign','--force','--deep','--options','runtime','--timestamp','--sign',cfg['APPLE_APP_SIGN_IDENTITY'],str(app)]);run(['codesign','--verify','--deep','--strict','--verbose=2',str(app)])
        stage=BUILD/'pkgroot';target=stage/'Applications'/app.name;target.parent.mkdir(parents=True,exist_ok=True);run(['ditto',str(app),str(target)])
        result=OUT/f'ProfessionalMonitorTool-{ver}-macos-{arch}.pkg';cmd=['pkgbuild','--root',str(stage),'--identifier',BUNDLE_ID,'--version',ver,'--install-location','/']
        if cfg:
            cmd+=['--sign',cfg['APPLE_INSTALLER_SIGN_IDENTITY']]
            if key:cmd+=['--keychain',str(key)]
        cmd+=[str(result)];run(cmd)
        if cfg:run(['pkgutil','--check-signature',str(result)]);notarize(result,cfg)
        return result
    finally:
        if key:subprocess.run(['security','delete-keychain',str(key)],check=False,capture_output=True)
        shutil.rmtree(BUILD/'signing',ignore_errors=True)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--target',required=True,choices=['windows-x64','macos-arm64','macos-x64']);a=ap.parse_args();ver=version();clean();print('APP_VERSION='+ver);print('RequireSigning='+str(require_signing()));print('Python='+sys.version.replace(chr(10),' '));print('Platform='+platform.platform());print('Machine='+platform.machine())
    if a.target=='windows-x64':
        if os.name!='nt':raise RuntimeError('Windows 目标必须在 Windows runner 构建')
        result,portable_dir=build_windows(ver)
        print('BUILD_OUTPUT='+str(result));print('PORTABLE_OUTPUT='+str(portable_dir));return 0
    else:
        if sys.platform!='darwin':raise RuntimeError('macOS 目标必须在 macOS runner 构建')
        want='arm64' if a.target.endswith('arm64') else 'x64';actual='arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x64'
        if actual!=want:raise RuntimeError(f'Runner 架构不匹配：需要 {want}，实际 {actual}')
        result=build_mac(ver,want)
        print('BUILD_OUTPUT='+str(result));return 0
if __name__=='__main__':raise SystemExit(main())

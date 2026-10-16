# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, base64, glob, os, platform, re, secrets, shutil, subprocess, sys, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'Page_Operations_Monitor.py';ICON_WIN=ROOT/'PageOperationsMonitor.ico';ICON_MAC=ROOT/'PageOperationsMonitor.icns';DEPLOYER=ROOT/'tools/windows_deployer.py'
BUILD=ROOT/'build';DIST=ROOT/'dist';OUT=ROOT/'cloud-release';APP_ID='ProfessionalMonitorTool';BUNDLE_ID='com.bstbuku.pageoperationsmonitor';DEFAULT_TIMESTAMP_URL='http://timestamp.digicert.com'

def truthy(v):return str(v or '').strip().lower() in {'1','true','yes','on'}
def require_signing():return truthy(os.environ.get('REQUIRE_SIGNING'))
def run(args,cwd=None,secret_values=()):
    shown=[]
    for raw in map(str,args):
        masked=raw
        for s in secret_values:
            if s:masked=masked.replace(s,'***')
        shown.append(masked)
    print('\n>',' '.join(shown),flush=True);subprocess.run(args,cwd=cwd or ROOT,check=True)
def version():
    t=SOURCE.read_text(encoding='utf-8-sig');m=re.search(r'APP_VERSION\s*=\s*["\']v?(\d+\.\d+\.\d+)["\']',t)
    if not m:raise RuntimeError('主程序找不到 APP_VERSION')
    return m.group(1)
def clean():
    shutil.rmtree(BUILD,ignore_errors=True);shutil.rmtree(DIST,ignore_errors=True);shutil.rmtree(OUT,ignore_errors=True)
    BUILD.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
def common(icon=None):
    cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir','--name',APP_ID,'--workpath',str(BUILD/'pyinstaller'),'--distpath',str(DIST),'--specpath',str(BUILD/'spec'),'--collect-all','playwright']
    if icon and icon.exists():cmd+=['--icon',str(icon)]
    return cmd

def decode_secret(env_name,target):
    data=''.join(str(os.environ.get(env_name,'') or '').split())
    if not data:return None
    try:raw=base64.b64decode(data,validate=True)
    except Exception as e:raise RuntimeError(f'{env_name} 不是有效 Base64') from e
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);return target

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
    if bool(b64)!=bool(password):raise RuntimeError('WINDOWS_CERT_PFX_B64 / WINDOWS_CERT_PASSWORD 必须同时设置')
    if not b64:
        if require_signing():raise RuntimeError('正式发布要求 Windows 代码签名证书')
        print('::warning::未配置 Windows 签名证书，本次为测试包');return None
    cert=decode_secret('WINDOWS_CERT_PFX_B64',BUILD/'signing/windows.pfx');return cert,password
def pfx_thumbprint(cert,password):
    env=dict(os.environ);env['POM_PFX_PASSWORD']=password
    ps=("$p=ConvertTo-SecureString $env:POM_PFX_PASSWORD -AsPlainText -Force; "
        f"$d=Get-PfxData -FilePath '{str(cert).replace("'","''")}' -Password $p; "
        "$c=$d.EndEntityCertificates | Select-Object -First 1; if(-not $c){exit 2}; $c.Thumbprint")
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
def zip_payload(app_dir,payload):
    with zipfile.ZipFile(payload,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as zf:
        for p in sorted(app_dir.rglob('*')):
            if p.is_file():zf.write(p,p.relative_to(app_dir).as_posix())
def build_windows(ver):
    if not ICON_WIN.exists() or not DEPLOYER.exists():raise RuntimeError('缺少 Windows 图标或部署器源码')
    material=windows_material();thumb=pfx_thumbprint(*material) if material else ''
    patch_update_identity(win_thumb=thumb)
    run(common(ICON_WIN)+[str(SOURCE)])
    app_dir=DIST/APP_ID;exe=app_dir/(APP_ID+'.exe')
    if not exe.exists():raise RuntimeError('主程序 EXE 未生成')
    sign_windows(exe,material)
    payload=BUILD/'payload.zip';zip_payload(app_dir,payload)
    name=f'ProfessionalMonitorTool-{ver}-windows-x64-deployer'
    run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onefile','--name',name,'--workpath',str(BUILD/'deployer-work'),'--distpath',str(OUT),'--specpath',str(BUILD/'deployer-spec'),'--icon',str(ICON_WIN),'--add-data',str(payload)+os.pathsep+'.','--add-data',str(ICON_WIN)+os.pathsep+'.',str(DEPLOYER)])
    result=OUT/(name+'.exe')
    if not result.exists():raise RuntimeError('Windows 自定义部署器未生成')
    sign_windows(result,material)
    return result

def mac_config():
    names=('APPLE_APP_CERT_P12_B64','APPLE_APP_CERT_PASSWORD','APPLE_INSTALLER_CERT_P12_B64','APPLE_INSTALLER_CERT_PASSWORD','APPLE_APP_SIGN_IDENTITY','APPLE_INSTALLER_SIGN_IDENTITY')
    cfg={n:str(os.environ.get(n,'') or '').strip() for n in names}
    if any(cfg.values()) and not all(cfg.values()):raise RuntimeError('macOS 签名 Secrets 配置不完整')
    if not all(cfg.values()):
        if require_signing():raise RuntimeError('正式发布要求 Apple Developer ID 证书')
        print('::warning::未配置 macOS 签名证书，本次为测试包');return None
    for n in ('APPLE_ID','APPLE_TEAM_ID','APPLE_APP_PASSWORD'):cfg[n]=str(os.environ.get(n,'') or '').strip()
    if require_signing() and not all(cfg[n] for n in ('APPLE_ID','APPLE_TEAM_ID','APPLE_APP_PASSWORD')):raise RuntimeError('正式发布要求 Apple 公证凭据')
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
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--target',required=True,choices=['windows-x64','macos-arm64','macos-x64']);a=ap.parse_args();ver=version();clean();print('APP_VERSION='+ver);print('RequireSigning='+str(require_signing()))
    if a.target=='windows-x64':
        if os.name!='nt':raise RuntimeError('Windows 目标必须在 Windows runner 构建')
        result=build_windows(ver)
    else:
        if sys.platform!='darwin':raise RuntimeError('macOS 目标必须在 macOS runner 构建')
        want='arm64' if a.target.endswith('arm64') else 'x64';actual='arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x64'
        if actual!=want:raise RuntimeError(f'Runner 架构不匹配：需要 {want}，实际 {actual}')
        result=build_mac(ver,want)
    print('BUILD_OUTPUT='+str(result));return 0
if __name__=='__main__':raise SystemExit(main())

; 专业监控工具 Windows 安装程序（Inno Setup 6 脚本）
; 由 tools/cloud_build.py 在云端构建时以 /D 参数传入版本号、文件目录与输出位置：
;   /DAppVersion  版本号（取自主程序 APP_VERSION）
;   /DStageDir    待安装文件的 staging 目录（PyInstaller onedir 产物，不含 portable.mode）
;   /DOutputDir   安装程序输出目录
;   /DOutputName  安装程序文件名（固定历史名 ProfessionalMonitorTool-<ver>-windows-x64-deployer）
;   /DAppIcon     安装程序图标（.ico 绝对路径）
; 界面语言：官方简体中文（ChineseSimplified.isl）。构建脚本会在调用编译器之前
; 先核对该语言文件存在，缺失时直接报错，绝不静默回退英文界面。

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef StageDir
  #define StageDir "."
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif
#ifndef OutputName
  #define OutputName "ProfessionalMonitorTool-setup"
#endif
#ifndef AppIcon
  #define AppIcon "PageOperationsMonitor.ico"
#endif

[Setup]
AppName=专业监控工具
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersion}
AppVerName=专业监控工具 {#AppVersion}
AppId=ProfessionalMonitorTool
AppPublisher=bstbuku-ship-it
AppPublisherURL=https://github.com/bstbuku-ship-it/Page-Operations-Monitor
DefaultDirName={localappdata}\Programs\专业监控工具
DefaultGroupName=专业监控工具
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
SetupIconFile="{#AppIcon}"
UninstallDisplayIcon={app}\ProfessionalMonitorTool.exe
WizardStyle=modern
ShowLanguageDialog=no
SolidCompression=yes
Compression=lzma2

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\专业监控工具"; Filename: "{app}\ProfessionalMonitorTool.exe"
Name: "{autodesktop}\专业监控工具"; Filename: "{app}\ProfessionalMonitorTool.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ProfessionalMonitorTool.exe"; Description: "{cm:LaunchProgram,专业监控工具}"; Flags: nowait postinstall skipifsilent

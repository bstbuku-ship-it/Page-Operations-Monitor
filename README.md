# 主页运营监控工具

用于监控 Facebook 公共主页的粉丝增长、最近发帖时间及主页活跃情况的桌面工具。

当前版本：**v1.3.0**  
GitHub：`bstbuku-ship-it/Page-Operations-Monitor`

## v1.3.0

- 浏览器连接器改为同一台电脑自动发现、自动连接，不再要求手动输入配对码。
- 同时检测到多个 Chrome Profile 时，由用户选择用于巡检的浏览器，并记住上次选择。
- 专业 ID 管理支持粉丝监控与发帖监控独立启用，支持单个勾选和批量管理。
- 主界面显示上次巡检时间，并支持随机巡检间隔与随机主页间隔。
- 关闭窗口后可静默留在系统托盘继续运行；再次启动程序时唤回已有窗口，避免重复启动多个实例。
- 最近预警增加主页头像，主页名称、头像与浏览器数据同步逻辑持续优化。
- 软件更新支持 GitHub Releases；Windows 与 macOS 安装包由 GitHub Actions 云端构建。

## 用户下载哪个文件？

推荐普通用户只下载自己系统对应的 **bundle.zip 完整包**：

- Windows：`PageOperationsMonitor-1.3.0-windows-x64-bundle.zip`
- Mac Apple 芯片（M1/M2/M3/M4...）：`PageOperationsMonitor-1.3.0-macos-arm64-bundle.zip`
- Mac Intel：`PageOperationsMonitor-1.3.0-macos-x64-bundle.zip`

每个完整包里已经同时放入：

1. 当前系统的软件安装包；
2. `浏览器插件` 文件夹；
3. 本 README；
4. 安装说明。

因此用户不需要分别寻找“软件”和“插件”两个下载。

## Windows 安装

1. 解压 Windows 完整包。
2. 运行 `PageOperationsMonitor-1.3.0-windows-x64-setup.exe`。
3. 安装完成后启动 **主页运营监控工具**。
4. 按下面“安装 Chrome 浏览器连接器”步骤安装插件。

## macOS 安装

1. 根据 Mac 芯片下载 arm64 或 x64 完整包。
2. 解压后运行 `.pkg` 安装包。
3. 安装完成后从“应用程序”启动 **PageOperationsMonitor**。
4. 按下面步骤安装 Chrome 浏览器连接器。

> 当前云端工作流已经支持生成 macOS 安装包，但如果发布者还没有配置 Apple Developer ID 签名和 Apple 公证，macOS 可能显示“未知开发者”安全提示。正式大规模分发时建议后续补上 Apple 签名/公证。

## 安装 Chrome 浏览器连接器

1. 打开需要用于 Facebook 巡检的 Chrome Profile。
2. 地址栏输入 `chrome://extensions`。
3. 打开右上角 **开发者模式**。
4. 点击 **加载已解压的扩展程序**。
5. 选择完整包中的 **浏览器插件** 文件夹；该文件夹里面应直接看到 `manifest.json`。
6. 软件与插件处于同一台电脑时会自动发现并连接，不需要配对码。
7. 如果软件识别到多个在线浏览器/Profile，在软件右上角 **浏览器** 中选择需要使用的连接。

Chrome 必须保持运行，且对应 Profile 中 Facebook 登录状态有效。

## 自动巡检

- 软件启动后默认不会自动开始巡检，是否启动由用户自行开启。
- 每轮巡检间隔及随机浮动范围可以在软件中设置。
- 两个主页之间的等待时间支持随机范围，减少固定时间间隔。
- 关闭主窗口后可继续在系统托盘运行。

## 自动更新

安装版会从 GitHub Releases 检查更新。云端发布流程会同时生成：

- Windows 安装包；
- macOS arm64 安装包；
- macOS x64 安装包；
- `update-manifest.json`（包含安装包 SHA-256）；
- 独立浏览器插件 ZIP；
- 各平台“软件 + 插件”完整 ZIP。

用户从软件内执行更新时，程序使用对应系统的安装包；普通新用户则推荐直接下载 bundle.zip。

---

# 发布者说明：只在 GitHub 云端打包

**本项目不要求发布者在自己的 Windows/Mac 电脑运行 PyInstaller、Inno Setup 或 pkgbuild。**

真正的打包工作全部在 `.github/workflows/release.yml` 指定的 GitHub Actions runner 中完成：

- Windows x64：GitHub Windows runner；
- macOS Apple Silicon：GitHub macOS arm64 runner；
- macOS Intel：GitHub macOS Intel runner。

## 仓库固定路径

仓库根目录应保持下面结构：

```text
Page-Operations-Monitor/
├─ Page_Operations_Monitor.py          # 你每次更新的主程序
├─ PageOperationsMonitor.ico           # Windows 图标
├─ PageOperationsMonitor.icns          # macOS 图标
├─ README.md                            # 使用说明 + 版本日志
├─ browser-extension/                  # Chrome 插件源码（长期保留）
│  ├─ manifest.json
│  ├─ background.js
│  ├─ extractor.js
│  ├─ options.html
│  ├─ options.js
│  ├─ popup.html
│  ├─ popup.js
│  ├─ ui.css
│  └─ icons/
├─ tools/
│  ├─ cloud_build.py                   # GitHub runner 构建安装器
│  └─ assemble_release.py              # 合并软件、插件、manifest
└─ .github/
   └─ workflows/
      └─ release.yml                   # 点击 Run workflow 就执行它
```

### 以后发布新版本，你通常只需要改这几个文件

1. `Page_Operations_Monitor.py`
2. `README.md` 中的版本日志
3. 如果插件也修改，再修改 `browser-extension/`
4. 图标没有变化就不用每次重新上传

**不要把 EXE、PKG、build、dist 文件手动上传到仓库。GitHub Actions 会自己生成。**

## 在 GitHub 网页上发布

1. 打开仓库：`bstbuku-ship-it/Page-Operations-Monitor`。
2. 确认上述文件已经提交到 `main` 分支。
3. 点击仓库顶部 **Actions**。
4. 左边选择 **Build and Release / 云端打包发布**。
5. 右边点击 **Run workflow**。
6. Branch 选择 `main`。
7. 再点击绿色 **Run workflow**。
8. 等待 Windows、macOS Apple Silicon、macOS Intel 三个平台全部变绿。
9. 工作流最后的“合并软件 + 插件并发布 Release”会自动创建 `v1.3.0` Release。
10. 打开仓库右侧 **Releases**，即可看到最终下载文件。

如果 `v1.3.0` 已存在，再运行同一个工作流会覆盖本版本附件，便于正式发布前反复测试。

## 版本规则

主程序必须存在：

```python
APP_VERSION = "1.3.0"
```

插件 `browser-extension/manifest.json` 的 `version` 也必须是：

```json
"version": "1.3.0"
```

两个版本不同，云端工作流会直接停止，避免发布错版本。

## 图标说明

Windows 原生安装包使用：

```text
PageOperationsMonitor.ico
```

macOS 原生 `.app` 使用：

```text
PageOperationsMonitor.icns
```

macOS 原生应用图标不应该直接使用 Windows `.ico`，因此仓库中需要同时保留 `.ico` 和 `.icns` 两个文件。

## 发布后的主要文件

```text
PageOperationsMonitor-1.3.0-windows-x64-setup.exe
PageOperationsMonitor-1.3.0-macos-arm64.pkg
PageOperationsMonitor-1.3.0-macos-x64.pkg
POM-Browser-Connector-1.3.0.zip
PageOperationsMonitor-1.3.0-windows-x64-bundle.zip
PageOperationsMonitor-1.3.0-macos-arm64-bundle.zip
PageOperationsMonitor-1.3.0-macos-x64-bundle.zip
PageOperationsMonitor-1.3.0-source.zip
update-manifest.json
```

其中 **bundle.zip 就是给普通用户的一次性“软件 + 插件”完整下载包**。

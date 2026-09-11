<p align="center">
    <picture>
      <source media="(prefers-color-scheme: light)" srcset="./docs/assets/readme/hero-light.png" />
      <img src="./docs/assets/readme/hero-dark.png" />
  </picture>
</p>
<h1 align="center">
  <span>YASB Reborn</span>
</h1>
<p align="center">
  <span align="center">YASB（Yet Another Status Bar）是一款高度可配置的 Windows 状态栏，使用 Python 编写，支持众多组件、轻松换肤与深度自定义。</span>
</p>

<h3 align="center">
  <a href="https://github.com/amnweb/yasb/wiki/Installation">安装</a>
  <span> · </span>
  <a href="https://github.com/amnweb/yasb/wiki">文档</a>
  <span> · </span>
  <a href="https://github.com/amnweb/yasb-themes">主题</a>
  <span> · </span>
  <a href="https://github.com/amnweb/yasb/discussions">讨论</a>
  <span> · </span>
  <a href="https://discord.gg/qkeunvBFgX">Discord</a>
</h3>
<br/><br/>

## 📋 Installation

详细的安装说明与系统要求请参阅[安装文档](https://github.com/amnweb/yasb/wiki/Installation)。
如果想快速上手，可从以下安装方式中选择一种：
<br/><br/>
<details open>
<summary><strong>从 GitHub 下载 .msi 安装包</strong></summary>
<br/>
前往 <a href="https://github.com/amnweb/yasb/releases/latest">YASB 的 GitHub Releases 页面</a>，点击 Assets 展开下载列表，选择与你设备架构和安装范围匹配的安装包。大多数设备选择 x64 用户级安装包即可。
</details>

<details>
<summary><strong>WinGet</strong></summary>
<br/>
通过 <a href="https://github.com/microsoft/winget-cli#installing-the-client">WinGet</a> 下载 YASB。使用 winget 更新 YASB 会遵循当前的安装范围。在命令行 / PowerShell 中运行以下命令即可安装：

*用户级安装包【默认】*
```powershell
winget install AmN.yasb
```

*计算机全局安装包*
```powershell
winget install --scope machine AmN.yasb
```
</details>

<details>
<summary><strong>Scoop</strong></summary>
<br/>
通过 <a href="https://scoop.sh/">Scoop</a> 下载 YASB。使用 Scoop 更新 YASB 会遵循当前的安装范围。使用 Scoop 安装 YASB，请在命令行 / PowerShell 中运行：

*使用 Scoop 安装 YASB*
```powershell
scoop bucket add extras
scoop install extras/yasb
```
</details>
 
<details>
<summary><strong>Chocolatey</strong></summary>
<br/>
通过 <a href="https://chocolatey.org/">Chocolatey</a> 下载 YASB。使用 Chocolatey 更新 YASB 会遵循当前的安装范围。使用 Chocolatey 安装 YASB，请在命令行 / PowerShell 中运行：

*使用 Chocolatey 安装 YASB*
```powershell
choco install yasb
```
</details>
 
## 💻 效果展示
![Dark Themea](https://raw.githubusercontent.com/amnweb/yasb/main/docs/assets/readme/demo-dark.jpg)
![Light Theme](https://raw.githubusercontent.com/amnweb/yasb/main/docs/assets/readme/demo-light.jpg)


## 🛠️ YASB 当前可用的组件列表

| 组件 | 说明 |
| --- | --- |
| [活动窗口标题](https://github.com/amnweb/yasb/wiki/(Widget)-Active-Windows-Title) | 显示当前活动窗口的标题。 |
| [应用程序](https://github.com/amnweb/yasb/wiki/(Widget)-Applications) | 显示预定义应用程序列表。 |
| [音频可视化](https://github.com/amnweb/yasb/wiki/(Widget)-Audio-Visualizer) | 默认输出设备的原生音频可视化（WASAPI 回环） |
| [电池](https://github.com/amnweb/yasb/wiki/(Widget)-Battery) | 显示当前电池状态。 |
| [蓝牙](https://github.com/amnweb/yasb/wiki/(Widget)-Bluetooth) | 显示当前蓝牙状态与已连接设备。 |
| [亮度](https://github.com/amnweb/yasb/wiki/(Widget)-Brightness) | 显示并调整当前屏幕亮度。 |
| [Cava](https://github.com/amnweb/yasb/wiki/(Widget)-Cava) | 使用 Cava 显示音频可视化。 |
| [Claude 用量](https://github.com/amnweb/yasb/wiki/(Widget)-Claude-Usage) | 显示你的 Claude 订阅用量。 |
| [Copilot](https://github.com/amnweb/yasb/wiki/(Widget)-Copilot) | GitHub Copilot 用量，带统计详情的菜单 |
| [CPU](https://github.com/amnweb/yasb/wiki/(Widget)-CPU) | 显示当前 CPU 使用率与信息。 |
| [时钟](https://github.com/amnweb/yasb/wiki/(Widget)-Clock) | 显示当前时间与日期，支持自定义格式。 |
| [控制中心](https://github.com/amnweb/yasb/wiki/(Widget)-Control-Center) | 可自定义的快速设置控制中心，包含快捷操作、滑块与媒体控制。 |
| [自定义](https://github.com/amnweb/yasb/wiki/(Widget)-Custom) | 创建自定义组件。 |
| [专注助手](https://github.com/amnweb/yasb/wiki/(Widget)-Dnd) | 监控并切换 Windows 专注助手（勿扰模式）。 |
| [GitHub](https://github.com/amnweb/yasb/wiki/(Widget)-Github) | 显示来自 GitHub 的通知。 |
| [GlazeWM 按键模式](https://github.com/amnweb/yasb/wiki/(Widget)-GlazeWM-Binding-Mode) | GlazeWM 按键模式组件。 |
| [GlazeWM 平铺方向](https://github.com/amnweb/yasb/wiki/(Widget)-GlazeWM-Tiling-Direction) | GlazeWM 平铺方向组件。 |
| [GlazeWM 工作区](https://github.com/amnweb/yasb/wiki/(Widget)-GlazeWM-Workspaces) | GlazeWM 工作区组件。 |
| [血糖监测](https://github.com/amnweb/yasb/wiki/(Widget)-Glucose-Monitor) | Nightscout CGM 组件。 |
| [分组器](https://github.com/amnweb/yasb/wiki/(Widget)-Grouper) | 将多个组件组合在一个容器中。 |
| [GPU](https://github.com/amnweb/yasb/wiki/(Widget)-GPU) | 显示 GPU 利用率、温度与显存占用。 |
| [主页](https://github.com/amnweb/yasb/wiki/(Widget)-Home) | 可自定义的主页组件菜单。 |
| [磁盘](https://github.com/amnweb/yasb/wiki/(Widget)-Disk) | 显示磁盘使用信息。 |
| [输入语言](https://github.com/amnweb/yasb/wiki/(Widget)-Language) | 显示当前输入语言并支持切换。 |
| [启动台](https://github.com/amnweb/yasb/wiki/(Widget)-Launchpad) | 可自定义的启动台，快速访问应用程序。 |
| [Libre Hardware Monitor](https://github.com/amnweb/yasb/wiki/(Widget)-Libre-HW-Monitor) | 连接 Libre Hardware Monitor 获取传感器数据。 |
| [媒体](https://github.com/amnweb/yasb/wiki/(Widget)-Media) | 显示媒体控制与信息。 |
| [极简媒体](https://github.com/amnweb/yasb/wiki/(Widget)-Media-Lite) | 竖排极简专辑风格媒体组件。 |
| [内存](https://github.com/amnweb/yasb/wiki/(Widget)-Memory) | 显示当前内存使用情况与信息。 |
| [麦克风](https://github.com/amnweb/yasb/wiki/(Widget)-Microphone) | 显示当前麦克风状态。 |
| [通知](https://github.com/amnweb/yasb/wiki/(Widget)-Notifications) | 显示来自 Windows 的通知数量。 |
| [便签](https://github.com/amnweb/yasb/wiki/(Widget)-Notes) | 简单的便签组件，支持添加、删除和查看。 |
| [OBS](https://github.com/amnweb/yasb/wiki/(Widget)-Obs) | 与 OBS Studio 集成，显示各类直播信息。 |
| [Open Meteo](https://github.com/amnweb/yasb/wiki/(Widget)-Open-Meteo) | 使用 Open Meteo API 显示天气信息。 |
| [电源计划](https://github.com/amnweb/yasb/wiki/(Widget)-Power-Plan) | 显示当前电源计划并支持切换。 |
| [服务器监控](https://github.com/amnweb/yasb/wiki/(Widget)-Server-Monitor) | 监控服务器状态。 |
| [系统托盘](https://github.com/amnweb/yasb/wiki/(Widget)-Systray) | 显示系统托盘图标。 |
| [网络流量](https://github.com/amnweb/yasb/wiki/(Widget)-Traffic) | 显示网络流量信息。 |
| [待办事项](https://github.com/amnweb/yasb/wiki/(Widget)-Todo) | 整理你的任务与待办清单。 |
| [任务栏](https://github.com/amnweb/yasb/wiki/(Widget)-Taskbar) | 可自定义的任务栏，用于启动应用程序。 |
| [番茄钟](https://github.com/amnweb/yasb/wiki/(Widget)-Pomodoro) | 番茄工作法计时器组件。 |
| [电源菜单](https://github.com/amnweb/yasb/wiki/(Widget)-Power-Menu) | 电源选项菜单。 |
| [快速启动](https://github.com/amnweb/yasb/wiki/(Widget)-Quick-Launch) | 功能强大、可高度自定义的快速启动组件，支持众多插件。 |
| [回收站](https://github.com/amnweb/yasb/wiki/(Widget)-Recycle-Bin) | 显示回收站状态。 |
| [更新检查](https://github.com/amnweb/yasb/wiki/(Widget)-Update-Check) | 使用 Windows Update 与 Winget 检查可用更新。 |
| [Visual Studio Code](https://github.com/amnweb/yasb/wiki/(Widget)-VSCode) | 显示 Visual Studio Code 最近打开的文件夹。 |
| [音量](https://github.com/amnweb/yasb/wiki/(Widget)-Volume) | 显示并控制系统音量。 |
| [壁纸](https://github.com/amnweb/yasb/wiki/(Widget)-Wallpapers) | 壁纸管理器组件。 |
| [天气](https://github.com/amnweb/yasb/wiki/(Widget)-Weather) | 显示当前天气信息。 |
| [WiFi](https://github.com/amnweb/yasb/wiki/(Widget)-WiFi) | 显示当前 WiFi 状态与可用网络。 |
| [WHKD](https://github.com/amnweb/yasb/wiki/(Widget)-Whkd) | 显示 WHKD 当前的按键绑定模式。 |  
| [Windows 虚拟桌面](https://github.com/amnweb/yasb/wiki/(Widget)-Windows-Desktops) | Windows 虚拟桌面组件。 |
| [窗口控制](https://github.com/amnweb/yasb/wiki/(Widget)-Window-Controls) | 提供最小化、最大化/还原与关闭当前焦点窗口的按钮。 |
| [窗口切换器](https://github.com/amnweb/yasb/wiki/(Widget)-Window-Switcher) | 快速轻量的应用切换器。 |
| [Komorebi 控制](https://github.com/amnweb/yasb/wiki/(Widget)-Komorebi-Control) | Komorebi 控制组件。 |
| [Komorebi 布局](https://github.com/amnweb/yasb/wiki/(Widget)-Komorebi-Layout) | 显示 Komorebi 当前布局。 |
| [Komorebi 堆叠](https://github.com/amnweb/yasb/wiki/(Widget)-Komorebi-Stack) | 显示 Komorebi 当前堆叠中的窗口。 |
| [Komorebi 工作区](https://github.com/amnweb/yasb/wiki/(Widget)-Komorebi-Workspaces) | Komorebi 工作区组件。 |


## 🤝 贡献者
感谢所有出色的贡献者！

[![YASB Contributors](https://contrib.rocks/image?repo=amnweb/yasb)](https://github.com/amnweb/yasb/graphs/contributors)

## 🔑 代码签名政策
免费代码签名由 [SignPath.io](https://about.signpath.io/) 提供，证书由 [SignPath Foundation](https://signpath.org/) 颁发

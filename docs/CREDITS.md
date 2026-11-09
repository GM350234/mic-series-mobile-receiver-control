# 致谢与许可

本项目是独立实现，但站在社区工作的肩膀上。以下列出实际参考/复用的内容。

## 代码复用

### hogancv/dji-mic-mini-monitor — MIT

https://github.com/hogancv/dji-mic-mini-monitor

- `dji_mic/winusb.py` 的 SetupAPI / WinUSB ctypes 声明、设备枚举、OVERLAPPED 读写与超时取消逻辑，改编自该项目的 `src/micbattery.py`
- `driver/djimic_pc_winusb.inf`、`driver/install_winusb.ps1`、`driver/uninstall_winusb.ps1` 改编自该项目的 `driver/`（改了文件名、证书主题、去掉了它自己的电量读取步骤）

MIT 许可证允许修改与再分发，要求保留版权与许可声明。原始项目版权归其作者所有。

## 界面设计

### hhikr/endfield-ui-skill

https://github.com/hhikr/endfield-ui-skill

- 新版界面的设计语言、颜色/字号/切角/动效 token、`web/assets/endfield.css`、`fx.js`、`variant.js` 与等高线 SVG
- 该项目的 README 明确写明“所有代码、模板、token 和规则可自由使用”
- `web/assets/fonts/Saira.ttf` 是 Saira（Copyright 2020 The Saira Project Authors），SIL Open Font License 1.1，许可证见 `web/assets/fonts/Saira-OFL.txt`

## 协议事实来源

### ShadowBitBasher/DJI-Mic-Control — Unlicense（公有领域）

https://github.com/ShadowBitBasher/DJI-Mic-Control

- DUML 帧结构、CRC8/CRC16 参数、`0x5B` 命令集、v1/v2 心跳/状态字段、各设置命令 ID

### piedol/lavdeck — GPL-3.0

https://github.com/piedol/lavdeck

- 手机版接收器（Mobile RX）的 `0x5B/0x01` V2 负载布局、`0x0008` 声道、`0x0039` 增益
- TLV 状态推送的字段偏移（接收器 `h`、发射器 `w`、连接掩码、USB 位）
- 仅参考其公开协议文档与抓包结论，**没有复制其 Rust/Swift 代码**

### russellmilliner/dji-mic-mini-kde — MIT

https://github.com/russellmilliner/dji-mic-mini-kde

- 交叉验证 `2ca3:4011`、DUML v1/v2 帧结构与端点

## 仅作背景调研

- [caballeropedro/dji-mic](https://github.com/caballeropedro/dji-mic)（未声明许可证，未使用代码）
- [usokawa/dji-mic-mo](https://github.com/usokawa/dji-mic-mo)（BSD-2，未使用代码）
- [w1ne/stereo-bridge](https://github.com/w1ne/stereo-bridge)（Apache-2.0，不经接收器的 LC3 路线）
- [WilliamPrime/DJI-mic-mini-dongle-replacement](https://github.com/WilliamPrime/DJI-mic-mini-dongle-replacement)（GPL-3.0，硬件替代方案）

## 运行时与构建

| 组件 | 用途 | 许可证 |
|---|---|---|
| CPython / tkinter | 运行时与旧版兜底界面 | PSF License |
| Microsoft Edge / Google Chrome | 新版界面的应用窗口 | Microsoft / Google 系统组件 |
| Saira | 界面拉丁字体 | SIL OFL 1.1 |
| Pillow | 生成应用图标 | MIT-CMU |
| PyInstaller | 打包单文件 exe | GPL-2.0-or-later，含 bootloader 例外 |
| Microsoft `winusb.sys` | MI_06 的用户态 USB 驱动 | Microsoft 系统组件 |

## 商标

“DJI”“DJI Mic”“Mic Mini”是大疆创新（DJI）的商标。本项目为非官方兼容工具，与 DJI 无任何关联、未获其背书。

## 本项目许可

除上述第三方内容外，本项目代码以 MIT 许可证发布。使用风险自负。

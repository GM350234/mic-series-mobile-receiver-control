# 第三方组件与许可

本项目以 MIT 许可发布（见 `LICENSE`）。以下内容来自第三方，按各自许可使用。

## 1. WinUSB 访问代码与驱动脚本

`dji_mic/winusb.py` 的 SetupAPI / WinUSB ctypes 声明、设备枚举、OVERLAPPED 读写与超时取消逻辑，以及 `driver/djimic_pc_winusb.inf`、`driver/install_winusb.ps1`、`driver/uninstall_winusb.ps1`，改编自：

- **hogancv/dji-mic-mini-monitor** — https://github.com/hogancv/dji-mic-mini-monitor
- Copyright (c) 2026 Hogan (https://github.com/hogancv)
- MIT License

```
MIT License

Copyright (c) 2026 Hogan (https://github.com/hogancv)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 2. 界面套件

`web/assets/endfield.css`、`web/assets/fx.js`、`web/assets/variant.js` 和 `web/assets/contours/` 来自：

- **hhikr/endfield-ui-skill** — https://github.com/hhikr/endfield-ui-skill
- 该项目 README 明确写明“所有代码、模板、token 和规则可自由使用”
- 本项目只使用其代码/设计 token，不包含任何游戏官方素材

## 3. 字体

`web/assets/fonts/Saira.ttf` 是 **Saira**（Copyright 2020 The Saira Project Authors），SIL Open Font License 1.1。完整许可证见 `web/assets/fonts/Saira-OFL.txt`。

## 4. 协议事实参考

- **ShadowBitBasher/DJI-Mic-Control** — Unlicense（公有领域）：DUML 帧结构、CRC、命令集与状态字段
- **piedol/lavdeck** — GPL-3.0：手机版接收器的协议文档与抓包结论（仅参考事实，未复制代码）
- **russellmilliner/dji-mic-mini-kde** — MIT：交叉验证 VID/PID 与帧结构

## 5. 商标

“DJI”“DJI Mic”“Mic Mini”“Mic 2”“Mic 3”是大疆创新（DJI）的商标。本项目为非官方兼容工具，与 DJI 无任何关联，也未获其背书。

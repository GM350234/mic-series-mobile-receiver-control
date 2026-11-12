# AGENTS.md — Mic Series Mobile Receiver 交接手册

> 给接手这个仓库的 Agent。先读本文件，再读 [`README.md`](README.md)、[`docs/PROTOCOL.md`](docs/PROTOCOL.md) 和 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。
> 本项目是非官方工具，协议来自社区逆向；不要把“能读到状态”误认为“可以随便写”。

## 0. 一句话

Windows 上控制 DJI Mic 系列手机版接收器（USB-C 直插手机的那只 RX）的桌面工具：Python 负责 WinUSB/DUML，Web UI 负责界面，Edge/Chrome 应用窗口负责呈现。只写增益、声道、15 分钟自动关机三个已验证设置，不碰固件。

当前状态（交接时）：

- 应用版本：`1.0.0`（`dji_mic/__init__.py`）
- 已验证设备：DJI Mic Mini 2 手机版接收器，固件 `02.03.17.00`；TX 为 DJI Mic Mini
- 仓库：已初始化 git，初始提交 `179eb6d`；`docs/` 下的视频脚本/封面等是未跟踪内容，不要擅自删除或提交
- 本地生成、已被 `.gitignore` 排除：`build/`、`dist/`、`release/`、`vendor/`、`_recover/`、`_testchrome/`、`*.spec`、`gui.pid`
- 当前发布包：`release/MicSeriesControl-win64.zip`（不跟踪，建议挂 GitHub Releases）

## 1. 架构

```text
Edge/Chrome --app 窗口
  web/index.html + web/app.js + web/app.css + web/assets/endfield.css
        │  GET /api/state 每 300ms；POST /api/gain /channel /auto-off /reconnect /install-driver /quit
        ▼
dji_mic/webui.py
  AppState（命令串行化、日志、/api 路由、单实例、浏览器启动、watchdog）
        │
dji_mic/device.py  MicController
  watchdog（1s 找设备）+ reader 线程（0x86）+ pending ACK + 状态模型
        │
dji_mic/winusb.py  WinUsbDevice
  SetupAPI 枚举 → CreateFile(OVERLAPPED) → WinUsb_Initialize
  Bulk IN 0x86 / OUT 0x06
        │
DJI Mic Series Mobile RX（VID 2CA3 / PID 4011，MI_06）
```

另一个界面：`dji_mic/ui.py` 是旧 Tk 兜底（`python -m dji_mic --classic`），与 Web UI 共用同一个 `MicController`。它不是主界面，功能更新通常只做在 Web UI；`tools/gui_smoke.py` 测的是这个旧界面。

## 2. 文件地图

| 路径 | 职责 | 关键符号 / 备注 |
|---|---|---|
| `dji_mic/duml.py` | DUML 帧、CRC、状态模型、设置帧 | `Frame`、`StreamParser`、`crc8`、`crc16`、`apply_frame`、`MicStatus` |
| `dji_mic/winusb.py` | MI_06 的 WinUSB 封装 | `WinUsbDevice`、`find_interface_path`、`driver_state`、`enum_device_paths` |
| `dji_mic/device.py` | 连接生命周期、读写线程、命令 | `MicController`、`set_gain`、`set_channel`、`set_auto_power_off`、`_send` |
| `dji_mic/webui.py` | 本地 HTTP 服务 + 浏览器启动 + 生命周期 | `AppState`、`Handler`、`open_browser`、`watchdog` |
| `dji_mic/ui.py` | 旧 Tk 兜底界面 | `App`、`_apply_gain`、`_toggle_auto_off` |
| `launcher.py` | PyInstaller 入口 | 只调用 `dji_mic.webui.main` |
| `dji_mic/__main__.py` | `python -m dji_mic` 入口 | 默认 Web UI；`--classic` 切 Tk |
| `web/index.html` | 页面结构 | 增益滑块、声道、电源、TX、设备、日志 |
| `web/app.js` | 前端状态机 / API 调用 | `state`、`syncGain`、`previewGainAt`、`endGainDrag`、`loop` |
| `web/app.css` | 产品层样式 | `--x`/`--pos`、`.gain-slider`、`.tx-card`、`.log-panel`、响应式 |
| `web/assets/endfield.css` | Endfield 设计套件（第三方，可自由使用） | 不要手改；产品覆盖放 `app.css` |
| `web/assets/fx.js` | 主题切换、读数动画、toast | `wireTheme`、`scramble`、`toast`、`flashDone` |
| `driver/` | MI_06 的 WinUSB INF + 签名安装/卸载 | 只绑 `MI_06`；不碰 `MI_01`/`MI_00` |
| `tools/mic_cli.py` | 无界面命令行 | `status`、`set-gain`、`set-channel`、`caps`；暂无 `set-auto-off` |
| `tools/raw_dump.py` | 原始帧十六进制打印 | 只读，适合抓包/排错 |
| `tools/capture_fixtures.py` | 抓真实帧写 `tests/fixtures` | 会覆盖 fixtures，慎用 |
| `tests/test_duml.py` | 协议单元测试（9 个） | 不依赖设备；CI 跑这个 |
| `scripts/build_exe.ps1` | 打包 + 发布目录 + zip | 需要 PyInstaller；`--add-data web;web` |
| `.github/workflows/tests.yml` | CI | Windows + Python 3.12，只跑单元测试 |
| `THIRD_PARTY_NOTICES.md` | 第三方许可全文 | 与 `docs/CREDITS.md` 保持同步 |

## 3. 代码注释地图（读代码时先看这些）

### `duml.py`

- 顶部 docstring 是 DUML 帧布局：`0x55 | len(10bit)+ver | CRC8 | sender | receiver | seq | cmd_type | cmd_set | cmd_id | payload | CRC16`。
- `crc8` / `crc16` docstring 写明多项式/初值：CRC8 `0x8C` 反射、初值 `0x77`；CRC16 `0x8408` 反射、初值 `0x3692`。
- `Frame.encode/decode` 是唯一的帧编解码入口；不要在其他地方手拼帧。
- `StreamParser` 处理 iAP2 噪声和半包；切帧靠 CRC，不只看 `0x55`。
- `apply_frame` / `_apply_record` 的注释标出 record 类型：`0x01` 身份、`0x02` TX 状态、`0x03` RX 状态、`0x04` 蓝牙 ID、`0x05` 电平、`0x06` 产品名。
- 常量 `SETTING_TRANSMITTER_MUTE` 存在但未使用；不要因为“有常量”就发送。

### `winusb.py`

- 顶部 docstring 说明：Windows 没有 MI_06 内置驱动，必须先用 `driver/install_winusb.ps1` 绑 `winusb.sys`。
- `read()` docstring 明确返回值：`bytes` 成功，`b""` 超时，`None` 真错误。
- `close()` 上方注释解释为什么要等 `_io_idle` 再 `WinUsb_Free`：否则后台读线程会在 `WinUsb_GetOverlappedResult` 里访问已释放内存。
- `_enter_io` / `_leave_io` / `_active_io` 是关闭同步的关键，不要为了让 close 更快而删掉。
- `SP_DEVICE_INTERFACE_DATA` / `OVERLAPPED` 用原生对齐；不要加 `_pack_ = 1`。

### `device.py`

- 类 docstring：所有回调都在后台线程；UI 只能入队，不要直接碰 tkinter/浏览器 DOM。
- `_watchdog`：每 1s 查一次路径；没有 link 就尝试打开；路径消失就关闭。
- `_read_loop`：连续 3 次 `None` 才判定断开；`b""` 是超时，继续。
- `_send`：seq 与 `pending` 队列匹配 ACK；`_write_lock` 串行化写；等待 2s。
- `_send_setting`：ACK payload 首字节 0 才算成功；`0xff` 抛 `CommandRejected`。
- `set_gain` / `set_channel` / `set_auto_power_off`：先校验范围，再等状态帧确认（3s），不是“发出去就算成功”。

### `webui.py`

- 顶部 docstring：浏览器只是表现层，USB/DUML 都在 Python；用 Edge/Chrome `--app` 开窗口。
- `resource_dir()` vs `app_dir()` 是最容易搞混的一对：
  - `resource_dir()` → `_MEIPASS`（打包后的 `web/`）
  - `app_dir()` → exe 所在目录（`driver/`）
- `AppState.command_lock`：同一时刻只允许一个设置命令；`snapshot()["busy"]` 来自它。
- `Handler._serve_static` 的注释：所有静态资源 `no-store`，避免旧 `app.css/app.js` 配新 `index.html`。
- `Handler` 路由、`/api/bye`、`/api/quit`、`watchdog` 的注释/逻辑见第 5 节。
- `open_browser()`：优先 Edge/Chrome，`--app` + 专用 profile；没有浏览器则退回默认浏览器。

### `web/app.js`

- `state` 里的 `dirtyGain` / `dirtyChannel` / `gainDragging` / `busy` / `offline` 是 UI 状态机的核心。
- `syncGain()`：状态更新时只在 `!gainDragging` 时把 `--x` 设到最近档位；拖动中由 `previewGainAt` 自由控制。
- `previewGainAt()` 上方注释：拖动时 cap/fill 连续跟手；最近 6 dB 档位只用于读数和刻度；松手才吸附。
- `endGainDrag()`：先把 `state.gainDragging = false`，再 `selectGain()`；顺序反了会在松手瞬间仍不吸附。
- `render()` 里设备面板的“产品”固定写 `Mic Series Mobile Receiver`；实际检测到的型号放在 `title` 提示里（用户明确要求）。
- `loop()`：300ms 轮询；离线 1s；页面关闭时 `pagehide` 发 `/api/bye`。

### `web/app.css`

- 分区注释：command bar、page frame、dashboard、sections、transmitters、device+log、footer、states、responsive。
- 增益滑块两套坐标：
  - `--pos`：0–4 的离散档位索引（读数/刻度/当前值标记）
  - `--x`：0–1 的连续位置（拖动中的 cap/fill）
- `.gain-slider:not(.is-dragging)` 才给 `left/width` 过渡；拖动中必须没有过渡，否则“跟手”会变成慢半拍。
- `.ef-btn:disabled` 在 `app.css` 覆盖成 chip 底/次级文字，避免深色主题下按钮文字看不见。

### `ui.py`（旧 Tk）

- 顶部 docstring 已说明是 classic fallback；不要把它当主界面继续加功能，除非明确要求。
- `_apply_gain` / `_apply_channel` / `_toggle_auto_off` 与 Web 版共用 `MicController`；逻辑可参考但 UI 代码不要互相复制。

### `driver/`

- INF 只匹配 `USB\VID_2CA3&PID_4011&MI_06`；安装脚本创建本机自签名证书、加入 Root/TrustedPublisher、用 `pnputil` 绑定 `winusb.sys`。
- 脚本没有自带二进制；只是把接口重定向到微软驱动。
- 卸载脚本删除 OEM 驱动包和证书；不会碰 MI_01/MI_00。

## 4. 协议不变量（不要凭感觉改）

详细表格见 [`docs/PROTOCOL.md`](docs/PROTOCOL.md)。必须记住：

- 帧头 `0x55`；长度 = 13 + payload；字节 2 的低 2 位是长度高位，`| 0x04` 是版本。
- CRC8：poly `0x8C` 反射、init `0x77`；CRC16：poly `0x8408` 反射、init `0x3692`。
- 主机地址 `0x02`，接收器 `0x5A`；命令类型 `0x40` 请求 ACK，响应 bit7。
- 设置：`0x5B/0x01`，payload `02 | index u32 LE（0=RX） | setting u16 LE | 01 | value`。
  - 声道 `0x0008`：`0` 单声道，`2` 立体声（`1` 会被拒绝）。
  - 增益 `0x0039`：有符号 dB，−12/−6/0/+6/+12。
  - 自动关机 `0x0010`：0/1。
- ACK：`0x80` 响应，seq 相同，payload 首字节 `0x00` 成功、`0xFF` 拒绝。
- 状态推送：`0x5B/0x03`，payload 以 `0x03` 开头，随后 `总长 u16 LE`，再是 `type | index u32 LE | length | value` 记录。
- 绝对不要发：固件升级/重启相关命令（HID `0x55`/`0x52`、`0x5B/0x35` 等）。当前 allowlist 只有三个设置 + 读能力/版本。
- 写设置后必须等状态帧确认；ACK 成功但状态没变要报 `NotApplied`，不要假装成功。

## 5. 运行时生命周期

### 启动

1. `dji_mic.webui.main()` 解析 `--port` / `--no-browser` / `--no-quit`。
2. 先尝试绑 `127.0.0.1:47821`。
   - 端口被占且 `/api/ping` 返回本应用 → 打开已有窗口后退出（单实例）。
   - 端口被其他程序占 → 绑随机端口，继续启动。
3. `AppState.start()` 启动 `MicController` watchdog。
4. `ThreadingHTTPServer` 在后台线程 `serve_forever`。
5. `open_browser()` 用 Edge/Chrome `--app=http://127.0.0.1:<port>/` 打开应用窗口，profile 在 `%LOCALAPPDATA%\MicSeriesControl\browser`。
6. 主线程等 `quit_event`。

### 前后端

- `GET /api/state`：返回快照；同时刷新 `last_poll`、清 `bye_at`。前端 300ms 轮询。
- `GET /api/ping`：单实例识别。
- `POST /api/gain` `{db}`；`POST /api/channel` `{mode}`；`POST /api/auto-off` `{enabled}`。
- `POST /api/reconnect`：`controller.stop()` + `start()`。
- `POST /api/install-driver`：`ShellExecuteW runas` 启动 `driver/install_winusb.ps1`。
- `POST /api/quit`：0.35s 后置 `quit_event`。
- `POST /api/bye`：页面 `pagehide` 时 `sendBeacon`；3s 内没有新的 `/api/state` 就退出。
- 前端 `loop()` 在 `pagehide` 时发 bye；浏览器崩溃/断网则由 180s 没轮询的 watchdog 兜底。

### 关闭

- 正常关窗口：`pagehide` → `/api/bye` → 3s 后退出 → `server.shutdown()` → `controller.stop()`。
- 不要用 `Stop-Process` 强杀主进程来“测试关闭”；如果还有子进程/旧实例，MI_06 会短暂 `CreateFile` 失败（见第 8 节）。
- 关闭顺序：先停轮询/窗口，再停控制器；`WinUsbDevice.close()` 会取消 I/O 并等 `_io_idle`。

## 6. Web 前端状态机（改 UI 前必读）

- `state.snap` 是最后一次 `/api/state`；`render(s)` 只根据它渲染。
- `dirtyGain` / `dirtyChannel`：用户选了但没点“应用”时为 true；`render()` 不能用设备值覆盖用户选择。
- 增益拖动：
  - `pointerdown`：`gainDragging = true`，`previewGainAt(ratio)` 设 `--x`，`selectGain(nearest)` 更新读数/刻度/按钮。
  - `pointermove`：只更新 `--x` + 最近档位；**不要**让 `syncGain()` 把 `--x` 吸到档位。
  - `pointerup`：`gainDragging = false` → `selectGain(nearest)` → `syncGain()` 把 `--x` 吸到 25% 的整数倍。
  - `pointercancel`：不要用 `clientX`，保持最后的 `state.selectedGain`。
  - 键盘：←/→/Home/End 走 `selectGain`，不经过拖动。
- 按钮启用条件：`connected && dirty && !busy`；`updateButtons()` 是唯一入口。
- 自动关机开关：点击立即 POST，成功后再轮询；失败回滚 `aria-checked` 与标签。
- 产品字段：`els.devProduct.textContent = 'Mic Series Mobile Receiver'`；`title` 放真实 `receiver.product`。不要改回直接显示 `DJI Mic Mini 2`。
- 日志：`logs` 是服务端 deque（140 条），前端只渲染，不本地累积。
- 主题：`wireTheme()` 管 `data-theme` + localStorage；`?theme=dark` 仅测试用。
- 资源版本：`index.html` 的 `?v=20261109c` 与 `app.js` 的 `fx.js?v=...` 必须同步；改 CSS/JS 后要 bump。

## 7. API / 数据字段速查

`/api/state` 关键字段：

```json
{
  "connected": true,
  "driver": "ready | driver-missing | absent",
  "busy": false,
  "receiver": {
    "product": "DJI Mic Mini 2",
    "firmware": "02.03.17.00",
    "serial": "...",
    "gain_db": 6,
    "channel": 0,
    "channel_name": "单声道",
    "nc": true,
    "nc_level": 0,
    "auto_off": true,
    "usb": true,
    "battery": 0,
    "connected": [1]
  },
  "transmitters": [
    {
      "index": 1, "online": true, "product": "DJI Mic Mini",
      "battery": 2, "percent": 85, "charging": false,
      "nc": true, "level": 47, "signal": 0
    }
  ],
  "logs": ["[19:00:00] ..."]
}
```

注意：

- `battery` 是 3-bit 档位（1 满 → 7 空），`percent` 是估算，不是真实百分比。
- 接收器 `battery` 字段在手机版 RX 的 v2 帧里通常不可用，显示 0/None 是正常。
- `nc_level` 只用于显示“开 · 弱/强”；不确定时显示“开”，不要编造档位。
- `level` 是 0–100 的实时电平原始值（安静约 30、大声约 75），UI 只做宽度。

## 8. 关键注意事项 / 踩坑清单

### A. 编码：最容易把中文/JS 写坏

- **不要**在 Windows PowerShell 5.1 里对 UTF-8 中文/JS 做：
  ```powershell
  (Get-Content file -Raw).Replace(...) | Set-Content file -Encoding utf8
  ```
  这会把 UTF-8 当 ANSI 读，再写回 mojibake；本项目已发生过一次 `index.html`/`app.js` 被写坏。
- 安全做法：用编辑工具的 `read`/`edit`/`write`，或用 Python：
  ```python
  from pathlib import Path
  p = Path("web/app.js")
  text = p.read_text(encoding="utf-8")
  p.write_text(text, encoding="utf-8", newline="\n")
  ```
- PowerShell 7 用 `-Encoding utf8NoBOM`；不要产生 BOM。
- 如果文件已经坏了：优先从 git 恢复（`git checkout -- file`）；没有提交时从 `release/MicSeriesControl.exe` 的 `_MEIPASS` 里提取 `web/`（PyInstaller `CArchiveReader`），再重做改动。
- 用 `Get-Content` 看到 `鐢佃剳` 这类乱码，不一定是文件坏了，可能只是 PowerShell 5.1 按 ANSI 显示；先用 `read` 工具或 Python 确认真实编码。

### B. 浏览器缓存：新 HTML 配旧 CSS/JS

- 服务器已经对静态资源发 `Cache-Control: no-store`，但 Edge 的持久 profile 仍可能保留旧资源；`?v=` 是第二道保险。
- 改 `web/app.css`、`web/app.js`、`web/assets/endfield.css` 后，把 `web/index.html` 里三处 `?v=...` 和 `web/app.js` 里 `fx.js?v=...` 一起 bump。
- 症状：滑块变成一排裸文字、按钮样式丢失、页面 JS 报 `Cannot read properties of null`。先怀疑缓存，再怀疑代码。
- 清缓存：删 `%LOCALAPPDATA%\MicSeriesControl\browser`（会丢主题偏好），或用无痕/新 profile 验证。
- 不要用 `file://` 打开 `web/index.html`；ES module 和 `/api` 都需要本地 HTTP 服务。

### C. 打包路径：`resource_dir()` vs `app_dir()`

- PyInstaller onefile 解压到 `sys._MEIPASS`；`web/` 必须通过 `--add-data "web;web"` 打包，`resource_dir()` 才能找到。
- `driver/` 不打包，放在 exe 旁边；`app_dir()` 用 `sys.executable` 的目录。
- 症状：exe 打开是 404/空白，通常是漏了 `--add-data`；驱动按钮提示找不到脚本，通常是 `driver/` 没跟 exe 放一起。
- 打包后不要用 `__file__` 推资源路径；开发/打包两套路径已经封装在 `resource_dir()`/`app_dir()`。

### D. WinUSB：MI_06 的三个硬坑

1. **必须 `FILE_FLAG_OVERLAPPED`**：同步句柄 `CreateFile` 成功，但 `WinUsb_Initialize` 返回 6（`ERROR_INVALID_HANDLE`），很有误导性。
2. **ctypes 结构体不要 `_pack_=1`**：`USB_PIPE_INFO`/端点描述符错位，端点地址会读成 0、包长读成 `0x86`。
3. **超时必须 `CancelIoEx` 并收尾**：超时后直接释放 OVERLAPPED/缓冲区/事件会让内核写已释放内存；`WinUsbDevice.close()` 先 `CancelIoEx`、等 `_io_idle`、再 `WinUsb_Free`。

### E. MI_06 并发：同一时间只能有一个控制进程

- 两个 `MicController` 同时打开 MI_06，第二个会 `CreateFile(MI_06) failed`（errno 5）。本项目按单实例处理。
- 测试时最容易踩：旧的 `python -m dji_mic.webui --no-quit`、旧的 `MicSeriesControl.exe`、旧 Edge 窗口还占着接口，新实例日志会每秒刷“连接失败”。
- 处理：`Get-NetTCPConnection -LocalPort 47821` + `Get-CimInstance Win32_Process` 找旧实例；先停旧服务/窗口，再启动一个。不要同时开多个测试服务。
- 应用默认单实例（47821 + `/api/ping`）；但 `--port` 可以绕过，测试时注意。

### F. 协议安全：只发 allowlist

- 只发 `0x5B/0x01` 的 `0x0008`、`0x0039`、`0x0010`；读能力 `0x5B/0x12`、版本 `0x00/0x01`。
- 不发固件升级、重启、HID `0x55`/`0x52`、`0x5B/0x35`。不要为了“多一个设置”猜命令 ID。
- 新设置必须先在真机上验证 ACK + 状态位，再写进 `duml.py` / `device.py` / UI；并更新 `docs/PROTOCOL.md` 与测试 fixture。
- 固件升级后帧格式/字段可能变；先抓 `raw_dump`，不要假设旧偏移仍有效。

### G. 驱动与安全

- 驱动安装脚本会创建本机自签名证书并加入 `LocalMachine\Root` + `TrustedPublisher`，只绑 `MI_06`；音频 `MI_01`、HID `MI_00` 不动。
- 安装需要管理员/UAC；不要静默提权或绕过 UAC。`/api/install-driver` 只是 `ShellExecuteW runas`，用户必须确认。
- 卸载用 `driver/uninstall_winusb.bat`；不要手动删证书/驱动包，除非你知道在做什么。
- 本地 HTTP 没有鉴权，只绑 `127.0.0.1`；不要改成 `0.0.0.0` 暴露到局域网。
- exe 未签名，SmartScreen/杀软可能误报；这是已知限制，不是 bug。

### H. 浏览器窗口生命周期

- `open_browser()` 用 Edge/Chrome `--app` + 专用 profile；没有浏览器时退回默认浏览器（会有地址栏）。
- 窗口关闭 → `pagehide` → `/api/bye` → 3s 退出；浏览器崩溃/无响应 → 180s 没轮询才退出。
- Edge 可能在窗口关闭后留后台进程；`--disable-background-mode` 已加。不要用强杀来验证“正常关闭”。
- `--no-quit` 是测试用隐藏参数，会禁用 watchdog；正常发布不要带。

### I. 仓库 / 发布

- 只改受版本控制的源码/文档；`build/`、`dist/`、`release/`、`vendor/` 都是本地/忽略内容，不要提交。
- `THIRD_PARTY_NOTICES.md` 是许可全文；`docs/CREDITS.md` 是摘要。改第三方代码/字体时两边都要更新；`scripts/build_exe.ps1` 现在会把它复制进 release。
- 截图里的序列号已隐去；不要再把真实序列号截进去。
- `docs/` 下新增的视频脚本/封面是未跟踪内容，可能是用户素材；不要 `git add -A` 一把梭，先问。
- `.dsh-write-test.txt` 是 harness 测试残留，不是应用文件；可忽略/删除，但不要误提交。
- CI 只跑协议单元测试，不跑 UI/E2E；UI 改动必须手动在 Edge 窗口 + 真机验证。

## 9. 构建 / 测试 / 发布

### 源码运行

```powershell
python -m dji_mic                 # Web UI，自动开 Edge/Chrome 应用窗口
python -m dji_mic --classic       # 旧 Tk 兜底
python -m dji_mic --no-browser --port 47822   # 只起服务，便于浏览器/CDP 调试
```

### 测试

```powershell
python -m unittest discover -s tests -v
```

- 9 个协议测试，不依赖设备；CI 也跑这个。
- 真机只读：`python tools/raw_dump.py 3`、`python tools/mic_cli.py status`。
- 真机写入：`python tools/mic_cli.py set-gain 0`、`set-channel stereo`；测试后恢复原值。
- `python tools/gui_smoke.py` 只测旧 Tk 界面，需要设备；不能代替 Web UI 测试。
- Web UI 交互建议用 Edge/Chrome + DevTools/CDP 发真实 `Input.dispatchMouseEvent`，检查 `--x`、`aria-valuenow`、`applyDisabled` 和 `/api/state`。

### 打包

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name MicSeriesControl --icon assets/icon.ico `
  --add-data "web;web" launcher.py
```

或：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

- `scripts/build_exe.ps1` 会生成 `release/MicSeriesControl/` + zip；确保 `web/` 已最新、`driver/` 存在、`THIRD_PARTY_NOTICES.md` 被复制。
- 如果 `.venv` 不存在，脚本回退到 `python`；Windows 商店的 `python.exe` 是 0 字节占位符，会“什么都没发生”。用真实 Python 或 `py -3`，或先建 `.venv`。
- 打包后验证：双击 exe → Edge 应用窗口 → 已连接 → 关窗口 → 端口/进程释放。不要只验证“exe 能启动”。

### 发布

`release/` 不提交。把 `MicSeriesControl.exe`、`driver/`、`README.md`、`使用说明.txt`、`LICENSE`、`THIRD_PARTY_NOTICES.md`、`docs/` 放一起压缩；建议挂 GitHub Releases。附上 SHA256 更好。

## 10. 调试手册

| 症状 | 先查 | 处理 |
|---|---|---|
| 页面是裸文字/滑块消失/按钮无样式 | 缓存/版本号 | bump `?v=`，清 `%LOCALAPPDATA%\MicSeriesControl\browser`，确认 `index.html` 引用的文件存在 |
| exe 打开空白/404 | `--add-data` / `_MEIPASS` | 重新打包，确认 `web/` 在包内；`resource_dir()` 没被改坏 |
| 日志每秒 `CreateFile(MI_06) failed` | 旧实例占用 | 停掉旧 `MicSeriesControl`/`python` 测试服务/旧 Edge 窗口；只留一个 |
| `WinUsb_Initialize failed 6` | 句柄不是 overlapped | 检查 `CreateFileW` 的 `FILE_FLAG_OVERLAPPED` |
| 关闭时 access violation / 崩溃 | I/O 未收尾 | 不要绕过 `_io_idle`；超时先 `CancelIoEx` + `GetOverlappedResult` |
| 设备管理器 MI_06 黄色感叹号 | 驱动未绑 | 管理员跑 `driver/install_winusb.bat`；`pnputil /scan-devices`；确认接收器插着 |
| 提示“控制接口缺少驱动”但已装 | Problem 28/驱动包 | 看 `Get-PnpDevice` 的 Problem；重装/拔插；确认 HWID `MI_06` |
| 改设置没反应 | ACK/状态 | 看日志是 `CommandRejected` 还是 `NotApplied`；确认固件/协议没变 |
| 自动关机/增益按钮灰 | `connected`/`dirty`/`busy` | 看 `/api/state`；只有“已连接 + 有改动 + 不忙”才可点 |
| 关闭窗口后进程还在 | bye 未发/浏览器崩溃 | 等 180s watchdog；或手动关 exe；检查 `pagehide`/`sendBeacon` |
| 端口 47821 被占 | 旧实例/别的程序 | `/api/ping` 判断；旧实例会直接开窗口；别的程序用 `--port` |
| 中文变乱码 | PowerShell 编码 | 用 `read`/Python 确认；从 git/exe 恢复；不要 `Get-Content|Set-Content` |
| 打包版没有新 UI | 缓存/打包旧 web | bump 版本、清 profile、确认 `--add-data` 打的是当前 `web/` |

## 11. 已知限制 / TODO

- 只实现三个写入设置：增益、声道、接收器自动关机。TX 低切/LED/语音音色/TX 自动关机未验证，不要凭标准 RX 文档直接加。
- 不做固件升级/DFU/重启；不要为了“功能完整”破例。
- 接收器电量在手机版 RX 上通常读不到；TX 电量只有 3-bit/7 档，百分比是估算。
- 降噪是接收器侧面 O/L/H 硬件开关，软件只读；不要试图用软件“打开降噪”。
- 增益只有 5 个 6 dB 档位；滑块拖动是自由位置，但松手吸附到档位，不要改成连续 dB 写入。
- 无自动化 UI/E2E 测试；CI 只跑协议测试。
- `tools/mic_cli.py` 没有 `set-auto-off` 子命令；需要命令行改自动关机时，用 HTTP API 或补一个子命令。
- `device.py` 里 `receiver_present` 是未使用 import；`duml.py` 的 `Iterable` 也未使用；清理时别破坏行为。
- `scripts/build_exe.ps1` 的 `python` 回退可能是商店占位符；优先 `.venv`/完整路径。
- `docs/` 的视频脚本/封面是内容素材，不是运行时；未跟踪，不要擅自提交/删除。
- 截图序列号已隐去；保持这个约定。

## 12. 改动检查清单

改代码前：

- [ ] 读本文件 + `README.md` + `docs/PROTOCOL.md`
- [ ] `git status` 看未跟踪内容；不要 `git add -A`
- [ ] 确认没有旧 `MicSeriesControl` / 测试服务占着 MI_06

改协议/设备：

- [ ] 新命令先在真机 ACK + 状态位验证
- [ ] 更新 `duml.py` 常量、`device.py` allowlist、`docs/PROTOCOL.md`、测试 fixture
- [ ] 不碰固件/重启命令
- [ ] 失败路径抛 `DeviceError`，不要静默

改 Web UI：

- [ ] 只改 `web/`，不要手改 `web/assets/endfield.css`（产品覆盖放 `app.css`）
- [ ] 改完 bump `?v=`（index 三处 + app.js 的 fx import）
- [ ] 检查 `--x` / `--pos` / `gainDragging` 顺序
- [ ] 真机 + Edge 窗口验证；再打包验证
- [ ] 截图更新时隐去序列号

改发布：

- [ ] 跑 `python -m unittest discover -s tests -v`
- [ ] 打包 `--add-data "web;web"`
- [ ] release 包含 `driver/`、`THIRD_PARTY_NOTICES.md`、docs
- [ ] 关窗口验证进程/端口释放
- [ ] 只提交源码/文档，不提交 `build/`/`release/`/`vendor/`

## 13. 事故记录（避免重演）

1. **新 HTML 配旧 app.js/CSS**：`?v=` 未 bump + 浏览器缓存，滑块退化成裸文字/JS 在 `els.gainSteps` 上抛错。修复：静态资源 `no-store` + 版本查询 + 专用 profile。
2. **PowerShell 编码写坏 `index.html`/`app.js`**：用 `Get-Content -Raw | Set-Content -Encoding utf8` 处理 UTF-8 中文，出现 mojibake/损坏。修复：从打包 exe 的 `_MEIPASS` 提取干净版本，再用 Python/编辑工具重做。教训见 8.A。
3. **旧测试实例占着 MI_06**：新实例日志每秒 `CreateFile(MI_06) failed`，UI 显示连接成功但控制器反复重连。修复：停掉旧 `--no-quit` 服务/旧 exe/旧 Edge 窗口，单实例运行。

## 14. 参考

- [`README.md`](README.md) — 用户视角、安装/驱动/限制
- [`docs/PROTOCOL.md`](docs/PROTOCOL.md) — DUML 帧、设置、状态字段
- [`docs/可行性报告.md`](docs/可行性报告.md) — 调研/替代方案
- [`docs/CREDITS.md`](docs/CREDITS.md) — 第三方摘要
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — 许可全文
- 代码内 docstring：`duml.py`、`winusb.py`、`device.py`、`webui.py`、`web/app.js`

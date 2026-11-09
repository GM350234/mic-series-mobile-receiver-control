import { flashDone, scramble, toast, wireReadouts, wireTheme } from './assets/fx.js?v=20261109c';

if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const els = {
  linkPill: $('#linkPill'),
  linkLabel: $('#linkLabel'),
  linkField: $('#linkField'),
  fwField: $('#fwField'),
  snField: $('#snField'),
  notice: $('#notice'),
  noticeText: $('#noticeText'),
  noticeAction: $('#noticeAction'),
  gainBig: $('#gainBig'),
  gainSlider: $('#gainSlider'),
  gainRail: $('#gainRail'),
  gainThumb: $('#gainThumb'),
  gainTicks: $('#gainTicks'),
  gainNote: $('#gainNote'),
  applyGain: $('#applyGain'),
  channelBig: $('#channelBig'),
  channelUnit: $('#channelUnit'),
  channelSeg: $('#channelSeg'),
  channelDiagram: $('#channelDiagram'),
  channelNote: $('#channelNote'),
  applyChannel: $('#applyChannel'),
  autoOffSwitch: $('#autoOffSwitch'),
  autoOffLabel: $('#autoOffLabel'),
  ncState: $('#ncState'),
  usbState: $('#usbState'),
  txCount: $('#txCount'),
  devProduct: $('#devProduct'),
  devFw: $('#devFw'),
  devSn: $('#devSn'),
  devDriver: $('#devDriver'),
  devLink: $('#devLink'),
  logList: $('#logList'),
  copyDiag: $('#copyDiag'),
  quitBtn: $('#quitBtn'),
  reconnectBtn: $('#reconnectBtn'),
  themeBtn: $('#themeBtn'),
  version: $('#version'),
};

const GAIN_VALUES = [-12, -6, 0, 6, 12];

const state = {
  snap: null,
  selectedGain: 6,
  selectedChannel: 0,
  dirtyGain: false,
  gainDragging: false,
  dirtyChannel: false,
  busy: false,
  offline: false,
  logKey: '',
  firstState: true,
  pollTimer: 0,
};

function fmtGain(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return n > 0 ? `+${n}` : n < 0 ? `−${Math.abs(n)}` : '0';
}

function fmtChannel(value) {
  if (value === 0) return 'MONO';
  if (value === 2) return 'STEREO';
  return value == null ? '—' : `MODE ${value}`;
}

function channelName(value) {
  if (value === 0) return '单声道';
  if (value === 2) return '立体声';
  return value == null ? '—' : `模式 ${value}`;
}

function driverLabel(value) {
  if (value === 'ready') return 'WinUSB 已就绪';
  if (value === 'driver-missing') return '缺少 WinUSB 驱动';
  return '未检测到设备';
}

async function api(path, body) {
  const options = { cache: 'no-store', headers: { Accept: 'application/json' } };
  if (body !== undefined) {
    options.method = 'POST';
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  let data = null;
  try {
    data = await response.json();
  } catch (error) {
    throw new Error(`服务返回了无效响应（HTTP ${response.status}）`);
  }
  if (!response.ok || data?.ok === false) {
    throw new Error(data?.error || `请求失败（HTTP ${response.status}）`);
  }
  return data;
}

function setLink(kind, label) {
  els.linkPill.classList.toggle('is-off', kind === 'off');
  els.linkPill.classList.toggle('is-warn', kind === 'warn');
  els.linkLabel.textContent = label;
}

function setNotice(text, actionLabel, action) {
  if (!text) {
    els.notice.hidden = true;
    return;
  }
  els.notice.hidden = false;
  els.noticeText.textContent = text;
  els.noticeAction.hidden = !actionLabel;
  if (actionLabel) {
    els.noticeAction.textContent = actionLabel;
    els.noticeAction.onclick = action;
  }
}

function renderNotice(s) {
  if (s.connected) {
    setNotice('', '', null);
    return;
  }
  if (s.driver === 'driver-missing') {
    setNotice(
      '已检测到接收器，但 Windows 控制接口（MI_06）缺少 WinUSB 驱动。安装后即可读写设置，不影响录音。',
      '安装驱动',
      installDriver,
    );
  } else if (s.driver === 'absent') {
    setNotice('未检测到接收器。请用 USB-C 线把接收器直接插到电脑，然后重新检测。', '重新检测', reconnect);
  } else {
    setNotice('正在连接接收器的控制接口…', '', null);
  }
}

function renderLink(s) {
  if (s.connected) {
    setLink('on', '已连接');
    els.linkField.textContent = 'USB · MI_06';
  } else if (s.driver === 'driver-missing') {
    setLink('warn', '驱动缺失');
    els.linkField.textContent = '—';
  } else {
    setLink('off', '未连接');
    els.linkField.textContent = '—';
  }
}

function gainIndex(value) {
  let best = 0;
  let distance = Infinity;
  GAIN_VALUES.forEach((candidate, index) => {
    const delta = Math.abs(Number(value) - candidate);
    if (delta < distance) {
      distance = delta;
      best = index;
    }
  });
  return best;
}

function gainFromRatio(ratio) {
  const clamped = Math.max(0, Math.min(1, ratio));
  return GAIN_VALUES[Math.round(clamped * (GAIN_VALUES.length - 1))];
}

function syncGain() {
  const rx = state.snap?.receiver;
  const current = rx?.gain_db;
  const shown = state.dirtyGain ? state.selectedGain : current ?? state.selectedGain;
  const shownIndex = gainIndex(shown);
  const currentIndex = current == null ? shownIndex : gainIndex(current);

  els.gainBig.textContent = current == null && !state.dirtyGain ? '—' : fmtGain(shown);
  els.gainSlider.style.setProperty('--pos', shownIndex);
  els.gainSlider.style.setProperty('--cur', currentIndex);
  if (!state.gainDragging) {
    els.gainSlider.style.setProperty(
      '--x',
      (shownIndex / (GAIN_VALUES.length - 1)).toFixed(4),
    );
  }
  els.gainSlider.setAttribute('aria-valuenow', String(GAIN_VALUES[shownIndex]));
  els.gainSlider.setAttribute('aria-valuetext', `${fmtGain(GAIN_VALUES[shownIndex])} dB`);
  $$('span', els.gainTicks).forEach((tick, index) => {
    tick.classList.toggle('is-on', index === shownIndex);
  });

  if (state.dirtyGain) {
    els.gainNote.textContent = `待写入 ${fmtGain(state.selectedGain)} dB`;
  } else if (current != null) {
    els.gainNote.textContent = `当前 ${fmtGain(current)} dB`;
  } else {
    els.gainNote.textContent = '等待接收器';
  }
}

function syncChannel() {
  const rx = state.snap?.receiver;
  const current = rx?.channel;
  const shown = state.dirtyChannel ? state.selectedChannel : current ?? state.selectedChannel;
  els.channelBig.textContent = current == null && !state.dirtyChannel ? '—' : fmtChannel(shown);
  els.channelUnit.textContent = current == null && !state.dirtyChannel ? '—' : channelName(shown);
  els.channelDiagram.classList.toggle('is-stereo', shown === 2);
  for (const button of $$('button', els.channelSeg)) {
    button.classList.toggle('is-on', Number(button.dataset.mode) === shown);
  }
  if (state.dirtyChannel) {
    els.channelNote.textContent = `待写入 · ${channelName(state.selectedChannel)}`;
  } else if (shown === 2) {
    els.channelNote.textContent = 'TX1 左 / TX2 右';
  } else {
    els.channelNote.textContent = '两路混合为单声道';
  }
}

function syncPower(s) {
  const rx = s.receiver;
  const connected = !!s.connected;
  const busy = state.busy || !!s.busy;

  if (rx.auto_off == null) {
    els.autoOffSwitch.setAttribute('aria-checked', 'false');
    els.autoOffSwitch.disabled = true;
    els.autoOffLabel.textContent = '—';
  } else {
    els.autoOffSwitch.setAttribute('aria-checked', String(rx.auto_off));
    els.autoOffSwitch.disabled = !connected || busy;
    els.autoOffLabel.textContent = rx.auto_off ? '开' : '关';
  }

  if (rx.nc == null) {
    els.ncState.textContent = '—';
  } else if (!rx.nc) {
    els.ncState.textContent = '关';
  } else {
    const level = rx.nc_level === 1 ? ' · 弱' : rx.nc_level === 2 ? ' · 强' : '';
    els.ncState.textContent = `开${level}`;
  }

  els.usbState.textContent = rx.usb == null ? '—' : rx.usb ? '已连接' : '否';
  els.txCount.textContent = `${rx.connected?.length ?? 0} / 2`;
}

function buildCells(card) {
  const host = $('[data-f="cells"]', card);
  if (host.childElementCount) return;
  for (let i = 0; i < 7; i += 1) {
    const cell = document.createElement('span');
    cell.className = 'tx-cell';
    host.append(cell);
  }
}

function renderTxCard(card, tx) {
  buildCells(card);
  const online = !!tx?.online;
  card.classList.toggle('is-online', online);
  card.classList.toggle('is-offline', !online);
  card.classList.toggle('is-charging', !!tx?.charging);

  const product = $('[data-f="product"]', card);
  const stateTag = $('[data-f="state"]', card);
  const percent = $('[data-f="percent"]', card);
  const gauge = $('[data-f="gauge"]', card);
  const charging = $('[data-f="charging"]', card);
  const nc = $('[data-f="nc"]', card);
  const level = $('[data-f="level"]', card);
  const empty = $('[data-f="empty"]', card);

  if (!online) {
    if (empty) empty.hidden = false;
    product.textContent = '未连接';
    stateTag.textContent = '离线';
    percent.textContent = '—';
    gauge.textContent = '电量 —/7';
    charging.textContent = '—';
    nc.textContent = '—';
    level.style.width = '0%';
    $$('.tx-cell', card).forEach((cell) => cell.classList.remove('is-on'));
    return;
  }

  if (empty) empty.hidden = true;
  product.textContent = tx.product || 'DJI Mic';
  stateTag.textContent = tx.charging ? '充电中' : '在线';
  percent.textContent = tx.percent == null ? '—' : String(tx.percent);
  gauge.textContent = `电量 ${tx.battery ?? '—'}/7`;
  charging.textContent = tx.charging ? '充电中' : '否';
  nc.textContent = tx.nc ? '开' : '关';
  level.style.width = `${Math.max(0, Math.min(100, Number(tx.level) || 0))}%`;

  const filled = tx.battery ? Math.max(0, Math.min(7, 8 - tx.battery)) : 0;
  $$('.tx-cell', card).forEach((cell, index) => {
    cell.classList.toggle('is-on', index < filled);
  });
}

function renderLogs(logs) {
  const key = logs.join('\n');
  if (key === state.logKey) return;
  state.logKey = key;
  const fragment = document.createDocumentFragment();
  for (const line of logs) {
    const row = document.createElement('div');
    const match = line.match(/^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)$/);
    if (match) {
      const time = document.createElement('span');
      time.className = 't';
      time.textContent = `[${match[1]}]`;
      const message = document.createElement('span');
      message.textContent = ` ${match[2]}`;
      row.append(time, message);
    } else {
      row.textContent = line;
    }
    fragment.append(row);
  }
  els.logList.replaceChildren(fragment);
  els.logList.scrollTop = els.logList.scrollHeight;
}

function updateButtons() {
  const s = state.snap;
  const connected = !!s?.connected;
  const busy = state.busy || !!s?.busy;
  els.applyGain.disabled = !(connected && state.dirtyGain && !busy);
  els.applyChannel.disabled = !(connected && state.dirtyChannel && !busy);
  els.reconnectBtn.disabled = busy;
  if (s) {
    els.autoOffSwitch.disabled = !connected || busy;
  }
}

function render(s) {
  state.snap = s;
  state.busy = !!s.busy;
  renderLink(s);
  renderNotice(s);

  els.fwField.textContent = s.receiver?.firmware || '—';
  els.snField.textContent = s.receiver?.serial || '—';

  if (!state.dirtyGain && s.receiver?.gain_db != null) {
    state.selectedGain = s.receiver.gain_db;
  }
  if (!state.dirtyChannel && s.receiver?.channel != null) {
    state.selectedChannel = s.receiver.channel;
  }

  syncGain();
  syncChannel();
  syncPower(s);

  renderTxCard($('[data-tx="1"]'), s.transmitters?.find((tx) => tx.index === 1));
  renderTxCard($('[data-tx="2"]'), s.transmitters?.find((tx) => tx.index === 2));

  els.devProduct.textContent = 'Mic Series Mobile Receiver';
  els.devProduct.title = s.receiver?.product ? `检测到：${s.receiver.product}` : '';
  els.devFw.textContent = s.receiver?.firmware || '—';
  els.devSn.textContent = s.receiver?.serial || '—';
  els.devDriver.textContent = driverLabel(s.driver);
  els.devLink.textContent = s.connected ? 'USB · MI 06' : '—';
  els.version.textContent = s.version ? `v${s.version}` : 'v1.0.0';

  renderLogs(s.logs || []);
  updateButtons();

  if (state.firstState && s.connected && s.receiver?.gain_db != null) {
    state.firstState = false;
    scramble(els.gainBig);
    scramble(els.channelBig);
    for (const tx of $$('.tx-percent b')) scramble(tx);
  }
}

function renderOffline(error) {
  state.offline = true;
  setLink('off', '已断开');
  els.linkField.textContent = '—';
  setNotice(`控制台服务连接中断，正在重试…${error ? `（${error.message}）` : ''}`, '重新检测', reconnect);
  updateButtons();
}

async function pollOnce() {
  const data = await api('/api/state');
  state.offline = false;
  render(data);
  return data;
}

async function loop() {
  try {
    await pollOnce();
  } catch (error) {
    renderOffline(error);
  } finally {
    clearTimeout(state.pollTimer);
    state.pollTimer = setTimeout(loop, state.offline ? 1000 : 300);
  }
}

function selectGain(value) {
  state.selectedGain = Number(value);
  const current = state.snap?.receiver?.gain_db;
  state.dirtyGain = current !== state.selectedGain;
  syncGain();
  updateButtons();
}

function selectChannel(value) {
  state.selectedChannel = Number(value);
  const current = state.snap?.receiver?.channel;
  state.dirtyChannel = current !== state.selectedChannel;
  syncChannel();
  updateButtons();
}

async function applyGain() {
  if (els.applyGain.disabled) return;
  const value = state.selectedGain;
  const button = els.applyGain;
  button.setAttribute('aria-busy', 'true');
  button.textContent = '正在写入';
  state.busy = true;
  updateButtons();
  try {
    await api('/api/gain', { db: value });
    state.dirtyGain = false;
    toast(`增益已设为 ${fmtGain(value)} dB`);
    button.removeAttribute('aria-busy');
    button.textContent = '应用增益';
    flashDone(button, '已写入');
    await pollOnce();
  } catch (error) {
    toast(error.message, 3600);
    button.removeAttribute('aria-busy');
    button.textContent = '应用增益';
  } finally {
    state.busy = false;
    updateButtons();
  }
}

async function applyChannel() {
  if (els.applyChannel.disabled) return;
  const value = state.selectedChannel;
  const button = els.applyChannel;
  button.setAttribute('aria-busy', 'true');
  button.textContent = '正在写入';
  state.busy = true;
  updateButtons();
  try {
    await api('/api/channel', { mode: value });
    state.dirtyChannel = false;
    toast(`声道已切换为${channelName(value)}`);
    button.removeAttribute('aria-busy');
    button.textContent = '应用声道';
    flashDone(button, '已写入');
    await pollOnce();
  } catch (error) {
    toast(error.message, 3600);
    button.removeAttribute('aria-busy');
    button.textContent = '应用声道';
  } finally {
    state.busy = false;
    updateButtons();
  }
}

async function toggleAutoOff() {
  if (!state.snap?.connected || els.autoOffSwitch.disabled) return;
  const target = !state.snap.receiver.auto_off;
  els.autoOffSwitch.setAttribute('aria-checked', String(target));
  els.autoOffLabel.textContent = target ? '开' : '关';
  els.autoOffSwitch.disabled = true;
  try {
    await api('/api/auto-off', { enabled: target });
    toast(`自动关机已${target ? '开启' : '关闭'}`);
    await pollOnce();
  } catch (error) {
    toast(error.message, 3600);
    els.autoOffSwitch.setAttribute('aria-checked', String(!target));
    els.autoOffLabel.textContent = !target ? '开' : '关';
  } finally {
    if (state.snap?.connected) els.autoOffSwitch.disabled = false;
  }
}

async function reconnect() {
  if (els.reconnectBtn.disabled) return;
  els.reconnectBtn.setAttribute('aria-busy', 'true');
  els.reconnectBtn.textContent = '正在检测';
  try {
    await api('/api/reconnect', {});
    toast('正在重新查找接收器…');
    await pollOnce();
  } catch (error) {
    toast(error.message, 3600);
  } finally {
    els.reconnectBtn.removeAttribute('aria-busy');
    els.reconnectBtn.textContent = '重新检测';
  }
}

async function installDriver() {
  try {
    await api('/api/install-driver', {});
    toast('已启动驱动安装，请在 UAC 窗口中确认', 4200);
  } catch (error) {
    toast(error.message, 4200);
  }
}

async function copyDiagnostics() {
  const s = state.snap;
  const data = {
    app: 'Mic Series Mobile Receiver 电脑控制台',
    version: s?.version || '1.0.0',
    driver: s?.driver || 'unknown',
    connected: !!s?.connected,
    receiver: s?.receiver || null,
    transmitters: s?.transmitters || [],
    logs: s?.logs || [],
  };
  const text = JSON.stringify(data, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    toast('诊断信息已复制到剪贴板');
  } catch (error) {
    const area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.append(area);
    area.select();
    document.execCommand('copy');
    area.remove();
    toast('诊断信息已复制到剪贴板');
  }
}

async function quit() {
  try {
    await api('/api/quit', {});
  } catch (error) {
    // The server may exit before answering; closing the window is still fine.
  }
  window.close();
  setTimeout(() => {
    document.body.innerHTML = '<main style="padding:3rem;font-family:sans-serif"><h1>控制台已退出</h1><p>现在可以关闭此窗口。</p></main>';
  }, 250);
}

function syncThemeLabel() {
  const dark = document.documentElement.dataset.theme === 'dark'
    || (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
  els.themeBtn.textContent = dark ? '浅色' : '深色';
  els.themeBtn.setAttribute('aria-pressed', String(dark));
}

function wireNav() {
  const links = $$('[data-nav]');
  const sections = links
    .map((link) => document.querySelector(link.getAttribute('href')))
    .filter(Boolean);
  let ticking = false;
  const update = () => {
    ticking = false;
    let current = sections[0];
    for (const section of sections) {
      if (section.getBoundingClientRect().top <= 140) current = section;
    }
    if (!current) return;
    for (const link of links) {
      if (link.getAttribute('href') === `#${current.id}`) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
  };
  addEventListener('scroll', () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(update);
  }, { passive: true });
  update();
}

function wireEvents() {
  let draggingGain = false;

  const gainRatioFromPointer = (event) => {
    const rect = els.gainRail.getBoundingClientRect();
    return Math.max(0, Math.min(1, (event.clientX - rect.left) / Math.max(1, rect.width)));
  };

  // While the pointer is down the cap and the yellow fill follow it exactly.
  // The nearest 6 dB step is used for the readout/ticks; the cap snaps only
  // when the pointer is released.
  const previewGainAt = (ratio) => {
    els.gainSlider.style.setProperty('--x', ratio.toFixed(4));
    selectGain(gainFromRatio(ratio));
  };

  const endGainDrag = (event, cancelled) => {
    if (!draggingGain) return;
    draggingGain = false;
    state.gainDragging = false;
    els.gainSlider.classList.remove('is-dragging');
    const value = cancelled
      ? state.selectedGain
      : gainFromRatio(gainRatioFromPointer(event));
    selectGain(value);
    try {
      if (els.gainSlider.hasPointerCapture(event.pointerId)) {
        els.gainSlider.releasePointerCapture(event.pointerId);
      }
    } catch (error) {
      // ignore
    }
  };

  els.gainSlider.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    draggingGain = true;
    state.gainDragging = true;
    els.gainSlider.classList.add('is-dragging');
    try {
      els.gainSlider.setPointerCapture(event.pointerId);
    } catch (error) {
      // ignore
    }
    previewGainAt(gainRatioFromPointer(event));
    event.preventDefault();
  });

  els.gainSlider.addEventListener('pointermove', (event) => {
    if (!draggingGain) return;
    previewGainAt(gainRatioFromPointer(event));
    event.preventDefault();
  });

  els.gainSlider.addEventListener('pointerup', (event) => endGainDrag(event, false));
  els.gainSlider.addEventListener('pointercancel', (event) => endGainDrag(event, true));

  els.gainSlider.addEventListener('keydown', (event) => {
    let next = gainIndex(state.selectedGain);
    if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') next -= 1;
    else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') next += 1;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = GAIN_VALUES.length - 1;
    else return;
    event.preventDefault();
    next = Math.max(0, Math.min(GAIN_VALUES.length - 1, next));
    selectGain(GAIN_VALUES[next]);
  });

  els.channelSeg.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-mode]');
    if (button) selectChannel(button.dataset.mode);
  });
  els.applyGain.addEventListener('click', applyGain);
  els.applyChannel.addEventListener('click', applyChannel);
  els.autoOffSwitch.addEventListener('click', toggleAutoOff);
  els.reconnectBtn.addEventListener('click', reconnect);
  els.copyDiag.addEventListener('click', copyDiagnostics);
  els.quitBtn.addEventListener('click', quit);
  els.themeBtn.addEventListener('click', () => setTimeout(syncThemeLabel, 0));
  addEventListener('pagehide', () => {
    try {
      navigator.sendBeacon('/api/bye');
    } catch (error) {
      // ignore
    }
  });
}

wireTheme();
const themeParam = new URLSearchParams(location.search).get('theme');
if (themeParam === 'dark' || themeParam === 'light') {
  document.documentElement.dataset.theme = themeParam;
}
wireReadouts();
wireNav();
wireEvents();
syncThemeLabel();
if (!location.hash) scrollTo(0, 0);
// Safety net: if a browser/headless environment leaves the entrance animation
// paused at its first frame, make sure the working panels are still visible.
setTimeout(() => {
  for (const panel of $$('.ef-in-power')) panel.style.animation = 'none';
}, 1400);
loop();

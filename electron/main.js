// electron/main.js
// PurrCat 主进程：主窗口 + Python 后端 sidecar + 多 Tab WebContentsView 内置浏览器
// 安全：contextIsolation=true，nodeIntegration=false，前端只能用 preload 暴露的 window.purrcat

const { app, BrowserWindow, Menu, dialog, ipcMain, WebContentsView, session } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

// 关掉 Chromium 的 HTTP→HTTPS 自动升级：vite/后端都跑明文 http://localhost，
// 升级会导致 ERR_SSL_PROTOCOL_ERROR。必须在 app ready 前设置。
app.commandLine.appendSwitch('disable-features', 'HttpsUpgrades');

const IS_DEV = !!process.env.ELECTRON_DEV;
const DEV_URL = 'http://localhost:3000';   // vite dev server（热更新）
const PROD_URL = 'http://localhost:8000';  // 后端托管的前端 dist

let mainWindow = null;
let backendProcess = null;

// ===== 内置浏览器 Tab 状态 =====
// tabs: tabId -> { view: WebContentsView, url, title }
const tabs = new Map();
let activeTabId = null;
// 内置浏览器容器的 bounds（相对主窗口内容区的 CSS 像素），由前端 browserSetBounds 同步
let currentBounds = { x: 0, y: 0, width: 0, height: 0 };
let currentScale = 1; // 最近一次 browser:set-bounds 传来的 scale，showView 时配套恢复 zoomFactor
let _boundsInitialized = false; // 前端是否已发送过至少一次 browser:set-bounds
const OFFSCREEN = { x: -10000, y: 0, width: 1, height: 1 };
const _pickModeTabs = new Set();
const _inspectListeners = new Map(); // tabId -> cleanup function (CDP inspect mode)
let detachedWin = null;
let browserDetached = false;

function getTargetWin() {
  return (browserDetached && detachedWin && !detachedWin.isDestroyed()) ? detachedWin : mainWindow;
}

function updateDetachedBounds() {
  if (!detachedWin || !activeTabId) return;
  const [w, h] = detachedWin.getContentSize();
  const HEADER_H = 48;
  const t = tabs.get(activeTabId);
  if (t) {
    // pick 模式下 view 已移到屏外，不要拉回（否则会盖住 overlay）
    if (_pickModeTabs.has(activeTabId)) return;
    t.view.setBounds({ x: 0, y: HEADER_H, width: w, height: h - HEADER_H });
    try { t.view.webContents.setZoomFactor(1); } catch (_) {}
  }
}

function reattachBrowser() {
  if (!detachedWin) return;
  // 先把所有 view 设为 OFFSCREEN，重置 zoomFactor，防止独立窗口的大 bounds 或 zoom 残留
  for (const [id, t] of tabs) {
    _pickModeTabs.delete(id); // 清理 pick 状态
    // 清理 CDP inspect 监听
    const cleanup = _inspectListeners.get(id);
    if (cleanup) { cleanup(); _inspectListeners.delete(id); }
    try { t.view.webContents.setZoomFactor(1); } catch (_) {}
    t.view.setBounds(OFFSCREEN);
    try { detachedWin.contentView.removeChildView(t.view); } catch (_) {}
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.contentView.addChildView(t.view);
    }
  }
  browserDetached = false;
  // 🌟 主动调用 showView：跨窗口 reparent 后 WebContentsView 关联到新 DPI/坐标系，
  // 必须立即用 currentBounds + currentScale 重设，否则 view 还停留在 OFFSCREEN 或
  // zoomFactor=1 状态，用户看到"错位"，必须切换模式刷新才能恢复
  if (activeTabId) showView(activeTabId);
  // 通知前端恢复面板，前端会重新挂载 AgentBrowserPanel 并触发 sync 更新 bounds
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('browser:reattached');
  }
  const w = detachedWin;
  detachedWin = null;
  w.removeAllListeners('close');
  w.destroy();
}

function showView(tabId) {
  const t = tabs.get(tabId);
  if (!t) return;
  if (browserDetached && detachedWin) {
    updateDetachedBounds();
  } else if (mainWindow && _boundsInitialized) {
    // 只有前端已发送过 browser:set-bounds 后才设置 bounds，
    // 否则 currentBounds 还是 {0,0,0,0}、currentScale 还是初始值 1，
    // 会导致 view 短暂以 100% 缩放显示在 (0,0) 位置——这就是"偶尔网页很大"的根因
    t.view.setBounds(currentBounds);
    try { t.view.webContents.setZoomFactor(currentScale || 1); } catch (_) {}
  }
}

function hideView(tabId) {
  const t = tabs.get(tabId);
  if (!t) return;
  // pick 模式下保持 1280x800，不要缩成 1x1（否则视口变化导致布局错乱，后续 locate 会偏）
  if (_pickModeTabs.has(tabId)) {
    t.view.setBounds({ x: -20000, y: -20000, width: 1280, height: 800 });
  } else {
    t.view.setBounds(OFFSCREEN);
  }
}

function pushTabEvent(payload) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('browser:tab-event', payload);
  }
  if (detachedWin && !detachedWin.isDestroyed()) {
    detachedWin.webContents.send('browser:tab-event', payload);
  }
}

// ===== 后端 sidecar =====
function createBackend() {
  // 开发模式后端由 `npm run dev` 的 concurrently 拉起（uv run python main.py --api --headless）
  if (IS_DEV) return;
  // 生产模式：PyInstaller --onedir 产物为 main.exe + _internal/，由 extraResources 带到 resources/backend/
  const exeName = process.platform === 'win32' ? 'main.exe' : 'main';
  const exe = path.join(process.resourcesPath, 'backend', exeName);
  if (!fs.existsSync(exe)) {
    console.warn('[PurrCat] 后端 sidecar 未找到:', exe, '（生产包需先 PyInstaller 打包到 dist/main/）');
    return;
  }
  backendProcess = spawn(exe, ['--api', '--headless'], { cwd: path.dirname(exe) });
  backendProcess.stdout.on('data', (d) => process.stdout.write(d));
  backendProcess.stderr.on('data', (d) => process.stderr.write(d));
  backendProcess.on('exit', (code) => console.warn('[PurrCat] backend exited with', code));
}

function createWindow() {
  // 去掉默认菜单栏（File/Edit/View/Help 及 app-name 标签），啥都不要
  Menu.setApplicationMenu(null);

  mainWindow = new BrowserWindow({
    title: 'PurrCat',
    titleBarStyle: 'hidden',
    width: 1280,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (IS_DEV) {
    mainWindow.loadURL(DEV_URL);
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    // 生产模式：等后端就绪再 loadURL，避免端口未就绪导致空白页
    mainWindow.loadURL('about:blank');
    pollBackendAndLoad(PROD_URL);
  }

  // 重置主窗口页面缩放：Chromium 会按 origin 记住 Ctrl+滚轮/Ctrl+- 的缩放，
  // 可能导致 React 主界面被意外缩小、进而让内置浏览器 bounds 错位。每次加载完成强制恢复 1.0。
  mainWindow.webContents.on('did-finish-load', () => {
    try { mainWindow.webContents.setZoomFactor(1); } catch (_) {}
  });
}

async function pollBackendAndLoad(targetUrl) {
  // 先给后端 sidecar 足够启动时间（uvicorn 绑定 + 预热）
  await new Promise((r) => setTimeout(r, 1500));
  const started = Date.now();
  const MAX_WAIT_MS = 60_000;
  while (Date.now() - started < MAX_WAIT_MS) {
    try {
      const res = await fetch('http://localhost:8000/api/health');
      if (res.ok) {
        if (mainWindow && !mainWindow.isDestroyed()) mainWindow.loadURL(targetUrl);
        return;
      }
    } catch (_) {}
    await new Promise((r) => setTimeout(r, 500));
  }
  // 超时也强制加载，由前端自行处理后端未就绪
  console.warn('[PurrCat] 后端就绪超时，强制加载前端...');
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.loadURL(targetUrl);
}

// ===== IPC: File Reference =====
ipcMain.handle('dialog:open', async (_e, opts) => {
  const directory = !!(opts && opts.directory);
  // Windows/Linux 不能同框混选文件+文件夹，故按 directory 二选一
  const properties = directory ? ['openDirectory', 'multiSelections'] : ['openFile', 'multiSelections'];
  const r = await dialog.showOpenDialog(mainWindow, { properties });
  return r.canceled ? [] : r.filePaths;
});

// ===== IPC: 内置浏览器 Tab 管理 =====

// 阻止在内置浏览器中加载主窗口自身的 URL（localhost:3000 / localhost:8000），
// 否则两个完整 React 应用共享同一 origin，localStorage/storage 事件 + Vite HMR WebSocket 形成循环风暴
function isSelfUrl(url) {
  if (!url || typeof url !== 'string') return false;
  try {
    const u = new URL(url.startsWith('http') ? url : 'http://' + url);
    const selfUrls = [DEV_URL, PROD_URL].map(s => { try { return new URL(s); } catch { return null; } });
    return selfUrls.some(s => s && u.hostname === s.hostname && u.port === s.port);
  } catch { return false; }
}

ipcMain.handle('browser:new-tab', (_e, url) => {
  const targetWin = getTargetWin();
  if (!targetWin) return null;
  if (isSelfUrl(url)) {
    pushTabEvent({ type: 'blocked', url, reason: '不能在内置浏览器中打开应用自身的地址' });
    return null;
  }
  const tabId = 'tab_' + Date.now() + '_' + Math.floor(Math.random() * 1e6);
  const view = new WebContentsView({
    webPreferences: {
      contextIsolation: true,
      // 独立 session partition：隔离 localStorage/sessionStorage/ServiceWorker，
      // 防止在内置浏览器里打开同 origin 页面（如 localhost:3000）时与主窗口形成 storage 事件循环
      session: session.fromPartition('persist:browser'),
    },
  });
  targetWin.contentView.addChildView(view);
  view.setBounds(OFFSCREEN); // 初始屏外，等 set-bounds / switch-tab 再显示

  view.webContents.on('page-title-updated', (_e2, title) => {
    const t = tabs.get(tabId);
    if (t) t.title = title;
    pushTabEvent({ type: 'title', tabId, title });
  });
  view.webContents.on('did-navigate', (_e2, navUrl) => {
    const t = tabs.get(tabId);
    if (t) t.url = navUrl;
    pushTabEvent({ type: 'navigate', tabId, url: navUrl });
  });

  tabs.set(tabId, { view, url: url || '', title: '' });
  if (url) view.webContents.loadURL(url);

  // 新建即激活：隐藏旧的，显示新的
  if (activeTabId && tabs.has(activeTabId)) hideView(activeTabId);
  activeTabId = tabId;
  showView(tabId);
  return tabId;
});

ipcMain.handle('browser:close-tab', (_e, tabId) => {
  const t = tabs.get(tabId);
  if (!t) return;
  _pickModeTabs.delete(tabId);
  const inspectCleanup = _inspectListeners.get(tabId);
  if (inspectCleanup) { inspectCleanup(); _inspectListeners.delete(tabId); }
  const targetWin = getTargetWin();
  if (targetWin) targetWin.contentView.removeChildView(t.view);
  try { t.view.webContents.destroy(); } catch (_) {}
  tabs.delete(tabId);
  if (activeTabId === tabId) {
    const next = tabs.keys().next().value;
    activeTabId = next || null;
    if (next) {
      _pickModeTabs.delete(next);
      showView(next);
    }
  }
});

ipcMain.handle('browser:switch-tab', (_e, tabId) => {
  if (!tabs.has(tabId)) return;
  if (activeTabId && tabs.has(activeTabId)) hideView(activeTabId);
  activeTabId = tabId;
  // 切换到新 tab 时清理 pick 状态（否则回到 browse 时保持 1280x800 的屏外尺寸）
  _pickModeTabs.delete(tabId);
  showView(tabId);
});

ipcMain.handle('browser:navigate', (_e, { tabId, url }) => {
  const t = tabs.get(tabId);
  if (!t || !url) return;
  if (isSelfUrl(url)) {
    pushTabEvent({ type: 'blocked', url, reason: '不能在内置浏览器中打开应用自身的地址' });
    return;
  }
  t.url = url;
  t.view.webContents.loadURL(url);
});

let _setBoundsTimer = null;
ipcMain.handle('browser:set-bounds', (_e, { x, y, w, h, scale }) => {
  if (browserDetached) return;

  const safeW = Math.min(Math.max(Math.round(w) || 1, 1), 3840);
  const safeH = Math.min(Math.max(Math.round(h) || 1, 1), 2160);
  const factor = scale && Number.isFinite(scale) && scale > 0 ? Math.min(Math.max(scale, 0.1), 2.0) : 1;

  // 前端 resize 事件 + ResizeObserver 会同时触发多次 set-bounds，
  // 用 16ms debounce 合并，避免 setBounds/setZoomFactor 重复调用导致尺寸闪烁
  if (_setBoundsTimer) clearTimeout(_setBoundsTimer);
  _setBoundsTimer = setTimeout(() => {
    currentBounds = { x: Math.round(x) || 0, y: Math.round(y) || 0, width: safeW, height: safeH };
    currentScale = factor;
    _boundsInitialized = true;
    if (activeTabId) {
      const t = tabs.get(activeTabId);
      if (t) {
        // pick 模式下只更新 currentBounds/currentScale，不碰 view（view 保持屏外 1280x800）
        // 等 pick-end -> showView 时用最新的 currentBounds 恢复
        if (!_pickModeTabs.has(activeTabId)) {
          t.view.setBounds(currentBounds);
          try { t.view.webContents.setZoomFactor(factor); } catch (_) {}
        }
      }
    }
  }, 16);
});

// 隐藏内置浏览器：前端面板卸载时调用，把所有原生 view 移到屏外，避免盖住 React 工作区
ipcMain.handle('browser:hide', () => {
  if (browserDetached) return; // 独立窗口模式下不隐藏
  for (const id of tabs.keys()) hideView(id);
});

// 进入选取模式：截取 view 实时图作背景，view 移屏外（避免原生层盖住前端 overlay）
// 🌟 核心原则：绝不改变 zoomFactor 和 viewport 尺寸！直接按当前浏览模式的 live state 截图。
// 否则缩放被重置为 1 时 Chromium 会重新布局（响应式断点、字体、DPR 都会变），
// 截出来的图就和用户刚刚浏览的画面不一致——这就是"点击 pick 网页突然变大"的根因。
// _pickModeTabs 已在文件顶部声明
ipcMain.handle('browser:pick-start', async (_e, tabId) => {
  const t = tabs.get(tabId);
  if (!t) return { imageDataUrl: null, width: 0, height: 0 };
  // 🌟 竞态修复：第一行就加标记，避免 60ms 等待期间 set-bounds IPC 把 view 拉回屏幕
  _pickModeTabs.add(tabId);

  if (browserDetached && detachedWin) {
    // ===== 独立窗口模式 =====
    const [w, h] = detachedWin.getContentSize();
    const vw = w, vh = h - 48;
    // 保持 view 的 width/height=vw×vh 不变（视口尺寸不变→布局不变），只把位置移到屏外
    // 独立窗口模式下 zoomFactor 已为 1，所以 CSS viewport 恰好就是 vw×vh
    t.view.setBounds({ x: -20000, y: -20000, width: vw, height: vh });
    let imageDataUrl = null;
    try {
      await new Promise((r) => setTimeout(r, 30));
      const image = await t.view.webContents.capturePage();
      imageDataUrl = image.toDataURL();
    } catch (err) {
      console.error('[browser:pick-start] detached capturePage failed', err);
    }
    // 返回 CSS viewport 尺寸（供前端 overlay 用同样的坐标系渲染）
    return { imageDataUrl, width: vw, height: vh, viewportCssWidth: vw, viewportCssHeight: vh };
  }

  // ===== 主窗口模式：保持浏览模式的 currentBounds + currentScale，绝不重置！=====
  const snapW = currentBounds.width  || 1280;
  const snapH = currentBounds.height || 800;
  const scale = currentScale || 1;
  // 🌟 关键：width/height 保持 snapW×snapH 原样不变（和浏览时一样），zoomFactor 也不动
  // 只改 x/y 移到屏外 —— Chromium 视口尺寸没变，布局不动，画面和浏览时 1:1 对应
  t.view.setBounds({ x: -20000, y: -20000, width: snapW, height: snapH });
  // 注意：这里不再调用 setZoomFactor(1)！保持当前的 scale，这样：
  //   1) Chromium 不会 re-layout，截的图和浏览时看到的完全一样
  //   2) 后续 locate 返回的 CSS-pixel rect 可以被前端按同样的坐标系还原
  let imageDataUrl = null;
  try {
    await new Promise((r) => setTimeout(r, 30));
    const image = await t.view.webContents.capturePage();
    imageDataUrl = image.toDataURL();
  } catch (err) {
    console.error('[browser:pick-start] capturePage failed', err);
  }
  // 返回两个坐标系给前端：
  //   - width,height：截图本身的物理像素尺寸（用于 <img> 显示）
  //   - viewportCssWidth,Height：后端 locate/rect 返回值使用的 CSS 视口坐标空间
  //     = snapW/scale × snapH/scale。前端 overlay 要设为这个尺寸来对齐。
  const viewportCssWidth  = Math.max(1, Math.round(snapW / scale));
  const viewportCssHeight = Math.max(1, Math.round(snapH / scale));
  return { imageDataUrl, width: snapW, height: snapH, viewportCssWidth, viewportCssHeight };
});

// 退出选取模式：view 恢复到容器 bounds，并恢复当前的 zoomFactor
ipcMain.handle('browser:pick-end', (_e, tabId) => {
  _pickModeTabs.delete(tabId);
  showView(tabId);
});

// 跨域元素定位（见下方 locateInFrame）
//   1) 同源 iframe 递归：在主 frame 内 elementFromPoint，若命中 iframe 则在 iframe.contentDocument 内再定位
//   2) 跨域 iframe：同源无法访问，把命中的 iframe rect 作为相对坐标偏移，在 mainFrame.frames 中按 URL 匹配对应子 frame 二次定位
//   3) 多层嵌套支持：子 frame 命中 iframe 时继续递归
async function locateInFrame(wc, x, y, depth = 0) {
  if (depth > 5) return null; // 防无限嵌套
  const mainFrame = wc.mainFrame;
  // 把 x,y 作为脚本常量传入，避免拼接字符串问题
  const pickScript = `(() => {
    function pick(doc, px, py) {
      const el = doc.elementFromPoint(px, py);
      if (!el) return null;
      if (el.tagName === 'IFRAME') {
        const r = el.getBoundingClientRect();
        let sub = null;
        try { sub = pick(el.contentDocument, px - r.left, py - r.top); } catch (_) {}
        if (sub) return sub;
        return { tag: 'iframe', id: el.id, cls: typeof el.className === 'string' ? el.className : '', src: el.src || '', rect: { x: r.left, y: r.top, w: r.width, h: r.height }, _iframe: true };
      }
      const r = el.getBoundingClientRect();
      return { tag: el.tagName.toLowerCase(), id: el.id, cls: typeof el.className === 'string' ? el.className : '', rect: { x: r.left, y: r.top, w: r.width, h: r.height } };
    }
    return pick(document, ${x}, ${y});
  })()`;
  const hit = await mainFrame.executeJavaScript(pickScript);
  if (!hit) return null;
  if (!hit._iframe) return hit;
  // 跨域 iframe 二次定位（递归支持多层嵌套）
  const subFrames = mainFrame.frames || [];
  let sub = subFrames.find((f) => f.url === hit.src);
  if (!sub && hit.src) {
    // URL 带 query/hash 时宽松匹配：包含关系
    sub = subFrames.find((f) => f.url && (f.url === hit.src || f.url.startsWith(hit.src.split('?')[0]) || hit.src.startsWith(f.url.split('?')[0])));
  }
  if (sub) {
    const ix = x - hit.rect.x;
    const iy = y - hit.rect.y;
    return await locateInFrame(sub, ix, iy, depth + 1);
  }
  return hit;
}

ipcMain.handle('browser:locate', async (_e, { tabId, x, y }) => {
  const t = tabs.get(tabId);
  if (!t) return null;
  const nx = Number(x);
  const ny = Number(y);
  if (!Number.isFinite(nx) || !Number.isFinite(ny)) return null;

  // 前端 getCoords() 已经把鼠标位置换算为 1280x800 逻辑坐标（CSS 视口坐标），
  // setZoomFactor 不改变 CSS 视口坐标系，因此此处直接使用，不要再乘 zoom！
  try {
    return await locateInFrame(t.view.webContents, nx, ny);
  } catch (err) {
    console.error('[browser:locate] failed', err);
    return null;
  }
});

// ===== IPC: CDP 元素拾取 =====
// 使用 Chrome DevTools Protocol 提取元素的完整语义信息（outerHTML/innerText/attributes/CSS selector）
// 比 locateInFrame 的 elementFromPoint 更强大：直接返回 Agent 可读的 DOM 上下文
const _cdpAttached = new WeakSet();
async function ensureCdp(wc) {
  if (_cdpAttached.has(wc)) return;
  await wc.debugger.attach('1.3');
  _cdpAttached.add(wc);
}

ipcMain.handle('browser:cdp-pick-element', async (_e, { tabId, x, y }) => {
  const t = tabs.get(tabId);
  if (!t) return null;
  const wc = t.view.webContents;
  // 前端 getCoords() 已经换算为 1280x800 逻辑坐标（= CSS 视口坐标），直接使用
  const cx = Math.round(nx_safe(x));
  const cy = Math.round(ny_safe(y));

  try {
    await ensureCdp(wc);
    await wc.debugger.sendCommand('DOM.enable');
    await wc.debugger.sendCommand('Runtime.enable');

    await wc.debugger.sendCommand('DOM.getDocument', { depth: -1 });
    const nodeRes = await wc.debugger.sendCommand('DOM.getNodeForLocation', {
      x: cx, y: cy, includeUserAgentShadowDOM: true,
    });
    if (!nodeRes || !nodeRes.nodeId) return null;
    const nodeId = nodeRes.nodeId;

    // outerHTML
    const htmlRes = await wc.debugger.sendCommand('DOM.getOuterHTML', { nodeId });
    // 属性
    const detail = await wc.debugger.sendCommand('DOM.describeNode', { nodeId });
    const attrs = (detail.node && detail.node.attributes) || [];
    const attributes = {};
    for (let i = 0; i < attrs.length; i += 2) attributes[attrs[i]] = attrs[i + 1];

    // innerText / value / placeholder
    let innerText = '';
    try {
      const resolved = await wc.debugger.sendCommand('DOM.resolveNode', { nodeId });
      const objectId = resolved.object.objectId;
      const textRes = await wc.debugger.sendCommand('Runtime.callFunctionOn', {
        objectId,
        functionDeclaration: 'function() { return this.innerText || this.value || this.placeholder || ""; }',
        returnByValue: true,
      });
      innerText = (textRes.result && textRes.result.value) || '';
      await wc.debugger.sendCommand('Runtime.releaseObject', { objectId });
    } catch (_) {}

    // 唯一 CSS selector
    let cssSelector = '';
    try {
      const resolved = await wc.debugger.sendCommand('DOM.resolveNode', { nodeId });
      const objectId = resolved.object.objectId;
      const selRes = await wc.debugger.sendCommand('Runtime.callFunctionOn', {
        objectId,
        functionDeclaration: `function() {
          var el = this;
          if (el.id) return '#' + el.id;
          var path = [];
          while (el && el.nodeType === 1) {
            var idx = 1, sib = el.previousElementSibling;
            while (sib) { if (sib.tagName === el.tagName) idx++; sib = sib.previousElementSibling; }
            path.unshift(el.tagName.toLowerCase() + ':nth-of-type(' + idx + ')');
            el = el.parentElement;
          }
          return path.join(' > ');
        }`,
        returnByValue: true,
      });
      cssSelector = (selRes.result && selRes.result.value) || '';
      await wc.debugger.sendCommand('Runtime.releaseObject', { objectId });
    } catch (_) {}

    // rect（getBoundingClientRect 在 CSS 视口坐标系下 = 前端逻辑坐标系，无需缩放转换）
    let rect = null;
    try {
      const resolved = await wc.debugger.sendCommand('DOM.resolveNode', { nodeId });
      const objectId = resolved.object.objectId;
      const rectRes = await wc.debugger.sendCommand('Runtime.callFunctionOn', {
        objectId,
        functionDeclaration: 'function() { var r = this.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }',
        returnByValue: true,
      });
      const rv = rectRes.result && rectRes.result.value;
      if (rv) rect = { x: rv.x, y: rv.y, w: rv.w, h: rv.h };
      await wc.debugger.sendCommand('Runtime.releaseObject', { objectId });
    } catch (_) {}

    return {
      tagName: (detail.node && detail.node.nodeName || '').toLowerCase(),
      attributes,
      outerHTML: (htmlRes && htmlRes.outerHTML) || '',
      innerText,
      cssSelector,
      rect,
    };
  } catch (err) {
    console.error('[browser:cdp-pick-element] failed', err);
    return null;
  }
});

// CDP Overlay 原生化高亮（方案B）：像 Chrome DevTools F12 一样，由 Chromium 内核直接在网页内部绘制选中框
// 零坐标偏差、零延迟、自动适配任何 zoomFactor / 显示器缩放
ipcMain.handle('browser:cdp-highlight', async (_e, { tabId, x, y }) => {
  const t = tabs.get(tabId);
  if (!t) return null;
  const wc = t.view.webContents;
  const cx = Math.round(nx_safe(x));
  const cy = Math.round(ny_safe(y));

  try {
    await ensureCdp(wc);
    await wc.debugger.sendCommand('DOM.enable');
    await wc.debugger.sendCommand('Overlay.enable');
    await wc.debugger.sendCommand('DOM.getDocument', { depth: -1 });

    const nodeRes = await wc.debugger.sendCommand('DOM.getNodeForLocation', {
      x: cx, y: cy, includeUserAgentShadowDOM: true,
    });
    if (!nodeRes || !nodeRes.nodeId) {
      await wc.debugger.sendCommand('Overlay.hideHighlight');
      return null;
    }
    await wc.debugger.sendCommand('Overlay.highlightNode', {
      nodeId: nodeRes.nodeId,
      highlightConfig: {
        showInfo: true,
        contentColor: { r: 111, g: 168, b: 220, a: 0.55 },
        paddingColor: { r: 147, g: 196, b: 125, a: 0.45 },
        borderColor: { r: 255, g: 210, b: 100, a: 0.9 },
        marginColor: { r: 246, g: 178, b: 107, a: 0.4 },
      },
    });
    return { nodeId: nodeRes.nodeId };
  } catch (err) {
    console.error('[browser:cdp-highlight] failed', err);
    return null;
  }
});

ipcMain.handle('browser:cdp-unhighlight', async (_e, { tabId }) => {
  const t = tabs.get(tabId);
  if (!t) return;
  try {
    await ensureCdp(t.view.webContents);
    await t.view.webContents.debugger.sendCommand('Overlay.hideHighlight');
  } catch (_) {}
});

// ===== CDP Inspect Mode（终极方案：像 F12 元素拾取器一样，由 Chromium 内核自动高亮）=====
// 独立窗口 pick 模式专用：不需要截图、不需要坐标换算、不受缩放/DPI 影响
// setInspectMode('searchForNode') 会让 Chromium 自动在鼠标悬停时高亮元素，
// 用户点击时触发 Overlay.inspectNodeRequested 事件，主进程提取语义后发给前端
// _inspectListeners 已在文件顶部声明

ipcMain.handle('browser:cdp-inspect-start', async (_e, { tabId }) => {
  const t = tabs.get(tabId);
  if (!t) return;
  const wc = t.view.webContents;
  try {
    await ensureCdp(wc);
    await wc.debugger.sendCommand('DOM.enable');
    await wc.debugger.sendCommand('Overlay.enable');
    await wc.debugger.sendCommand('DOM.getDocument', { depth: -1 });

    // 开启 F12 式元素拾取模式：Chromium 自动在 hover 时高亮，click 时选中
    await wc.debugger.sendCommand('Overlay.setInspectMode', {
      mode: 'searchForNode',
      highlightConfig: {
        showInfo: true,
        showStyles: true,
        contentColor: { r: 111, g: 168, b: 220, a: 0.55 },
        paddingColor: { r: 147, g: 196, b: 125, a: 0.45 },
        borderColor: { r: 255, g: 210, b: 100, a: 0.9 },
        marginColor: { r: 246, g: 178, b: 107, a: 0.4 },
      },
    });

    // 监听用户点击选中元素的事件
    const onMessage = async (_event, method, params) => {
      if (method !== 'Overlay.inspectNodeRequested') return;
      const nodeId = params.nodeId;
      if (!nodeId) return;
      try {
        // 停止自动高亮（切换到持久高亮）
        await wc.debugger.sendCommand('Overlay.setInspectMode', { mode: 'none' });

        // 持久高亮选中的元素
        await wc.debugger.sendCommand('Overlay.highlightNode', {
          nodeId,
          highlightConfig: {
            showInfo: true,
            contentColor: { r: 235, g: 203, b: 139, a: 0.35 },
            paddingColor: { r: 235, g: 203, b: 139, a: 0.25 },
            borderColor: { r: 235, g: 203, b: 139, a: 0.9 },
          },
        });

        // 提取语义信息
        const htmlRes = await wc.debugger.sendCommand('DOM.getOuterHTML', { nodeId });
        const detail = await wc.debugger.sendCommand('DOM.describeNode', { nodeId });
        const attrs = (detail.node && detail.node.attributes) || [];
        const attributes = {};
        for (let i = 0; i < attrs.length; i += 2) attributes[attrs[i]] = attrs[i + 1];

        let innerText = '';
        let cssSelector = '';
        let rect = null;
        try {
          const resolved = await wc.debugger.sendCommand('DOM.resolveNode', { nodeId });
          const objectId = resolved.object.objectId;

          const textRes = await wc.debugger.sendCommand('Runtime.callFunctionOn', {
            objectId,
            functionDeclaration: 'function() { return this.innerText || this.value || this.placeholder || ""; }',
            returnByValue: true,
          });
          innerText = (textRes.result && textRes.result.value) || '';

          const selRes = await wc.debugger.sendCommand('Runtime.callFunctionOn', {
            objectId,
            functionDeclaration: `function() {
              var el = this;
              if (el.id) return '#' + el.id;
              var path = [];
              while (el && el.nodeType === 1) {
                var idx = 1, sib = el.previousElementSibling;
                while (sib) { if (sib.tagName === el.tagName) idx++; sib = sib.previousElementSibling; }
                path.unshift(el.tagName.toLowerCase() + ':nth-of-type(' + idx + ')');
                el = el.parentElement;
              }
              return path.join(' > ');
            }`,
            returnByValue: true,
          });
          cssSelector = (selRes.result && selRes.result.value) || '';

          const rectRes = await wc.debugger.sendCommand('Runtime.callFunctionOn', {
            objectId,
            functionDeclaration: 'function() { var r = this.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }',
            returnByValue: true,
          });
          const rv = rectRes.result && rectRes.result.value;
          if (rv) rect = { x: rv.x, y: rv.y, w: rv.w, h: rv.h };

          await wc.debugger.sendCommand('Runtime.releaseObject', { objectId });
        } catch (_) {}

        // 发给独立窗口前端
        const elementData = {
          tagName: (detail.node && detail.node.nodeName || '').toLowerCase(),
          attributes, outerHTML: (htmlRes && htmlRes.outerHTML) || '',
          innerText, cssSelector, rect,
        };
        const targetWin = getTargetWin();
        if (targetWin && !targetWin.isDestroyed()) {
          targetWin.webContents.send('pick:element-selected', elementData);
        }
      } catch (err) {
        console.error('[cdp-inspect] inspectNodeRequested error:', err);
      }
    };

    wc.debugger.on('message', onMessage);
    _inspectListeners.set(tabId, () => {
      try { wc.debugger.off('message', onMessage); } catch (_) {}
    });
  } catch (err) {
    console.error('[cdp-inspect-start] error:', err);
  }
});

// 恢复 inspect 模式（用户提交评论后，继续拾取下一个元素）
ipcMain.handle('browser:cdp-inspect-resume', async (_e, { tabId }) => {
  const t = tabs.get(tabId);
  if (!t) return;
  const wc = t.view.webContents;
  try {
    await ensureCdp(wc);
    await wc.debugger.sendCommand('Overlay.hideHighlight');
    await wc.debugger.sendCommand('Overlay.setInspectMode', {
      mode: 'searchForNode',
      highlightConfig: {
        showInfo: true,
        contentColor: { r: 111, g: 168, b: 220, a: 0.55 },
        paddingColor: { r: 147, g: 196, b: 125, a: 0.45 },
        borderColor: { r: 255, g: 210, b: 100, a: 0.9 },
        marginColor: { r: 246, g: 178, b: 107, a: 0.4 },
      },
    });
  } catch (_) {}
});

// 停止 inspect 模式
ipcMain.handle('browser:cdp-inspect-stop', async (_e, { tabId }) => {
  const t = tabs.get(tabId);
  if (!t) return;
  const wc = t.view.webContents;
  try {
    await ensureCdp(wc);
    await wc.debugger.sendCommand('Overlay.setInspectMode', { mode: 'none' });
    await wc.debugger.sendCommand('Overlay.hideHighlight');
  } catch (_) {}
  const cleanup = _inspectListeners.get(tabId);
  if (cleanup) { cleanup(); _inspectListeners.delete(tabId); }
});

// 独立窗口：调整 view 底部留白（为评论框腾出空间）
ipcMain.handle('browser:detach-resize-view', (_e, bottomPx) => {
  if (!detachedWin || !activeTabId) return;
  const [w, h] = detachedWin.getContentSize();
  const HEADER_H = 48;
  const t = tabs.get(activeTabId);
  if (t && !_pickModeTabs.has(activeTabId)) {
    const viewH = Math.max(50, h - HEADER_H - (bottomPx || 0));
    t.view.setBounds({ x: 0, y: HEADER_H, width: w, height: viewH });
  }
});

function nx_safe(v) { const n = Number(v); return Number.isFinite(n) ? n : 0; }
function ny_safe(v) { return nx_safe(v); }

// ===== IPC: 独立预览窗口 =====
// 创建独立 BrowserWindow，内嵌涂鸦风格 HTML 页面，用 img/video/iframe 引用后端 /preview URL
function escapeHtmlAttr(str) {
  return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// 窗口控制 IPC（通用，通过 e.sender 找到调用方窗口，主窗口/预览窗口共用）
ipcMain.handle('win:minimize', (e) => { BrowserWindow.fromWebContents(e.sender)?.minimize(); });
ipcMain.handle('win:toggle-maximize', (e) => {
  const w = BrowserWindow.fromWebContents(e.sender);
  if (!w) return;
  if (w.isMaximized()) w.unmaximize(); else w.maximize();
});
ipcMain.handle('win:close', (e) => { BrowserWindow.fromWebContents(e.sender)?.close(); });

// ===== IPC: 内置浏览器独立窗口 =====
ipcMain.handle('browser:detach', () => {
  if (browserDetached || !mainWindow) return;
  browserDetached = true;

  const activeTab = tabs.get(activeTabId);
  const currentUrl = escapeHtmlAttr(activeTab?.url || '');
  const tabIdStr = activeTabId || '';

  detachedWin = new BrowserWindow({
    width: 1200, height: 800,
    title: 'PurrCat Browser',
    titleBarStyle: 'hidden',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  Menu.setApplicationMenu(null);

  const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>PurrCat Browser</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#FAF8F5; font-family:'Comic Sans MS',cursive,sans-serif; width:100vw; height:100vh; overflow:hidden; }
  .container { width:100%; height:100%; display:flex; flex-direction:column; overflow:hidden; }
  .header { display:flex; align-items:center; gap:8px; padding:6px 10px; border-bottom:3px solid rgba(26,26,26,0.15); flex-shrink:0; -webkit-app-region:drag; height:48px; background:#FAF8F5; }
  .mode-group { display:flex; gap:4px; -webkit-app-region:no-drag; }
  .mode-btn { width:34px; height:34px; border:2px solid #1A1A1A; background:#fff; cursor:pointer; display:flex; align-items:center; justify-content:center; color:#1A1A1A; transition:all 0.15s; border-radius:6px 10px 5px 8px/8px 5px 10px 6px; }
  .mode-btn:hover { background:#ECEFF4; }
  .mode-btn.active { background:#88c0d0; color:#fff; }
  .mode-btn.active.pick { background:#EBCB8B; color:#1A1A1A; }
  .mode-btn.active.draw { background:#bf616a; color:#fff; }
  .addr { flex:1; -webkit-app-region:no-drag; border:2px solid #1A1A1A; background:#fff; padding:4px 10px; font-size:13px; font-weight:900; border-radius:6px 10px 5px 8px/8px 5px 10px 6px; outline:none; min-width:0; }
  .dock-btn { -webkit-app-region:no-drag; padding:0 12px; height:30px; border:2px solid #1A1A1A; background:#88c0d0; color:#fff; font-size:11px; font-weight:900; letter-spacing:0.08em; cursor:pointer; border-radius:6px 10px 5px 8px/8px 5px 10px 6px; transition:all 0.15s; white-space:nowrap; }
  .dock-btn:hover { background:#5e81ac; transform:translateY(-1px); }
  .win-controls { display:flex; gap:6px; -webkit-app-region:no-drag; }
  .win-btn { width:26px; height:26px; border:2px solid #1A1A1A; background:transparent; cursor:pointer; display:flex; align-items:center; justify-content:center; color:#1A1A1A; transition:all 0.15s; border-radius:6px 10px 5px 8px/8px 5px 10px 6px; }
  .win-btn:hover { background:rgba(26,26,26,0.1); }
  .win-close:hover { background:#D47A5A; color:#FFF; border-color:#D47A5A; }
  .view-area { flex:1; position:relative; overflow:hidden; background:#e5e9f0; }
  .overlay { position:absolute; inset:0; z-index:10; }
  .overlay img { width:100%; height:100%; object-fit:fill; pointer-events:none; }
  .interact { position:absolute; inset:0; cursor:crosshair; }
  .hover-rect { position:absolute; border:2px solid #EBCB8B; background:rgba(235,203,139,0.15); pointer-events:none; z-index:20; display:none; }
  .current-rect { position:absolute; border:3px solid #bf616a; background:rgba(191,97,106,0.2); pointer-events:none; z-index:20; display:none; }
  .pick-rect { position:absolute; border:3px solid #EBCB8B; background:rgba(235,203,139,0.2); pointer-events:none; z-index:20; display:none; }
  .pick-label { position:absolute; top:-22px; left:-3px; background:#1A1A1A; color:#FAF8F5; font-size:10px; font-weight:900; padding:2px 8px; border-radius:4px 4px 0 0; white-space:nowrap; pointer-events:none; }
  .comment-box { position:absolute; z-index:30; background:#FAF8F5; border:3px solid #1A1A1A; box-shadow:6px 6px 0 rgba(26,26,26,1); padding:12px; width:280px; border-radius:6px 10px 5px 8px/8px 5px 10px 6px; display:none; }
  .comment-box h4 { font-size:13px; font-weight:900; color:#bf616a; letter-spacing:0.08em; margin-bottom:8px; }
  .comment-box textarea { width:100%; background:#FDF8F0; border:2px solid #1A1A1A; padding:8px; font-size:13px; font-weight:700; resize:none; height:64px; outline:none; border-radius:4px; font-family:inherit; }
  .comment-box button { width:100%; background:#1A1A1A; color:#FAF8F5; font-weight:900; padding:8px; border:2px solid #1A1A1A; cursor:pointer; margin-top:8px; display:flex; align-items:center; justify-content:center; gap:6px; border-radius:4px; }
  .comment-box button:hover { background:#bf616a; color:#1A1A1A; }
  .comment-box .close-btn { width:auto; position:absolute; top:8px; right:8px; background:transparent; border:none; color:#1A1A1A; font-size:16px; padding:4px; }
  .comment-box .close-btn:hover { background:rgba(26,26,26,0.1); }
</style></head><body>
<div class="container">
  <div class="header">
    <div class="mode-group">
      <button class="mode-btn active" id="btnBrowse" title="浏览" onclick="setMode('browse')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg></button>
      <button class="mode-btn" id="btnPick" title="元素选取" onclick="setMode('pick')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m3 3 7.07 16.97 2.51-7.39 7.39-2.51L3 3z"/><path d="m13 13 6 6"/></svg></button>
      <button class="mode-btn" id="btnDraw" title="自由画框" onclick="setMode('draw')"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="3" width="18" height="18" rx="2" transform="rotate(3 12 12)"/></svg></button>
    </div>
    <input class="addr" id="addr" value="${currentUrl}" placeholder="输入网址，回车访问..."
      onkeydown="if(event.key==='Enter'){window.purrcat.browserNavigate('${tabIdStr}',this.value)}" />
    <button class="dock-btn" onclick="window.purrcat.browserReattach()" title="回归主窗口">&larr; DOCK</button>
    <div class="win-controls">
      <button class="win-btn" onclick="window.purrcat.winMinimize()"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round"><line x1="5" y1="12" x2="19" y2="12"/></svg></button>
      <button class="win-btn" onclick="window.purrcat.winToggleMaximize()"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round"><rect x="5" y="5" width="14" height="14" rx="1"/></svg></button>
      <button class="win-btn win-close" onclick="window.purrcat.winClose()"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg></button>
    </div>
  </div>
  <div class="view-area" id="viewArea">
    <div class="overlay" id="overlay" style="display:none">
      <img id="snapshot" />
      <div class="interact" id="interact"></div>
      <div class="hover-rect" id="hoverRect"></div>
      <div class="pick-rect" id="pickRect"><div class="pick-label" id="pickLabel"></div></div>
      <div class="current-rect" id="currentRect"></div>
      <div class="comment-box" id="commentBox">
        <button class="close-btn" onclick="cancelComment()">&times;</button>
        <h4>COMMAND</h4>
        <textarea id="commentText" placeholder="要求 Agent 修改此处的..." onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();submitComment()}"></textarea>
        <button onclick="submitComment()">EXECUTE</button>
      </div>
    </div>
  </div>
</div>
<script>
  var TAB_ID = '${tabIdStr}';
  var mode = 'browse';
  var snapW = 1280, snapH = 800;
  var isDrawing = false, startX = 0, startY = 0;
  var pickedEl = null, currentRectData = null;

  function setMode(m) {
    if (mode === m) return;
    // 退出旧模式
    if (mode === 'pick') {
      // pick 模式用 CDP inspect，退出时停止
      window.purrcat.browserCdpInspectStop(TAB_ID);
      window.purrcat.browserDetachResizeView(0); // 恢复 view 全高
    } else if (mode === 'draw') {
      // draw 模式用截图，退出时恢复 view
      window.purrcat.browserPickEnd(TAB_ID);
    }
    mode = m;
    // 更新按钮样式
    document.getElementById('btnBrowse').className = 'mode-btn' + (m==='browse'?' active':'');
    document.getElementById('btnPick').className = 'mode-btn' + (m==='pick'?' active pick':'');
    document.getElementById('btnDraw').className = 'mode-btn' + (m==='draw'?' active draw':'');
    // 清理 UI
    document.getElementById('overlay').style.display = 'none';
    document.getElementById('commentBox').style.display = 'none';
    pickedEl = null; currentRectData = null;

    if (m === 'pick') {
      // 🌟 CDP Inspect 模式：view 保持可见，Chromium 自动 hover 高亮 + click 选中
      // 不需要截图、不需要坐标换算、不受缩放/DPI 影响 —— 和 F12 元素拾取器一模一样
      window.purrcat.browserCdpInspectStart(TAB_ID);
    } else if (m === 'draw') {
      // draw 模式仍用截图（自由画框需要 overlay 交互层）
      window.purrcat.browserPickStart(TAB_ID).then(function(res) {
        if (!res || !res.imageDataUrl) { setMode('browse'); return; }
        snapW = res.viewportCssWidth || res.width || 1280;
        snapH = res.viewportCssHeight || res.height || 800;
        document.getElementById('snapshot').src = res.imageDataUrl;
        document.getElementById('overlay').style.display = 'block';
      }).catch(function() { setMode('browse'); });
    }
  }

  // 🌟 CDP inspect 选中元素后的回调（主进程提取完语义后推送）
  if (window.purrcat && window.purrcat.onPickElementSelected) {
    window.purrcat.onPickElementSelected(function(el) {
      if (mode !== 'pick' || !el) return;
      pickedEl = el;
      currentRectData = el.rect || { x: 0, y: 0, w: 100, h: 30 };
      // 缩小 view 腾出底部空间给评论框（180px）
      window.purrcat.browserDetachResizeView(180);
      // 显示评论框
      var cb = document.getElementById('commentBox');
      cb.style.left = '50%';
      cb.style.top = 'auto';
      cb.style.bottom = '12px';
      cb.style.transform = 'translateX(-50%)';
      cb.style.width = '420px';
      cb.style.display = 'block';
      // 更新提示文字
      var ph = '修改 <' + (el.tagName || '?') + '>';
      if (el.innerText) ph = '修改 <' + el.tagName + '> "' + el.innerText.substring(0,40) + '"';
      document.getElementById('commentText').placeholder = ph;
      document.getElementById('commentText').focus();
    });
  }

  // 坐标换算：屏幕像素 → 截图的 CSS 视口坐标（draw 模式用）
  function getCoords(clientX, clientY) {
    var r = document.getElementById('interact').getBoundingClientRect();
    return { x: clientX - r.left, y: clientY - r.top };
  }

  // 交互层鼠标事件（draw 模式专用）
  var interact = document.getElementById('interact');
  interact.addEventListener('mousemove', function(e) {
    if (mode !== 'draw' || !isDrawing) return;
    var c = getCoords(e.clientX, e.clientY);
    currentRectData = {
      x: Math.min(startX, c.x), y: Math.min(startY, c.y),
      w: Math.abs(c.x - startX), h: Math.abs(c.y - startY)
    };
    updateRect('currentRect', currentRectData);
  });

  interact.addEventListener('mousedown', function(e) {
    if (mode !== 'draw') return;
    var c = getCoords(e.clientX, e.clientY);
    isDrawing = true;
    startX = c.x; startY = c.y;
    currentRectData = { x: c.x, y: c.y, w: 0, h: 0 };
    updateRect('currentRect', currentRectData);
    document.getElementById('currentRect').style.display = 'block';
  });

  interact.addEventListener('mouseup', function(e) {
    if (mode === 'draw' && isDrawing) {
      isDrawing = false;
      if (currentRectData && currentRectData.w > 10 && currentRectData.h > 10) {
        // draw 模式画完框后，缩小 view 显示评论框
        window.purrcat.browserDetachResizeView(180);
        var cb = document.getElementById('commentBox');
        cb.style.left = '50%';
        cb.style.top = 'auto';
        cb.style.bottom = '12px';
        cb.style.transform = 'translateX(-50%)';
        cb.style.width = '420px';
        cb.style.display = 'block';
        document.getElementById('commentText').focus();
      } else {
        document.getElementById('currentRect').style.display = 'none';
      }
    }
  });

  function updateRect(id, r) {
    var el = document.getElementById(id);
    el.style.left = r.x + 'px';
    el.style.top = r.y + 'px';
    el.style.width = Math.max(r.w, 8) + 'px';
    el.style.height = Math.max(r.h, 8) + 'px';
  }

  function cancelComment() {
    document.getElementById('commentBox').style.display = 'none';
    document.getElementById('currentRect').style.display = 'none';
    pickedEl = null; currentRectData = null;
    // 恢复 view 全高
    window.purrcat.browserDetachResizeView(0);
    // pick 模式：恢复 inspect（继续拾取下一个元素）
    if (mode === 'pick') {
      window.purrcat.browserCdpInspectResume(TAB_ID);
    }
  }

  function submitComment() {
    var text = document.getElementById('commentText').value.trim();
    if (!text || !currentRectData) return;
    var url = document.getElementById('addr').value;

    var elementContext;
    if (pickedEl) {
      var parts = [];
      parts.push('Element: <' + pickedEl.tagName + '>');
      if (pickedEl.innerText) parts.push('Text: "' + pickedEl.innerText.trim().substring(0, 200) + '"');
      if (pickedEl.cssSelector) parts.push('CSS Selector: ' + pickedEl.cssSelector);
      parts.push('HTML: ' + pickedEl.outerHTML.substring(0, 500));
      elementContext = parts.join('\\n');
    } else {
      elementContext = 'User drawn area';
    }

    window.purrcat.browserDetachedComment({
      mode: mode,
      rect: currentRectData,
      domContext: elementContext,
      viewport: { width: snapW, height: snapH }
    }, text, url);

    document.getElementById('commentText').value = '';
    document.getElementById('commentBox').style.display = 'none';
    document.getElementById('currentRect').style.display = 'none';
    pickedEl = null; currentRectData = null;
    // 恢复 view 全高
    window.purrcat.browserDetachResizeView(0);
    // pick 模式：恢复 inspect
    if (mode === 'pick') {
      window.purrcat.browserCdpInspectResume(TAB_ID);
    }
  }

  // Tab 事件监听
  if (window.purrcat && window.purrcat.onTabEvent) {
    window.purrcat.onTabEvent(function(evt) {
      if (evt.type === 'navigate' && evt.tabId === TAB_ID) {
        document.getElementById('addr').value = evt.url;
        if (mode !== 'browse') setMode('browse');
      }
    });
  }
</script>
</body></html>`;

  // 🌟 事件监听必须在 loadURL 之前注册！否则 data: URL 加载太快，did-finish-load 已经过去，监听永远不触发
  detachedWin.webContents.on('did-finish-load', () => {
    // did-finish-load 时，view 已经 addChildView 了吗？不一定——因为 addChildView 是同步的而 loadURL 是异步的
    // 这里再显式调一次，保证尺寸被设置
    updateDetachedBounds();
  });
  detachedWin.on('resize', () => { setTimeout(updateDetachedBounds, 50); });
  detachedWin.on('close', () => { if (detachedWin) reattachBrowser(); });

  detachedWin.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));

  // 把所有 view 从主窗口移到独立窗口
  for (const [, t] of tabs) {
    try { mainWindow.contentView.removeChildView(t.view); } catch (_) {}
    detachedWin.contentView.addChildView(t.view);
  }
  // 🌟 立刻显式调用一次 updateDetachedBounds，防止 loadURL 的 did-finish-load 已经触发（竞态）
  // 即使 did-finish-load 慢一点，用户打开独立窗口后不会看到空白
  updateDetachedBounds();
});

ipcMain.handle('browser:reattach', reattachBrowser);

// 独立窗口拾取的 comment 转发给主窗口的 React 应用
ipcMain.handle('browser:detached-comment', (_e, { pixelData, comment, url }) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('browser:comment', { pixelData, comment, url });
  }
});

ipcMain.handle('preview:open-file', (_e, { url, title, type }) => {
  const safeUrl = escapeHtmlAttr(url);
  const safeTitle = escapeHtmlAttr(title || 'Preview');

  let mediaTag = '';
  if (type === 'image') {
    mediaTag = `<img src="${safeUrl}" alt="Preview">`;
  } else if (type === 'video') {
    mediaTag = `<video src="${safeUrl}" controls autoPlay></video>`;
  } else {
    mediaTag = `<iframe src="${safeUrl}" sandbox="allow-scripts allow-same-origin allow-popups allow-forms"></iframe>`;
  }

  const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${safeTitle}</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#FAF8F5; font-family:'Comic Sans MS',cursive,sans-serif; width:100vw; height:100vh; overflow:hidden; }
  .container { width:100%; height:100%; border:4px solid #1A1A1A; background:#FFFFFF; display:flex; flex-direction:column; overflow:hidden; }
  .header { display:flex; align-items:center; gap:12px; padding:10px 16px; border-bottom:3px solid rgba(26,26,26,0.15); flex-shrink:0; -webkit-app-region:drag; }
  .header .title-icon { flex-shrink:0; color:#3498DB; -webkit-app-region:no-drag; }
  .header h3 { font-size:16px; font-weight:900; letter-spacing:0.08em; color:#1A1A1A; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1; }
  .win-controls { display:flex; gap:8px; -webkit-app-region:no-drag; }
  .win-btn { width:28px; height:28px; border:2px solid #1A1A1A; background:transparent; cursor:pointer; display:flex; align-items:center; justify-content:center; color:#1A1A1A; transition:all 0.15s; border-radius:6px 10px 5px 8px/8px 5px 10px 6px; }
  .win-btn:hover { background:rgba(26,26,26,0.1); transform:translateY(-1px); }
  .win-btn:active { transform:translateY(0); }
  .win-close:hover { background:#D47A5A; color:#FFF; border-color:#D47A5A; }
  .content { flex:1; overflow:auto; display:flex; align-items:center; justify-content:center; position:relative; }
  .content img { max-width:100%; max-height:100%; object-fit:contain; }
  .content video { max-width:100%; max-height:100%; }
  .content iframe { width:100%; height:100%; border:none; }
</style></head><body>
<div class="container">
  <div class="header">
    <svg class="title-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
    <h3>${safeTitle}</h3>
    <div class="win-controls">
      <button class="win-btn" onclick="window.purrcat.winMinimize()" title="最小化">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round"><line x1="5" y1="12" x2="19" y2="12"/></svg>
      </button>
      <button class="win-btn" onclick="window.purrcat.winToggleMaximize()" title="最大化">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round"><rect x="5" y="5" width="14" height="14" rx="1"/></svg>
      </button>
      <button class="win-btn win-close" onclick="window.purrcat.winClose()" title="关闭">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>
      </button>
    </div>
  </div>
  <div class="content">${mediaTag}</div>
</div>
</body></html>`;

  const win = new BrowserWindow({
    width: type === 'video' ? 960 : 900,
    height: type === 'video' ? 540 : 700,
    title: title || 'Preview',
    titleBarStyle: 'hidden',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  Menu.setApplicationMenu(null);
  win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));
});

// ===== 生命周期 =====
app.whenReady().then(() => {
  createBackend();
  createWindow();
});

app.on('window-all-closed', () => {
  if (backendProcess) { try { backendProcess.kill(); } catch (_) {} }
  app.quit();
});

app.on('before-quit', () => {
  if (backendProcess) { try { backendProcess.kill(); } catch (_) {} }
  for (const [, t] of tabs) {
    if (mainWindow) mainWindow.contentView.removeChildView(t.view);
    try { t.view.webContents.destroy(); } catch (_) {}
  }
  tabs.clear();
});

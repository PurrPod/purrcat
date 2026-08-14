// electron/main.js
// PurrCat 主进程：主窗口 + Python 后端 sidecar + 多 Tab WebContentsView 内置浏览器
// 安全：contextIsolation=true，nodeIntegration=false，前端只能用 preload 暴露的 window.purrcat

const { app, BrowserWindow, Menu, dialog, ipcMain, WebContentsView } = require('electron');
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
const OFFSCREEN = { x: -10000, y: 0, width: 1, height: 1 };

function showView(tabId) {
  const t = tabs.get(tabId);
  if (!t || !mainWindow) return;
  t.view.setBounds(currentBounds);
}

function hideView(tabId) {
  const t = tabs.get(tabId);
  if (!t) return;
  t.view.setBounds(OFFSCREEN);
}

function pushTabEvent(payload) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('browser:tab-event', payload);
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
    titleBarOverlay: { color: '#fdfaf5', symbolColor: '#1a1a1a', height: 32 },
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
ipcMain.handle('browser:new-tab', (_e, url) => {
  if (!mainWindow) return null;
  const tabId = 'tab_' + Date.now() + '_' + Math.floor(Math.random() * 1e6);
  const view = new WebContentsView({ webPreferences: { contextIsolation: true } });
  mainWindow.contentView.addChildView(view);
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
  if (mainWindow) mainWindow.contentView.removeChildView(t.view);
  try { t.view.webContents.destroy(); } catch (_) {}
  tabs.delete(tabId);
  if (activeTabId === tabId) {
    const next = tabs.keys().next().value;
    activeTabId = next || null;
    if (next) showView(next);
  }
});

ipcMain.handle('browser:switch-tab', (_e, tabId) => {
  if (!tabs.has(tabId)) return;
  if (activeTabId && tabs.has(activeTabId)) hideView(activeTabId);
  activeTabId = tabId;
  showView(tabId);
});

ipcMain.handle('browser:navigate', (_e, { tabId, url }) => {
  const t = tabs.get(tabId);
  if (!t || !url) return;
  t.url = url;
  t.view.webContents.loadURL(url);
});

ipcMain.handle('browser:set-bounds', (_e, { x, y, w, h, scale }) => {
  currentBounds = { x: Math.round(x), y: Math.round(y), width: Math.round(w), height: Math.round(h) };
  if (activeTabId) {
    showView(activeTabId);
    const t = tabs.get(activeTabId);
    if (t) {
      // ⚠️ 只作用于内置浏览器 Tab 的 webContents（t.view.webContents）。
      //    绝不能用 event.sender / mainWindow.webContents，否则会把 React 主界面缩放！
      // setZoomFactor 原理：scale<1 = 页面缩小(Zoom Out)，网页 CSS 视口宽 = 物理宽 / scale，
      // 例：物理宽 640 + scale 0.5 → 网页认为视口 1280，按桌面宽屏排版后整体缩小塞进 640，
      // 既不触发移动端/窄版布局，又实现等比例无损缩小。
      const factor = scale && Number.isFinite(scale) && scale > 0 ? scale : 1;
      try { t.view.webContents.setZoomFactor(factor); } catch (_) {}
    }
  }
});

// 隐藏内置浏览器：前端面板卸载时调用，把所有原生 view 移到屏外，避免盖住 React 工作区
ipcMain.handle('browser:hide', () => {
  for (const id of tabs.keys()) hideView(id);
});

// 进入选取模式：截取 view 实时图作背景，view 移屏外（避免原生层盖住前端 overlay）
ipcMain.handle('browser:pick-start', async (_e, tabId) => {
  const t = tabs.get(tabId);
  if (!t) return { imageDataUrl: null };
  let imageDataUrl = null;
  try {
    const image = await t.view.webContents.capturePage();
    imageDataUrl = image.toDataURL();
  } catch (err) {
    console.error('[browser:pick-start] capturePage failed', err);
  }
  hideView(tabId);
  return { imageDataUrl };
});

// 退出选取模式：view 恢复到容器 bounds
ipcMain.handle('browser:pick-end', (_e, tabId) => {
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
  try {
    return await locateInFrame(t.view.webContents, nx, ny);
  } catch (err) {
    console.error('[browser:locate] failed', err);
    return null;
  }
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

// electron/preload.js
// 预加载脚本：通过 contextBridge 把受控的 Electron 能力暴露给前端 window.purrcat
// 安全原则：contextIsolation: true，不开 nodeIntegration，前端只能用这里暴露的接口

const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('purrcat', {
  // ===== File Reference =====
  // 文件/文件夹选择对话框，返回真实绝对路径数组
  // opts.directory=true 选文件夹，否则选文件(多选)
  // 注：Windows/Linux 不支持同框混选文件+文件夹，故由调用方按 directory 拆成两次调用
  openDialog: (opts) => ipcRenderer.invoke('dialog:open', opts || {}),
  // 拖拽文件拿真实绝对路径（替代 Tauri 的 file.path）。File 对象由渲染进程拖拽事件提供
  getPathForFile: (file) => webUtils.getPathForFile(file),

  // ===== 独立预览窗口 =====
  openPreviewWindow: (url, title, type) => ipcRenderer.invoke('preview:open-file', { url, title, type }),

  // ===== 窗口控制（主窗口/预览窗口共用，手绘风格按钮调用）=====
  winMinimize: () => ipcRenderer.invoke('win:minimize'),
  winToggleMaximize: () => ipcRenderer.invoke('win:toggle-maximize'),
  winClose: () => ipcRenderer.invoke('win:close'),

  // ===== 内置浏览器（多 Tab WebContentsView）=====
  // 新建一个浏览器 Tab，加载 url，返回 tabId
  browserNewTab: (url) => ipcRenderer.invoke('browser:new-tab', url),
  // 关闭指定 Tab
  browserCloseTab: (tabId) => ipcRenderer.invoke('browser:close-tab', tabId),
  // 切换到指定 Tab（显示其 view，隐藏其余）
  browserSwitchTab: (tabId) => ipcRenderer.invoke('browser:switch-tab', tabId),
  // 指定 Tab 导航到 url
  browserNavigate: (tabId, url) => ipcRenderer.invoke('browser:navigate', { tabId, url }),
  // 跨域元素定位：在指定 Tab 的所有 frame（含跨域 iframe）里 elementFromPoint(x,y)
  browserLocate: (tabId, x, y) => ipcRenderer.invoke('browser:locate', { tabId, x, y }),
  // 同步内置浏览器容器的 bounds（相对主窗口内容区的 CSS 像素坐标），主进程据此摆放活跃 view
  browserSetBounds: (x, y, w, h, scale) => ipcRenderer.invoke('browser:set-bounds', { x, y, w, h, scale }),
  // 隐藏内置浏览器（面板卸载时调用，把原生 view 移到屏外，避免盖住 React 工作区）
  browserHide: () => ipcRenderer.invoke('browser:hide'),
  // 进入选取模式：主进程截取当前 view 实时图返回 dataURL，并把 view 移到屏外（避免原生层盖住前端 overlay）
  browserPickStart: (tabId) => ipcRenderer.invoke('browser:pick-start', tabId),
  // 退出选取模式：把 view 移回容器 bounds 恢复显示
  browserPickEnd: (tabId) => ipcRenderer.invoke('browser:pick-end', tabId),
  // 监听主进程推送的 Tab 事件（导航完成/标题更新等）
  onTabEvent: (callback) => {
    const handler = (_e, payload) => callback(payload);
    ipcRenderer.on('browser:tab-event', handler);
    return () => ipcRenderer.removeListener('browser:tab-event', handler);
  },
});

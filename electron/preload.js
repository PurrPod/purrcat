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

  // ===== IDEPanel File Operations =====
  // 读目录：返回 { name, isDir, path }[]
  readDir: (dirPath) => ipcRenderer.invoke('fs:readDir', dirPath),
  // 读文件：返回文本内容
  readFile: (filePath) => ipcRenderer.invoke('fs:readFile', filePath),
  // 文件元信息（大小），IDE 大文件拦截用
  statFile: (filePath) => ipcRenderer.invoke('fs:stat', filePath),
  // 写文件：content 为文本，自动创建父目录
  writeFile: (filePath, content) => ipcRenderer.invoke('fs:writeFile', filePath, content),

  // ===== IDE 独立窗口 =====
  ideDetach: (workspacePath) => ipcRenderer.invoke('ide:detach', workspacePath),
  ideReattach: () => ipcRenderer.invoke('ide:reattach'),
  onIdeReattached: (callback) => {
    const handler = () => callback();
    ipcRenderer.on('ide:reattached', handler);
    return () => ipcRenderer.removeListener('ide:reattached', handler);
  },

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
  // 独立窗口模式：把浏览器 view 移到独立 BrowserWindow
  browserDetach: () => ipcRenderer.invoke('browser:detach'),
  // 回归主窗口：把浏览器 view 移回主窗口
  browserReattach: () => ipcRenderer.invoke('browser:reattach'),
  // 监听主进程推送的"已回归"事件（独立窗口被关闭时触发）
  onBrowserReattached: (callback) => {
    const handler = () => callback();
    ipcRenderer.on('browser:reattached', handler);
    return () => ipcRenderer.removeListener('browser:reattached', handler);
  },
  // 进入选取模式：主进程截取当前 view 实时图返回 dataURL，并把 view 移到屏外（避免原生层盖住前端 overlay）
  browserPickStart: (tabId) => ipcRenderer.invoke('browser:pick-start', tabId),
  // 退出选取模式：把 view 移回容器 bounds 恢复显示
  browserPickEnd: (tabId) => ipcRenderer.invoke('browser:pick-end', tabId),
  // CDP 元素拾取：返回完整语义信息（outerHTML/innerText/attributes/cssSelector/rect）
  browserCdpPickElement: (tabId, x, y) => ipcRenderer.invoke('browser:cdp-pick-element', { tabId, x, y }),
  // CDP Overlay 原生高亮（类似 F12 蓝色框，零坐标偏差）
  browserCdpHighlight: (tabId, x, y) => ipcRenderer.invoke('browser:cdp-highlight', { tabId, x, y }),
  // 清除 CDP Overlay 高亮
  browserCdpUnhighlight: (tabId) => ipcRenderer.invoke('browser:cdp-unhighlight', { tabId }),
  // 独立窗口拾取的 comment 发回主窗口
  browserDetachedComment: (pixelData, comment, url) => ipcRenderer.invoke('browser:detached-comment', { pixelData, comment, url }),
  // 监听主进程转发的独立窗口拾取 comment
  onBrowserComment: (callback) => {
    const handler = (_e, payload) => callback(payload);
    ipcRenderer.on('browser:comment', handler);
    return () => ipcRenderer.removeListener('browser:comment', handler);
  },
  // CDP Inspect 模式（F12 式元素拾取器）：Chromium 自动 hover 高亮 + click 选中
  browserCdpInspectStart: (tabId) => ipcRenderer.invoke('browser:cdp-inspect-start', { tabId }),
  browserCdpInspectResume: (tabId) => ipcRenderer.invoke('browser:cdp-inspect-resume', { tabId }),
  browserCdpInspectStop: (tabId) => ipcRenderer.invoke('browser:cdp-inspect-stop', { tabId }),
  // 监听 CDP inspect 选中的元素（主进程提取完语义后推送）
  onPickElementSelected: (callback) => {
    const handler = (_e, payload) => callback(payload);
    ipcRenderer.on('pick:element-selected', handler);
    return () => ipcRenderer.removeListener('pick:element-selected', handler);
  },
  // 独立窗口：调整 view 底部留白（为评论框腾出空间）
  browserDetachResizeView: (bottomPx) => ipcRenderer.invoke('browser:detach-resize-view', bottomPx),
  // 监听主进程推送的 Tab 事件（导航完成/标题更新等）
  onTabEvent: (callback) => {
    const handler = (_e, payload) => callback(payload);
    ipcRenderer.on('browser:tab-event', handler);
    return () => ipcRenderer.removeListener('browser:tab-event', handler);
  },
});

/* ============================================================
   桌宠插件 · 后端（Node 子进程）
   - 走 stdio 单行 JSON 协议（见 src/server/api/plugin_runtime.py）
   - 依赖由本插件目录自己的 package.json / node_modules 管理，
     主程序（Python/PyInstaller）不接触这些依赖。
   - handlers: list_apps / launch_app / ping
   ============================================================ */
'use strict';
const readline = require('readline');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

/* ---- 简易运行时：按行读取 stdin，解析请求并回写结果 ---- */
const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });

function reply(id, ok, result, error) {
  const msg = { id, ok };
  if (ok) msg.result = result;
  else msg.error = error || 'unknown error';
  process.stdout.write(JSON.stringify(msg) + '\n');
}

/* ---- handlers ---- */

/** 枚举开始菜单 / 桌面上的快捷方式，作为"本地应用"列表的近似来源（Windows）。 */
function listApps(payload) {
  const dirs = [];
  if (process.platform === 'win32') {
    const common = process.env.ProgramData
      ? path.join(process.env.ProgramData, 'Microsoft', 'Windows', 'Start Menu', 'Programs')
      : '';
    const user = process.env.APPDATA
      ? path.join(process.env.APPDATA, 'Microsoft', 'Windows', 'Start Menu', 'Programs')
      : '';
    const desktop = process.env.USERPROFILE
      ? path.join(process.env.USERPROFILE, 'Desktop')
      : '';
    if (common) dirs.push(common);
    if (user) dirs.push(user);
    if (desktop) dirs.push(desktop);
  } else {
    dirs.push('/Applications', '/usr/share/applications', path.join(process.env.HOME || '', '.local', 'share', 'applications'));
  }
  const seen = new Set();
  const results = [];
  const scan = (dir, depth) => {
    if (depth > 2) return;
    if (!fs.existsSync(dir)) return;
    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
    catch (_) { return; }
    for (const e of entries) {
      const full = path.join(dir, e.name);
      if (e.isDirectory()) scan(full, depth + 1);
      else if (/\.(lnk|url)$/i.test(e.name) || (process.platform !== 'win32' && /\.desktop$/.test(e.name))) {
        const name = path.basename(e.name).replace(/\.(lnk|url|desktop)$/i, '');
        const key = name.toLowerCase();
        if (!seen.has(key)) { seen.add(key); results.push({ name, path: full }); }
      }
    }
  };
  dirs.forEach((d) => scan(d, 0));
  const limit = Number(payload && payload.limit) || 50;
  results.sort((a, b) => a.name.localeCompare(b.name, 'zh'));
  return { count: results.length, apps: results.slice(0, limit) };
}

/** 启动一个本地应用（用 start/OPEN 交由系统关联打开，非阻塞）。 */
function launchApp(payload) {
  const target = (payload && payload.path) || '';
  if (!target) return { started: false, error: '缺少目标路径' };
  try {
    if (process.platform === 'win32') {
      // 用 cmd start 可正确打开 .lnk / .url / 任意关联文件
      const child = spawn('cmd', ['/c', 'start', '', `"${target}"`], { detached: true, stdio: 'ignore' });
      child.unref();
    } else {
      const child = spawn('open', [target], { detached: true, stdio: 'ignore' });
      child.unref();
    }
    return { started: true };
  } catch (e) {
    return { started: false, error: String(e && e.message || e) };
  }
}

function ping() { return { pong: true, pid: process.pid }; }

const handlers = { list_apps: listApps, launch_app: launchApp, ping };

rl.on('line', (line) => {
  line = line.trim();
  if (!line) return;
  let req;
  try { req = JSON.parse(line); } catch (_) { return; }
  const { id, handler, payload } = req;
  const fn = handlers[handler];
  if (!fn) { reply(id, false, null, `未实现的 handler: ${handler}`); return; }
  try {
    const result = fn(payload || {});
    reply(id, true, result);
  } catch (e) {
    reply(id, false, null, String(e && e.message || e));
  }
});

// 就绪信号：宿主等这一行后才认定进程 online
process.stdout.write(JSON.stringify({ event: 'ready', pid: process.pid }) + '\n');
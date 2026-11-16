import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { findAvailablePort } from '../electron/api-port.cjs';

const children = new Set();
const isWindows = process.platform === 'win32';
const npxCommand = isWindows ? 'npx.cmd' : 'npx';
const uvCommand = isWindows ? 'uv.exe' : 'uv';
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const electronBinary = path.join(
  projectRoot,
  'node_modules',
  'electron',
  'dist',
  isWindows ? 'electron.exe' : 'electron',
);

function requestedPortFromArgs() {
  const index = process.argv.findIndex((value) => value === '--api-port');
  if (index !== -1) {
    const value = process.argv[index + 1];
    return !value || value.startsWith('--') ? '__missing__' : value;
  }
  const inline = process.argv.find((value) => value.startsWith('--api-port='));
  if (inline) return inline.slice('--api-port='.length) || '__missing__';
  return process.env.PURRCAT_API_PORT;
}

function spawnChild(command, args, env, options = {}) {
  const child = spawn(command, args, {
    env,
    stdio: 'inherit',
    windowsHide: true,
    // Windows 的 npm/npx 是 .cmd 脚本：Node ≥18.20/20.12 修复 CVE-2024-27980 后，
    // 不带 shell 直接 spawn .cmd/.bat 会同步抛 EINVAL，必须经 shell 调起
    shell: command.endsWith('.cmd'),
    ...options,
  });
  children.add(child);
  child.once('exit', () => children.delete(child));
  return child;
}

function waitForPort(port, child, label, timeoutMs = 60_000, host = '127.0.0.1') {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    let timer;
    let settled = false;
    const finish = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      child.removeListener('exit', onExit);
      child.removeListener('error', onError);
      if (error) reject(error); else resolve();
    };
    const onExit = (code, signal) => finish(
      new Error(`${label} exited before port ${port} was ready (code=${code}, signal=${signal || 'none'})`),
    );
    const onError = (error) => finish(new Error(`${label} failed to start: ${error.message}`));
    child.once('exit', onExit);
    child.once('error', onError);

    const probe = () => {
      if (Date.now() - started >= timeoutMs) {
        finish(new Error(`${label} did not open port ${port} within ${timeoutMs / 1000}s`));
        return;
      }
      const socket = net.createConnection({ host, port });
      socket.once('connect', () => {
        socket.destroy();
        finish();
      });
      socket.once('error', () => {
        socket.destroy();
        timer = setTimeout(probe, 100);
      });
    };
    probe();
  });
}

function stopChild(child) {
  if (!child || child.exitCode !== null || child.killed) return;
  try {
    if (isWindows) {
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], {
        stdio: 'ignore',
        windowsHide: true,
      });
    } else {
      child.kill('SIGTERM');
    }
  } catch (_) {
    // The process may have exited between the state check and the cleanup call.
  }
}

function spawnElectron(env) {
  // 直接调 electron 可执行文件：npx 在 Windows 上要额外拉起 cmd 解析包，多耗约 1s
  if (fs.existsSync(electronBinary)) {
    // 🌟 必须 windowsHide:false：直接子进程带 SW_HIDE 启动标记时，Electron 的
    // 首个窗口会继承隐藏状态——进程在跑、页面也加载了，但屏幕上始终不出现窗口
    return spawnChild(electronBinary, ['.'], env, { windowsHide: false });
  }
  return spawnChild(npxCommand, ['--no-install', 'electron', '.'], env);
}

async function main() {
  const apiPort = await findAvailablePort(requestedPortFromArgs());
  const childEnv = {
    ...process.env,
    PURRCAT_API_PORT: String(apiPort),
  };

  console.log(`[PurrCat] API port selected: ${apiPort}`);
  const backend = spawnChild(
    uvCommand,
    ['run', 'python', 'main.py', '--api', '--headless', '--api-port', String(apiPort)],
    childEnv,
  );

  // 🌟 Electron 与后端并行启动：壳先出来（about:blank 用主题底色），
  // 主进程自己轮询 /api/health 通过后才加载界面。串行等待会让窗口出现时间
  // 完全等于后端导入 + uvicorn 绑定耗时（实测多等 5-6s）。
  const electron = spawnElectron({ ...childEnv, ELECTRON_DEV: '1' });

  const electronExit = new Promise((resolve, reject) => {
    electron.once('error', reject);
    electron.once('exit', (exitCode, exitSignal) => resolve([exitCode, exitSignal]));
  });
  const backendReady = waitForPort(apiPort, backend, 'Python backend')
    .then(() => console.log('[PurrCat] Python backend ready'))
    .catch((error) => {
      // 后端起不来时不要留一个永远等 health 的壳
      console.error(`[PurrCat] ${error.message}`);
      stopChild(electron);
      throw error;
    });

  const [[code, signal]] = await Promise.all([electronExit, backendReady]);
  return signal ? 1 : (code ?? 1);
}

let stopping = false;
async function stopAll(exitCode) {
  if (stopping) return;
  stopping = true;
  for (const child of children) stopChild(child);
  process.exitCode = exitCode;
}

process.once('SIGINT', () => { void stopAll(130); });
process.once('SIGTERM', () => { void stopAll(143); });

try {
  const exitCode = await main();
  await stopAll(exitCode);
} catch (error) {
  console.error(`[PurrCat] Development startup failed: ${error.message}`);
  await stopAll(1);
}

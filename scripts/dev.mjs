import { spawn } from 'node:child_process';
import net from 'node:net';

import { findAvailablePort } from '../electron/api-port.cjs';

const children = new Set();
const isWindows = process.platform === 'win32';
const npmCommand = isWindows ? 'npm.cmd' : 'npm';
const npxCommand = isWindows ? 'npx.cmd' : 'npx';
const uvCommand = isWindows ? 'uv.exe' : 'uv';

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

function spawnChild(command, args, env) {
  const child = spawn(command, args, {
    env,
    stdio: 'inherit',
    windowsHide: true,
  });
  children.add(child);
  child.once('exit', () => children.delete(child));
  return child;
}

function waitForPort(port, child, label, timeoutMs = 60_000) {
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
      const socket = net.createConnection({ host: '127.0.0.1', port });
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
  const vite = spawnChild(npmCommand, ['run', 'dev', '--prefix', 'ui'], childEnv);

  await Promise.all([
    waitForPort(apiPort, backend, 'Python backend'),
    waitForPort(3000, vite, 'Vite dev server'),
  ]);

  const electron = spawnChild(
    npxCommand,
    ['--no-install', 'electron', '.'],
    { ...childEnv, ELECTRON_DEV: '1' },
  );
  const [code, signal] = await new Promise((resolve, reject) => {
    electron.once('error', reject);
    electron.once('exit', (exitCode, exitSignal) => resolve([exitCode, exitSignal]));
  });
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

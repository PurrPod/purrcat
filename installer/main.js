// PurrCat 安装器主进程：窗口、路径校验、流式安装、模型配置与快捷方式
const { app, BrowserWindow, Menu, dialog, ipcMain, shell, net } = require('electron');
const path = require('path');
const fs = require('fs');
const fsp = fs.promises;
const os = require('os');
const { spawn } = require('child_process');

const REQUIRED_BYTES = 500 * 1024 * 1024;
const SETTINGS_FILE = path.join(os.homedir(), '.purrcat', 'settings.json');
const DEFAULT_DATA_ROOT_NAME = 'purrcat_data';

let mainWindow = null;
let installProcess = null;
let installCancelled = false;
let stdoutBuffer = '';
let stderrBuffer = '';

app.setAppUserModelId('com.purrpod.purrcat.installer');

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 760,
    height: 560,
    minWidth: 700,
    minHeight: 480,
    frame: false,
    resizable: true,
    maximizable: false,
    backgroundColor: '#fdfdfd',
    title: 'PurrCat Setup',
    icon: path.join(__dirname, 'assets', 'app.ico'),
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      spellcheck: false,
    },
  });

  Menu.setApplicationMenu(null);
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
  mainWindow.on('close', () => stopInstall());
}

function sendEvent(payload) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('installer:event', payload);
  }
}

function stripAnsi(text) {
  return text.replace(/\u001b\[[0-9;]*[A-Za-z]/g, '');
}

function normalizeInputPath(input) {
  if (typeof input !== 'string') return '';
  let value = input.trim();
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    value = value.slice(1, -1).trim();
  }
  return value;
}

function findExistingAncestor(target) {
  let current = target;
  for (let i = 0; i < 20; i += 1) {
    if (fs.existsSync(current)) return current;
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return null;
}

function validatePath(input) {
  const raw = normalizeInputPath(input);
  if (!raw) return { ok: false, errorCode: 'empty' };
  if (!path.isAbsolute(raw)) return { ok: false, errorCode: 'notAbsolute' };

  const target = path.resolve(raw);
  const parsed = path.parse(target);
  if (parsed.root.toLowerCase() === target.toLowerCase()) {
    return { ok: false, errorCode: 'fsRoot' };
  }

  let stat = null;
  try {
    stat = fs.statSync(target);
  } catch (error) {
    if (error.code !== 'ENOENT') return { ok: false, errorCode: 'inspectFailed' };
  }

  let existingInstall = false;

  if (stat) {
    if (!stat.isDirectory()) return { ok: false, errorCode: 'notDir' };
    let entries = [];
    try {
      entries = fs.readdirSync(target);
    } catch (error) {
      return { ok: false, errorCode: 'inspectFailed' };
    }
    existingInstall = fs.existsSync(path.join(target, '.git'));
    if (entries.length > 0 && !existingInstall) {
      return { ok: false, errorCode: 'dirNotEmpty' };
    }
    try {
      fs.accessSync(target, fs.constants.W_OK);
    } catch (error) {
      return { ok: false, errorCode: 'notWritable' };
    }
  } else {
    const parent = findExistingAncestor(path.dirname(target));
    if (!parent) return { ok: false, errorCode: 'parentMissing' };
    try {
      fs.accessSync(parent, fs.constants.W_OK);
    } catch (error) {
      return { ok: false, errorCode: 'parentNotWritable' };
    }
  }

  return { ok: true, path: target, existingInstall };
}

async function getDiskSpace(input) {
  const validation = validatePath(input);
  const base = validation.ok
    ? findExistingAncestor(validation.path)
    : findExistingAncestor(path.dirname(path.resolve(normalizeInputPath(input) || '.')));

  if (!base) {
    return { required: REQUIRED_BYTES, available: REQUIRED_BYTES, sufficient: true };
  }

  try {
    const stats = await fsp.statfs(base);
    const available = Number(stats.bsize) * Number(stats.bavail);
    return {
      required: REQUIRED_BYTES,
      available,
      sufficient: available >= REQUIRED_BYTES,
    };
  } catch (error) {
    return { required: REQUIRED_BYTES, available: 0, sufficient: false };
  }
}

function readExistingModel() {
  try {
    const file = path.join(os.homedir(), '.purrcat', 'model.json');
    const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    const main = data && data.main ? data.main : {};
    const key = Object.keys(main)[0];
    if (!key) return null;
    const entry = main[key] || {};
    return {
      key,
      model: key.includes(':') ? key.split(':').slice(1).join(':') : key,
      baseUrl: entry.base_url || '',
      apiKey: (entry.api_keys && entry.api_keys[0]) || entry.api_key || '',
    };
  } catch (error) {
    return null;
  }
}

function readExistingSettings() {
  try {
    const data = JSON.parse(fs.readFileSync(SETTINGS_FILE, 'utf8'));
    return data && typeof data === 'object' && !Array.isArray(data) ? data : {};
  } catch (error) {
    return {};
  }
}

function validateDataRoot(input) {
  const raw = normalizeInputPath(input);
  if (!raw) return { ok: false, errorCode: 'empty' };
  if (!path.isAbsolute(raw)) return { ok: false, errorCode: 'notAbsolute' };

  const target = path.resolve(raw);
  const parsed = path.parse(target);
  if (parsed.root.toLowerCase() === target.toLowerCase()) {
    return { ok: false, errorCode: 'fsRoot' };
  }

  let stat = null;
  try {
    stat = fs.statSync(target);
  } catch (error) {
    if (error.code !== 'ENOENT') return { ok: false, errorCode: 'inspectFailed' };
  }

  if (stat) {
    if (!stat.isDirectory()) return { ok: false, errorCode: 'notDir' };
    try {
      fs.accessSync(target, fs.constants.W_OK);
    } catch (error) {
      return { ok: false, errorCode: 'notWritable' };
    }
  } else {
    const parent = findExistingAncestor(path.dirname(target));
    if (!parent) return { ok: false, errorCode: 'parentMissing' };
    try {
      fs.accessSync(parent, fs.constants.W_OK);
    } catch (error) {
      return { ok: false, errorCode: 'parentNotWritable' };
    }
  }

  return { ok: true, path: target };
}

async function saveDataRoot(target) {
  await fsp.mkdir(path.dirname(SETTINGS_FILE), { recursive: true });
  const settings = readExistingSettings();
  settings.data_root = target;
  await fsp.writeFile(SETTINGS_FILE, JSON.stringify(settings, null, 4), 'utf8');
  await fsp.mkdir(target, { recursive: true });
}

function resolveInstallScript() {
  const candidates = [
    path.join(process.resourcesPath || '', 'install.ps1'),
    path.join(__dirname, '..', 'install.ps1'),
    path.join(process.cwd(), 'install.ps1'),
  ];
  return candidates.find((file) => fs.existsSync(file)) || null;
}

function resolveAppIcon() {
  const candidates = [
    path.join(process.resourcesPath || '', 'app.ico'),
    path.join(__dirname, 'assets', 'app.ico'),
    path.join(__dirname, '..', 'electron', 'app.ico'),
  ];
  return candidates.find((file) => fs.existsSync(file)) || '';
}

const STAGE_RULES = [
  { key: 'done', percent: 100, re: /PurrCat installed successfully/i },
  { key: 'register', percent: 90, re: /PurrCat CLI launcher|Added .* to (user )?PATH|Register/i },
  { key: 'docker', percent: 76, re: /Docker/i },
  { key: 'embedding', percent: 64, re: /embedding model/i },
  { key: 'node', percent: 48, re: /Installing desktop dependencies|npm install/i },
  { key: 'python', percent: 24, re: /Syncing Python dependencies|uv sync/i },
  { key: 'source', percent: 14, re: /Cloning PurrCat|Existing source|git pull/i },
  {
    key: 'dependencies',
    percent: 6,
    re: /Installing git|Installing uv|Installing Node|git detected|uv detected|Node\.js detected/i,
  },
];

function handleInstallLine(line, source) {
  const text = stripAnsi(line).trim();
  if (!text) return;

  if (source === 'stderr') {
    stderrBuffer += `${text}\n`;
    if (stderrBuffer.length > 8000) stderrBuffer = stderrBuffer.slice(-8000);
    return;
  }

  stdoutBuffer += `${text}\n`;
  if (stdoutBuffer.length > 16000) stdoutBuffer = stdoutBuffer.slice(-16000);

  for (const rule of STAGE_RULES) {
    if (rule.re.test(text)) {
      sendEvent({ type: 'progress', stage: rule.key, percent: rule.percent });
      break;
    }
  }

  if (ruleError(text)) {
    sendEvent({ type: 'log', line: text });
  }
}

function ruleError(text) {
  return /\[x\]|错误|失败/i.test(text);
}

function readStreamChunk(chunk, source) {
  const text = stripAnsi(chunk.toString('utf8'));
  const parts = text.split(/\r?\n/);
  for (const part of parts) {
    if (part.trim()) handleInstallLine(part, source);
  }
}

function buildFailureMessage(code) {
  const stderrLines = stderrBuffer
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const stdoutLines = stdoutBuffer
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  const candidates = stderrLines.length ? stderrLines : stdoutLines;
  const meaningful =
    candidates.find((line) => /\[x\]|exception|error|failed|失败|无法|不允许/i.test(line)) ||
    candidates[0];

  if (meaningful) return meaningful;
  return `安装脚本退出，代码 ${code}`;
}

function stopInstall() {
  if (!installProcess) return;
  installCancelled = true;
  const pid = installProcess.pid;
  try {
    spawn('taskkill', ['/pid', String(pid), '/T', '/F'], { windowsHide: true });
  } catch (error) {
    // 忽略结束进程失败
  }
  installProcess = null;
}

ipcMain.handle('installer:get-defaults', async () => {
  const settings = readExistingSettings();
  const configuredDataRoot =
    typeof settings.data_root === 'string' && settings.data_root.trim()
      ? settings.data_root.trim()
      : '';
  return {
    version: app.getVersion(),
    defaultPath: path.join(os.homedir(), 'purrcat'),
    defaultDataRoot: configuredDataRoot || path.join(os.homedir(), DEFAULT_DATA_ROOT_NAME),
    dataRootConfigured: !!configuredDataRoot,
    existingModel: readExistingModel(),
    platform: process.platform,
  };
});

ipcMain.handle('installer:choose-directory', async (event, payload) => {
  const fallback = path.join(os.homedir(), 'purrcat');
  const requested =
    payload && typeof payload.defaultPath === 'string' ? payload.defaultPath.trim() : '';
  const initial =
    requested && path.isAbsolute(requested) && fs.existsSync(requested)
      ? requested
      : fs.existsSync(fallback)
        ? fallback
        : os.homedir();

  const result = await dialog.showOpenDialog(mainWindow, {
    title: (payload && payload.title) || 'Select folder',
    buttonLabel: 'Select',
    properties: ['openDirectory', 'createDirectory'],
    defaultPath: initial,
  });
  if (result.canceled || !result.filePaths.length) return null;
  return result.filePaths[0];
});

ipcMain.handle('installer:validate-path', async (event, target) => validatePath(target));

ipcMain.handle('installer:validate-data-root', async (event, target) => validateDataRoot(target));

ipcMain.handle('installer:disk-space', async (event, target) => getDiskSpace(target));

ipcMain.handle('installer:start-install', async (event, payload) => {
  if (installProcess) return { ok: false, errorCode: 'busy' };

  const validation = validatePath(payload && payload.installPath);
  if (!validation.ok) return validation;

  const dataRootValidation = validateDataRoot(payload && payload.dataRoot);
  if (!dataRootValidation.ok) return dataRootValidation;

  const scriptPath = resolveInstallScript();
  if (!scriptPath) return { ok: false, errorCode: 'scriptMissing' };

  // 先把数据目录写入 settings.json，安装脚本才能把向量模型等大文件放到用户选的盘
  try {
    await saveDataRoot(dataRootValidation.path);
  } catch (error) {
    return { ok: false, errorCode: 'dataRootSaveFailed' };
  }

  stdoutBuffer = '';
  stderrBuffer = '';
  installCancelled = false;

  sendEvent({ type: 'progress', stage: 'preparing', percent: 2 });

  const escapedScript = scriptPath.replace(/'/g, "''");
  const command =
    `[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); ` +
    `& '${escapedScript}'; exit $LASTEXITCODE`;

  const env = {
    ...process.env,
    PURRCAT_HOME: validation.path,
    PYTHONIOENCODING: 'utf-8',
    PYTHONUTF8: '1',
  };

  const child = spawn(
    'powershell.exe',
    ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command],
    {
      cwd: fs.existsSync(validation.path) ? validation.path : os.homedir(),
      env,
      windowsHide: true,
    }
  );

  installProcess = child;
  let finished = false;

  child.stdout.on('data', (chunk) => readStreamChunk(chunk, 'stdout'));
  child.stderr.on('data', (chunk) => readStreamChunk(chunk, 'stderr'));

  child.on('error', (error) => {
    if (finished) return;
    finished = true;
    installProcess = null;
    sendEvent({ type: 'error', message: error.message });
  });

  child.on('close', (code) => {
    if (finished) return;
    finished = true;
    installProcess = null;

    if (installCancelled) {
      sendEvent({ type: 'error', errorCode: 'cancelled', message: '' });
      return;
    }

    if (code === 0) {
      sendEvent({ type: 'progress', stage: 'done', percent: 100 });
      sendEvent({
        type: 'done',
        path: validation.path,
        existingInstall: validation.existingInstall,
      });
      return;
    }

    sendEvent({ type: 'error', message: buildFailureMessage(code) });
  });

  return { ok: true, path: validation.path, existingInstall: validation.existingInstall };
});

ipcMain.handle('installer:test-model', async (event, payload) => {
  const apiKey = (payload && payload.apiKey ? String(payload.apiKey) : '').trim();
  const modelRaw = (payload && payload.model ? String(payload.model) : '').trim();
  const baseRaw = (payload && payload.baseUrl ? String(payload.baseUrl) : '').trim();

  if (!apiKey) return { success: false, errorCode: 'missingKey' };
  if (!modelRaw) return { success: false, errorCode: 'missingModel' };
  if (!baseRaw) return { success: false, errorCode: 'missingBaseUrl' };

  let url;
  try {
    const withScheme = /^https?:\/\//i.test(baseRaw) ? baseRaw : `https://${baseRaw}`;
    const parsed = new URL(withScheme);
    let basePath = parsed.pathname.replace(/\/+$/, '');
    if (!/\/chat\/completions$/.test(basePath)) basePath += '/chat/completions';
    parsed.pathname = basePath;
    url = parsed.toString();
  } catch (error) {
    return { success: false, errorCode: 'invalidBaseUrl' };
  }

  const model = modelRaw.includes(':') ? modelRaw.split(':').slice(1).join(':') : modelRaw;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25000);

  try {
    const response = await net.fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
        max_tokens: 8,
        stream: false,
      }),
      signal: controller.signal,
    });

    const text = await response.text();
    if (!response.ok) {
      return {
        success: false,
        message: `HTTP ${response.status}: ${text.slice(0, 220)}`,
      };
    }

    let data = null;
    try {
      data = JSON.parse(text);
    } catch (error) {
      return { success: false, errorCode: 'invalidResponse' };
    }

    if (data && data.error) {
      const message = data.error.message || JSON.stringify(data.error).slice(0, 220);
      return { success: false, message };
    }

    if (!data || !Array.isArray(data.choices) || data.choices.length === 0) {
      return { success: false, errorCode: 'emptyResponse' };
    }

    return { success: true };
  } catch (error) {
    if (error.name === 'AbortError') return { success: false, errorCode: 'timeout' };
    return { success: false, message: error.message };
  } finally {
    clearTimeout(timer);
  }
});

ipcMain.handle('installer:save-model', async (event, payload) => {
  const apiKey = (payload && payload.apiKey ? String(payload.apiKey) : '').trim();
  const modelRaw = (payload && payload.model ? String(payload.model) : '').trim();
  const baseRaw = (payload && payload.baseUrl ? String(payload.baseUrl) : '').trim();

  if (!apiKey || !modelRaw || !baseRaw) return { ok: false, errorCode: 'missing' };

  const model = modelRaw.includes(':') ? modelRaw.split(':').slice(1).join(':') : modelRaw;
  const key = `openai:${model}`;

  try {
    const dir = path.join(os.homedir(), '.purrcat');
    await fsp.mkdir(dir, { recursive: true });
    const file = path.join(dir, 'model.json');

    let existing = {};
    try {
      existing = JSON.parse(await fsp.readFile(file, 'utf8'));
    } catch (error) {
      existing = {};
    }

    const next = {
      ...existing,
      main: {
        [key]: {
          api_keys: [apiKey],
          base_url: baseRaw,
          rpm: 60,
          tpm: 1000000,
          concurrency: 3,
          max_token: 500000,
          vision: false,
        },
      },
      task: existing.task && typeof existing.task === 'object' ? existing.task : {},
      vision: existing.vision && typeof existing.vision === 'object' ? existing.vision : {},
    };

    await fsp.writeFile(file, JSON.stringify(next, null, 2), 'utf8');
    return { ok: true, key };
  } catch (error) {
    return { ok: false, message: error.message };
  }
});

function runPowerShell(command) {
  return new Promise((resolve) => {
    const child = spawn(
      'powershell.exe',
      ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command],
      { windowsHide: true }
    );
    child.on('close', (code) => resolve(code === 0));
    child.on('error', () => resolve(false));
  });
}

function writeDesktopLauncher(cmdPath) {
  const binDir = path.join(os.homedir(), '.local', 'bin');
  fs.mkdirSync(binDir, { recursive: true });
  const vbsPath = path.join(binDir, 'purrcat-desktop.vbs');
  const escaped = cmdPath.replace(/"/g, '""');
  const content =
    'Set sh = CreateObject("WScript.Shell")\r\n' +
    `sh.Run """" & "${escaped}" & """ desktop start", 0, False\r\n`;
  fs.writeFileSync(vbsPath, content, 'utf8');
  return vbsPath;
}

function createShortcut(linkPath, vbsPath, iconPath) {
  fs.mkdirSync(path.dirname(linkPath), { recursive: true });
  const operation = fs.existsSync(linkPath) ? 'update' : 'create';
  return shell.writeShortcutLink(linkPath, operation, {
    target: 'wscript.exe',
    args: `"${vbsPath}"`,
    icon: iconPath,
    iconIndex: 0,
    description: 'PurrCat',
    appUserModelId: 'com.purrpod.purrcat',
  });
}

ipcMain.handle('installer:finalize', async (event, payload) => {
  const installPath = normalizeInputPath(payload && payload.installPath);
  const warnings = [];

  if (installPath) {
    const safePath = installPath.replace(/'/g, "''");
    const envOk = await runPowerShell(
      `[Environment]::SetEnvironmentVariable('PURRCAT_HOME', '${safePath}', 'User')`
    );
    if (!envOk) warnings.push('env');
  }

  const cmdPath = path.join(os.homedir(), '.local', 'bin', 'purrcat.cmd');
  let vbsPath = null;
  const iconPath = resolveAppIcon();

  if (fs.existsSync(cmdPath)) {
    try {
      vbsPath = writeDesktopLauncher(cmdPath);
    } catch (error) {
      warnings.push('launcher');
    }
  } else {
    warnings.push('command');
  }

  if (vbsPath && payload && payload.desktopShortcut) {
    try {
      const desktopLink = path.join(app.getPath('desktop'), 'PurrCat.lnk');
      if (!createShortcut(desktopLink, vbsPath, iconPath)) warnings.push('desktopShortcut');
    } catch (error) {
      warnings.push('desktopShortcut');
    }
  }

  if (vbsPath && payload && payload.startMenu) {
    try {
      const startMenuLink = path.join(
        app.getPath('appData'),
        'Microsoft',
        'Windows',
        'Start Menu',
        'Programs',
        'PurrCat',
        'PurrCat.lnk'
      );
      if (!createShortcut(startMenuLink, vbsPath, iconPath)) warnings.push('startMenuShortcut');
    } catch (error) {
      warnings.push('startMenuShortcut');
    }
  }

  if (vbsPath && payload && payload.launch) {
    try {
      const child = spawn('wscript.exe', [vbsPath], {
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
      });
      child.unref();
    } catch (error) {
      warnings.push('launch');
    }
  }

  return { ok: true, warnings };
});

ipcMain.handle('installer:open-path', async (event, target) => {
  const normalized = normalizeInputPath(target);
  if (!normalized) return { ok: false };
  const error = await shell.openPath(normalized);
  return { ok: !error, message: error || '' };
});

ipcMain.on('installer:minimize', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on('installer:close', () => {
  stopInstall();
  if (mainWindow) mainWindow.close();
});

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  stopInstall();
  app.quit();
});

app.on('before-quit', () => stopInstall());

(function () {
  'use strict';

  const I18N = {
    zh: {
      productName: 'PurrCat 安装程序',
      'welcome.version': '版本 {{version}}',
      'window.toggleTheme': '切换外观',
      'window.minimize': '最小化',
      'window.close': '关闭',
      'steps.language': '语言',
      'steps.install': '安装',
      'steps.model': '模型',
      'steps.complete': '完成',
      'language.title': '选择语言',
      'language.description': '选择安装过程与首次启动时使用的语言。',
      'language.continue': '继续',
      'options.title': '安装 PurrCat',
      'options.pathLabel': '安装位置',
      'options.dataRootLabel': '数据目录',
      'options.dataRootHint': '存放向量模型、Agent 虚拟机等大型数据，建议选择空间充足的磁盘。',
      'options.pathTitle': '选择安装位置',
      'options.dataRootTitle': '选择数据目录',
      'options.browse': '浏览',
      'options.existingUpdate': '检测到此处已有 PurrCat，安装将在原位置更新。',
      'options.required': '所需空间',
      'options.available': '可用空间',
      'options.insufficientSpace': '磁盘空间不足',
      'options.optionsLabel': '安装选项',
      'options.desktopShortcut': '创建桌面快捷方式',
      'options.startMenu': '添加到开始菜单',
      'options.changeLanguage': '切换语言',
      'options.install': '安装',
      'options.installing': '正在安装',
      'progress.title': '正在安装 PurrCat',
      'progress.description': '安装可能需要一些时间，请保持窗口打开。',
      'progress.completed': '安装完成',
      'progress.completedDescription': 'PurrCat 已准备就绪，可以开始使用了。',
      'progress.failed': '安装失败',
      'progress.preparing': '准备安装',
      'progress.dependencies': '检查依赖',
      'progress.source': '获取源码',
      'progress.python': '安装 Python 依赖',
      'progress.node': '安装桌面端依赖',
      'progress.embedding': '准备向量模型',
      'progress.docker': '配置 Docker',
      'progress.register': '注册命令行工具',
      'progress.done': '完成',
      'progress.starting': '正在启动',
      'progress.backOptions': '安装选项',
      'progress.retry': '重试',
      'progress.continue': '继续设置',
      'model.title': '连接模型',
      'model.description': '填入 OpenAI 兼容接口的 API Key，也可以在安装后随时修改。',
      'model.providerLabel': '服务商',
      'model.customProvider': '自定义服务商',
      'model.apiKeyLabel': 'API Key',
      'model.show': '显示',
      'model.hide': '隐藏',
      'model.apiKeyPlaceholder': 'sk-...',
      'model.modelLabel': '模型',
      'model.customModel': '自定义模型…',
      'model.customModelPlaceholder': '输入模型名称',
      'model.advanced': '高级设置',
      'model.baseUrlLabel': '接口地址',
      'model.baseUrlPlaceholder': 'https://api.example.com/v1',
      'model.baseUrlHint': '仅支持 OpenAI 兼容接口。',
      'model.test': '测试连接',
      'model.testing': '正在测试…',
      'model.testSuccess': '连接成功',
      'model.testFailed': '连接失败',
      'model.skip': '稍后配置',
      'model.next': '完成设置',
      'model.customProviderHint': '填写服务商提供的 OpenAI 兼容接口地址。',
      'finish.title': 'PurrCat 已准备就绪',
      'finish.descriptionConfigured': '安装已完成，并且已配置好默认模型。',
      'finish.descriptionSkipped': '安装已完成，可以稍后在设置中配置模型。',
      'finish.location': '安装位置',
      'finish.dataRoot': '数据目录',
      'finish.model': '默认模型',
      'finish.configured': '已配置',
      'finish.skipped': '未配置',
      'finish.launch': '立即启动 PurrCat',
      'finish.openFolder': '打开安装文件夹',
      'finish.complete': '完成',
      'finish.finalizing': '正在完成…',
      'errors.empty': '请输入安装路径',
      'errors.notAbsolute': '请输入完整的绝对路径',
      'errors.fsRoot': '不能直接安装到磁盘根目录',
      'errors.notDir': '该路径不是文件夹',
      'errors.inspectFailed': '无法读取该路径',
      'errors.dirNotEmpty': '该文件夹非空，且不是 PurrCat 安装目录',
      'errors.notWritable': '没有写入该文件夹的权限',
      'errors.parentMissing': '上级目录不存在',
      'errors.parentNotWritable': '没有创建该文件夹的权限',
      'errors.dataRootSaveFailed': '数据目录配置保存失败，请检查写入权限',
      'errors.busy': '已有安装任务正在运行',
      'errors.scriptMissing': '找不到安装脚本 install.ps1',
      'errors.cancelled': '安装已取消',
      'errors.installFailed': '安装未能完成',
      'errors.finalizeFailed': '完成安装时出错',
      'dataRootErrors.empty': '请输入数据目录',
      'dataRootErrors.notAbsolute': '请输入完整的数据目录绝对路径',
      'dataRootErrors.fsRoot': '不能直接使用磁盘根目录',
      'dataRootErrors.notDir': '该路径不是文件夹',
      'dataRootErrors.inspectFailed': '无法读取该路径',
      'dataRootErrors.notWritable': '没有写入该文件夹的权限',
      'dataRootErrors.parentMissing': '上级目录不存在',
      'dataRootErrors.parentNotWritable': '没有创建该文件夹的权限',
      'model.testErrors.missingKey': '请先填写 API Key',
      'model.testErrors.missingModel': '请先选择或填写模型',
      'model.testErrors.missingBaseUrl': '请先填写接口地址',
      'model.testErrors.invalidBaseUrl': '接口地址格式不正确',
      'model.testErrors.invalidResponse': '接口返回内容无法解析',
      'model.testErrors.emptyResponse': '接口没有返回模型输出',
      'model.testErrors.timeout': '连接超时，请检查接口地址与网络',
      'model.testErrors.failed': '连接失败，请检查配置',
      'model.saveErrors.missing': '请填写完整的模型配置',
      'model.saveFailed': '模型配置保存失败',
      'finish.warnings.env': '未能写入 PURRCAT_HOME 环境变量，请手动设置后重启应用。',
      'finish.warnings.launcher': '未能创建启动器，请通过 purrcat desktop start 启动。',
      'finish.warnings.command': '未找到 purrcat 命令，请重新运行安装。',
      'finish.warnings.desktopShortcut': '未能创建桌面快捷方式。',
      'finish.warnings.startMenuShortcut': '未能创建开始菜单快捷方式。',
      'finish.warnings.launch': '未能自动启动 PurrCat，请手动打开。',
    },
    en: {
      productName: 'PurrCat Setup',
      'welcome.version': 'Version {{version}}',
      'window.toggleTheme': 'Toggle appearance',
      'window.minimize': 'Minimize',
      'window.close': 'Close',
      'steps.language': 'Language',
      'steps.install': 'Install',
      'steps.model': 'Model',
      'steps.complete': 'Finish',
      'language.title': 'Choose a language',
      'language.description': 'Select the language used during setup and on first launch.',
      'language.continue': 'Continue',
      'options.title': 'Install PurrCat',
      'options.pathLabel': 'Install location',
      'options.dataRootLabel': 'Data directory',
      'options.dataRootHint': 'Stores large data such as the embedding model and agent VMs. Pick a drive with plenty of free space.',
      'options.pathTitle': 'Select install location',
      'options.dataRootTitle': 'Select data directory',
      'options.browse': 'Browse',
      'options.existingUpdate': 'An existing PurrCat installation was found here. Setup will update it in place.',
      'options.required': 'Required',
      'options.available': 'Available',
      'options.insufficientSpace': 'Not enough disk space',
      'options.optionsLabel': 'Install options',
      'options.desktopShortcut': 'Create a desktop shortcut',
      'options.startMenu': 'Add to Start menu',
      'options.changeLanguage': 'Change language',
      'options.install': 'Install',
      'options.installing': 'Installing',
      'progress.title': 'Installing PurrCat',
      'progress.description': 'This may take a while. Please keep this window open.',
      'progress.completed': 'Installation complete',
      'progress.completedDescription': 'PurrCat is ready to use on your computer.',
      'progress.failed': 'Installation failed',
      'progress.preparing': 'Preparing',
      'progress.dependencies': 'Checking dependencies',
      'progress.source': 'Getting source code',
      'progress.python': 'Installing Python dependencies',
      'progress.node': 'Installing desktop dependencies',
      'progress.embedding': 'Preparing embedding model',
      'progress.docker': 'Setting up Docker',
      'progress.register': 'Registering command line tool',
      'progress.done': 'Finished',
      'progress.starting': 'Starting',
      'progress.backOptions': 'Install options',
      'progress.retry': 'Retry',
      'progress.continue': 'Continue setup',
      'model.title': 'Connect a model',
      'model.description': 'Add an API key for an OpenAI-compatible endpoint. You can change this later in Settings.',
      'model.providerLabel': 'Provider',
      'model.customProvider': 'Custom provider',
      'model.apiKeyLabel': 'API key',
      'model.show': 'Show',
      'model.hide': 'Hide',
      'model.apiKeyPlaceholder': 'sk-...',
      'model.modelLabel': 'Model',
      'model.customModel': 'Custom model…',
      'model.customModelPlaceholder': 'Enter a model name',
      'model.advanced': 'Advanced settings',
      'model.baseUrlLabel': 'Base URL',
      'model.baseUrlPlaceholder': 'https://api.example.com/v1',
      'model.baseUrlHint': 'Only OpenAI-compatible endpoints are supported.',
      'model.test': 'Test connection',
      'model.testing': 'Testing…',
      'model.testSuccess': 'Connected successfully',
      'model.testFailed': 'Connection failed',
      'model.skip': 'Configure later',
      'model.next': 'Finish setup',
      'model.customProviderHint': 'Enter the OpenAI-compatible endpoint provided by your service.',
      'finish.title': 'PurrCat is ready',
      'finish.descriptionConfigured': 'Installation is complete and your default model is configured.',
      'finish.descriptionSkipped': 'Installation is complete. You can configure a model later in Settings.',
      'finish.location': 'Location',
      'finish.dataRoot': 'Data directory',
      'finish.model': 'Default model',
      'finish.configured': 'Configured',
      'finish.skipped': 'Not configured',
      'finish.launch': 'Launch PurrCat now',
      'finish.openFolder': 'Open install folder',
      'finish.complete': 'Finish',
      'finish.finalizing': 'Finishing…',
      'errors.empty': 'Enter an install location',
      'errors.notAbsolute': 'Enter a full absolute path',
      'errors.fsRoot': 'PurrCat cannot be installed at a drive root',
      'errors.notDir': 'That path is not a folder',
      'errors.inspectFailed': 'Unable to read that path',
      'errors.dirNotEmpty': 'The folder is not empty and is not a PurrCat installation',
      'errors.notWritable': 'No permission to write to that folder',
      'errors.parentMissing': 'The parent folder does not exist',
      'errors.parentNotWritable': 'No permission to create that folder',
      'errors.dataRootSaveFailed': 'Could not save the data directory settings. Check write permissions.',
      'errors.busy': 'Another installation is already running',
      'errors.scriptMissing': 'The install script could not be found',
      'errors.cancelled': 'Installation was cancelled',
      'errors.installFailed': 'Installation did not complete',
      'errors.finalizeFailed': 'Something went wrong while finishing setup',
      'dataRootErrors.empty': 'Enter a data directory',
      'dataRootErrors.notAbsolute': 'Enter a full absolute path for the data directory',
      'dataRootErrors.fsRoot': 'A drive root cannot be used as the data directory',
      'dataRootErrors.notDir': 'That path is not a folder',
      'dataRootErrors.inspectFailed': 'Unable to read that path',
      'dataRootErrors.notWritable': 'No permission to write to that folder',
      'dataRootErrors.parentMissing': 'The parent folder does not exist',
      'dataRootErrors.parentNotWritable': 'No permission to create that folder',
      'model.testErrors.missingKey': 'Enter an API key first',
      'model.testErrors.missingModel': 'Choose or enter a model first',
      'model.testErrors.missingBaseUrl': 'Enter a base URL first',
      'model.testErrors.invalidBaseUrl': 'The base URL is not valid',
      'model.testErrors.invalidResponse': 'The endpoint returned an unreadable response',
      'model.testErrors.emptyResponse': 'The endpoint returned no model output',
      'model.testErrors.timeout': 'The connection timed out. Check the URL and network.',
      'model.testErrors.failed': 'Connection failed. Check the configuration.',
      'model.saveErrors.missing': 'Fill in the full model configuration',
      'model.saveFailed': 'Could not save the model configuration',
      'finish.warnings.env': 'Could not set PURRCAT_HOME. Set it manually and restart the app.',
      'finish.warnings.launcher': 'Could not create the launcher. Start the app with purrcat desktop start.',
      'finish.warnings.command': 'The purrcat command was not found. Run the installer again.',
      'finish.warnings.desktopShortcut': 'Could not create the desktop shortcut.',
      'finish.warnings.startMenuShortcut': 'Could not create the Start menu shortcut.',
      'finish.warnings.launch': 'PurrCat could not be launched automatically. Open it manually.',
    },
  };

  const PROVIDERS = [
    {
      id: 'deepseek',
      name: { zh: 'DeepSeek', en: 'DeepSeek' },
      baseUrl: 'https://api.deepseek.com',
      models: ['deepseek-v4-flash', 'deepseek-chat', 'deepseek-reasoner'],
    },
    {
      id: 'zhipu',
      name: { zh: '智谱 AI', en: 'Zhipu AI' },
      baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
      models: ['glm-4.6', 'glm-4.5', 'glm-4-flash'],
    },
    {
      id: 'moonshot',
      name: { zh: '月之暗面', en: 'Moonshot AI' },
      baseUrl: 'https://api.moonshot.cn/v1',
      models: ['kimi-k2', 'moonshot-v1-8k'],
    },
    {
      id: 'qwen',
      name: { zh: '通义千问', en: 'Alibaba Qwen' },
      baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      models: ['qwen3-max', 'qwen-plus', 'qwen-turbo'],
    },
    {
      id: 'siliconflow',
      name: { zh: '硅基流动', en: 'SiliconFlow' },
      baseUrl: 'https://api.siliconflow.cn/v1',
      models: ['deepseek-ai/DeepSeek-V3.2', 'Qwen/Qwen3-8B'],
    },
    {
      id: 'openrouter',
      name: { zh: 'OpenRouter', en: 'OpenRouter' },
      baseUrl: 'https://openrouter.ai/api/v1',
      models: ['deepseek/deepseek-chat', 'anthropic/claude-sonnet-4'],
    },
    {
      id: 'custom',
      name: { zh: '自定义服务商', en: 'Custom provider' },
      baseUrl: '',
      models: [],
    },
  ];

  const state = {
    lang: 'zh',
    step: 'language',
    version: '0.1.0',
    options: {
      installPath: '',
      dataRoot: '',
      desktopShortcut: true,
      startMenu: true,
    },
    validation: null,
    dataRootValidation: null,
    dataRootDisk: null,
    disk: null,
    pathError: '',
    dataRootError: '',
    dataRootTouched: false,
    installing: false,
    installDone: false,
    installError: '',
    progress: { stage: 'preparing', percent: 0 },
    model: {
      providerId: 'deepseek',
      apiKey: '',
      baseUrl: PROVIDERS[0].baseUrl,
      model: PROVIDERS[0].models[0],
      customModel: false,
      showKey: false,
    },
    modelSaved: false,
    savingModel: false,
    modelError: '',
    testStatus: { kind: '', message: '' },
    finishing: false,
    finishError: '',
  };

  const isPreview = typeof window.installerApi !== 'object';
  const api = isPreview ? createPreviewApi() : window.installerApi;

  const dom = {};

  document.addEventListener('DOMContentLoaded', () => {
    collectDom();
    bindEvents();
    registerInstallEvents();
    applyTheme(localStorage.getItem('purrcat-installer-theme') || 'light');
    init();
  });

  function collectDom() {
    dom.pages = Array.from(document.querySelectorAll('[data-page]'));
    dom.stepIndicator = document.getElementById('stepIndicator');
    dom.stepItems = Array.from(document.querySelectorAll('#stepIndicator li'));
    dom.previewBadge = document.getElementById('previewBadge');
    dom.themeToggle = document.getElementById('themeToggle');
    dom.minimizeBtn = document.getElementById('minimizeBtn');
    dom.closeBtn = document.getElementById('closeBtn');
    dom.languageRadios = Array.from(document.querySelectorAll('input[name="language"]'));
    dom.languageContinue = document.getElementById('languageContinue');
    dom.installPath = document.getElementById('installPath');
    dom.browseBtn = document.getElementById('browseBtn');
    dom.pathError = document.getElementById('pathError');
    dom.existingInstallNotice = document.getElementById('existingInstallNotice');
    dom.requiredSpace = document.getElementById('requiredSpace');
    dom.availableSpace = document.getElementById('availableSpace');
    dom.insufficientSpace = document.getElementById('insufficientSpace');
    dom.dataRoot = document.getElementById('dataRoot');
    dom.browseDataBtn = document.getElementById('browseDataBtn');
    dom.dataRootError = document.getElementById('dataRootError');
    dom.dataRootAvailable = document.getElementById('dataRootAvailable');
    dom.dataRootInsufficient = document.getElementById('dataRootInsufficient');
    dom.desktopShortcut = document.getElementById('desktopShortcut');
    dom.startMenu = document.getElementById('startMenu');
    dom.installBtn = document.getElementById('installBtn');
    dom.installError = document.getElementById('installError');
    dom.optionsBack = document.getElementById('optionsBack');
    dom.progressBrand = document.getElementById('progressBrand');
    dom.progressTitle = document.getElementById('progressTitle');
    dom.progressDescription = document.getElementById('progressDescription');
    dom.progressBlock = document.getElementById('progressBlock');
    dom.progressStage = document.getElementById('progressStage');
    dom.progressPercent = document.getElementById('progressPercent');
    dom.progressFill = document.getElementById('progressFill');
    dom.progressError = document.getElementById('progressError');
    dom.progressBack = document.getElementById('progressBack');
    dom.progressRetry = document.getElementById('progressRetry');
    dom.progressContinue = document.getElementById('progressContinue');
    dom.providerSelect = document.getElementById('providerSelect');
    dom.apiKeyInput = document.getElementById('apiKeyInput');
    dom.toggleKeyBtn = document.getElementById('toggleKeyBtn');
    dom.modelSelect = document.getElementById('modelSelect');
    dom.modelSelectWrap = document.getElementById('modelSelectWrap');
    dom.modelCustomInput = document.getElementById('modelCustomInput');
    dom.baseUrlInput = document.getElementById('baseUrlInput');
    dom.advancedDisclosure = document.getElementById('advancedDisclosure');
    dom.testModelBtn = document.getElementById('testModelBtn');
    dom.testStatus = document.getElementById('testStatus');
    dom.modelError = document.getElementById('modelError');
    dom.modelNextBtn = document.getElementById('modelNextBtn');
    dom.skipModelBtn = document.getElementById('skipModelBtn');
    dom.finishPath = document.getElementById('finishPath');
    dom.finishDataRoot = document.getElementById('finishDataRoot');
    dom.finishModel = document.getElementById('finishModel');
    dom.finishDescription = document.getElementById('finishDescription');
    dom.finishError = document.getElementById('finishError');
    dom.launchAfterInstall = document.getElementById('launchAfterInstall');
    dom.openFolderBtn = document.getElementById('openFolderBtn');
    dom.finishBtn = document.getElementById('finishBtn');
  }

  function bindEvents() {
    if (!isPreview) dom.previewBadge.hidden = true;
    dom.themeToggle.addEventListener('click', () => {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      localStorage.setItem('purrcat-installer-theme', next);
    });
    dom.minimizeBtn.addEventListener('click', () => api.minimize());
    dom.closeBtn.addEventListener('click', () => api.close());

    dom.languageRadios.forEach((radio) => {
      radio.addEventListener('change', () => {
        if (!radio.checked) return;
        state.lang = radio.value;
        document.documentElement.lang = state.lang === 'zh' ? 'zh-CN' : 'en';
        refreshI18n();
      });
    });
    dom.languageContinue.addEventListener('click', () => showStep('options'));

    dom.installPath.addEventListener('input', () => {
      state.options.installPath = dom.installPath.value;
      state.validation = null;
      updateOptionsControls();
      schedulePathCheck();
    });
    dom.browseBtn.addEventListener('click', async () => {
      const selected = await api.chooseDirectory({
        defaultPath: state.options.installPath,
        title: t('options.pathTitle'),
      });
      if (!selected) return;
      state.options.installPath = selected;
      dom.installPath.value = selected;
      if (!state.dataRootTouched) {
        state.options.dataRoot = `${selected}_data`;
        dom.dataRoot.value = state.options.dataRoot;
      }
      await Promise.all([refreshPathInfo(), refreshDataRootInfo()]);
    });
    dom.dataRoot.addEventListener('input', () => {
      state.options.dataRoot = dom.dataRoot.value;
      state.dataRootTouched = true;
      state.dataRootValidation = null;
      updateOptionsControls();
      scheduleDataRootCheck();
    });
    dom.browseDataBtn.addEventListener('click', async () => {
      const selected = await api.chooseDirectory({
        defaultPath: state.options.dataRoot || state.options.installPath,
        title: t('options.dataRootTitle'),
      });
      if (!selected) return;
      state.options.dataRoot = selected;
      state.dataRootTouched = true;
      dom.dataRoot.value = selected;
      await refreshDataRootInfo();
    });
    dom.desktopShortcut.addEventListener('change', () => {
      state.options.desktopShortcut = dom.desktopShortcut.checked;
    });
    dom.startMenu.addEventListener('change', () => {
      state.options.startMenu = dom.startMenu.checked;
    });
    dom.installBtn.addEventListener('click', handleInstall);
    dom.optionsBack.addEventListener('click', () => showStep('language'));

    dom.progressRetry.addEventListener('click', handleInstall);
    dom.progressBack.addEventListener('click', () => showStep('options'));
    dom.progressContinue.addEventListener('click', () => showStep('model'));

    dom.providerSelect.addEventListener('change', handleProviderChange);
    dom.apiKeyInput.addEventListener('input', () => {
      state.model.apiKey = dom.apiKeyInput.value;
      resetTestStatus();
      syncModelControls();
    });
    dom.toggleKeyBtn.addEventListener('click', () => {
      state.model.showKey = !state.model.showKey;
      dom.apiKeyInput.type = state.model.showKey ? 'text' : 'password';
      dom.toggleKeyBtn.textContent = t(state.model.showKey ? 'model.hide' : 'model.show');
    });
    dom.modelSelect.addEventListener('change', handleModelSelectChange);
    dom.modelCustomInput.addEventListener('input', () => {
      state.model.model = dom.modelCustomInput.value;
      resetTestStatus();
      syncModelControls();
    });
    dom.baseUrlInput.addEventListener('input', () => {
      state.model.baseUrl = dom.baseUrlInput.value;
      resetTestStatus();
      syncModelControls();
    });
    dom.testModelBtn.addEventListener('click', handleTestConnection);
    dom.modelNextBtn.addEventListener('click', handleModelNext);
    dom.skipModelBtn.addEventListener('click', () => {
      state.modelSaved = false;
      showStep('finish');
    });
    dom.launchAfterInstall.addEventListener('change', () => {
      // 仅记录选中状态，完成时读取
    });
    dom.openFolderBtn.addEventListener('click', () => api.openPath(state.options.installPath));
    dom.finishBtn.addEventListener('click', handleFinish);
  }

  function registerInstallEvents() {
    api.onInstallEvent((event) => {
      if (!event || !event.type) return;

      if (event.type === 'progress') {
        if (event.percent >= state.progress.percent) {
          state.progress.percent = Math.min(100, Math.max(0, event.percent));
          state.progress.stage = event.stage || state.progress.stage;
        }
        updateProgress();
        return;
      }

      if (event.type === 'error') {
        state.installing = false;
        state.installDone = false;
        state.installError = event.errorCode
          ? tFor(state.lang, `errors.${event.errorCode}`)
          : event.message || t('errors.installFailed');
        updateProgress();
        return;
      }

      if (event.type === 'done') {
        state.installing = false;
        state.installDone = true;
        state.installError = '';
        state.progress.percent = 100;
        state.progress.stage = 'done';
        updateProgress();
      }
    });
  }

  async function init() {
    const defaults = await api.getDefaults();
    state.version = defaults.version || state.version;
    state.options.installPath = defaults.defaultPath || '';
    dom.installPath.value = state.options.installPath;

    state.options.dataRoot =
      defaults.defaultDataRoot || `${state.options.installPath}_data`;
    state.dataRootTouched = !!defaults.dataRootConfigured;
    dom.dataRoot.value = state.options.dataRoot;

    if (defaults.existingModel) {
      prefillModel(defaults.existingModel);
    }

    if (isPreview) {
      dom.previewBadge.hidden = false;
    }

    refreshI18n();
    await Promise.all([refreshPathInfo(), refreshDataRootInfo()]);
    showStep('language');
  }

  function t(key) {
    return tFor(state.lang, key);
  }

  function tFor(lang, key) {
    const dict = I18N[lang] || I18N.zh;
    let value = dict[key];
    if (value === undefined) value = I18N.en[key] !== undefined ? I18N.en[key] : key;
    return value;
  }

  function refreshI18n() {
    document.querySelectorAll('[data-i18n]').forEach((element) => {
      element.textContent = t(element.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach((element) => {
      element.placeholder = t(element.dataset.i18nPlaceholder);
    });
    document.querySelectorAll('[data-i18n-title]').forEach((element) => {
      element.title = t(element.dataset.i18nTitle);
    });

    document.getElementById('brandVersion').textContent = t('welcome.version').replace(
      '{{version}}',
      state.version
    );
    dom.languageContinue.querySelector('.btn-label').textContent = t('language.continue');

    dom.languageRadios.forEach((radio) => {
      radio.checked = radio.value === state.lang;
    });

    dom.installBtn.querySelector('.btn-label').textContent = state.installing
      ? t('options.installing')
      : t('options.install');
    dom.progressContinue.querySelector('.btn-label').textContent = t('progress.continue');
    dom.modelNextBtn.querySelector('.btn-label').textContent = t('model.next');
    dom.finishBtn.querySelector('.btn-label').textContent = state.finishing
      ? t('finish.finalizing')
      : t('finish.complete');

    updateStepIndicator();
    updateOptionsControls();
    syncModelControls();
    updateProgress();
    updateFinish();
  }

  function showStep(step) {
    state.step = step;
    dom.pages.forEach((page) => {
      page.hidden = page.dataset.page !== step;
    });
    dom.stepIndicator.hidden = step === 'language';
    updateStepIndicator();

    if (step === 'options') {
      dom.installPath.value = state.options.installPath;
      dom.dataRoot.value = state.options.dataRoot;
      updateOptionsControls();
      refreshPathInfo();
      refreshDataRootInfo();
    } else if (step === 'progress') {
      updateProgress();
    } else if (step === 'model') {
      syncModelControls();
    } else if (step === 'finish') {
      updateFinish();
    }
  }

  function updateStepIndicator() {
    const map = { options: 0, progress: 1, model: 2, finish: 3 };
    const activeIndex = map[state.step];
    dom.stepItems.forEach((item, index) => {
      item.classList.toggle('active', index === activeIndex);
      item.classList.toggle('complete', index < activeIndex);
    });
  }

  let pathCheckTimer = 0;

  function schedulePathCheck() {
    window.clearTimeout(pathCheckTimer);
    pathCheckTimer = window.setTimeout(() => {
      refreshPathInfo();
    }, 450);
  }

  async function refreshPathInfo() {
    const target = state.options.installPath.trim();
    state.options.installPath = target;
    if (!target) {
      state.validation = { ok: false, errorCode: 'empty' };
      state.disk = null;
      state.pathError = t('errors.empty');
      updateOptionsControls();
      return;
    }

    try {
      const [validation, disk] = await Promise.all([
        api.validatePath(target),
        api.getDiskSpace(target),
      ]);
      state.validation = validation;
      state.disk = disk;
      state.pathError = validation.ok ? '' : t(`errors.${validation.errorCode || 'installFailed'}`);
    } catch (error) {
      state.validation = { ok: false, errorCode: 'inspectFailed' };
      state.disk = null;
      state.pathError = t('errors.inspectFailed');
    }
    updateOptionsControls();
  }

  let dataRootCheckTimer = 0;

  function scheduleDataRootCheck() {
    window.clearTimeout(dataRootCheckTimer);
    dataRootCheckTimer = window.setTimeout(() => {
      refreshDataRootInfo();
    }, 450);
  }

  async function refreshDataRootInfo() {
    const target = state.options.dataRoot.trim();
    state.options.dataRoot = target;
    if (!target) {
      state.dataRootValidation = { ok: false, errorCode: 'empty' };
      state.dataRootDisk = null;
      state.dataRootError = t('dataRootErrors.empty');
      updateOptionsControls();
      return;
    }

    try {
      const [validation, disk] = await Promise.all([
        api.validateDataRoot(target),
        api.getDiskSpace(target),
      ]);
      state.dataRootValidation = validation;
      state.dataRootDisk = disk;
      state.dataRootError = validation.ok
        ? ''
        : t(`dataRootErrors.${validation.errorCode || 'inspectFailed'}`);
    } catch (error) {
      state.dataRootValidation = { ok: false, errorCode: 'inspectFailed' };
      state.dataRootDisk = null;
      state.dataRootError = t('dataRootErrors.inspectFailed');
    }
    updateOptionsControls();
  }

  function updateOptionsControls() {
    if (!dom.installPath) return;
    const validation = state.validation;
    const disk = state.disk;
    const invalid = !!state.pathError;
    dom.pathError.hidden = !invalid;
    dom.pathError.textContent = state.pathError;
    dom.installPath.dataset.invalid = invalid ? 'true' : 'false';
    dom.existingInstallNotice.hidden = !(validation && validation.ok && validation.existingInstall);
    dom.requiredSpace.textContent = disk ? formatBytes(disk.required) : '—';
    dom.availableSpace.textContent = disk ? formatBytes(disk.available) : '—';
    dom.insufficientSpace.hidden = !(disk && disk.sufficient === false);

    const dataRootValidation = state.dataRootValidation;
    const dataRootDisk = state.dataRootDisk;
    const dataRootInvalid = !!state.dataRootError;
    dom.dataRootError.hidden = !dataRootInvalid;
    dom.dataRootError.textContent = state.dataRootError;
    dom.dataRoot.dataset.invalid = dataRootInvalid ? 'true' : 'false';
    dom.dataRootAvailable.textContent = dataRootDisk ? formatBytes(dataRootDisk.available) : '—';
    dom.dataRootInsufficient.hidden = !(dataRootDisk && dataRootDisk.sufficient === false);
    const dataRootOk =
      !!dataRootValidation &&
      dataRootValidation.ok &&
      !(dataRootDisk && dataRootDisk.sufficient === false);

    dom.installBtn.disabled =
      state.installing ||
      !validation ||
      !validation.ok ||
      (disk ? disk.sufficient === false : false) ||
      !dataRootOk;
    dom.installBtn.querySelector('.btn-label').textContent = state.installing
      ? t('options.installing')
      : t('options.install');
  }

  async function handleInstall() {
    if (state.installing) return;
    await Promise.all([refreshPathInfo(), refreshDataRootInfo()]);
    if (!state.validation || !state.validation.ok) {
      updateOptionsControls();
      return;
    }
    if (!state.dataRootValidation || !state.dataRootValidation.ok) {
      updateOptionsControls();
      return;
    }
    if (state.dataRootDisk && state.dataRootDisk.sufficient === false) {
      updateOptionsControls();
      return;
    }

    state.installing = true;
    state.installDone = false;
    state.installError = '';
    state.progress = { stage: 'preparing', percent: 2 };
    showStep('progress');
    updateProgress();

    let result = null;
    try {
      result = await api.startInstall({
        installPath: state.options.installPath,
        dataRoot: state.options.dataRoot,
        desktopShortcut: state.options.desktopShortcut,
        startMenu: state.options.startMenu,
      });
    } catch (error) {
      result = { ok: false, errorCode: 'installFailed', message: error.message };
    }

    if (!result || !result.ok) {
      state.installing = false;
      state.installError = result && result.errorCode
        ? t(`errors.${result.errorCode}`)
        : (result && result.message) || t('errors.installFailed');
      updateProgress();
    }
  }

  function updateProgress() {
    const failed = !!state.installError;
    const done = state.installDone && !failed;

    dom.progressBrand.className = `progress-brand${done ? ' completed' : ''}${failed ? ' failed' : ''}`;

    if (failed) {
      dom.progressTitle.textContent = t('progress.failed');
      dom.progressDescription.hidden = true;
      dom.progressDescription.textContent = '';
      dom.progressBlock.hidden = true;
      dom.progressError.hidden = false;
      dom.progressError.textContent = state.installError;
    } else {
      dom.progressTitle.textContent = done ? t('progress.completed') : t('progress.title');
      dom.progressDescription.hidden = false;
      dom.progressDescription.textContent = done
        ? t('progress.completedDescription')
        : t('progress.description');
      dom.progressBlock.hidden = false;
      dom.progressError.hidden = true;
      dom.progressError.textContent = '';

      const percent = Math.min(100, Math.max(0, state.progress.percent));
      dom.progressStage.textContent = t(`progress.${state.progress.stage}`);
      dom.progressPercent.textContent = `${Math.round(percent)}%`;
      dom.progressFill.style.width = `${percent}%`;
      dom.progressFill.classList.toggle('completed', done);
    }

    dom.progressBack.hidden = !failed;
    dom.progressRetry.hidden = !failed;
    dom.progressContinue.hidden = !done;
    dom.progressBack.textContent = t('progress.backOptions');
    dom.progressRetry.textContent = t('progress.retry');
  }

  function prefillModel(existing) {
    const provider = PROVIDERS.find(
      (item) => normalizeUrl(item.baseUrl) === normalizeUrl(existing.baseUrl)
    );
    state.model.apiKey = existing.apiKey || '';
    state.model.baseUrl = existing.baseUrl || (provider ? provider.baseUrl : '');
    state.model.model = existing.model || '';
    state.model.providerId = provider ? provider.id : 'custom';
    state.model.customModel = !provider || !provider.models.includes(state.model.model);
    dom.apiKeyInput.value = state.model.apiKey;
    dom.baseUrlInput.value = state.model.baseUrl;
  }

  function normalizeUrl(value) {
    return (value || '').trim().replace(/\/+$/, '').toLowerCase();
  }

  function handleProviderChange() {
    state.model.providerId = dom.providerSelect.value;
    const provider = PROVIDERS.find((item) => item.id === state.model.providerId) || PROVIDERS[0];
    state.model.customModel = provider.id === 'custom';
    state.model.baseUrl = provider.baseUrl;
    state.model.model = provider.id === 'custom' ? '' : provider.models[0] || '';
    state.modelError = '';
    resetTestStatus();
    syncModelControls();
  }

  function handleModelSelectChange() {
    const value = dom.modelSelect.value;
    if (value === '__custom__') {
      state.model.customModel = true;
      state.model.model = '';
    } else {
      state.model.customModel = false;
      state.model.model = value;
    }
    resetTestStatus();
    syncModelControls();
    if (value === '__custom__') dom.modelCustomInput.focus();
  }

  function syncModelControls() {
    dom.providerSelect.innerHTML = PROVIDERS.map(
      (provider) => `<option value="${provider.id}">${escapeHtml(provider.name[state.lang] || provider.name.en)}</option>`
    ).join('');
    dom.providerSelect.value = state.model.providerId;

    const provider = PROVIDERS.find((item) => item.id === state.model.providerId) || PROVIDERS[0];
    const isCustomProvider = provider.id === 'custom';

    if (isCustomProvider) {
      dom.modelSelectWrap.hidden = true;
      dom.modelCustomInput.hidden = false;
      if (dom.modelCustomInput.value !== state.model.model) {
        dom.modelCustomInput.value = state.model.model;
      }
    } else {
      dom.modelSelectWrap.hidden = false;
      const options = provider.models.slice();
      if (state.model.customModel || !options.includes(state.model.model)) {
        options.push('__custom__');
      }
      dom.modelSelect.innerHTML = options
        .map((model) =>
          model === '__custom__'
            ? `<option value="__custom__">${escapeHtml(t('model.customModel'))}</option>`
            : `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`
        )
        .join('');
      dom.modelSelect.value = state.model.customModel ? '__custom__' : state.model.model;
      dom.modelCustomInput.hidden = !state.model.customModel;
      if (state.model.customModel && dom.modelCustomInput.value !== state.model.model) {
        dom.modelCustomInput.value = state.model.model;
      }
    }

    if (dom.apiKeyInput.value !== state.model.apiKey) {
      dom.apiKeyInput.value = state.model.apiKey;
    }
    dom.apiKeyInput.type = state.model.showKey ? 'text' : 'password';
    dom.toggleKeyBtn.textContent = t(state.model.showKey ? 'model.hide' : 'model.show');

    if (dom.baseUrlInput.value !== state.model.baseUrl) {
      dom.baseUrlInput.value = state.model.baseUrl;
    }

    dom.modelError.hidden = !state.modelError;
    dom.modelError.textContent = state.modelError;
    dom.modelNextBtn.disabled = state.savingModel || !canSaveModel();
    dom.modelNextBtn.querySelector('.btn-label').textContent = t('model.next');

    updateTestStatus();
  }

  function canSaveModel() {
    return !!(
      state.model.apiKey.trim() &&
      state.model.model.trim() &&
      state.model.baseUrl.trim() &&
      state.model.providerId
    );
  }

  function resetTestStatus() {
    state.testStatus = { kind: '', message: '' };
    updateTestStatus();
  }

  function setTestStatus(kind, message) {
    state.testStatus = { kind, message };
    updateTestStatus();
  }

  function updateTestStatus() {
    const status = state.testStatus;
    dom.testStatus.hidden = !status.kind || !status.message;
    dom.testStatus.className = `test-status${status.kind ? ` ${status.kind}` : ''}`;
    dom.testStatus.textContent = status.message || '';
  }

  async function handleTestConnection() {
    if (!canSaveModel()) {
      const missing = !state.model.apiKey.trim()
        ? 'missingKey'
        : !state.model.model.trim()
          ? 'missingModel'
          : 'missingBaseUrl';
      setTestStatus('error', t(`model.testErrors.${missing}`));
      return;
    }

    setButtonLoading(dom.testModelBtn, true);
    setTestStatus('pending', t('model.testing'));

    let result = null;
    try {
      result = await api.testModel({
        apiKey: state.model.apiKey,
        baseUrl: state.model.baseUrl,
        model: state.model.model,
      });
    } catch (error) {
      result = { success: false, message: error.message };
    }

    setButtonLoading(dom.testModelBtn, false);

    if (result && result.success) {
      setTestStatus('success', t('model.testSuccess'));
    } else {
      const message = result && result.message
        ? result.message
        : t(`model.testErrors.${(result && result.errorCode) || 'failed'}`);
      setTestStatus('error', message);
    }
  }

  async function handleModelNext() {
    if (!canSaveModel() || state.savingModel) return;
    state.savingModel = true;
    state.modelError = '';
    setButtonLoading(dom.modelNextBtn, true);
    syncModelControls();

    let result = null;
    try {
      result = await api.saveModel({
        apiKey: state.model.apiKey,
        baseUrl: state.model.baseUrl,
        model: state.model.model,
      });
    } catch (error) {
      result = { ok: false, message: error.message };
    }

    state.savingModel = false;
    setButtonLoading(dom.modelNextBtn, false);

    if (!result || !result.ok) {
      state.modelError = result && result.errorCode
        ? t(`model.saveErrors.${result.errorCode}`)
        : (result && result.message) || t('model.saveFailed');
      syncModelControls();
      return;
    }

    state.modelSaved = true;
    showStep('finish');
  }

  function updateFinish() {
    dom.finishPath.textContent = state.options.installPath;
    dom.finishDataRoot.textContent = state.options.dataRoot;
    dom.finishModel.textContent = state.modelSaved
      ? `${state.model.model} · ${state.model.baseUrl}`
      : t('finish.skipped');
    dom.finishDescription.textContent = state.modelSaved
      ? t('finish.descriptionConfigured')
      : t('finish.descriptionSkipped');
    dom.finishError.hidden = !state.finishError;
    dom.finishError.textContent = state.finishError;
    dom.finishBtn.querySelector('.btn-label').textContent = state.finishing
      ? t('finish.finalizing')
      : t('finish.complete');
  }

  async function handleFinish() {
    if (state.finishing) return;
    state.finishing = true;
    state.finishError = '';
    updateFinish();
    setButtonLoading(dom.finishBtn, true);

    let result = null;
    try {
      result = await api.finalize({
        installPath: state.options.installPath,
        desktopShortcut: state.options.desktopShortcut,
        startMenu: state.options.startMenu,
        launch: dom.launchAfterInstall.checked,
      });
    } catch (error) {
      result = { ok: false, message: error.message };
    }

    state.finishing = false;
    setButtonLoading(dom.finishBtn, false);

    if (!result || !result.ok) {
      state.finishError = (result && result.message) || t('errors.finalizeFailed');
      updateFinish();
      return;
    }

    const warnings = (result.warnings || []).filter((key) =>
      ['env', 'launcher', 'command', 'desktopShortcut', 'startMenuShortcut', 'launch'].includes(key)
    );
    if (warnings.includes('launch') || warnings.includes('command')) {
      state.finishError = t(`finish.warnings.${warnings[0]}`);
      updateFinish();
      return;
    }

    api.close();
  }

  function setButtonLoading(button, loading) {
    if (!button) return;
    const spinner = button.querySelector('.spinner');
    if (loading) {
      button.dataset.loading = 'true';
      if (spinner) spinner.hidden = false;
      button.disabled = true;
      return;
    }
    delete button.dataset.loading;
    if (spinner) spinner.hidden = true;
    button.disabled = button === dom.modelNextBtn ? !canSaveModel() : false;
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
    const value = bytes / Math.pow(1024, index);
    return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
  }

  function applyTheme(theme) {
    const next = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    dom.themeToggle.title = t('window.toggleTheme');
    dom.themeToggle.setAttribute('aria-label', t('window.toggleTheme'));
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // 浏览器内预览时使用的模拟接口，方便在没有 Electron 的情况下检查界面。
  function createPreviewApi() {
    let installEvents = () => {};
    let timers = [];
    let mockModel = null;

    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    const validate = (target) => {
      const value = (target || '').trim();
      if (!value) return { ok: false, errorCode: 'empty' };
      if (!/^(?:[A-Za-z]:[\\/]|\\\\)/.test(value)) return { ok: false, errorCode: 'notAbsolute' };
      if (/^[A-Za-z]:[\\/]?$/.test(value)) return { ok: false, errorCode: 'fsRoot' };
      if (/nonempty/i.test(value)) return { ok: false, errorCode: 'dirNotEmpty' };
      return {
        ok: true,
        path: value,
        existingInstall: /purrcat[\\/]?$/i.test(value),
      };
    };

    const validateRoot = (target) => {
      const value = (target || '').trim();
      if (!value) return { ok: false, errorCode: 'empty' };
      if (!/^(?:[A-Za-z]:[\\/]|\\\\)/.test(value)) return { ok: false, errorCode: 'notAbsolute' };
      if (/^[A-Za-z]:[\\/]?$/.test(value)) return { ok: false, errorCode: 'fsRoot' };
      return { ok: true, path: value };
    };

    return {
      getDefaults: async () => ({
        version: '0.1.0',
        defaultPath: 'C:\\Users\\Preview\\purrcat',
        defaultDataRoot: 'C:\\Users\\Preview\\purrcat_data',
        dataRootConfigured: false,
        existingModel: mockModel,
      }),
      chooseDirectory: async (options) =>
        window.prompt('选择文件夹', (options && options.defaultPath) || 'C:\\Users\\Preview'),
      validatePath: async (target) => {
        await sleep(120);
        return validate(target);
      },
      validateDataRoot: async (target) => {
        await sleep(120);
        return validateRoot(target);
      },
      getDiskSpace: async () => ({
        required: 500 * 1024 * 1024,
        available: 64 * 1024 * 1024 * 1024,
        sufficient: true,
      }),
      startInstall: async () => {
        timers.forEach((timer) => clearTimeout(timer));
        timers = [];
        const stages = [
          ['preparing', 2],
          ['dependencies', 6],
          ['source', 14],
          ['python', 24],
          ['node', 48],
          ['embedding', 64],
          ['docker', 76],
          ['register', 90],
          ['done', 100],
        ];
        stages.forEach(([stage, percent], index) => {
          const timer = setTimeout(() => {
            if (stage === 'done') {
              installEvents({ type: 'progress', stage, percent });
              installEvents({ type: 'done', path: 'C:\\Users\\Preview\\purrcat' });
            } else {
              installEvents({ type: 'progress', stage, percent });
            }
          }, 500 + index * 700);
          timers.push(timer);
        });
        return { ok: true, path: 'C:\\Users\\Preview\\purrcat' };
      },
      testModel: async (payload) => {
        await sleep(900);
        if (!payload.apiKey) return { success: false, errorCode: 'missingKey' };
        if (/bad/i.test(payload.apiKey)) return { success: false, message: 'HTTP 401: invalid api key' };
        return { success: true };
      },
      saveModel: async (payload) => {
        await sleep(500);
        if (!payload.apiKey || !payload.model || !payload.baseUrl) {
          return { ok: false, errorCode: 'missing' };
        }
        mockModel = {
          model: payload.model,
          baseUrl: payload.baseUrl,
          apiKey: payload.apiKey,
        };
        return { ok: true };
      },
      finalize: async () => {
        await sleep(800);
        return { ok: true, warnings: [] };
      },
      openPath: async () => ({ ok: true }),
      minimize: () => {},
      close: () => {
        if (window.confirm('关闭安装程序预览？')) window.close();
      },
      onInstallEvent: (callback) => {
        installEvents = callback;
        return () => {
          installEvents = () => {};
        };
      },
    };
  }
})();

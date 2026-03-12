import type { Message, ThoughtChain, Project, Task, ModelConfig, Skill, FileContent, Plugin, ConfigCategory } from './types'

// 模拟全局消息列表
export const mockMessages: Message[] = [
  {
    id: '1',
    role: 'user',
    content: '请帮我分析一下这个代码文件',
    timestamp: new Date('2026-03-12T10:00:00'),
  },
  {
    id: '2',
    role: 'agent',
    content: '好的，我正在分析代码文件。这是一个 Python 项目，主要包含以下模块...',
    timestamp: new Date('2026-03-12T10:00:05'),
  },
  {
    id: '3',
    role: 'system',
    content: '[系统] 已加载文件: /src/main.py',
    timestamp: new Date('2026-03-12T10:00:03'),
  },
  {
    id: '4',
    role: 'user',
    content: '能否优化这段代码的性能？',
    timestamp: new Date('2026-03-12T10:01:00'),
  },
  {
    id: '5',
    role: 'agent',
    content: '我发现了几个可以优化的地方：\n1. 使用列表推导式替代循环\n2. 添加缓存机制\n3. 使用异步处理',
    timestamp: new Date('2026-03-12T10:01:10'),
  },
]

// 模拟思考链数据
export const mockThoughtChain: ThoughtChain[] = [
  {
    id: 't1',
    step: 1,
    thought: '用户想要分析代码文件，我需要先读取文件内容',
    action: 'read_file("/src/main.py")',
    observation: '成功读取文件，共 150 行代码',
    timestamp: new Date('2026-03-12T10:00:02'),
  },
  {
    id: 't2',
    step: 2,
    thought: '文件已读取，现在需要分析代码结构和功能',
    action: 'analyze_code(content)',
    observation: '识别出 3 个类，5 个函数',
    timestamp: new Date('2026-03-12T10:00:04'),
  },
  {
    id: 't3',
    step: 3,
    thought: '用户询问性能优化，我需要检查代码中的性能瓶颈',
    action: 'find_performance_issues(code)',
    observation: '发现 2 个潜在的性能问题',
    timestamp: new Date('2026-03-12T10:01:05'),
  },
]

// 模拟 Project 队列
export const mockProjects: Project[] = [
  {
    id: 'p1',
    name: '代码分析任务',
    description: '分析 src 目录下的所有 Python 代码，生成分析报告',
    status: 'running',
    progress: 65,
    pipeline: [
      { id: 'ps1', name: '初始化环境', status: 'completed', progress: 100, startedAt: new Date('2026-03-12T09:30:00'), completedAt: new Date('2026-03-12T09:30:05') },
      { id: 'ps2', name: '扫描文件', status: 'completed', progress: 100, startedAt: new Date('2026-03-12T09:30:05'), completedAt: new Date('2026-03-12T09:30:15') },
      { id: 'ps3', name: '代码解析', status: 'running', progress: 60, startedAt: new Date('2026-03-12T09:30:15') },
      { id: 'ps4', name: '生成报告', status: 'pending', progress: 0 },
    ],
    createdAt: new Date('2026-03-12T09:30:00'),
    updatedAt: new Date('2026-03-12T10:00:00'),
  },
  {
    id: 'p2',
    name: '文档生成',
    description: '根据代码注释自动生成 API 文档',
    status: 'pending',
    progress: 0,
    pipeline: [
      { id: 'ps5', name: '读取源文件', status: 'pending', progress: 0 },
      { id: 'ps6', name: '提取注释', status: 'pending', progress: 0 },
      { id: 'ps7', name: '生成 Markdown', status: 'pending', progress: 0 },
    ],
    createdAt: new Date('2026-03-12T09:45:00'),
  },
  {
    id: 'p3',
    name: '单元测试生成',
    description: '为核心模块自动生成单元测试用例',
    status: 'completed',
    progress: 100,
    pipeline: [
      { id: 'ps8', name: '分析函数签名', status: 'completed', progress: 100, startedAt: new Date('2026-03-12T08:00:00'), completedAt: new Date('2026-03-12T08:05:00') },
      { id: 'ps9', name: '生成测试用例', status: 'completed', progress: 100, startedAt: new Date('2026-03-12T08:05:00'), completedAt: new Date('2026-03-12T08:20:00') },
      { id: 'ps10', name: '验证测试', status: 'completed', progress: 100, startedAt: new Date('2026-03-12T08:20:00'), completedAt: new Date('2026-03-12T08:25:00') },
    ],
    createdAt: new Date('2026-03-12T08:00:00'),
    updatedAt: new Date('2026-03-12T08:25:00'),
  },
]

// 模拟 Task 队列
export const mockTasks: Task[] = [
  {
    id: 't1',
    projectId: 'p1',
    name: '读取源代码',
    description: '读取并解析 /src 目录下的所有 .py 文件',
    status: 'completed',
    progress: 100,
    logs: [
      '[09:30:01] 开始扫描目录...',
      '[09:30:02] 发现 15 个 Python 文件',
      '[09:30:03] 读取完成',
    ],
    createdAt: new Date('2026-03-12T09:30:01'),
    updatedAt: new Date('2026-03-12T09:30:03'),
  },
  {
    id: 't2',
    projectId: 'p1',
    name: '代码结构分析',
    description: '分析代码的类、函数和依赖关系',
    status: 'running',
    progress: 45,
    logs: [
      '[09:30:04] 开始分析代码结构...',
      '[09:30:10] 正在解析 AST...',
      '[09:30:15] 已分析 7/15 个文件',
    ],
    createdAt: new Date('2026-03-12T09:30:02'),
    updatedAt: new Date('2026-03-12T09:30:15'),
  },
  {
    id: 't3',
    projectId: 'p1',
    name: '生成分析报告',
    description: '汇总分析结果并生成 Markdown 报告',
    status: 'pending',
    progress: 0,
    logs: [],
    createdAt: new Date('2026-03-12T09:30:03'),
  },
  {
    id: 't4',
    name: '定时备份任务',
    description: '每日自动备份数据到云端',
    status: 'running',
    progress: 30,
    logs: [
      '[10:00:00] 开始备份...',
      '[10:00:05] 正在压缩文件...',
    ],
    createdAt: new Date('2026-03-12T10:00:00'),
    updatedAt: new Date('2026-03-12T10:00:05'),
  },
]

// 模拟模型配置
export const mockModelConfig: ModelConfig = {
  'gpt-4': {
    provider: 'openai',
    model: 'gpt-4-turbo',
    baseUrl: 'https://api.openai.com/v1',
  },
  'claude-3': {
    provider: 'anthropic',
    model: 'claude-3-opus',
    baseUrl: 'https://api.anthropic.com',
  },
  'deepseek': {
    provider: 'deepseek',
    model: 'deepseek-coder',
    baseUrl: 'https://api.deepseek.com',
  },
}

// 模拟 Skill 列表
export const mockSkills: Skill[] = [
  { name: 'code_analysis', path: '/skills/code_analysis', description: '代码分析技能' },
  { name: 'web_search', path: '/skills/web_search', description: '网络搜索技能' },
  { name: 'file_manager', path: '/skills/file_manager', description: '文件管理技能' },
  { name: 'data_processor', path: '/skills/data_processor', description: '数据处理技能' },
]

// 模拟文件内容
export const mockFiles: Record<string, FileContent> = {
  'user_profile': {
    path: '/src/agent/core/user_profile.md',
    content: `# 用户配置文件

## 基本信息
- 名称: 默认用户
- 语言偏好: 中文

## 偏好设置
- 代码风格: PEP8
- 响应详细度: 详细

## 历史记录
最近使用的功能：
1. 代码分析
2. 文档生成
`,
    lastModified: new Date('2026-03-11T15:00:00'),
  },
  'me': {
    path: '/me.md',
    content: `# 关于我

这是一个 AI Agent 助手，专注于：
- 代码分析与优化
- 项目管理
- 任务自动化

## 能力
- 多语言代码理解
- 智能任务分解
- 持续学习与改进
`,
    lastModified: new Date('2026-03-10T12:00:00'),
  },
  'soul': {
    path: '/SOUL.md',
    content: `# SOUL - Agent 灵魂配置

## 核心价值观
1. 准确性 - 提供准确可靠的信息
2. 效率 - 高效完成用户任务
3. 安全性 - 保护用户数据和隐私

## 行为准则
- 始终保持礼貌和专业
- 遇到不确定的问题时主动询问
- 优先考虑用户的实际需求

## 思考模式
- 分步骤思考问题
- 考虑多种可能的解决方案
- 评估每个方案的优缺点
`,
    lastModified: new Date('2026-03-09T18:00:00'),
  },
}

// 模拟 Plugin 列表
export const mockPlugins: Plugin[] = [
  { name: 'github_integration', path: '/plugin/plugin_collection/github_integration', description: 'GitHub 集成插件，支持仓库管理和 PR 操作', enabled: true, version: '1.2.0' },
  { name: 'slack_notifier', path: '/plugin/plugin_collection/slack_notifier', description: 'Slack 通知插件，发送任务状态更新', enabled: true, version: '1.0.5' },
  { name: 'code_formatter', path: '/plugin/plugin_collection/code_formatter', description: '代码格式化插件，支持多种语言', enabled: false, version: '2.1.0' },
  { name: 'database_connector', path: '/plugin/plugin_collection/database_connector', description: '数据库连接插件，支持 MySQL/PostgreSQL', enabled: false, version: '1.3.2' },
  { name: 'file_watcher', path: '/plugin/plugin_collection/file_watcher', description: '文件监控插件，实时检测文件变化', enabled: true, version: '1.1.0' },
]

// 模拟配置项
export const mockConfigs: ConfigCategory[] = [
  {
    name: 'general',
    items: [
      { key: 'language', value: 'zh-CN', type: 'string', description: '界面语言' },
      { key: 'theme', value: 'dark', type: 'string', description: '主题模式' },
      { key: 'auto_save', value: true, type: 'boolean', description: '自动保存' },
      { key: 'save_interval', value: 30, type: 'number', description: '自动保存间隔（秒）' },
    ],
  },
  {
    name: 'agent',
    items: [
      { key: 'default_model', value: 'gpt-4', type: 'string', description: '默认使用的模型' },
      { key: 'max_tokens', value: 4096, type: 'number', description: '最大 token 数' },
      { key: 'temperature', value: 0.7, type: 'number', description: '温度参数' },
      { key: 'stream_response', value: true, type: 'boolean', description: '流式输出' },
    ],
  },
  {
    name: 'project',
    items: [
      { key: 'max_concurrent_projects', value: 3, type: 'number', description: '最大并发项目数' },
      { key: 'auto_cleanup', value: true, type: 'boolean', description: '自动清理已完成项目' },
      { key: 'cleanup_after_days', value: 7, type: 'number', description: '清理天数' },
    ],
  },
  {
    name: 'task',
    items: [
      { key: 'max_concurrent_tasks', value: 5, type: 'number', description: '最大并发任务数' },
      { key: 'retry_on_failure', value: true, type: 'boolean', description: '失败时自动重试' },
      { key: 'max_retries', value: 3, type: 'number', description: '最大重试次数' },
      { key: 'timeout', value: 300, type: 'number', description: '任务超时时间（秒）' },
    ],
  },
]

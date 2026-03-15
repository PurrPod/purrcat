// Agent 相关类型
export interface Message {
  id: string
  role: 'user' | 'agent' | 'system'
  type?: string
  content: string
  timestamp: Date
}

export interface ThoughtChain {
  id: string
  role?: string
  type?: string
  content: any
  timestamp: Date
}

// Project 和 Task 相关类型
export interface PipelineStep {
  id: string
  name: string
  status: 'running' | 'pending' | 'completed' | 'failed'
  progress: number
  startedAt?: Date
  completedAt?: Date
}

export interface Project {
  id: string
  name: string
  description?: string
  status: 'running' | 'pending' | 'completed' | 'failed'
  progress: number
  pipeline: PipelineStep[]
  history?: any[]
  core?: string
  createTime?: string
  availableTools?: string[]
  availableWorkers?: string[]
  checkMode?: boolean
  refineMode?: boolean
  judgeMode?: boolean
  isAgent?: boolean
  createdAt: Date
  updatedAt: Date
}

export interface Task {
  id: string
  projectId?: string
  name: string
  description?: string
  status: 'running' | 'pending' | 'completed' | 'failed'
  progress: number
  worker?: string
  judger?: string
  creat_time?: string
  logs: string[]
  history?: any[]
  createdAt: Date
  updatedAt: Date
}

// Model 配置类型
export interface ModelConfigItem {
  provider: string
  model: string
  apiKey?: string
  baseUrl?: string
  maxTokens?: number
  temperature?: number
}

export interface ModelConfig {
  models?: {
    [key: string]: ModelConfigItem
  }
  [key: string]: any
}

// Skill 类型
export interface Skill {
  name: string
  path: string
  description?: string
}

// Plugin 类型
export interface Plugin {
  name: string
  path: string
  description?: string
  enabled: boolean
  version?: string
}

// 配置项类型
export interface ConfigItem {
  key: string;
  value: any;
  type: 'string' | 'number' | 'boolean' | 'object';
  description?: string;
}

export interface ConfigCategory {
  name: string;
  items: ConfigItem[];
}

export interface Tool {
  name: string;
  description: string;
}

export interface ToolGroup {
  name: string;
  description: string;
  tools: Tool[];
}

// 文件内容类型
export interface ScheduleItem {
  id: string
  title: string
  start_time: string
  end_time?: string
  description?: string
  createdAt?: string
}

export interface AlarmItem {
  id: string
  title: string
  trigger_time: string
  repeat_rule: string
  active: boolean
  createdAt?: string
}

export interface FileContent {
  path: string
  content: string
  lastModified: Date
}

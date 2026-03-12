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
  step: number
  thought: string
  action?: string
  observation?: string
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
  pipeline: any[]
  history?: any[]
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
  key: string
  value: any
  type: 'string' | 'number' | 'boolean' | 'object'
  description?: string
}

export interface ConfigCategory {
  name: string
  items: ConfigItem[]
}

// 文件内容类型
export interface FileContent {
  path: string
  content: string
  lastModified: Date
}

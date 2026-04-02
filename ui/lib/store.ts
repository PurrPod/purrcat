'use client'

import { create } from 'zustand'
import type { Message, ThoughtChain, Project, Task, Skill, FileContent, Plugin, ConfigCategory, ModelConfig, ToolGroup, ScheduleItem, AlarmItem } from './types'

export const API_BASE = 'http://localhost:8000/api'
export const API_ORIGIN = API_BASE.replace(/\/api\/?$/, '')

type ConnectionStatus = 'connected' | 'disconnected' | 'reconnecting'

function toErrorMessage(error: unknown): string {
  if (typeof error === 'string') return error
  if (error && typeof error === 'object' && 'message' in error && typeof (error as any).message === 'string') {
    return (error as any).message
  }
  try {
    return JSON.stringify(error)
  } catch {
    return String(error)
  }
}

async function fetchWithTimeout(input: RequestInfo | URL, init: RequestInit | undefined, timeoutMs: number) {
  // 检查是否在浏览器环境中
  if (typeof window === 'undefined') {
    // 在服务器端，使用标准的fetch函数
    return fetch(input, init)
  }

  if (!timeoutMs || timeoutMs <= 0) return fetch(input, init)

  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)

  try {
    return await fetch(input, { ...init, signal: controller.signal })
  } finally {
    window.clearTimeout(timer)
  }
}

interface AppState {
  connectionStatus: ConnectionStatus
  connectionError: string | null
  lastConnectedAt: number | null
  apiFetch: (pathOrUrl: string, init?: RequestInit, opts?: { timeoutMs?: number; treat5xxAsDisconnected?: boolean }) => Promise<Response>
  pingBackend: (opts?: { timeoutMs?: number }) => Promise<boolean>
  reconnectNow: () => Promise<boolean>
  refreshAll: () => Promise<void>
  setConnectionStatus: (status: ConnectionStatus, error?: string | null) => void
  // Messages
  messages: Message[]
  fetchMessages: () => Promise<void>
  addMessage: (message: Omit<Message, 'id' | 'timestamp'>) => Promise<void>
  removeMessage: (id: string) => Promise<void>
  
  // Thought Chain
  thoughtChain: ThoughtChain[]
  fetchThoughtChain: () => Promise<void>
  forcePush: (content: string) => Promise<void>
  summarizeMemory: () => Promise<void>
  
  // Tasks
  tasks: Task[]
  fetchTasks: () => Promise<void>
  addTask: (task: {
    title: string,
    desc: string,
    deliverable: string,
    prompt: string,
    judge_mode: boolean,
    task_histories: string,
    core: string
  }) => Promise<void>
  removeTask: (id: string) => Promise<void>
  stopTask: (id: string) => Promise<void>
  injectTask: (taskId: string, content: string) => Promise<void>

  // Schedule + Alarm
  scheduleItems: ScheduleItem[]
  fetchSchedule: () => Promise<void>
  addSchedule: (item: {
    title: string
    start_time: string
    end_time?: string
    description?: string
  }) => Promise<void>
  removeSchedule: (id: string) => Promise<void>

  alarms: AlarmItem[]
  fetchAlarms: () => Promise<void>
  addAlarm: (item: {
    title: string
    trigger_time: string
    repeat_rule: string
    active?: boolean
  }) => Promise<void>
  updateAlarm: (id: string, updates: Partial<{ title: string; trigger_time: string; repeat_rule: string; active: boolean }>) => Promise<void>
  removeAlarm: (id: string) => Promise<void>

  // Tool Groups
  toolGroups: ToolGroup[];
  fetchToolGroups: () => Promise<void>;
  
  // Skills
  skills: Skill[]
  fetchSkills: () => Promise<void>
  
  // Model Config
  modelConfig: ModelConfig
  fetchModelConfig: () => Promise<void>
  updateModelConfig: (key: string, config: ModelConfig[string]) => Promise<void>
  
  // Files
  files: Record<string, FileContent>
  fetchFile: (path: string) => Promise<void>
  updateFile: (path: string, content: string) => Promise<void>
  
  // Plugins
  plugins: Plugin[]
  fetchPlugins: () => Promise<void>
  togglePlugin: (name: string) => Promise<void>
  
  // Databases
  databases: string[]
  fetchDatabases: () => Promise<void>
  
  // Configs
  configs: ConfigCategory[]
  fetchConfigs: () => Promise<void>
  updateConfig: (categoryName: string, key: string, value: string | number | boolean) => Promise<void>
  
  // UI State
  clearScreenMode: boolean
  toggleClearScreenMode: () => void
}

export const useAppStore = create<AppState>((set, get) => ({
  connectionStatus: 'connected',
  connectionError: null,
  lastConnectedAt: null,
  setConnectionStatus: (status, error) => {
    set((prev) => ({
      connectionStatus: status,
      connectionError: error === undefined ? prev.connectionError : error,
      lastConnectedAt: status === 'connected' ? Date.now() : prev.lastConnectedAt,
    }))
  },
  apiFetch: async (pathOrUrl, init, opts) => {
    const timeoutMs = opts?.timeoutMs ?? 8000
    const treat5xxAsDisconnected = opts?.treat5xxAsDisconnected ?? true

    const state = get()
    if (typeof window !== 'undefined' && 'onLine' in window.navigator && window.navigator.onLine === false) {
      state.setConnectionStatus('disconnected', 'offline')
      throw new Error('offline')
    }

    const url = /^https?:\/\//i.test(pathOrUrl)
      ? pathOrUrl
      : `${API_BASE}${pathOrUrl.startsWith('/') ? pathOrUrl : `/${pathOrUrl}`}`

    try {
      const res = await fetchWithTimeout(url, init, timeoutMs)
      if (treat5xxAsDisconnected && res.status >= 500) {
        state.setConnectionStatus('disconnected', `server_${res.status}`)
      } else {
        state.setConnectionStatus('connected', null)
      }
      return res
    } catch (e) {
      state.setConnectionStatus('disconnected', toErrorMessage(e))
      throw e
    }
  },
  pingBackend: async (opts) => {
    const timeoutMs = opts?.timeoutMs ?? 2500
    try {
      const res = await fetchWithTimeout(`${API_ORIGIN}/`, { method: 'GET' }, timeoutMs)
      if (!res.ok) {
        get().setConnectionStatus('disconnected', `ping_${res.status}`)
        return false
      }
      get().setConnectionStatus('connected', null)
      return true
    } catch (e) {
      get().setConnectionStatus('disconnected', toErrorMessage(e))
      return false
    }
  },
  refreshAll: async () => {
    await Promise.allSettled([
      get().fetchMessages(),
      get().fetchTasks(),
      get().fetchConfigs(),
      get().fetchPlugins(),
      get().fetchSkills(),
      get().fetchDatabases(),
      get().fetchThoughtChain(),
      get().fetchModelConfig(),
      get().fetchSchedule(),
      get().fetchAlarms(),
      get().fetchToolGroups(),
    ])
  },

  reconnectNow: async () => {
    const state = get()
    state.setConnectionStatus('reconnecting')
    const ok = await state.pingBackend({ timeoutMs: 3000 })
    if (!ok) return false
    await state.refreshAll()
    await state.resumeInterruptedProjects()
    state.setConnectionStatus('connected', null)
    return true
  },

  messages: [],
  fetchMessages: async () => {
     try {
       const res = await get().apiFetch('/messages')
       const data = await res.json()
       set({ 
         messages: data.map((m: any) => ({
           id: m.id,
           role: (m.type === 'owner_message' || m.chat_id === 'owner') ? 'user' : (m.type === 'system' || m.type === 'schedule' || m.type === 'rss_update') ? 'system' : 'agent',
           type: m.type,
           content: m.content,
           timestamp: new Date(m.timestamp * 1000)
         })) 
       })
     } catch (e) {
       console.error('Failed to fetch messages:', e)
     }
   },
  addMessage: async (message) => {
    try {
      await get().apiFetch('/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: message.role === 'user' ? 'owner_message' : 'agent_message',
          content: message.content
        })
      })
      get().fetchMessages()
    } catch (e) {
      console.error('Failed to add message:', e)
    }
  },
  removeMessage: async (id) => {
    try {
      await get().apiFetch(`/messages/${id}`, { method: 'DELETE' })
      get().fetchMessages()
    } catch (e) {
      console.error('Failed to remove message:', e)
    }
  },
  
  thoughtChain: [],
  fetchThoughtChain: async () => {
    try {
      const res = await get().apiFetch('/thought-chain')
      const data = await res.json()
      set({
        thoughtChain: (Array.isArray(data) ? data : []).map((t: any, index: number) => {
          const rawTimestamp = t?.timestamp ?? t?.time ?? t?.created_at ?? t?.createdAt
          let timestamp = new Date()
          if (typeof rawTimestamp === 'number') {
            timestamp = new Date(rawTimestamp > 1e12 ? rawTimestamp : rawTimestamp * 1000)
          } else if (typeof rawTimestamp === 'string') {
            const d = new Date(rawTimestamp)
            timestamp = isNaN(d.getTime()) ? new Date() : d
          }

          let content: any = t?.content ?? t?.message?.content
          if (content === undefined || content === null || (typeof content === 'string' && content.trim() === '')) {
            content = t
          }
          // If has tool_calls, always use the full object
          if (t?.tool_calls || t?.toolCalls) {
            content = t
          }

          return {
            id: String(t?.id ?? index),
            role: t?.role ?? t?.message?.role ?? t?.sender ?? undefined,
            type: t?.type ?? t?.kind ?? t?.message_type ?? undefined,
            content,
            timestamp,
          }
        }),
      })
    } catch (e) {
      console.error('Failed to fetch thought chain:', e)
    }
  },
  forcePush: async (content) => {
    try {
      await get().apiFetch('/agent/force-push', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      })
      get().fetchThoughtChain()
    } catch (e) {
      console.error('Failed to force push:', e)
    }
  },
  summarizeMemory: async () => {
    try {
      await get().apiFetch('/agent/summarize-memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      get().fetchThoughtChain()
    } catch (e) {
      console.error('Failed to summarize memory:', e)
    }
  },
  

  
  tasks: [],
  fetchTasks: async () => {
    try {
      const res = await get().apiFetch('/tasks')
      const data = await res.json()
      set({ 
        tasks: data.map((t: any) => ({
          id: t.id,
          projectId: t.projectId || '',
          name: t.name || '未命名任务',
          description: t.description || '',
          status: (t.state === 'running' || t.state === 'pending' || t.state === 'completed' || t.state === 'error') 
            ? (t.state === 'error' ? 'failed' : t.state) 
            : 'pending',
          progress: t.state === 'completed' ? 100 : (t.progress || 50),
          creat_time: t.creat_time,
          logs: t.logs || [],
          history: t.history || [],
          createdAt: t.createdAt ? new Date(t.createdAt) : new Date(),
          updatedAt: t.updatedAt ? new Date(t.updatedAt) : new Date()
        })) 
      })
    } catch (e) {
      console.error('Failed to fetch tasks:', e)
    }
  },
  addTask: async (task) => {
    try {
      await get().apiFetch('/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(task)
      })
      get().fetchTasks()
    } catch (e) {
      console.error('Failed to add task:', e)
    }
  },
  removeTask: async (id) => {
    try {
      await get().apiFetch(`/tasks/${id}`, { method: 'DELETE' })
      get().fetchTasks()
    } catch (e) {
      console.error('Failed to remove task:', e)
    }
  },
  stopTask: async (id) => {
    try {
      await get().apiFetch(`/tasks/${id}/stop`, { method: 'POST' })
      get().fetchTasks()
    } catch (e) {
      console.error('Failed to stop task:', e)
    }
  },
  injectTask: async (taskId, content) => {
    try {
      await get().apiFetch(`/tasks/${taskId}/inject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      })
    } catch (e) {
      console.error('Failed to inject task:', e)
    }
  },

  // Schedule & Alarm
  scheduleItems: [],
  fetchSchedule: async () => {
    try {
      const res = await get().apiFetch('/schedule')
      const data = await res.json()
      set({ scheduleItems: Array.isArray(data) ? data : [] })
    } catch (e) {
      console.error('Failed to fetch schedule:', e)
    }
  },
  addSchedule: async (item) => {
    try {
      await get().apiFetch('/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item)
      })
      get().fetchSchedule()
    } catch (e) {
      console.error('Failed to add schedule:', e)
    }
  },
  removeSchedule: async (id) => {
    try {
      await get().apiFetch(`/schedule/${id}`, { method: 'DELETE' })
      get().fetchSchedule()
    } catch (e) {
      console.error('Failed to remove schedule:', e)
    }
  },

  alarms: [],
  fetchAlarms: async () => {
    try {
      const res = await get().apiFetch('/cron')
      const data = await res.json()
      set({ alarms: Array.isArray(data) ? data : [] })
    } catch (e) {
      console.error('Failed to fetch alarms:', e)
    }
  },
  addAlarm: async (item) => {
    try {
      await get().apiFetch('/cron', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item)
      })
      get().fetchAlarms()
    } catch (e) {
      console.error('Failed to add alarm:', e)
    }
  },
  updateAlarm: async (id, updates) => {
    try {
      await get().apiFetch(`/cron/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
      })
      get().fetchAlarms()
    } catch (e) {
      console.error('Failed to update alarm:', e)
    }
  },
  removeAlarm: async (id) => {
    try {
      await get().apiFetch(`/cron/${id}`, { method: 'DELETE' })
      get().fetchAlarms()
    } catch (e) {
      console.error('Failed to remove alarm:', e)
    }
  },

  toolGroups: [],
  fetchToolGroups: async () => {
    try {
      const res = await get().apiFetch('/tools');
      const data = await res.json();
      set({ toolGroups: data });
    } catch (error) {
      console.error("Failed to fetch tool groups:", error);
      set({ toolGroups: [] });
    }
  },
  
  skills: [],
  fetchSkills: async () => {
    try {
      const res = await get().apiFetch('/skills')
      const data = await res.json()
      set({ skills: data })
    } catch (e) {
      console.error('Failed to fetch skills:', e)
    }
  },
  
  modelConfig: {},
  fetchModelConfig: async () => {
    try {
      const res = await get().apiFetch('/config')
      const data = await res.json()
      if (data['model_config.json']) {
        set({ modelConfig: data['model_config.json'] })
      }
    } catch (e) {
      console.error('Failed to fetch model config:', e)
    }
  },
  updateModelConfig: async (key, config) => {
    try {
      const current = get().modelConfig
      const updated = { ...current, [key]: config }
      await get().apiFetch('/config/model_config.json', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updated)
      })
      set({ modelConfig: updated })
    } catch (e) {
      console.error('Failed to update model config:', e)
    }
  },
  
  files: {},
  fetchFile: async (path) => {
    try {
      const res = await get().apiFetch(`/files?path=${path}`)
      const data = await res.json()
      set((state) => ({
        files: {
          ...state.files,
          [path]: {
            path,
            content: data.content,
            lastModified: new Date()
          }
        }
      }))
    } catch (e) {
      console.error('Failed to fetch file:', e)
    }
  },
  updateFile: async (path, content) => {
    try {
      await get().apiFetch(`/files?path=${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      })
      get().fetchFile(path)
    } catch (e) {
      console.error('Failed to update file:', e)
    }
  },
  
  plugins: [],
  fetchPlugins: async () => {
    try {
      const res = await get().apiFetch('/plugins')
      const data = await res.json()
      set({ plugins: data })
    } catch (e) {
      console.error('Failed to fetch plugins:', e)
    }
  },
  togglePlugin: async (name) => {
    try {
      await get().apiFetch(`/plugins/${name}/toggle`, { method: 'POST' })
      get().fetchPlugins()
    } catch (e) {
       console.error('Failed to toggle plugin:', e)
     }
   },
   
   databases: [],
   fetchDatabases: async () => {
     try {
       const res = await get().apiFetch('/databases')
       const data = await res.json()
       set({ databases: data })
     } catch (e) {
       console.error('Failed to fetch databases:', e)
     }
   },
   
   configs: [],
  fetchConfigs: async () => {
    try {
      const res = await get().apiFetch('/config')
      const data = await res.json()
      const categories: ConfigCategory[] = Object.entries(data).map(([filename, content]: [string, any]) => ({
        name: filename,
        items: Array.isArray(content) ? [
          {
            key: 'rss_subscriptions',
            value: content,
            type: 'object'
          }
        ] : Object.entries(content).map(([key, value]) => {
          let type: 'string' | 'number' | 'boolean' | 'object' = 'string'
          if (typeof value === 'boolean') type = 'boolean'
          else if (typeof value === 'number') type = 'number'
          else if (typeof value === 'object' && value !== null) type = 'object'
          
          return {
            key,
            value,
            type
          }
        })
      }))
      set({ configs: categories })
    } catch (e) {
      console.error('Failed to fetch configs:', e)
    }
  },
  updateConfig: async (categoryName, key, value) => {
    try {
      const category = get().configs.find(c => c.name === categoryName)
      if (!category) return
      
      let configObj: any
      
      // 处理 RSS 配置的特殊情况（数组类型）
      if (categoryName === 'rss_config.json' && key === 'rss_subscriptions') {
        configObj = value
      } else {
        const updatedItems = category.items.map(item => 
          item.key === key ? { ...item, value } : item
        )
        
        configObj = {}
        updatedItems.forEach(item => {
          configObj[item.key] = item.value
        })
      }
      
      await get().apiFetch(`/config/${categoryName}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(configObj)
      })
      get().fetchConfigs()
    } catch (e) {
      console.error('Failed to update config:', e)
    }
  },
  
  clearScreenMode: false,
  toggleClearScreenMode: () =>
    set((state) => ({
      clearScreenMode: !state.clearScreenMode,
    })),
}))

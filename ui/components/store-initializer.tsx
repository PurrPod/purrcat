'use client'

import { useEffect, useRef } from 'react'
import { useAppStore } from '@/lib/store'

export function StoreInitializer() {
  const refreshAll = useAppStore((state) => state.refreshAll)
  const fetchFile = useAppStore((state) => state.fetchFile)
  const fetchMessages = useAppStore((state) => state.fetchMessages)
  const fetchProjects = useAppStore((state) => state.fetchProjects)
  const fetchTasks = useAppStore((state) => state.fetchTasks)
  const fetchThoughtChain = useAppStore((state) => state.fetchThoughtChain)
  const fetchModelConfig = useAppStore((state) => state.fetchModelConfig)
  const fetchSchedule = useAppStore((state) => state.fetchSchedule)
  const fetchAlarms = useAppStore((state) => state.fetchAlarms)
  const connectionStatus = useAppStore((state) => state.connectionStatus)
  const reconnectNow = useAppStore((state) => state.reconnectNow)
  const setConnectionStatus = useAppStore((state) => state.setConnectionStatus)
  const backoffRef = useRef(1500)
  const reconnectTimerRef = useRef<number | null>(null)

  useEffect(() => {
    refreshAll()

    // Fetch system files for sidebar
    fetchFile('user_profile')
    fetchFile('me')
    fetchFile('soul')

    // Refresh every 5 seconds for messages, projects, tasks
    const interval = setInterval(() => {
      if (useAppStore.getState().connectionStatus !== 'connected') return
      fetchMessages()
      fetchProjects()
      fetchTasks()
      fetchThoughtChain()
      fetchModelConfig()
      fetchSchedule()
      fetchAlarms()
    }, 5000)

    return () => clearInterval(interval)
  }, [fetchAlarms, fetchFile, fetchMessages, fetchModelConfig, fetchProjects, fetchSchedule, fetchTasks, fetchThoughtChain, refreshAll])

  useEffect(() => {
    const onOnline = () => {
      reconnectNow()
    }
    const onOffline = () => {
      setConnectionStatus('disconnected', 'offline')
    }

    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
    }
  }, [reconnectNow, setConnectionStatus])

  useEffect(() => {
    if (reconnectTimerRef.current != null) {
      window.clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }

    if (connectionStatus === 'connected') {
      backoffRef.current = 1500
      return
    }

    const schedule = () => {
      reconnectTimerRef.current = window.setTimeout(async () => {
        if (useAppStore.getState().connectionStatus === 'connected') {
          backoffRef.current = 1500
          return
        }

        const ok = await reconnectNow()
        if (!ok) {
          backoffRef.current = Math.min(Math.round(backoffRef.current * 1.7), 30000)
          schedule()
        } else {
          backoffRef.current = 1500
        }
      }, backoffRef.current)
    }

    schedule()

    return () => {
      if (reconnectTimerRef.current != null) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
    }
  }, [connectionStatus, reconnectNow])

  return null
}

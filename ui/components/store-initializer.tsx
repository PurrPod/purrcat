'use client'

import { useEffect } from 'react'
import { useAppStore } from '@/lib/store'

export function StoreInitializer() {
  const fetchMessages = useAppStore((state) => state.fetchMessages)
  const fetchProjects = useAppStore((state) => state.fetchProjects)
  const fetchTasks = useAppStore((state) => state.fetchTasks)
  const fetchConfigs = useAppStore((state) => state.fetchConfigs)
  const fetchPlugins = useAppStore((state) => state.fetchPlugins)
  const fetchSkills = useAppStore((state) => state.fetchSkills)
  const fetchDatabases = useAppStore((state) => state.fetchDatabases)
  const fetchThoughtChain = useAppStore((state) => state.fetchThoughtChain)
  const fetchModelConfig = useAppStore((state) => state.fetchModelConfig)
  const fetchFile = useAppStore((state) => state.fetchFile)

  useEffect(() => {
    // Initial fetch
    fetchMessages()
    fetchProjects()
    fetchTasks()
    fetchConfigs()
    fetchPlugins()
    fetchSkills()
    fetchDatabases()
    fetchThoughtChain()
    fetchModelConfig()
    
    // Fetch system files for sidebar
    fetchFile('user_profile')
    fetchFile('me')
    fetchFile('soul')

    // Refresh every 5 seconds for messages, projects, tasks
    const interval = setInterval(() => {
      fetchMessages()
      fetchProjects()
      fetchTasks()
      fetchThoughtChain()
      fetchModelConfig()
    }, 5000)

    return () => clearInterval(interval)
  }, [fetchMessages, fetchProjects, fetchTasks, fetchConfigs, fetchPlugins, fetchSkills, fetchThoughtChain, fetchModelConfig])

  return null
}

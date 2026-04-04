'use client'

import React, { useEffect, useState } from 'react'
import Link from 'next/link'
import { Cat, Github, Star, GitFork } from 'lucide-react'

interface GitHubStats {
  stars: number | null
  forks: number | null
}

export function TopBar() {
  const [stats, setStats] = useState<GitHubStats>({ stars: null, forks: null })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchGitHubStats = async () => {
      try {
        const response = await fetch('https://api.github.com/repos/PurrPod/cat-in-cup', {
          headers: {
            'Accept': 'application/vnd.github.v3+json'
          }
        })
        
        if (!response.ok) {
          throw new Error('Failed to fetch')
        }
        
        const data = await response.json()
        setStats({
          stars: data.stargazers_count,
          forks: data.forks_count
        })
      } catch (error) {
        console.error('Failed to fetch GitHub stats:', error)
        setStats({ stars: null, forks: null })
      } finally {
        setLoading(false)
      }
    }

    fetchGitHubStats()
  }, [])

  const formatNumber = (num: number | null): string => {
    if (num === null) return '--'
    if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'k'
    }
    return num.toString()
  }

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex h-14 items-center justify-end px-6">
        {/* Right: GitHub Stats */}
        <Link
          href="https://github.com/PurrPod/cat-in-cup"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 px-4 py-2 rounded-full bg-muted/50 hover:bg-muted transition-colors"
          title="GitHub Repository"
        >
          <Github className="size-5 text-muted-foreground" />
          
          {/* 仓库名 */}
          <span className="text-sm font-medium text-foreground">cat-in-cup</span>
          
          {/* 分隔线 */}
          <div className="h-4 w-px bg-border/60" />
          
          <div className="flex items-center gap-3 text-sm">
            {/* Stars */}
            <div className="flex items-center gap-1.5">
              <Star className="size-4 text-yellow-500" />
              <span className="font-medium text-muted-foreground min-w-[2rem]">
                {loading ? '...' : formatNumber(stats.stars)}
              </span>
            </div>
            
            {/* 分隔线 */}
            <div className="h-4 w-px bg-border/60" />
            
            {/* Forks */}
            <div className="flex items-center gap-1.5">
              <GitFork className="size-4 text-blue-500" />
              <span className="font-medium text-muted-foreground min-w-[2rem]">
                {loading ? '...' : formatNumber(stats.forks)}
              </span>
            </div>
          </div>
        </Link>
      </div>
    </header>
  )
}

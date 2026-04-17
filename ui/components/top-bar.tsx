'use client'

import React from 'react'
import Link from 'next/link'
import { Cat, Github, Book } from 'lucide-react'

export function TopBar() {
  return (
    <header className="sticky top-0 z-50 w-full bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex h-14 items-center justify-end px-6 gap-3">
        {/* GitHub Link */}
        <Link
          href="https://github.com/PurrPod/cat-in-cup"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center w-10 h-10 rounded-full bg-muted/50 hover:bg-muted transition-colors"
          title="GitHub Repository"
        >
          <Github className="size-5 text-muted-foreground" />
        </Link>
        
        {/* Book Link */}
        <Link
          href="https://purrpod.github.io/"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center w-10 h-10 rounded-full bg-muted/50 hover:bg-muted transition-colors"
          title="Documentation"
        >
          <Book className="size-5 text-muted-foreground" />
        </Link>
      </div>
    </header>
  )
}

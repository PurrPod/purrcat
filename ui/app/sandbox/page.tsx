'use client'

import React, { useState } from 'react'
import { 
  File, 
  Folder, 
  ChevronRight, 
  ChevronDown, 
  Search, 
  RefreshCw, 
  Plus, 
  Save,
  Terminal,
  Play
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { 
  ResizableHandle, 
  ResizablePanel, 
  ResizablePanelGroup 
} from "@/components/ui/resizable"

interface FileItem {
  name: string
  type: 'file' | 'folder'
  children?: FileItem[]
  content?: string
  path: string
}

const mockFiles: FileItem[] = [
  {
    name: 'agent_vm',
    type: 'folder',
    path: '/agent_vm',
    children: [
      {
        name: 'src',
        type: 'folder',
        path: '/agent_vm/src',
        children: [
          { name: 'main.py', type: 'file', path: '/agent_vm/src/main.py', content: 'print("Hello from Agent VM")' },
          { name: 'utils.py', type: 'file', path: '/agent_vm/src/utils.py', content: 'def helper():\n    pass' }
        ]
      },
      { name: 'requirements.txt', type: 'file', path: '/agent_vm/requirements.txt', content: 'openai\nrequests' },
      { name: 'README.md', type: 'file', path: '/agent_vm/README.md', content: '# Agent Workspace' }
    ]
  }
]

export default function SandboxPage() {
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null)
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['/agent_vm']))

  const toggleFolder = (path: string) => {
    const next = new Set(expandedFolders)
    if (next.has(path)) next.delete(path)
    else next.add(path)
    setExpandedFolders(next)
  }

  const renderTree = (items: FileItem[], depth = 0) => {
    return items.map((item) => {
      const isExpanded = expandedFolders.has(item.path)
      const isSelected = selectedFile?.path === item.path

      return (
        <div key={item.path}>
          <div
            className={cn(
              "flex items-center gap-2 px-2 py-1 cursor-pointer hover:bg-muted/50 transition-colors",
              isSelected && "bg-primary/10 text-primary"
            )}
            style={{ paddingLeft: `${depth * 12 + 8}px` }}
            onClick={() => {
              if (item.type === 'folder') toggleFolder(item.path)
              else setSelectedFile(item)
            }}
          >
            {item.type === 'folder' ? (
              <>
                {isExpanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
                <Folder className="size-4 fill-primary/20 text-primary" />
              </>
            ) : (
              <>
                <div className="size-3.5" />
                <File className="size-4 text-muted-foreground" />
              </>
            )}
            <span className="text-sm truncate">{item.name}</span>
          </div>
          {item.type === 'folder' && isExpanded && item.children && (
            <div>{renderTree(item.children, depth + 1)}</div>
          )}
        </div>
      )
    })
  }

  return (
    <div className="flex h-full flex-col bg-background">
      {/* Header Toolbar */}
      <div className="flex items-center justify-between border-b px-4 py-2 bg-muted/20">
        <div className="flex items-center gap-4">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <Terminal className="size-4" />
            Sandbox Workspace
          </h2>
          <div className="flex items-center gap-1">
            <button className="p-1 hover:bg-muted rounded transition-colors" title="New File">
              <Plus className="size-4" />
            </button>
            <button className="p-1 hover:bg-muted rounded transition-colors" title="Refresh">
              <RefreshCw className="size-4" />
            </button>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button className="flex items-center gap-1.5 px-3 py-1 bg-primary text-primary-foreground rounded text-xs font-medium hover:bg-primary/90 transition-colors">
            <Play className="size-3" />
            Run
          </button>
          <button className="flex items-center gap-1.5 px-3 py-1 bg-muted text-muted-foreground border rounded text-xs font-medium hover:bg-muted/80 transition-colors">
            <Save className="size-3" />
            Save
          </button>
        </div>
      </div>

      <ResizablePanelGroup direction="horizontal" className="flex-1">
        {/* File Explorer */}
        <ResizablePanel defaultSize={20} minSize={15} maxSize={40}>
          <div className="h-full border-r bg-muted/5">
            <div className="p-2 border-b">
              <div className="relative">
                <Search className="absolute left-2 top-2.5 size-3.5 text-muted-foreground" />
                <input 
                  placeholder="Search files..." 
                  className="w-full bg-muted/50 border-none rounded px-8 py-1.5 text-xs focus:ring-1 focus:ring-primary outline-none"
                />
              </div>
            </div>
            <div className="py-2 overflow-y-auto">
              {renderTree(mockFiles)}
            </div>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Editor Area */}
        <ResizablePanel defaultSize={80}>
          {selectedFile ? (
            <div className="flex flex-col h-full">
              <div className="flex items-center gap-2 px-4 py-2 border-b bg-muted/10">
                <File className="size-3.5 text-muted-foreground" />
                <span className="text-xs font-medium">{selectedFile.path}</span>
              </div>
              <div className="flex-1 p-4 font-mono text-sm overflow-auto">
                <pre className="text-foreground/80 leading-relaxed">
                  {selectedFile.content || "// No content"}
                </pre>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground/40">
              <Terminal className="size-12 mb-4 opacity-10" />
              <p className="text-sm italic">Select a file to view its content</p>
            </div>
          )}
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}

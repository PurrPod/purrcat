'use client'

import { useState, useRef } from 'react'
import { useAppStore } from '@/lib/store'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Send, Paperclip, Wand2, Database } from 'lucide-react'

// 模拟数据库列表
const mockDatabases = [
  { id: 'db1', name: 'users_db' },
  { id: 'db2', name: 'products_db' },
  { id: 'db3', name: 'logs_db' },
]

export function MessageInput() {
  const [message, setMessage] = useState('')
  const [skillDialogOpen, setSkillDialogOpen] = useState(false)
  const [dbDialogOpen, setDbDialogOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  const addMessage = useAppStore((state) => state.addMessage)
  const skills = useAppStore((state) => state.skills)
  const databases = useAppStore((state) => state.databases)

  const handleSend = () => {
    if (!message.trim()) return
    
    addMessage({
      role: 'user',
      content: message,
    })
    setMessage('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      // 模拟文件路径（实际应用中会是真实路径）
      const fakePath = `/uploads/${file.name}`
      setMessage((prev) => prev + (prev ? '\n' : '') + `[文件: ${fakePath}]`)
    }
    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleSkillSelect = (skillPath: string) => {
    setMessage((prev) => prev + (prev ? '\n' : '') + `[Skill: ${skillPath}]`)
    setSkillDialogOpen(false)
  }

  const handleDatabaseSelect = (dbName: string) => {
    setMessage((prev) => prev + (prev ? '\n' : '') + `[数据库: ${dbName}]`)
    setDbDialogOpen(false)
  }

  return (
    <div className="border-t pt-4">
      <div className="flex gap-2 mb-2">
        {/* 上传文件按钮 */}
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          onChange={handleFileSelect}
        />
        <Button
          variant="outline"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
        >
          <Paperclip className="size-4 mr-1" />
          上传文件
        </Button>

        {/* 上传 Skill 按钮 */}
        <Dialog open={skillDialogOpen} onOpenChange={setSkillDialogOpen}>
          <DialogTrigger asChild>
            <Button variant="outline" size="sm">
              <Wand2 className="size-4 mr-1" />
              选择 Skill
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>选择 Skill</DialogTitle>
            </DialogHeader>
            <ScrollArea className="h-64">
              <div className="flex flex-col gap-2">
                {skills.map((skill) => (
                  <button
                    key={skill.name}
                    onClick={() => handleSkillSelect(skill.path)}
                    className="flex flex-col items-start p-3 rounded-lg border hover:bg-accent transition-colors text-left"
                  >
                    <span className="font-medium text-sm">{skill.name}</span>
                    {skill.description && (
                      <span className="text-xs text-muted-foreground">
                        {skill.description}
                      </span>
                    )}
                    <span className="text-xs text-muted-foreground mt-1 font-mono">
                      {skill.path}
                    </span>
                  </button>
                ))}
              </div>
            </ScrollArea>
          </DialogContent>
        </Dialog>

        {/* 上传数据库按钮 */}
        <Dialog open={dbDialogOpen} onOpenChange={setDbDialogOpen}>
          <DialogTrigger asChild>
            <Button variant="outline" size="sm">
              <Database className="size-4 mr-1" />
              插入数据库
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>选择数据库</DialogTitle>
            </DialogHeader>
            <ScrollArea className="h-60">
              <div className="flex flex-col gap-2 p-1">
                {databases.map((dbName) => (
                  <Button
                    key={dbName}
                    variant="ghost"
                    className="justify-start font-normal"
                    onClick={() => handleDatabaseSelect(dbName)}
                  >
                    <Database className="size-4 mr-2" />
                    {dbName}
                  </Button>
                ))}
                {databases.length === 0 && (
                  <div className="text-center py-8 text-muted-foreground text-sm">
                    未发现可用数据库
                  </div>
                )}
              </div>
            </ScrollArea>
          </DialogContent>
        </Dialog>
      </div>

      <div className="flex gap-2">
        <Textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
          className="min-h-20 resize-none"
        />
        <Button onClick={handleSend} className="h-auto">
          <Send className="size-4" />
        </Button>
      </div>
    </div>
  )
}

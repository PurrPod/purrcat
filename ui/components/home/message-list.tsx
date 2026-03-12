'use client'

import { useAppStore } from '@/lib/store'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import { cn } from '@/lib/utils'
import { User, Bot, Terminal, Trash2 } from 'lucide-react'
import type { Message } from '@/lib/types'

function MessageItem({ message }: { message: Message }) {
  const removeMessage = useAppStore((state) => state.removeMessage)

  const getRoleIcon = () => {
    switch (message.role) {
      case 'user':
        return <User className="size-4" />
      case 'agent':
        return <Bot className="size-4" />
      case 'system':
        return <Terminal className="size-4" />
    }
  }

  const getRoleStyle = () => {
    switch (message.role) {
      case 'user':
        return 'bg-primary/10 border-primary/20'
      case 'agent':
        return 'bg-accent border-accent-foreground/20'
      case 'system':
        return 'bg-muted border-muted-foreground/20 text-muted-foreground text-xs'
    }
  }

  const getRoleLabel = () => {
    switch (message.role) {
      case 'user':
        return '用户'
      case 'agent':
        return 'Agent'
      case 'system':
        return message.type ? `系统 (${message.type})` : '系统'
    }
  }

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <div
          className={cn(
            'rounded-lg border p-3 transition-colors hover:bg-accent/50 cursor-context-menu',
            getRoleStyle()
          )}
        >
          <div className="flex items-center gap-2 mb-2">
            <div className="flex items-center justify-center size-6 rounded-full bg-background border">
              {getRoleIcon()}
            </div>
            <span className="text-xs font-medium">{getRoleLabel()}</span>
            <span className="text-xs text-muted-foreground ml-auto">
              {message.timestamp.toLocaleTimeString('zh-CN')}
            </span>
          </div>
          <div className="text-sm whitespace-pre-wrap pl-8">{message.content}</div>
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuItem
          variant="destructive"
          onClick={() => removeMessage(message.id)}
        >
          <Trash2 className="size-4 mr-2" />
          踢出全局消息列
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  )
}

export function MessageList() {
  const messages = useAppStore((state) => state.messages)

  return (
    <ScrollArea className="flex-1 pr-4">
      <div className="flex flex-col gap-3 pb-4">
        {messages
          .sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())
          .map((message) => (
            <MessageItem key={message.id} message={message} />
          ))}
      </div>
    </ScrollArea>
  )
}

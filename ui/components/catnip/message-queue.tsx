'use client'

import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Info, AlertCircle, CheckCircle2, MessageSquare, ListTodo, ChevronDown, ExternalLink } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { useAppStore } from '@/lib/store'
import { useRouter } from 'next/navigation'

interface Message {
  id: string
  type: 'info' | 'success' | 'warning' | 'error' | 'agent'
  title: string
  content: string
  timestamp: string
  taskId?: string
}

interface MessageQueueProps {
  messages: Message[]
  className?: string
}

export function MessageQueue({ messages, className }: MessageQueueProps) {
  const [selectedMessage, setSelectedMessage] = useState<Message | null>(null)
  const [queueType, setQueueType] = useState<'messages' | 'tasks'>('messages')
  const tasks = useAppStore((state) => state.tasks)
  const router = useRouter()

  const handleTaskClick = (taskId: string) => {
    router.push(`/task`)
    // 这里可以添加逻辑来自动选择对应的任务
    // 由于需要状态管理，暂时只跳转到任务页面
  }

  return (
    <div className={cn("flex flex-col h-full", className)}>
      <div className="bg-muted/40 rounded-[24px] m-4 overflow-hidden shadow-sm h-full flex flex-col">
        {/* 队列切换标签 */}
        <div className="flex items-center justify-between p-4 border-b border-border/50">
          <div className="flex items-center gap-2">
            <div className="flex gap-1 bg-muted/60 p-1 rounded-full">
              <button
                onClick={() => setQueueType('messages')}
                className={cn(
                  "px-3 py-1 rounded-full text-xs font-medium transition-all",
                  queueType === 'messages' 
                    ? "bg-background shadow-sm text-foreground" 
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <MessageSquare className="size-3 inline mr-1" />
                消息
              </button>
              <button
                onClick={() => setQueueType('tasks')}
                className={cn(
                  "px-3 py-1 rounded-full text-xs font-medium transition-all",
                  queueType === 'tasks' 
                    ? "bg-background shadow-sm text-foreground" 
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <ListTodo className="size-3 inline mr-1" />
                任务
              </button>
            </div>
          </div>
          <span className="text-[10px] bg-muted text-muted-foreground px-2 py-0.5 rounded-full">
            {queueType === 'messages' ? messages.length : tasks.length} 项
          </span>
        </div>

        {/* 队列内容 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2 scrollbar-thin">
          <AnimatePresence initial={false}>
            {queueType === 'messages' ? (
              messages.length === 0 ? (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-center py-12 text-muted-foreground/40"
                >
                  <Info className="size-8 mx-auto mb-2 opacity-10" />
                  <p className="text-xs italic">暂无消息</p>
                </motion.div>
              ) : (
                messages.slice().reverse().map((msg) => (
                  <motion.div
                    key={msg.id}
                    initial={{ x: 10, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    exit={{ x: 10, opacity: 0 }}
                    onClick={() => setSelectedMessage(msg)}
                    className={cn(
                      "p-5 rounded-lg border bg-background/60 shadow-sm transition-all duration-200 hover:bg-background cursor-pointer group",
                      msg.type === 'error' && "border-destructive/20",
                      msg.type === 'success' && "border-green-500/20",
                      msg.type === 'warning' && "border-amber-500/20",
                      msg.type === 'info' && "border-blue-500/20",
                      msg.type === 'agent' && "border-primary/20"
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <div className={cn(
                        "mt-0.5 shrink-0 opacity-70",
                        msg.type === 'error' && "text-destructive",
                        msg.type === 'success' && "text-green-500",
                        msg.type === 'warning' && "text-amber-500",
                        msg.type === 'info' && "text-blue-500",
                        msg.type === 'agent' && "text-primary"
                      )}>
                        {msg.type === 'error' && <AlertCircle className="size-4" />}
                        {msg.type === 'success' && <CheckCircle2 className="size-4" />}
                        {msg.type === 'warning' && <AlertCircle className="size-4" />}
                        {msg.type === 'info' && <Info className="size-4" />}
                        {msg.type === 'agent' && <MessageSquare className="size-4" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <p className="text-sm font-bold truncate leading-none text-foreground/80">
                            {msg.title}
                          </p>
                          <span className="text-xs text-muted-foreground whitespace-nowrap">
                            {msg.timestamp}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
                          {msg.content}
                        </p>
                      </div>
                    </div>
                  </motion.div>
                ))
              )
            ) : (
              tasks.length === 0 ? (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-center py-12 text-muted-foreground/40"
                >
                  <ListTodo className="size-8 mx-auto mb-2 opacity-10" />
                  <p className="text-xs italic">暂无任务</p>
                </motion.div>
              ) : (
                tasks.map((task) => (
                  <motion.div
                    key={task.id}
                    initial={{ x: 10, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    exit={{ x: 10, opacity: 0 }}
                    onClick={() => handleTaskClick(task.id)}
                    className="p-4 rounded-lg border bg-background/60 shadow-sm transition-all duration-200 hover:bg-background cursor-pointer group"
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 shrink-0 opacity-70 text-primary">
                        <ListTodo className="size-4" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <p className="text-sm font-bold truncate leading-none text-foreground/80">
                            {task.name}
                          </p>
                          <span className={cn(
                            'text-xs px-2 py-0.5 rounded-full shrink-0',
                            task.status === 'running' && 'bg-blue-500/10 text-blue-500',
                            task.status === 'pending' && 'bg-amber-500/10 text-amber-500',
                            task.status === 'completed' && 'bg-green-500/10 text-green-500',
                            task.status === 'failed' && 'bg-red-500/10 text-red-500'
                          )}>
                            {task.status === 'running' && '运行中'}
                            {task.status === 'pending' && '等待中'}
                            {task.status === 'completed' && '已完成'}
                            {task.status === 'failed' && '失败'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>{task.progress}% 完成</span>
                          <button className="flex items-center gap-1 hover:text-primary transition-colors">
                            查看 <ExternalLink className="size-3" />
                          </button>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                ))
              )
            )}
          </AnimatePresence>
        </div>
      </div>

      <Dialog open={!!selectedMessage} onOpenChange={(open) => !open && setSelectedMessage(null)}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <MessageSquare className="size-5 text-primary" />
              消息详情
            </DialogTitle>
            <DialogDescription>查看完整消息内容</DialogDescription>
          </DialogHeader>
          {selectedMessage && (
            <div className="space-y-4 py-4">
              <div className="flex justify-between items-center text-xs text-muted-foreground">
                <span className="capitalize px-2 py-0.5 rounded-full bg-muted">
                  类型: {selectedMessage.type}
                </span>
                <span>{selectedMessage.timestamp}</span>
              </div>
              <h4 className="font-bold text-sm">{selectedMessage.title}</h4>
              <div className="bg-muted/40 p-4 rounded-lg border border-border/50 max-h-[200px] overflow-y-auto scrollbar-thin">
                <p className="text-sm leading-relaxed whitespace-pre-wrap">
                  {selectedMessage.content}
                </p>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

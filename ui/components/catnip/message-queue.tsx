'use client'

import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Info, AlertCircle, CheckCircle2, MessageSquare } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"

interface Message {
  id: string
  type: 'info' | 'success' | 'warning' | 'error' | 'agent'
  title: string
  content: string
  timestamp: string
}

interface MessageQueueProps {
  messages: Message[]
  className?: string
}

export function MessageQueue({ messages, className }: MessageQueueProps) {
  const [selectedMessage, setSelectedMessage] = useState<Message | null>(null)

  return (
    <div className={cn("flex flex-col h-full", className)}>
      <div className="flex items-center justify-between p-4 pb-2 border-b">
        <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
          <MessageSquare className="size-4" />
          系统消息列表
        </h3>
        <span className="text-[10px] bg-muted text-muted-foreground px-2 py-0.5 rounded-full">
          {messages.length} 条消息
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        <AnimatePresence initial={false}>
          {messages.length === 0 ? (
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
                  "p-3 rounded-lg border bg-muted/30 shadow-sm transition-all duration-200 hover:bg-muted/60 cursor-pointer group",
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
                    {msg.type === 'error' && <AlertCircle className="size-3.5" />}
                    {msg.type === 'success' && <CheckCircle2 className="size-3.5" />}
                    {msg.type === 'warning' && <AlertCircle className="size-3.5" />}
                    {msg.type === 'info' && <Info className="size-3.5" />}
                    {msg.type === 'agent' && <MessageSquare className="size-3.5" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <p className="text-[11px] font-bold truncate leading-none text-foreground/80">
                        {msg.title}
                      </p>
                      <span className="text-[9px] text-muted-foreground whitespace-nowrap">
                        {msg.timestamp}
                      </span>
                    </div>
                    <p className="text-[10px] text-muted-foreground leading-relaxed line-clamp-2">
                      {msg.content}
                    </p>
                  </div>
                </div>
              </motion.div>
            ))
          )}
        </AnimatePresence>
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
              <div className="bg-muted/40 p-4 rounded-lg border border-border/50 max-h-[200px] overflow-y-auto">
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

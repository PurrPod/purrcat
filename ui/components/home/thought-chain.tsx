'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { useAppStore } from '@/lib/store'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Brain, Play, Eye, Send, AlertCircle, RefreshCcw, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { ThoughtChain } from '@/lib/types'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

function ThoughtItem({ thought }: { thought: ThoughtChain }) {
  return (
    <div className="rounded-lg border bg-card p-3 shadow-sm transition-all hover:shadow-md">
      <div className="flex items-center gap-2 mb-2">
        <div className="flex items-center justify-center size-5 rounded-full bg-primary/10 text-primary text-[10px] font-bold">
          {thought.step}
        </div>
        <span className="text-[10px] text-muted-foreground font-mono">
          {thought.timestamp.toLocaleTimeString('zh-CN')}
        </span>
      </div>
      
      <div className="space-y-2 pl-7">
        <div className="flex items-start gap-2">
          <Brain className="size-3.5 text-blue-500 mt-0.5 shrink-0" />
          <div className="text-sm leading-relaxed text-foreground/90">
            {thought.thought}
          </div>
        </div>
        
        {thought.action && (
          <div className="flex items-start gap-2 bg-muted/30 p-2 rounded-md border border-border/50">
            <Play className="size-3.5 text-green-500 mt-0.5 shrink-0" />
            <div className="text-xs font-mono break-all">
              <span className="text-muted-foreground block mb-1 uppercase tracking-tighter text-[9px]">Action</span>
              {thought.action}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export function ThoughtChainPanel() {
  const thoughtChain = useAppStore((state) => state.thoughtChain)
  const forcePush = useAppStore((state) => state.forcePush)
  const summarizeMemory = useAppStore((state) => state.summarizeMemory)
  const [pushContent, setPushContent] = useState('')
  const [isPushing, setIsPushing] = useState(false)
  const [isSummarizing, setIsSummarizing] = useState(false)
  const [cooldownTime, setCooldownTime] = useState(0)
  const [isAtBottom, setIsAtBottom] = useState(true)
  const [showScrollButton, setShowScrollButton] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Cooldown timer effect
  useEffect(() => {
    if (cooldownTime > 0) {
      const timer = setTimeout(() => {
        setCooldownTime(cooldownTime - 1)
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [cooldownTime])

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    if (scrollRef.current) {
      const scrollContainer = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]')
      if (scrollContainer) {
        scrollContainer.scrollTo({
          top: scrollContainer.scrollHeight,
          behavior
        })
      }
    }
  }, [])

  // Handle scroll event to detect if we are at bottom
  const handleScroll = useCallback(() => {
    if (scrollRef.current) {
      const scrollContainer = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]')
      if (scrollContainer) {
        const { scrollTop, scrollHeight, clientHeight } = scrollContainer
        const isBottom = Math.abs(scrollHeight - clientHeight - scrollTop) < 50
        setIsAtBottom(isBottom)
        setShowScrollButton(!isBottom && scrollHeight > clientHeight)
      }
    }
  }, [])

  useEffect(() => {
    const scrollContainer = scrollRef.current?.querySelector('[data-radix-scroll-area-viewport]')
    if (scrollContainer) {
      scrollContainer.addEventListener('scroll', handleScroll)
      return () => scrollContainer.removeEventListener('scroll', handleScroll)
    }
  }, [handleScroll])

  // Auto-scroll logic
  useEffect(() => {
    if (isAtBottom) {
      scrollToBottom('smooth')
    }
  }, [thoughtChain, isAtBottom, scrollToBottom])

  const handleForcePush = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!pushContent.trim() || isPushing) return
    
    setIsPushing(true)
    try {
      await forcePush(pushContent)
      setPushContent('')
    } finally {
      setIsPushing(false)
    }
  }

  const handleSummarizeMemory = async () => {
    if (isSummarizing || thoughtChain.length <= 40 || cooldownTime > 0) return
    setIsSummarizing(true)
    try {
      await summarizeMemory()
    } finally {
      setIsSummarizing(false)
      setCooldownTime(30) // Start 30s cooldown
    }
  }

  const canSummarize = thoughtChain.length > 40
  const isSummarizeButtonDisabled = isSummarizing || !canSummarize || cooldownTime > 0

  return (
    <div className="flex flex-col h-full overflow-hidden relative">
      <div className="flex items-center justify-between pb-3 border-b mb-3 shrink-0 px-1">
        <div className="flex items-center gap-2">
          <div className="p-1 bg-primary/10 rounded">
            <Brain className="size-4 text-primary" />
          </div>
          <h3 className="text-sm font-bold tracking-tight text-foreground/80 uppercase">Agent 思考链</h3>
        </div>
        <div className="flex items-center gap-2">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button 
                  variant="ghost" 
                  size="icon" 
                  className="size-7 text-muted-foreground hover:text-primary disabled:opacity-50 disabled:cursor-not-allowed"
                  onClick={handleSummarizeMemory}
                  disabled={isSummarizeButtonDisabled}
                >
                  <RefreshCcw className={isSummarizing ? "size-4 animate-spin" : "size-4"} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {isSummarizing ? (
                  <p>正在压缩记忆...</p>
                ) : !canSummarize ? (
                  <p>思考链步数需大于 40</p>
                ) : cooldownTime > 0 ? (
                  <p>请在 {cooldownTime} 秒后重试</p>
                ) : (
                  <p>压缩记忆</p>
                )}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <span className="px-2 py-0.5 bg-muted rounded-full text-[10px] font-mono text-muted-foreground border">
            {thoughtChain.length} STEPS
          </span>
        </div>
      </div>
      
      <div className="flex-1 relative min-h-0 overflow-hidden group/scroll">
        <ScrollArea ref={scrollRef} className="h-full">
          <div className="flex flex-col gap-3 pr-4 pb-4">
            {thoughtChain
              .sort((a, b) => Number(a.id) - Number(b.id))
              .map((thought) => (
                <ThoughtItem key={thought.id} thought={thought} />
              ))}
          </div>
        </ScrollArea>

        {/* Floating scroll to bottom button */}
        {showScrollButton && (
          <Button
            size="icon"
            variant="secondary"
            className="absolute bottom-4 right-6 size-8 rounded-full shadow-lg border animate-in fade-in zoom-in duration-200"
            onClick={() => scrollToBottom('smooth')}
          >
            <ChevronDown className="size-4" />
          </Button>
        )}
      </div>

      {/* Force Push 输入框 */}
      <div className="mt-3 pt-3 border-t shrink-0 px-1">
        <form onSubmit={handleForcePush} className="space-y-2">
          <div className="flex items-center gap-2">
            <AlertCircle className="size-3 text-amber-500" />
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Force Push 注入</span>
          </div>
          <div className="flex items-stretch gap-2">
            <div className="relative flex-1">
              <Input
                value={pushContent}
                onChange={(e) => setPushContent(e.target.value)}
                placeholder="强行注入对话历史..."
                className="text-xs h-9 bg-muted/20 border-border focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:border-primary/40 transition-all pr-8 shadow-none outline-none ring-0"
              />
              <div className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none opacity-30">
                <Send className="size-3" />
              </div>
            </div>
            <Button 
              type="submit" 
              size="sm" 
              variant="secondary" 
              className="h-9 px-4 border border-border/50 font-medium text-xs shadow-sm active:scale-95 transition-all shrink-0"
              disabled={isPushing || !pushContent.trim()}
            >
              {isPushing ? (
                <RefreshCcw className="size-3.5 animate-spin" />
              ) : (
                '注入'
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}

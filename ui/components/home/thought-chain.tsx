'use client'

import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { useAppStore } from '@/lib/store'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Brain, Send, AlertCircle, RefreshCcw, ChevronDown, User, Wrench, MessageSquare, AlertTriangle, CupSoda, Cat } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { ThoughtChain } from '@/lib/types'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'

type Severity = 'error' | 'warning' | 'normal'

function normalizeRole(role: unknown): 'assistant' | 'user' | 'tool' | 'system' | 'unknown' {
  const r = String(role ?? '').toLowerCase()
  if (r === 'agent') return 'assistant'
  if (r.includes('assistant')) return 'assistant'
  if (r.includes('user') || r.includes('owner')) return 'user'
  if (r.includes('tool') || r.includes('function')) return 'tool'
  if (r.includes('system')) return 'system'
  return 'unknown'
}

function tryParseTypedMessage(value: unknown): { type?: string; content?: any } | null {
  if (value && typeof value === 'object' && 'type' in value && 'content' in value) {
    const v = value as any
    return { type: typeof v.type === 'string' ? v.type : undefined, content: v.content }
  }
  if (typeof value === 'string') {
    const s = value.trim()
    if (!s) return null
    if (!((s.startsWith('{') && s.endsWith('}')) || (s.startsWith('[') && s.endsWith(']')))) return null
    try {
      const parsed = JSON.parse(s)
      if (parsed && typeof parsed === 'object' && 'type' in parsed && 'content' in parsed) {
        return { type: typeof (parsed as any).type === 'string' ? (parsed as any).type : undefined, content: (parsed as any).content }
      }
      return null
    } catch {
      return null
    }
  }
  return null
}

function severityFromType(type: unknown): Severity {
  const t = String(type ?? '').toLowerCase()
  if (t === 'error') return 'error'
  if (t === 'warning') return 'warning'
  return 'normal'
}

function stringifyContent(value: unknown) {
  if (typeof value === 'string') return value
  if (value === null || value === undefined) return ''
  try {
    const s = JSON.stringify(value, null, 2)
    return typeof s === 'string' ? s : String(value)
  } catch {
    return String(value)
  }
}

function safeParseJson(value: unknown) {
  if (typeof value !== 'string') return null
  const s = value.trim()
  if (!s) return null
  if (!((s.startsWith('{') && s.endsWith('}')) || (s.startsWith('[') && s.endsWith(']')))) return null
  try {
    return JSON.parse(s)
  } catch {
    return null
  }
}

function findToolCall(value: unknown, depth = 0): { name?: string; args?: any; raw?: any } | null {
  if (depth > 4) return null
  const parsed = safeParseJson(value)
  const v: any = parsed ?? value
  if (!v || typeof v !== 'object') return null

  const toolCalls = v.tool_calls ?? v.toolCalls
  if (Array.isArray(toolCalls) && toolCalls.length > 0) {
    const first = toolCalls[0]
    const fn = first?.function ?? first?.fn ?? first
    const name = fn?.name ?? first?.name
    const args = fn?.arguments ?? first?.arguments
    if (typeof name === 'string' && name.trim()) return { name, args, raw: first }
  }

  const toolCall = v.tool_call ?? v.toolCall
  if (toolCall && typeof toolCall === 'object') {
    const fn = (toolCall as any).function ?? toolCall
    const name = fn?.name
    const args = fn?.arguments
    if (typeof name === 'string' && name.trim()) return { name, args, raw: toolCall }
  }

  const functionCall = v.function_call ?? v.functionCall
  if (functionCall && typeof functionCall === 'object') {
    const name = (functionCall as any).name
    const args = (functionCall as any).arguments
    if (typeof name === 'string' && name.trim()) return { name, args, raw: functionCall }
  }

  if (typeof v.name === 'string' && v.name.trim() && ('arguments' in v || 'args' in v)) {
    return { name: v.name, args: v.arguments ?? v.args, raw: v }
  }

  if ('content' in v) {
    const found = findToolCall(v.content, depth + 1)
    if (found) return found
  }

  if ('message' in v) {
    const found = findToolCall(v.message, depth + 1)
    if (found) return found
  }

  return null
}

function ThoughtItem({ item }: { item: ThoughtChain }) {
  const contentRoot = (item?.content && typeof item.content === 'object') ? (item.content as any) : undefined
  const role = normalizeRole(item.role ?? contentRoot?.role ?? contentRoot?.sender)
  const rawType = item.type ?? contentRoot?.type ?? contentRoot?.kind ?? contentRoot?.message_type

  const isAssistant = role === 'assistant'
  const isToolCalling =
    isAssistant &&
    (String(rawType ?? '').toLowerCase().includes('tool') ||
      Boolean(contentRoot?.tool_calls || contentRoot?.tool_call || contentRoot?.function_call) ||
      (contentRoot?.name && contentRoot?.arguments))

  const typedPayload = useMemo(() => {
    if (isAssistant) return null
    const candidate = tryParseTypedMessage(item.content) ?? tryParseTypedMessage(contentRoot) ?? null
    if (candidate) return candidate
    if (item.type) return { type: item.type, content: item.content }
    return { type: undefined, content: item.content }
  }, [contentRoot, isAssistant, item.content, item.type])

  const severity = useMemo(() => {
    if (typedPayload?.type) return severityFromType(typedPayload.type)
    return 'normal' as const
  }, [typedPayload?.type])

  const timestampText = useMemo(() => {
    try {
      return item.timestamp.toLocaleTimeString('zh-CN')
    } catch {
      return ''
    }
  }, [item.timestamp])

  const headerIcon = (() => {
    if (severity === 'error') return AlertCircle
    if (severity === 'warning') return AlertTriangle
    if (role === 'user') return User
    if (role === 'assistant') return Cat
    if (role === 'tool') return Wrench
    return Brain
  })()

  const headerLabel = (() => {
    if (role === 'user') return 'USER'
    if (role === 'assistant') return isToolCalling ? 'AGENT · TOOL' : 'AGENT · MESSAGE'
    if (role === 'tool') return 'TOOL'
    if (role === 'system') return 'SYSTEM'
    return 'UNKNOWN'
  })()

  const containerClassName = cn(
    'rounded-lg border p-3',
    role === 'tool' && 'bg-muted/30'
  )

  const HeaderIcon = headerIcon

  return (
    <div className={containerClassName}>
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <HeaderIcon
            className={cn(
              'size-4 shrink-0',
              // 错误与警告仍然用颜色强调
              severity === 'error' && 'text-destructive',
              severity === 'warning' && 'text-amber-500',
              // 其它角色一律灰度，保持整体简洁
              severity === 'normal' && (role === 'assistant' && !isToolCalling ? 'text-yellow-500' : 'text-muted-foreground'),
            )}
          />
          <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider truncate">
            {headerLabel}
          </span>
          {typedPayload?.type && (
            <span
              className={cn(
                'text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded border',
                severity === 'error' && 'border-destructive/40 text-destructive',
                severity === 'warning' && 'border-amber-500/40 text-amber-600',
                severity === 'normal' && 'border-border text-muted-foreground',
              )}
            >
              {String(typedPayload.type)}
            </span>
          )}
        </div>
        <span className="text-[10px] text-muted-foreground font-mono shrink-0">{timestampText}</span>
      </div>

      {isAssistant ? (
        <>
          {(() => {
            const raw = contentRoot?.content ?? item.content
            const hasContent = (typeof raw === 'string' && raw.trim()) || (typeof raw === 'object' && raw?.content && typeof raw.content === 'string' && raw.content.trim())
            return hasContent ? (
              <div className="prose prose-sm dark:prose-invert max-w-none prose-p:text-[9px] prose-li:text-[9px] prose-code:text-[9px] prose-pre:text-[9px] prose-pre:bg-muted prose-pre:text-muted-foreground prose-pre:overflow-x-auto mb-3">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {typeof raw === 'string' ? raw : raw?.content || ''}
                </ReactMarkdown>
              </div>
            ) : null
          })()}
          {isToolCalling ? (
            <div className="rounded-md border p-2">
              {(() => {
                const toolCall =
                  findToolCall(contentRoot) ??
                  findToolCall(item.content) ??
                  (typeof rawType === 'string' && rawType.toLowerCase().includes('tool') ? { name: rawType } : null)

                const name = toolCall?.name
                const args = toolCall?.args

                const signature =
                  typeof name === 'string' && name.trim()
                    ? `${name}()`
                    : 'tool_calling'

                const argsText = (() => {
                  if (args === undefined || args === null) return ''
                  if (typeof args === 'string') return args.trim()
                  const s = stringifyContent(args)
                  return s.trim()
                })()

                return (
                  <>
                    <div className="text-xs font-mono text-muted-foreground break-all">
                      {signature}
                    </div>
                    {argsText ? (
                      <pre className="mt-2 text-xs font-mono whitespace-pre-wrap break-words leading-snug text-muted-foreground">
                        {argsText}
                      </pre>
                    ) : null}
                  </>
                )
              })()}
            </div>
          ) : null}
        </>
      ) : (
        role === 'tool' ? (
          <div className="rounded-md border p-2">
            <div className="text-xs font-mono text-muted-foreground break-all">
              Tool Result
            </div>
            <pre className="mt-2 text-xs font-mono whitespace-pre-wrap break-words leading-snug text-muted-foreground">
              {(() => stringifyContent(typedPayload?.content ?? item.content))()}
            </pre>
          </div>
        ) : (
          <div
            className={cn(
              'text-sm whitespace-pre-wrap break-words leading-relaxed',
              role === 'system' && 'text-muted-foreground italic',
            )}
          >
            {(() => stringifyContent(typedPayload?.content ?? item.content))()}
          </div>
        )
      )}
    </div>
  )
}

export function ThoughtChainPanel() {
  const thoughtChain = useAppStore((state) => state.thoughtChain)
  const fetchThoughtChain = useAppStore((state) => state.fetchThoughtChain)
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

  // Auto-refresh thought chain
  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        await fetchThoughtChain()
      } catch {
      }
    }, 1000)
    return () => window.clearInterval(timer)
  }, [fetchThoughtChain])

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
        <ScrollArea type="always" ref={scrollRef} className="h-full">
          <div className="flex flex-col gap-3 pr-4 pb-4">
            {thoughtChain.map((item) => (
              <ThoughtItem key={item.id} item={item} />
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

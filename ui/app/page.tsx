'use client'

import { useState, useCallback, useEffect, useMemo, useRef } from "react"
import { useAppStore } from "@/lib/store"
import { Omnibar } from "@/components/catnip/omnibar"
import { StreamBlocks, type StreamBlock } from "@/components/catnip/stream-blocks"
import { ContextDrawer } from "@/components/catnip/context-drawer"
import { StatusIndicator } from "@/components/catnip/status-indicator"
import { Settings, LayoutPanelLeft, Brain } from "lucide-react"
import { MessageQueue } from "@/components/catnip/message-queue"
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup
} from "@/components/ui/resizable"
import { cn } from "@/lib/utils"

export default function HomePage() {
  const {
    thoughtChain,
    messages,
    addMessage,
    connectionStatus,
    plugins,
    modelConfig,
    refreshAll,
    agentStatus,
    fetchAgentStatus
  } = useAppStore()

  const [isDrawerOpen, setIsDrawerOpen] = useState(false)
  const [status, setStatus] = useState<"idle" | "running" | "error">("idle")
  const [showQueue, setShowQueue] = useState(true)
  const [prevToken, setPrevToken] = useState(0)
  const [tokenDelta, setTokenDelta] = useState<number | null>(null)

  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const [isAtBottom, setIsAtBottom] = useState(true)

  const handleScroll = useCallback(() => {
    if (scrollContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current
      const atBottom = scrollHeight - scrollTop - clientHeight < 100
      setIsAtBottom(atBottom)
    }
  }, [])

  useEffect(() => {
    if (isAtBottom && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo({
        top: scrollContainerRef.current.scrollHeight,
        behavior: 'smooth'
      })
    }
  }, [thoughtChain, isAtBottom])

  const queueMessages = useMemo(() => {
    return (messages || []).map(m => ({
      id: m.id,
      type: (m.type === 'owner_message' ? 'info' :
             m.type === 'task_message' ? 'agent' :
             m.type === 'error' ? 'error' : 'info') as any,
      title: m.type || 'System',
      content: m.content || '',
      timestamp: m.timestamp instanceof Date ? m.timestamp.toLocaleTimeString() : ''
    }))
  }, [messages])

  useEffect(() => {
    if (connectionStatus === 'disconnected') {
      setStatus("error")
    } else {
      const lastItem = thoughtChain[thoughtChain.length - 1]
      if (lastItem && (lastItem.role === 'assistant' || lastItem.role === 'agent') && !lastItem.content) {
         setStatus("running")
      } else {
         setStatus("idle")
      }
    }
  }, [connectionStatus, thoughtChain])

  useEffect(() => {
    fetchAgentStatus()
    const interval = setInterval(fetchAgentStatus, 3000)
    return () => clearInterval(interval)
  }, [fetchAgentStatus])

  useEffect(() => {
    const delta = agentStatus.window_token - prevToken
    if (delta > 0 && prevToken > 0) {
      setTokenDelta(delta)
      setTimeout(() => setTokenDelta(null), 2000)
    }
    setPrevToken(agentStatus.window_token)
  }, [agentStatus.window_token])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === ".") {
        e.preventDefault()
        setIsDrawerOpen((prev) => !prev)
      }
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [])

  const handleSubmit = useCallback(async (message: string) => {
    setStatus("running")
    setIsAtBottom(true)

    if (scrollContainerRef.current) {
      setTimeout(() => {
        if(scrollContainerRef.current) {
           scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight
        }
      }, 50)
    }

    try {
      await addMessage({ role: 'user', content: message })
      setTimeout(refreshAll, 500)
    } catch (error) {
      console.error("Failed to send message:", error)
      setStatus("error")
    }
  }, [addMessage, refreshAll])

  const blocks = useMemo(() => {
    const result: StreamBlock[] = []
    thoughtChain.forEach((item, index) => {
      const role = (item.role || "").toLowerCase()
      const timestamp = item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : ""

      if (role === 'user') {
        result.push({
          id: item.id || `user-${index}`,
          type: "user",
          content: typeof item.content === 'string' ? item.content : (item.content?.content || ""),
          timestamp
        })
      } else if (role === 'assistant') {
        const content = typeof item.content === 'string' ? item.content : (item.content?.content || "");
        if (content) {
          result.push({ id: item.id || `agent-${index}`, type: "agent", content, timestamp })
        }

        const toolCalls = item.content?.tool_calls || (item as any).tool_calls || item.content?.toolCalls || (item as any).toolCalls;
        if (toolCalls && Array.isArray(toolCalls)) {
          result.push({
            id: `thought-${index}`,
            type: "thought",
            content: "",
            toolCalls: toolCalls.map((tc: any) => ({
              id: tc.id,
              timestamp,
              tool: tc.function?.name || tc.tool || 'unknown',
              args: tc.function?.arguments || JSON.stringify(tc.args || {}),
              status: "running"
            }))
          })
        }
      } else if (role === 'tool') {
        const lastThoughtBlock = [...result].reverse().find(b => b.type === 'thought')
        if (lastThoughtBlock && lastThoughtBlock.toolCalls) {
          const tcId = (item as any).tool_call_id
          const tc = lastThoughtBlock.toolCalls.find(tc => tc.id === tcId)
          if (tc) {
            tc.result = typeof item.content === 'string' ? item.content : (item.content?.content || JSON.stringify(item.content))
            tc.status = "done"
          }
        }
      }
    })
    return result
  }, [thoughtChain])

  return (
    <div className="absolute inset-0 flex flex-col w-full bg-background overflow-hidden">
      <ResizablePanelGroup direction="horizontal" className="h-full w-full">
        <ResizablePanel defaultSize={75} minSize={60}>
          <div className="relative h-full w-full overflow-hidden">
            
            {/* 顶部渐变层：与导航栏之间的过渡效果 */}
            <div className="absolute top-0 left-0 right-0 z-10 bg-gradient-to-b from-background via-background/90 to-transparent pb-16 pointer-events-none" />

            {/* Token 计数悬浮框 */}
            <div className="absolute top-20 right-4 z-20 pointer-events-none">
              <div className="relative bg-gradient-to-br from-slate-100/60 via-gray-100/60 to-zinc-100/60 dark:from-slate-800/40 dark:via-gray-800/40 dark:to-zinc-800/40 backdrop-blur-sm rounded-xl px-3 py-1.5 border border-slate-200/30 dark:border-slate-700/30 shadow-sm">
                <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                  <Brain className="size-3 text-slate-400 dark:text-slate-500" />
                  <span className="font-mono">{agentStatus.window_token.toLocaleString()}</span>
                  <span className="text-slate-400/60 dark:text-slate-500/60">tokens</span>
                </div>
                {tokenDelta && (
                  <div 
                    className="absolute left-1/2 -top-6 text-emerald-500 text-sm font-mono pointer-events-none whitespace-nowrap"
                    style={{ 
                      animation: 'floatUp 2s cubic-bezier(0.4, 0, 0.2, 1) forwards',
                    }}
                  >
                    +{tokenDelta.toLocaleString()}
                  </div>
                )}
              </div>
            </div>

            {/* 1. 滑动层：去掉之前无效的 pb-96 */}
            <div
              ref={scrollContainerRef}
              onScroll={handleScroll}
              className="absolute inset-0 overflow-y-auto overflow-x-hidden pt-16 pb-4 md:pt-24 md:pb-8 scroll-smooth scrollbar-thin scrollbar-thumb-muted-foreground/20 hover:scrollbar-thumb-muted-foreground/40 scrollbar-track-transparent"
            >
              {/* 2. 内容层：把超级巨大的留白加在这里！pb-48 (12rem) 保证了绝对安全的间距 */}
              <div className="max-w-4xl mx-auto w-full pb-48">
                <StreamBlocks blocks={blocks} />
                {/* 终极保险：一个隐形的占位块，确保高度计算万无一失 */}
                <div className="h-16 w-full shrink-0" />
              </div>
            </div>

            {/* 3. 悬浮输入框与渐变层 */}
            <div className="absolute bottom-0 left-0 right-0 z-10 bg-gradient-to-t from-background via-background/90 to-transparent pt-64 pb-16 px-4 md:px-8 pointer-events-none">
              <div className="max-w-4xl mx-auto w-full pointer-events-auto">
                {/* 增加轻微的底色和阴影区分 */}
                <div className="bg-background/80 backdrop-blur-md rounded-[24px] shadow-[0_-10px_40px_rgba(0,0,0,0.05)] dark:shadow-none">
                  <Omnibar onSubmit={handleSubmit} status={status} />
                </div>
              </div>
            </div>
          </div>
        </ResizablePanel>

        {showQueue && (
          <ResizablePanel defaultSize={25} minSize={25} maxSize={25}>
            <div className="h-full">
              <MessageQueue messages={queueMessages} />
            </div>
          </ResizablePanel>
        )}
      </ResizablePanelGroup>

      <ContextDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        context={{
          status,
          memory: "N/A",
          plugins: plugins.filter(p => p.enabled).map(p => p.name),
          model: modelConfig?.models ? Object.keys(modelConfig.models)[0] : "unknown",
        }}
      />
    </div>
  )
}
"use client"

import { useState, useMemo } from "react"
import { cn } from "@/lib/utils"
import { ChevronRight } from "lucide-react"
import { motion } from "framer-motion"

// Types
export interface ToolCall {
  id: string
  timestamp: string
  tool: string
  args: string
  result?: string
  status: "pending" | "running" | "done" | "error"
}

export interface StreamBlock {
  id: string
  type: "user" | "agent" | "thought"
  content: string
  timestamp?: string
  toolCalls?: ToolCall[]
  isStreaming?: boolean
}

interface UserBlockProps {
  content: string
}

function UserBlock({ content }: UserBlockProps) {
  return (
    <div className="flex gap-3">
      <div className="w-0.5 bg-black dark:bg-white shrink-0 rounded-full" />
      <p className="font-medium text-base leading-relaxed text-foreground">
        {content}
      </p>
    </div>
  )
}

interface AgentBlockProps {
  content: string
  isStreaming?: boolean
}

function AgentBlock({ content, isStreaming }: AgentBlockProps) {
  // Split content to detect code blocks
  const parts = content.split(/(```[\s\S]*?```)/g)

  return (
    <div className="space-y-3">
      {parts.map((part, index) => {
        if (part.startsWith("```")) {
          // Code block
          const match = part.match(/```(\w+)?\n?([\s\S]*?)```/)
          const lang = match?.[1] || ""
          const code = match?.[2] || part.slice(3, -3)
          
          return (
            <pre
              key={index}
              className={cn(
                "p-4 bg-muted/40 rounded-xl border border-border/50",
                "font-mono text-sm leading-relaxed overflow-x-auto"
              )}
            >
              {lang && (
                <div className="text-[10px] text-muted-foreground/60 uppercase tracking-wider mb-2 font-bold">
                  {lang}
                </div>
              )}
              <code className="text-foreground/90">{code}</code>
            </pre>
          )
        }
        
        // Regular text
        return part.trim() ? (
          <p key={index} className="text-foreground/80 leading-relaxed whitespace-pre-wrap text-[15px]">
            {part}
            {isStreaming && index === parts.length - 1 && (
              <span className="inline-block w-0.5 h-4 bg-foreground/60 ml-0.5 animate-blink" />
            )}
          </p>
        ) : null
      })}
    </div>
  )
}

interface ThoughtBlockProps {
  toolCalls: ToolCall[]
}

function ThoughtBlock({ toolCalls }: ThoughtBlockProps) {
  if (toolCalls.length === 0) return null

  return (
    <div className="space-y-1.5 pl-3">
      {toolCalls.map((call) => (
        <ToolCallItem key={call.id} call={call} />
      ))}
    </div>
  )
}

interface ToolCallItemProps {
  call: ToolCall
}

function ToolCallItem({ call }: ToolCallItemProps) {
  const [showResult, setShowResult] = useState(false)

  // Format arguments for display
  const formattedArgs = useMemo(() => {
    try {
      const parsed = typeof call.args === 'string' ? JSON.parse(call.args) : call.args
      const entries = Object.entries(parsed)
      if (entries.length === 0) return '()'
      return `(${entries.map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(', ')})`
    } catch (e) {
      return call.args || '()'
    }
  }, [call.args])

  return (
    <div className="font-mono text-[11px] text-muted-foreground/70">
      <button
        onClick={() => call.result && setShowResult(!showResult)}
        className={cn(
          "flex items-center gap-2 text-left transition-all duration-200 py-1 px-2 rounded-md",
          "hover:text-foreground hover:bg-muted/50 group cursor-pointer"
        )}
      >
        <ChevronRight 
          className={cn(
            "w-3 h-3 transition-transform duration-200",
            showResult && "rotate-90"
          )} 
        />
        <div className="flex items-center gap-1.5 overflow-hidden">
          <span className="shrink-0 text-muted-foreground/40 font-bold">🔧</span>
          <span className="font-bold text-foreground/60 shrink-0">工具调用:</span>
          <span className="truncate">{call.tool}</span>
          <span className="text-muted-foreground/50 truncate max-w-[300px]">{formattedArgs}</span>
        </div>
        
        <div className="ml-auto flex items-center gap-3 shrink-0">
          {(call.status === "pending" || call.status === "running") && (
            <span className="flex items-center gap-1.5 opacity-50">
              <span className="size-1 bg-black dark:bg-white rounded-full animate-pulse" />
              运行中
            </span>
          )}
          {call.status === "done" && (
            <span className="flex items-center gap-1 text-[10px] bg-muted px-1.5 py-0.5 rounded text-muted-foreground/60">
              完成
            </span>
          )}
          {call.status === "error" && <span className="text-black dark:text-white font-bold underline">错误</span>}
        </div>
      </button>
      
      {showResult && call.result && (
        <motion.div 
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          className="overflow-hidden"
        >
          <pre className="mt-2 ml-8 p-3 bg-muted/20 rounded-xl text-[10px] overflow-x-auto whitespace-pre-wrap break-all border border-border/40 text-muted-foreground/80 leading-relaxed">
            {typeof call.result === 'string' ? call.result : JSON.stringify(call.result, null, 2)}
          </pre>
        </motion.div>
      )}
    </div>
  )
}

interface StreamBlocksProps {
  blocks: StreamBlock[]
}

export function StreamBlocks({ blocks }: StreamBlocksProps) {
  return (
    <div className="space-y-12">
      {blocks.map((block) => (
        <div key={block.id} className="animate-in fade-in duration-100">
          {block.type === "user" && <UserBlock content={block.content} />}
          {block.type === "agent" && (
            <div className="flex gap-3">
              <div className="w-0.5 bg-muted-foreground/30 shrink-0 rounded-full" />
              <div className="flex-1">
                <AgentBlock content={block.content} isStreaming={block.isStreaming} />
              </div>
            </div>
          )}
          {block.type === "thought" && block.toolCalls && (
            <ThoughtBlock toolCalls={block.toolCalls} />
          )}
        </div>
      ))}
    </div>
  )
}

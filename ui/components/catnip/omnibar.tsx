"use client"

import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from "react"
import { Send } from "lucide-react"
import { cn } from "@/lib/utils"

interface OmnibarProps {
  onSubmit: (message: string) => void
  status: "idle" | "running" | "error"
  placeholder?: string
  disabled?: boolean
}

export function Omnibar({ 
  onSubmit, 
  status, 
  placeholder = "输入指令...",
  disabled = false 
}: OmnibarProps) {
  const [value, setValue] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea
  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = "auto"
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }
  }, [])

  useEffect(() => {
    adjustHeight()
  }, [value, adjustHeight])

  const handleSubmit = () => {
    if (value.trim() && !disabled && status !== "running") {
      onSubmit(value.trim())
      setValue("")
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto"
      }
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="w-full mx-auto">
      <div
        className={cn(
          "flex items-end gap-2 bg-gradient-to-br from-slate-100/60 via-gray-100/60 to-zinc-100/60 dark:from-slate-800/40 dark:via-gray-800/40 dark:to-zinc-800/40 backdrop-blur-sm p-1.5 pl-4 rounded-[24px] border border-slate-200/30 dark:border-slate-700/30 shadow-sm transition-all duration-300",
          // 聚焦时微微加深背景并给一点阴影，保持极简
          "focus-within:from-slate-100/80 focus-within:via-gray-100/80 focus-within:to-zinc-100/80 dark:focus-within:from-slate-800/60 dark:focus-within:via-gray-800/60 dark:focus-within:to-zinc-800/60 focus-within:shadow-md"
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || status === "running"}
          rows={1}
          className={cn(
            "flex-1 bg-transparent resize-none outline-none py-6 px-1",
            "text-foreground placeholder:text-muted-foreground/50",
            "font-sans text-[15px] leading-relaxed",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "scrollbar-hide"
          )}
        />
      </div>
    </div>
  )
}

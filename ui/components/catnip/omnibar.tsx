"use client"

import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from "react"
import { Send } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

interface OmnibarProps {
  onSubmit: (message: string) => void
  status: "idle" | "running" | "error"
  placeholder?: string
  disabled?: boolean
  models?: string[]
  currentModel?: string
  onModelChange?: (model: string) => void
}

export function Omnibar({ 
  onSubmit, 
  status, 
  placeholder = "输入指令...",
  disabled = false,
  models = [],
  currentModel = "",
  onModelChange
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
          "bg-gradient-to-br from-slate-100/60 via-gray-100/60 to-zinc-100/60 dark:from-slate-800/40 dark:via-gray-800/40 dark:to-zinc-800/40 backdrop-blur-sm rounded-[24px] border border-slate-200/30 dark:border-slate-700/30 shadow-sm transition-all duration-300 overflow-hidden",
          // 聚焦时微微加深背景并给一点阴影，保持极简
          "focus-within:from-slate-100/80 focus-within:via-gray-100/80 focus-within:to-zinc-100/80 dark:focus-within:from-slate-800/60 dark:focus-within:via-gray-800/60 dark:focus-within:to-zinc-800/60 focus-within:shadow-md"
        )}
      >
        {/* 输入框 */}
        <div className="p-4">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled || status === "running"}
            rows={1}
            className={cn(
              "w-full bg-transparent resize-none outline-none py-2 px-0",
              "text-foreground placeholder:text-muted-foreground/50",
              "font-sans text-[15px] leading-relaxed",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              "scrollbar-hide"
            )}
          />
        </div>
        
        {/* 模型选择器 - 放在输入框下方 */}
        {models.length > 0 && (
          <div className="flex items-center justify-end px-4 py-2">
            <Select value={currentModel} onValueChange={onModelChange}>
              <SelectTrigger className="w-8 h-8 bg-gray-100 dark:bg-gray-800 border-none rounded-full px-0 flex items-center justify-center">
                {/* 只显示箭头图标，不显示模型名称 */}
              </SelectTrigger>
              <SelectContent align="end" className="w-auto max-w-xs">
                {models.map((model) => (
                  <SelectItem key={model} value={model} className="text-xs">
                    {model}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>
    </div>
  )
}

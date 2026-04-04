"use client"

import { useEffect } from "react"
import { cn } from "@/lib/utils"
import { X, Home, ListTodo, Calendar, Settings as SettingsIcon, Puzzle } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"

export interface AgentContext {
  status: "idle" | "running" | "error"
  memory: string
  plugins: string[]
  model?: string
  checkpoint?: Record<string, unknown>
}

interface ContextDrawerProps {
  isOpen: boolean
  onClose: () => void
  context: AgentContext
}

const navItems = [
  { href: '/', label: '首页', icon: Home },
  { href: '/task', label: '任务', icon: ListTodo },
  { href: '/schedule', label: '日程', icon: Calendar },
  { href: '/setting', label: '设置', icon: SettingsIcon },
  { href: '/plugin', label: '插件', icon: Puzzle },
]

export function ContextDrawer({ isOpen, onClose, context }: ContextDrawerProps) {
  const pathname = usePathname()
  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose()
      }
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [isOpen, onClose])

  // Prevent body scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden"
    } else {
      document.body.style.overflow = ""
    }
    return () => {
      document.body.style.overflow = ""
    }
  }, [isOpen])

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-foreground/5 z-40"
          onClick={onClose}
        />
      )}
      
      {/* Drawer */}
      <div
        className={cn(
          "fixed top-0 right-0 h-full w-80 bg-background z-50",
          "border-l border-border",
          "transform transition-transform duration-100",
          isOpen ? "translate-x-0" : "translate-x-full"
        )}
      >
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-border">
            <h2 className="font-medium text-sm text-foreground">导航 & 上下文</h2>
            <button
              onClick={onClose}
              className="p-1 text-muted-foreground hover:text-foreground transition-colors duration-100"
            >
              <X className="w-4 h-4" />
              <span className="sr-only">关闭</span>
            </button>
          </div>

          {/* Navigation */}
          <div className="px-6 py-4 border-b border-border">
            <div className="space-y-1">
              {navItems.map((item) => {
                const Icon = item.icon
                const isActive = pathname === item.href
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={onClose}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                      isActive 
                        ? "bg-muted text-foreground" 
                        : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                    )}
                  >
                    <Icon className="w-4 h-4" />
                    {item.label}
                  </Link>
                )
              })}
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto px-6 py-6">
            <div className="space-y-6 font-mono text-sm">
              <ContextRow label="Status" value={
                <span className={cn(
                  context.status === "running" && "text-foreground",
                  context.status === "idle" && "text-muted-foreground",
                  context.status === "error" && "text-destructive"
                )}>
                  {context.status === "running" ? "Running" : 
                   context.status === "idle" ? "Idle" : "Error"}
                </span>
              } />
              
              <ContextRow label="Memory" value={context.memory} />
              
              {context.model && (
                <ContextRow label="Model" value={context.model} />
              )}
              
              <ContextRow 
                label="Plugins" 
                value={`${context.plugins.length} Active`}
                detail={context.plugins.length > 0 ? `(${context.plugins.join(", ")})` : undefined}
              />
              
              {context.checkpoint && Object.keys(context.checkpoint).length > 0 && (
                <div className="pt-4 border-t border-border">
                  <div className="text-muted-foreground text-xs uppercase tracking-wider mb-3">
                    Checkpoint
                  </div>
                  <div className="space-y-2">
                    {Object.entries(context.checkpoint).map(([key, value]) => (
                      <ContextRow 
                        key={key} 
                        label={key} 
                        value={String(value)} 
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-border">
            <p className="text-[10px] text-muted-foreground font-mono">
              按 <kbd className="px-1 py-0.5 bg-muted rounded">Esc</kbd> 关闭
            </p>
          </div>
        </div>
      </div>
    </>
  )
}

interface ContextRowProps {
  label: string
  value: React.ReactNode
  detail?: string
}

function ContextRow({ label, value, detail }: ContextRowProps) {
  return (
    <div className="flex justify-between items-baseline gap-4">
      <span className="text-muted-foreground shrink-0">{label}:</span>
      <span className="text-foreground text-right">
        {value}
        {detail && <span className="text-muted-foreground ml-1">{detail}</span>}
      </span>
    </div>
  )
}

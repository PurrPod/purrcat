"use client"

import { cn } from "@/lib/utils"

interface StatusIndicatorProps {
  status: "idle" | "running" | "error"
  label?: string
  className?: string
}

export function StatusIndicator({ status, label, className }: StatusIndicatorProps) {
  return (
    <div className="flex items-center gap-2">
      <div
        className={cn(
          "w-2 h-2 rounded-full transition-colors duration-300",
          status === "idle" && "bg-black dark:bg-white opacity-40",
          status === "running" && "bg-black dark:bg-white animate-pulse",
          status === "error" && "bg-black dark:bg-white underline decoration-2 underline-offset-4",
          className
        )}
      />
      {label && (
        <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
          {label}
        </span>
      )}
    </div>
  )
}

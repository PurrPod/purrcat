"use client"

import { cn } from "@/lib/utils"

interface CatnipLogoProps {
  status: "idle" | "running" | "error"
  className?: string
}

export function CatnipLogo({ status, className }: CatnipLogoProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn(
        "w-5 h-5 text-foreground transition-colors duration-100",
        status === "running" && "animate-breathe",
        status === "error" && "text-destructive",
        className
      )}
    >
      {/* Cup */}
      <path d="M5 8h10a2 2 0 0 1 2 2v4a6 6 0 0 1-6 6H9a6 6 0 0 1-6-6v-4a2 2 0 0 1 2-2z" />
      {/* Cup handle */}
      <path d="M17 10h1a2 2 0 0 1 2 2v1a2 2 0 0 1-2 2h-1" />
      {/* Cat ears peeking from cup */}
      <path d="M7 8V6l2 2" />
      <path d="M13 8V6l-2 2" />
      {/* Cat face - eyes */}
      <circle cx="8" cy="12" r="0.5" fill="currentColor" />
      <circle cx="12" cy="12" r="0.5" fill="currentColor" />
      {/* Cat nose */}
      <path d="M10 13.5l-0.5 0.5h1l-0.5-0.5" />
    </svg>
  )
}

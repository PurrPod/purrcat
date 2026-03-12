'use client'

import { useAppStore } from '@/lib/store'
import Image from 'next/image'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import catInCup from '@/app/cat-in-cup.svg'

export function ClearScreenCat() {
  const clearScreenMode = useAppStore((state) => state.clearScreenMode)
  const toggleClearScreenMode = useAppStore((state) => state.toggleClearScreenMode)

  if (!clearScreenMode) return null

  return (
    <div className="absolute inset-0 flex items-center justify-center bg-background z-50">
      <Button
        variant="outline"
        size="icon"
        className="absolute top-8 right-8 rounded-full hover:bg-destructive hover:text-destructive-foreground transition-all duration-300"
        onClick={toggleClearScreenMode}
      >
        <X className="size-6" />
      </Button>

      <div className="flex flex-col items-center gap-4">
        <div className="w-[560px] max-w-[90vw]">
          <Image src={catInCup} alt="cat-in-cup" className="w-full h-auto" priority />
        </div>
        <p className="text-muted-foreground text-sm animate-pulse">
          清屏模式已开启，点击按钮关闭
        </p>
      </div>
    </div>
  )
}

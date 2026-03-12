'use client'

import { useAppStore } from '@/lib/store'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function ClearScreenCat() {
  const clearScreenMode = useAppStore((state) => state.clearScreenMode)
  const toggleClearScreenMode = useAppStore((state) => state.toggleClearScreenMode)

  if (!clearScreenMode) return null

  return (
    <div className="absolute inset-0 flex items-center justify-center bg-background z-50">
      {/* 退出按钮 */}
      <Button
        variant="outline"
        size="icon"
        className="absolute top-8 right-8 rounded-full hover:bg-destructive hover:text-destructive-foreground transition-all duration-300"
        onClick={toggleClearScreenMode}
      >
        <X className="size-6" />
      </Button>

      <div className="flex flex-col items-center gap-4">
        {/* 杯子和小猫 CSS 动画 */}
        <div className="relative">
          {/* 杯子 */}
          <div className="relative w-32 h-36">
            {/* 杯身 */}
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-28 h-28 bg-gradient-to-b from-amber-100 to-amber-200 rounded-b-3xl border-4 border-amber-300 overflow-hidden">
              {/* 咖啡/茶的液面 */}
              <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-amber-800 to-amber-600 opacity-80" />
            </div>
            
            {/* 杯子把手 */}
            <div className="absolute right-0 top-1/2 -translate-y-1/2 w-6 h-12 border-4 border-amber-300 rounded-r-full bg-transparent" />
            
            {/* 小猫 */}
            <div className="absolute -top-2 left-1/2 -translate-x-1/2 animate-bounce-slow">
              {/* 猫头 */}
              <div className="relative w-20 h-16">
                {/* 耳朵 */}
                <div className="absolute -top-3 left-2 w-0 h-0 border-l-8 border-r-8 border-b-12 border-l-transparent border-r-transparent border-b-gray-400" />
                <div className="absolute -top-3 right-2 w-0 h-0 border-l-8 border-r-8 border-b-12 border-l-transparent border-r-transparent border-b-gray-400" />
                
                {/* 头部 */}
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-16 h-14 bg-gray-400 rounded-full" />
                
                {/* 眼睛 */}
                <div className="absolute top-4 left-4 w-3 h-4 bg-black rounded-full animate-blink">
                  <div className="absolute top-0.5 left-0.5 w-1 h-1 bg-white rounded-full" />
                </div>
                <div className="absolute top-4 right-4 w-3 h-4 bg-black rounded-full animate-blink">
                  <div className="absolute top-0.5 left-0.5 w-1 h-1 bg-white rounded-full" />
                </div>
                
                {/* 鼻子 */}
                <div className="absolute top-8 left-1/2 -translate-x-1/2 w-2 h-1.5 bg-pink-400 rounded-full" />
                
                {/* 嘴巴 */}
                <div className="absolute top-9 left-1/2 -translate-x-1/2 w-4 h-2">
                  <div className="absolute top-0 left-0 w-2 h-2 border-b-2 border-gray-600 rounded-bl-full" />
                  <div className="absolute top-0 right-0 w-2 h-2 border-b-2 border-gray-600 rounded-br-full" />
                </div>
                
                {/* 胡须 */}
                <div className="absolute top-7 left-0 w-4 h-0.5 bg-gray-600 -rotate-12" />
                <div className="absolute top-8 left-0 w-5 h-0.5 bg-gray-600" />
                <div className="absolute top-9 left-0 w-4 h-0.5 bg-gray-600 rotate-12" />
                <div className="absolute top-7 right-0 w-4 h-0.5 bg-gray-600 rotate-12" />
                <div className="absolute top-8 right-0 w-5 h-0.5 bg-gray-600" />
                <div className="absolute top-9 right-0 w-4 h-0.5 bg-gray-600 -rotate-12" />
              </div>
              
              {/* 前爪搭在杯沿 */}
              <div className="absolute top-12 left-1 w-6 h-4 bg-gray-400 rounded-full" />
              <div className="absolute top-12 right-1 w-6 h-4 bg-gray-400 rounded-full" />
            </div>
          </div>
          
          {/* 蒸汽动画 */}
          <div className="absolute -top-8 left-1/2 -translate-x-1/2 flex gap-2">
            <div className="w-1 h-6 bg-gray-300/50 rounded-full animate-steam-1" />
            <div className="w-1 h-8 bg-gray-300/50 rounded-full animate-steam-2" />
            <div className="w-1 h-6 bg-gray-300/50 rounded-full animate-steam-3" />
          </div>
        </div>
        
        <p className="text-muted-foreground text-sm animate-pulse">
          清屏模式已开启，点击按钮关闭
        </p>
      </div>
    </div>
  )
}

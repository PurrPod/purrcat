'use client'

import { useAppStore } from '@/lib/store'
import { Button } from '@/components/ui/button'
import { MessageList } from '@/components/home/message-list'
import { ThoughtChainPanel } from '@/components/home/thought-chain'
import { MessageInput } from '@/components/home/message-input'
import { SidebarIcons } from '@/components/home/sidebar-icons'
import { StatusCards } from '@/components/home/status-cards'
import { ClearScreenCat } from '@/components/home/clear-screen-cat'
import { Eye, EyeOff } from 'lucide-react'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'

export default function HomePage() {
  const clearScreenMode = useAppStore((state) => state.clearScreenMode)
  const toggleClearScreenMode = useAppStore((state) => state.toggleClearScreenMode)

  return (
    <div className="relative flex h-[calc(100vh-3.5rem)] overflow-hidden">
      {/* 清屏模式下的小猫 */}
      <ClearScreenCat />

      {/* 左侧图标栏 */}
      <div className="flex flex-col items-center py-4 px-3 border-r bg-muted/30 shrink-0">
        <SidebarIcons />
      </div>

      {/* 主内容区域 */}
      <div className="flex-1 flex flex-col min-w-0 bg-background">
        {/* 顶部工具栏 */}
        <div className="flex items-center justify-between p-4 border-b">
          <h1 className="text-lg font-semibold flex items-center gap-2">
            <span className="size-2 rounded-full bg-green-500 animate-pulse" />
            Agent 交互中心
          </h1>
          <Button
            variant={clearScreenMode ? 'default' : 'outline'}
            size="sm"
            onClick={toggleClearScreenMode}
            className="rounded-full px-4"
          >
            {clearScreenMode ? (
              <>
                <EyeOff className="size-4 mr-2" />
                退出沉浸模式
              </>
            ) : (
              <>
                <Eye className="size-4 mr-2" />
                沉浸模式
              </>
            )}
          </Button>
        </div>

        {/* 交互区域 */}
        <div className="flex-1 flex flex-col min-h-0">
          {!clearScreenMode && (
            <div className="flex-1 flex min-h-0 overflow-hidden">
              <ResizablePanelGroup direction="horizontal">
                {/* 消息列表 */}
                <ResizablePanel defaultSize={30} minSize={20}>
                  <div className="h-full flex flex-col min-w-0 border-r overflow-hidden">
                    <div className="p-3 border-b bg-muted/10">
                      <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        全局消息队列
                      </h2>
                    </div>
                    <div className="flex-1 min-h-0 p-4">
                      <MessageList />
                    </div>
                  </div>
                </ResizablePanel>

                <ResizableHandle withHandle />

                {/* 思考链面板 */}
                <ResizablePanel defaultSize={70} minSize={40}>
                  <div className="h-full flex flex-col min-h-0 bg-muted/5 overflow-hidden">
                    <div className="p-3 border-b bg-muted/10">
                      <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        Agent 思考链
                      </h2>
                    </div>
                    <div className="flex-1 min-h-0 p-4">
                      <ThoughtChainPanel />
                    </div>
                  </div>
                </ResizablePanel>
              </ResizablePanelGroup>
            </div>
          )}

          {/* 消息输入区 */}
          {!clearScreenMode && (
            <div className="p-4 border-t bg-background">
              <MessageInput />
            </div>
          )}
        </div>
      </div>

      {/* 右侧状态卡片 */}
      <div className="w-64 p-4 border-l bg-muted/30 shrink-0 overflow-y-auto">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4 px-2">
          运行状态
        </h3>
        <StatusCards />
      </div>
    </div>
  )
}

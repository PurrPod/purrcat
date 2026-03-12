'use client'

import { useAppStore } from '@/lib/store'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Puzzle, FolderOpen, CheckCircle, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

export default function PluginPage() {
  const plugins = useAppStore((state) => state.plugins)
  const togglePlugin = useAppStore((state) => state.togglePlugin)

  const enabledCount = plugins.filter((p) => p.enabled).length

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      <div className="p-4 border-b">
        <div className="flex items-center gap-3">
          <Puzzle className="size-5" />
          <h1 className="font-semibold">插件管理</h1>
        </div>
        <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
          <FolderOpen className="size-3" />
          plugin/plugin_collection
          <span className="mx-2">|</span>
          共 {plugins.length} 个插件，{enabledCount} 个已启用
        </p>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-6 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {plugins.map((plugin) => (
            <Card 
              key={plugin.name}
              className={cn(
                'transition-all',
                plugin.enabled ? 'border-primary/50' : 'opacity-70'
              )}
            >
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <div className={cn(
                      'size-8 rounded-lg flex items-center justify-center',
                      plugin.enabled ? 'bg-primary/10' : 'bg-muted'
                    )}>
                      <Puzzle className={cn(
                        'size-4',
                        plugin.enabled ? 'text-primary' : 'text-muted-foreground'
                      )} />
                    </div>
                    <div>
                      <CardTitle className="text-sm">{plugin.name}</CardTitle>
                      {plugin.version && (
                        <Badge variant="secondary" className="text-xs mt-1">
                          v{plugin.version}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <Switch
                    checked={plugin.enabled}
                    onCheckedChange={() => togglePlugin(plugin.name)}
                  />
                </div>
              </CardHeader>
              <CardContent>
                {plugin.description && (
                  <CardDescription className="text-xs mb-3">
                    {plugin.description}
                  </CardDescription>
                )}
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground font-mono truncate max-w-[180px]">
                    {plugin.path}
                  </span>
                  <span className={cn(
                    'flex items-center gap-1',
                    plugin.enabled ? 'text-green-500' : 'text-muted-foreground'
                  )}>
                    {plugin.enabled ? (
                      <>
                        <CheckCircle className="size-3" />
                        已启用
                      </>
                    ) : (
                      <>
                        <XCircle className="size-3" />
                        已禁用
                      </>
                    )}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {plugins.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
            <Puzzle className="size-16 mb-4 opacity-20" />
            <p className="text-lg">暂无插件</p>
            <p className="text-sm">请在 plugin/plugin_collection 目录添加插件</p>
          </div>
        )}
      </ScrollArea>
    </div>
  )
}

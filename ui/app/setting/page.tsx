'use client'

import { useAppStore } from '@/lib/store'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import { Settings, Save, FileJson, Type, Hash, ToggleLeft, ArrowUp } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'
import { Textarea } from '@/components/ui/textarea'

export default function SettingPage() {
  const configs = useAppStore((state) => state.configs)
  const updateConfig = useAppStore((state) => state.updateConfig)
  const [saved, setSaved] = useState(false)
  const [localConfigs, setLocalConfigs] = useState<Record<string, any>>({})
  const [showScrollTop, setShowScrollTop] = useState(false)
  const scrollAreaRef = useRef<HTMLDivElement>(null)

  // 监听滚动事件
  useEffect(() => {
    const scrollViewport = scrollAreaRef.current?.querySelector('[data-radix-scroll-area-viewport]')
    if (!scrollViewport) return

    const onScroll = () => {
      setShowScrollTop(scrollViewport.scrollTop > 300)
    }

    scrollViewport.addEventListener('scroll', onScroll)
    return () => scrollViewport.removeEventListener('scroll', onScroll)
  }, [])

  const scrollToTop = () => {
    const scrollViewport = scrollAreaRef.current?.querySelector('[data-radix-scroll-area-viewport]')
    if (scrollViewport) {
      scrollViewport.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  // 初始化本地配置状态，避免输入时频繁触发全局 store 更新
  useEffect(() => {
    const initial: Record<string, any> = {}
    configs.forEach(cat => {
      cat.items.forEach(item => {
        const value = typeof item.value === 'object' ? JSON.stringify(item.value, null, 2) : String(item.value)
        initial[`${cat.name}-${item.key}`] = value
      })
    })
    setLocalConfigs(initial)
  }, [configs])

  const handleSave = async () => {
    // 批量保存所有更改
    for (const key in localConfigs) {
      const [catName, itemKey] = key.split(/-(.+)/)
      const category = configs.find(c => c.name === catName)
      const item = category?.items.find(i => i.key === itemKey)
      
      if (item) {
        let val: any = localConfigs[key]
        
        if (item.type === 'object') {
          try { 
            val = JSON.parse(val) 
          } catch(e) {
            console.error(`Failed to parse JSON for ${key}:`, e)
            continue 
          }
        } else if (item.type === 'number') {
          val = parseFloat(val) || 0
        } else if (item.type === 'boolean') {
          val = val === 'true'
        }
        
        if (JSON.stringify(val) !== JSON.stringify(item.value)) {
          await updateConfig(catName, itemKey, val)
        }
      }
    }
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const categoryLabels: Record<string, string> = {
    'general_config.json': '通用设置',
    'agent_config.json': 'Agent 核心配置',
    'model_config.json': '模型服务配置',
    'file_config.json': '文件系统配置',
    'plugin_config.json': '插件系统配置',
  }

  const getItemIcon = (type: string) => {
    switch (type) {
      case 'boolean': return <ToggleLeft className="size-3.5 text-blue-500" />
      case 'number': return <Hash className="size-3.5 text-amber-500" />
      case 'object': return <FileJson className="size-3.5 text-purple-500" />
      default: return <Type className="size-3.5 text-emerald-500" />
    }
  }

  return (
    <div className="h-[calc(100vh-3.5rem)] flex flex-col bg-muted/10">
      <div className="px-6 py-4 border-b bg-background flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <Settings className="size-5 text-primary" />
          </div>
          <div>
            <h1 className="font-bold text-lg leading-none">配置管理中心</h1>
            <p className="text-xs text-muted-foreground mt-1.5">管理数据目录 data/config 下的所有 JSON 配置文件</p>
          </div>
        </div>
        <Button size="sm" onClick={handleSave} className="shadow-sm">
          <Save className="size-4 mr-2" />
          {saved ? '配置已同步' : '保存所有修改'}
        </Button>
      </div>

      <ScrollArea ref={scrollAreaRef} className="flex-1">
        <div className="max-w-5xl mx-auto p-8 space-y-10">
          {configs.map((category) => (
            <div key={category.name} id={`config-${category.name}`} className="space-y-4">
              <div className="flex items-end justify-between px-1">
                <div>
                  <h2 className="text-xl font-bold tracking-tight">
                    {categoryLabels[category.name] || category.name}
                  </h2>
                  <p className="text-sm text-muted-foreground font-mono mt-1">
                    {category.name}
                  </p>
                </div>
              </div>

              <Card className="border-none shadow-md bg-card overflow-hidden">
                <CardContent className="p-0">
                  <div className="divide-y divide-border/50">
                    {category.items.map((item) => {
                      const isLongContent = typeof item.value === 'string' && item.value.length > 50;
                      const displayType = item.type;

                      return (
                        <div key={item.key} className="group p-6 hover:bg-muted/5 transition-colors">
                          <div className="flex items-start justify-between gap-8 mb-4">
                            <div className="space-y-1 flex-1">
                              <div className="flex items-center gap-2">
                                <span className="p-1 bg-muted rounded">
                                  {getItemIcon(displayType)}
                                </span>
                                <span className="font-mono text-sm font-semibold tracking-tight group-hover:text-primary transition-colors">
                                  {item.key}
                                </span>
                              </div>
                              {item.description && (
                                <p className="text-xs text-muted-foreground leading-relaxed pl-7">
                                  {item.description}
                                </p>
                              )}
                            </div>
                            
                            {item.type === 'boolean' && (
                              <div className="pt-1">
                                <Switch
                                  checked={localConfigs[`${category.name}-${item.key}`] === 'true'}
                                  onCheckedChange={(checked) => 
                                    setLocalConfigs(prev => ({ ...prev, [`${category.name}-${item.key}`]: String(checked) }))
                                  }
                                />
                              </div>
                            )}
                          </div>

                          {item.type !== 'boolean' && (
                            <div className="pl-7">
                              {item.type === 'number' ? (
                                <Input
                                  type="number"
                                  value={localConfigs[`${category.name}-${item.key}`] || '0'}
                                  onChange={(e) => 
                                    setLocalConfigs(prev => ({ ...prev, [`${category.name}-${item.key}`]: e.target.value }))
                                  }
                                  className="max-w-[200px] font-mono text-sm bg-muted/30 border-muted-foreground/20"
                                />
                              ) : (
                                <div className="relative group/editor">
                                  <div className="absolute top-2 right-3 z-10 opacity-0 group-hover/editor:opacity-100 transition-opacity">
                                    <span className="text-[10px] font-mono bg-background/80 px-1.5 py-0.5 rounded border border-border shadow-sm text-muted-foreground uppercase">
                                      {displayType} editor
                                    </span>
                                  </div>
                                  <Textarea
                                    value={localConfigs[`${category.name}-${item.key}`] || ''}
                                    onChange={(e) => {
                                      setLocalConfigs(prev => ({ ...prev, [`${category.name}-${item.key}`]: e.target.value }))
                                    }}
                                    className="font-mono text-xs leading-relaxed bg-zinc-100 dark:bg-zinc-900 text-zinc-800 dark:text-zinc-300 border-zinc-200 dark:border-zinc-800 focus-visible:ring-zinc-400 dark:focus-visible:ring-zinc-700 min-h-[80px] selection:bg-zinc-200 dark:selection:bg-zinc-700"
                                    spellCheck={false}
                                  />
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            </div>
          ))}
        </div>
      </ScrollArea>

      {showScrollTop && (
        <Button
          onClick={scrollToTop}
          variant="outline"
          size="icon"
          className="fixed bottom-8 right-8 z-50 rounded-full shadow-lg animate-in fade-in-50 slide-in-from-bottom-4"
        >
          <ArrowUp className="size-5" />
        </Button>
      )}
    </div>
  )
}

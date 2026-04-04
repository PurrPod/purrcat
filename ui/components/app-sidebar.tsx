'use client'

import * as React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import { AlarmClock, Calendar, Database, Cat, Plus, Trash2, Clock, Calendar as CalendarIcon, Home, ListTodo, Terminal, Puzzle, Eye } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { useAppStore } from '@/lib/store'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { ScrollArea } from '@/components/ui/scroll-area'
import { format } from 'date-fns'

const navItems = [
  { href: '/', label: '首页', icon: Home },
  { href: '/task', label: '后台任务', icon: ListTodo },
  { href: '/sandbox', label: '沙盒', icon: Terminal },
  { href: '/extension', label: '拓展与配置', icon: Puzzle },
  { href: '/sensor', label: '传感器', icon: Eye },
]

export function AppSidebar() {
  const [activeDialog, setActiveDialog] = React.useState<'alarm' | 'schedule' | 'database' | null>(null)
  const pathname = usePathname()
  
  const { 
    alarms, fetchAlarms, addAlarm, removeAlarm, updateAlarm,
    scheduleItems, fetchSchedule, addSchedule, removeSchedule,
    databases, fetchDatabases,
    tasks, fetchTasks
  } = useAppStore()

  // 计算运行中的任务数
  const runningTasksCount = tasks.filter(task => task.status === 'running').length

  // 组件加载时获取任务列表
  React.useEffect(() => {
    fetchTasks()
  }, [fetchTasks])

  // Form states
  const [alarmForm, setAlarmForm] = React.useState({ title: '', trigger_time: '08:00', repeat_rule: 'none' })
  const [scheduleForm, setScheduleForm] = React.useState({ 
    title: '', 
    start_time: format(new Date(), "yyyy-MM-dd'T'HH:mm"),
    description: '' 
  })

  React.useEffect(() => {
    if (activeDialog === 'alarm') fetchAlarms()
    if (activeDialog === 'schedule') fetchSchedule()
    if (activeDialog === 'database') fetchDatabases()
  }, [activeDialog, fetchAlarms, fetchSchedule, fetchDatabases])

  const handleAddAlarm = async () => {
    if (!alarmForm.title) return
    await addAlarm({ ...alarmForm, active: true })
    setAlarmForm({ title: '', trigger_time: '08:00', repeat_rule: 'none' })
  }

  const handleAddSchedule = async () => {
    if (!scheduleForm.title) return
    await addSchedule(scheduleForm)
    setScheduleForm({ 
      title: '', 
      start_time: format(new Date(), "yyyy-MM-dd'T'HH:mm"),
      description: '' 
    })
  }

  return (
    <>
      <aside className="w-[200px] flex flex-col items-start py-4 border-r bg-background/50 backdrop-blur-sm z-30">
        <div className="flex flex-col items-start gap-4 w-full px-3">
          {/* Logo */}
          <div className="flex items-center gap-2 mb-2 w-full p-3">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
              <Cat className="size-5" />
            </div>
            <span className="text-lg font-semibold text-foreground">CatInCup</span>
          </div>
          
          {/* Navigation Links */}
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = pathname === item.href
            const isTaskItem = item.label === 'Task'
            
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'flex items-center justify-between w-full p-3 rounded-xl transition-colors',
                  isActive
                    ? 'bg-muted text-foreground'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                )}
              >
                <div className="flex items-center gap-3">
                  <Icon className="size-5 shrink-0" />
                  <span className="text-sm font-medium">{item.label}</span>
                </div>
                {isTaskItem && runningTasksCount > 0 && (
                  <span className="flex items-center justify-center size-5 rounded-full bg-primary text-primary-foreground text-xs font-bold">
                    {runningTasksCount}
                  </span>
                )}
              </Link>
            )
          })}
          
          <div className="w-full h-px bg-border/60 my-2" />

          {/* Feature Buttons */}
          <button 
            onClick={() => setActiveDialog('alarm')}
            className="flex items-center gap-3 w-full p-3 rounded-xl hover:bg-muted transition-all duration-200 group relative"
            title="闹钟"
          >
            <AlarmClock className="size-5 text-muted-foreground group-hover:text-primary shrink-0" />
            <span className="text-sm font-medium text-muted-foreground group-hover:text-primary">闹钟</span>
            <div className="absolute -right-1 -top-1 size-2 bg-primary rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
          </button>

          <button 
            onClick={() => setActiveDialog('schedule')}
            className="flex items-center gap-3 w-full p-3 rounded-xl hover:bg-muted transition-all duration-200 group relative"
            title="日程"
          >
            <Calendar className="size-5 text-muted-foreground group-hover:text-primary shrink-0" />
            <span className="text-sm font-medium text-muted-foreground group-hover:text-primary">日程</span>
          </button>

          <button 
            onClick={() => setActiveDialog('database')}
            className="flex items-center gap-3 w-full p-3 rounded-xl hover:bg-muted transition-all duration-200 group relative"
            title="数据库"
          >
            <Database className="size-5 text-muted-foreground group-hover:text-primary shrink-0" />
            <span className="text-sm font-medium text-muted-foreground group-hover:text-primary">数据库</span>
          </button>
        </div>
      </aside>

      {/* Alarm Dialog */}
      <Dialog open={activeDialog === 'alarm'} onOpenChange={(open) => !open && setActiveDialog(null)}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Clock className="size-5 text-primary" />
              管理闹钟
            </DialogTitle>
            <DialogDescription>查看并添加定时提醒</DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div className="grid gap-3 p-3 border rounded-lg bg-muted/30">
              <div className="grid grid-cols-4 items-center gap-3">
                <Label htmlFor="alarm-title" className="text-right text-xs">标题</Label>
                <Input 
                  id="alarm-title" 
                  className="col-span-3 h-8 text-xs focus-visible:ring-0 focus-visible:border-primary/50 focus-visible:outline-none" 
                  value={alarmForm.title}
                  onChange={e => setAlarmForm(prev => ({ ...prev, title: e.target.value }))}
                  placeholder="闹钟名称" 
                />
              </div>
              <div className="grid grid-cols-4 items-center gap-3">
                <Label htmlFor="alarm-time" className="text-right text-xs">时间</Label>
                <Input 
                  id="alarm-time" 
                  type="time" 
                  className="col-span-3 h-8 text-xs focus-visible:ring-0 focus-visible:border-primary/50 focus-visible:outline-none" 
                  value={alarmForm.trigger_time}
                  onChange={e => setAlarmForm(prev => ({ ...prev, trigger_time: e.target.value }))}
                />
              </div>
              <div className="grid grid-cols-4 items-center gap-3">
                <Label htmlFor="alarm-repeat" className="text-right text-xs">重复</Label>
                <select 
                  id="alarm-repeat" 
                  className="col-span-3 h-8 text-xs rounded border p-1 focus-visible:ring-0 focus-visible:border-primary/50 focus-visible:outline-none" 
                  value={alarmForm.repeat_rule}
                  onChange={e => setAlarmForm(prev => ({ ...prev, repeat_rule: e.target.value }))}
                >
                  <option value="none">仅一次</option>
                  <option value="everyday">每天</option>
                  <option value="weekly_1">每周一</option>
                  <option value="weekly_2">每周二</option>
                  <option value="weekly_3">每周三</option>
                  <option value="weekly_4">每周四</option>
                  <option value="weekly_5">每周五</option>
                  <option value="weekly_6">每周六</option>
                  <option value="weekly_7">每周日</option>
                </select>
              </div>
              <Button size="sm" className="w-full mt-1 h-8 text-xs" onClick={handleAddAlarm}>
                <Plus className="size-3 mr-1" /> 添加新闹钟
              </Button>
            </div>

            <ScrollArea className="h-[200px] pr-4">
              <div className="space-y-2">
                {alarms.map(alarm => (
                  <div key={alarm.id} className="flex items-center justify-between p-2 rounded-md border bg-background text-xs">
                    <div className="flex flex-col">
                      <span className="font-medium">{alarm.title}</span>
                      <span className="text-muted-foreground">{alarm.trigger_time} ({alarm.repeat_rule === 'none' ? '仅一次' : alarm.repeat_rule === 'everyday' ? '每天' : alarm.repeat_rule.startsWith('weekly_') ? `每周${alarm.repeat_rule.slice(-1)}` : alarm.repeat_rule})</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Switch 
                        checked={alarm.active} 
                        onCheckedChange={checked => updateAlarm(alarm.id, { active: checked })} 
                      />
                      <Button variant="ghost" size="icon" className="size-7" onClick={() => removeAlarm(alarm.id)}>
                        <Trash2 className="size-3.5 text-destructive" />
                      </Button>
                    </div>
                  </div>
                ))}
                {alarms.length === 0 && <p className="text-center text-xs text-muted-foreground py-8">暂无闹钟</p>}
              </div>
            </ScrollArea>
          </div>
        </DialogContent>
      </Dialog>

      {/* Schedule Dialog */}
      <Dialog open={activeDialog === 'schedule'} onOpenChange={(open) => !open && setActiveDialog(null)}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CalendarIcon className="size-5 text-primary" />
              管理日程
            </DialogTitle>
            <DialogDescription>记录并管理你的重要事项</DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div className="grid gap-3 p-3 border rounded-lg bg-muted/30">
              <div className="grid grid-cols-4 items-center gap-3">
                <Label htmlFor="sch-title" className="text-right text-xs">标题</Label>
                <Input 
                  id="sch-title" 
                  className="col-span-3 h-8 text-xs" 
                  value={scheduleForm.title}
                  onChange={e => setScheduleForm(prev => ({ ...prev, title: e.target.value }))}
                  placeholder="日程名称" 
                />
              </div>
              <div className="grid grid-cols-4 items-center gap-3">
                <Label htmlFor="sch-time" className="text-right text-xs">时间</Label>
                <Input 
                  id="sch-time" 
                  type="datetime-local" 
                  className="col-span-3 h-8 text-xs" 
                  value={scheduleForm.start_time}
                  onChange={e => setScheduleForm(prev => ({ ...prev, start_time: e.target.value }))}
                />
              </div>
              <Button size="sm" className="w-full mt-1 h-8 text-xs" onClick={handleAddSchedule}>
                <Plus className="size-3 mr-1" /> 添加新日程
              </Button>
            </div>

            <ScrollArea className="h-[200px] pr-4">
              <div className="space-y-2">
                {scheduleItems.map(item => (
                  <div key={item.id} className="flex items-center justify-between p-2 rounded-md border bg-background text-xs">
                    <div className="flex flex-col">
                      <span className="font-medium">{item.title}</span>
                      <span className="text-muted-foreground">{format(new Date(item.start_time), 'yyyy-MM-dd HH:mm')}</span>
                    </div>
                    <Button variant="ghost" size="icon" className="size-7" onClick={() => removeSchedule(item.id)}>
                      <Trash2 className="size-3.5 text-destructive" />
                    </Button>
                  </div>
                ))}
                {scheduleItems.length === 0 && <p className="text-center text-xs text-muted-foreground py-8">暂无日程</p>}
              </div>
            </ScrollArea>
          </div>
        </DialogContent>
      </Dialog>

      {/* Database Dialog */}
      <Dialog open={activeDialog === 'database'} onOpenChange={(open) => !open && setActiveDialog(null)}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Database className="size-5 text-primary" />
              数据库查看
            </DialogTitle>
            <DialogDescription>查看已连接的数据库和表</DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <ScrollArea className="h-[300px] pr-4">
              <div className="space-y-2">
                {databases.map((db, idx) => (
                  <div key={idx} className="flex items-center gap-3 p-3 rounded-lg border bg-muted/20 hover:bg-muted/40 transition-colors cursor-pointer">
                    <div className="size-8 rounded bg-background border flex items-center justify-center">
                      <Database className="size-4 text-primary/70" />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">{db}</span>
                      <span className="text-[10px] text-muted-foreground uppercase">Local SQL Lite</span>
                    </div>
                  </div>
                ))}
                {databases.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                    <Database className="size-8 mb-2 opacity-20" />
                    <p className="text-xs italic">未发现可用数据库</p>
                  </div>
                )}
              </div>
            </ScrollArea>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

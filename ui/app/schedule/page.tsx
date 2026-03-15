'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAppStore } from '@/lib/store'
import { format, parseISO, isSameMonth, isSameDay } from 'date-fns'
import { DayPicker } from 'react-day-picker'
import 'react-day-picker/dist/style.css'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Plus, Trash2, Clock, Calendar as CalendarIcon, ChevronLeft, ChevronRight } from 'lucide-react'
import { useToast } from '@/hooks/use-toast'

interface AlarmForm {
  title: string
  trigger_time: string
  repeat_rule: string
  active: boolean
}

interface ScheduleForm {
  title: string
  start_time: string
  end_time: string
  description: string
}

export default function SchedulePage() {
  const scheduleItems = useAppStore((state) => state.scheduleItems)
  const fetchSchedule = useAppStore((state) => state.fetchSchedule)
  const addSchedule = useAppStore((state) => state.addSchedule)
  const removeSchedule = useAppStore((state) => state.removeSchedule)

  const alarms = useAppStore((state) => state.alarms)
  const fetchAlarms = useAppStore((state) => state.fetchAlarms)
  const addAlarm = useAppStore((state) => state.addAlarm)
  const updateAlarm = useAppStore((state) => state.updateAlarm)
  const removeAlarm = useAppStore((state) => state.removeAlarm)

  const [selectedDate, setSelectedDate] = useState<Date>(new Date())
  const [currentMonth, setCurrentMonth] = useState<Date>(new Date())

  const [alarmDialogOpen, setAlarmDialogOpen] = useState(false)
  const [scheduleDialogOpen, setScheduleDialogOpen] = useState(false)
  const [alarmForm, setAlarmForm] = useState<AlarmForm>({
    title: '',
    trigger_time: '08:00',
    repeat_rule: 'none',
    active: true,
  })
  const [scheduleForm, setScheduleForm] = useState<ScheduleForm>({
    title: '',
    start_time: format(new Date(), "yyyy-MM-dd'T'HH:mm"),
    end_time: format(new Date(), "yyyy-MM-dd'T'HH:mm"),
    description: '',
  })

  useEffect(() => {
    fetchSchedule()
    fetchAlarms()
  }, [fetchSchedule, fetchAlarms])

  const eventsByDate = useMemo(() => {
    const map = new Map<string, any[]>()
    scheduleItems.forEach((item) => {
      try {
        const dt = parseISO(item.start_time)
        if (!isNaN(dt.getTime())) {
          const key = format(dt, 'yyyy-MM-dd')
          const list = map.get(key) || []
          list.push(item)
          map.set(key, list)
        }
      } catch {
        // ignore
      }
    })
    return map
  }, [scheduleItems])

  const dayEvents = useMemo(() => {
    const key = format(selectedDate, 'yyyy-MM-dd')
    return eventsByDate.get(key) || []
  }, [eventsByDate, selectedDate])

  const { toast } = useToast()

  const handleAddAlarm = async () => {
    if (!alarmForm.title.trim()) {
      toast({ title: '请填写闹钟标题', variant: 'destructive' })
      return
    }
    await addAlarm(alarmForm)
    setAlarmDialogOpen(false)
  }

  const handleAddSchedule = async () => {
    if (!scheduleForm.title.trim()) {
      toast({ title: '请填写日程标题', variant: 'destructive' })
      return
    }
    if (new Date(scheduleForm.end_time) <= new Date(scheduleForm.start_time)) {
      toast({ title: '终止时间必须晚于起始时间', variant: 'destructive' })
      return
    }
    await addSchedule(scheduleForm)
    setScheduleDialogOpen(false)
  }

  return (
    <div className="h-[calc(100vh-4rem)] flex">
      <div className="w-80 border-r flex flex-col min-h-0">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="size-5" />
            <h1 className="font-semibold">闹钟</h1>
          </div>
          <Button size="sm" variant="outline" onClick={() => setAlarmDialogOpen(true)}>
            <Plus className="size-4 mr-1" /> 添加
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {alarms.length === 0 ? (
            <div className="p-6 text-center text-sm text-muted-foreground">暂无闹钟</div>
          ) : (
            <div className="space-y-2 p-3">
              {alarms
                .slice()
                .sort((a, b) => a.trigger_time.localeCompare(b.trigger_time))
                .map((alarm) => (
                  <div
                    key={alarm.id}
                    className="flex items-center justify-between rounded-lg border p-3"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{alarm.title}</span>
                        <span className="text-xs text-muted-foreground">{alarm.trigger_time}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {alarm.repeat_rule === 'none'
                          ? '仅一次'
                          : alarm.repeat_rule === 'everyday'
                          ? '每天'
                          : alarm.repeat_rule.startsWith('weekly_')
                          ? `每周${alarm.repeat_rule.slice(-1)}`
                          : alarm.repeat_rule}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={alarm.active}
                        onCheckedChange={(checked) => updateAlarm(alarm.id, { active: checked })}
                      />
                      <button
                        className="text-destructive hover:text-destructive/80"
                        onClick={() => removeAlarm(alarm.id)}
                        aria-label="Delete alarm"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </div>
                ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 flex flex-col min-h-0">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CalendarIcon className="size-5" />
            <h1 className="font-semibold">日程</h1>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => setScheduleDialogOpen(true)}>
              <Plus className="size-4 mr-1" /> 添加
            </Button>
          </div>
        </div>

        <div className="flex flex-1 min-h-0 overflow-hidden">
          <div className="w-[340px] border-r p-4 overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm font-medium">{format(currentMonth, 'yyyy年MM月')}</div>
              <div className="flex items-center gap-2">
                <button
                  className="rounded-md p-1 hover:bg-muted/50"
                  onClick={() => setCurrentMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}
                >
                  <ChevronLeft className="size-4" />
                </button>
                <button
                  className="rounded-md p-1 hover:bg-muted/50"
                  onClick={() => setCurrentMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}
                >
                  <ChevronRight className="size-4" />
                </button>
              </div>
            </div>
            <DayPicker
              mode="single"
              selected={selectedDate}
              onSelect={(date) => date && setSelectedDate(date)}
              month={currentMonth}
              onMonthChange={(month) => month && setCurrentMonth(month)}
              modifiers={{ hasEvent: (date) => {
                const key = format(date, 'yyyy-MM-dd')
                return eventsByDate.has(key)
              } }}
              modifiersClassNames={{
                hasEvent: 'relative before:absolute before:bottom-1 before:left-1/2 before:-translate-x-1/2 before:h-1 before:w-1 before:rounded-full before:bg-amber-200',
              }}
            />
          </div>

          <div className="flex-1 p-4 overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="text-sm text-muted-foreground">所选日期</div>
                <div className="text-lg font-semibold">{format(selectedDate, 'yyyy年MM月dd日')}</div>
              </div>
              <div className="text-xs text-muted-foreground">
                共 {dayEvents.length} 个日程
              </div>
            </div>

            {dayEvents.length === 0 ? (
              <div className="text-center text-sm text-muted-foreground">该天暂无日程</div>
            ) : (
              <div className="space-y-3">
                {dayEvents
                  .slice()
                  .sort((a, b) => a.start_time.localeCompare(b.start_time))
                  .map((event) => (
                    <div key={event.id} className="rounded-lg border p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium">{event.title}</div>
                          <div className="text-xs text-muted-foreground mt-1">
                            {event.start_time}
                            {event.end_time ? ` - ${event.end_time}` : ''}
                          </div>
                        </div>
                        <button
                          className="text-destructive hover:text-destructive/80"
                          onClick={() => removeSchedule(event.id)}
                          aria-label="Delete schedule"
                        >
                          <Trash2 className="size-4" />
                        </button>
                      </div>
                      {event.description ? (
                        <div className="text-xs text-muted-foreground mt-2 whitespace-pre-wrap">
                          {event.description}
                        </div>
                      ) : null}
                    </div>
                  ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Add Alarm Dialog */}
      <Dialog open={alarmDialogOpen} onOpenChange={setAlarmDialogOpen}>
        <DialogContent className="sm:max-w-[520px]">
          <DialogHeader>
            <DialogTitle>添加闹钟</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium">标题</label>
              <Input
                value={alarmForm.title}
                onChange={(e) => setAlarmForm((prev) => ({ ...prev, title: e.target.value }))}
                placeholder="例如：喝水提醒"
              />
            </div>
            <div>
              <label className="text-sm font-medium">时间</label>
              <Input
                type="time"
                value={alarmForm.trigger_time}
                onChange={(e) => setAlarmForm((prev) => ({ ...prev, trigger_time: e.target.value }))}
              />
            </div>
            <div>
              <label className="text-sm font-medium">重复规则</label>
              <select
                className="mt-2 w-full rounded border p-2"
                value={alarmForm.repeat_rule}
                onChange={(e) => setAlarmForm((prev) => ({ ...prev, repeat_rule: e.target.value }))}
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
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Switch
                  checked={alarmForm.active}
                  onCheckedChange={(checked) => setAlarmForm((prev) => ({ ...prev, active: checked }))}
                />
                <span className="text-sm">启用</span>
              </div>
              <Button onClick={handleAddAlarm}>保存</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Schedule Dialog */}
      <Dialog open={scheduleDialogOpen} onOpenChange={setScheduleDialogOpen}>
        <DialogContent className="sm:max-w-[520px]">
          <DialogHeader>
            <DialogTitle>添加日程</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium">标题</label>
              <Input
                value={scheduleForm.title}
                onChange={(e) => setScheduleForm((prev) => ({ ...prev, title: e.target.value }))}
                placeholder="例如：团队会议"
              />
            </div>
            <div>
              <label className="text-sm font-medium">开始时间</label>
              <Input
                type="datetime-local"
                value={scheduleForm.start_time}
                onChange={(e) => setScheduleForm((prev) => ({ ...prev, start_time: e.target.value }))}
              />
            </div>
            <div>
              <label className="text-sm font-medium">结束时间（可选）</label>
              <Input
                type="datetime-local"
                value={scheduleForm.end_time}
                onChange={(e) => setScheduleForm((prev) => ({ ...prev, end_time: e.target.value }))}
              />
            </div>
            <div>
              <label className="text-sm font-medium">备注</label>
              <textarea
                value={scheduleForm.description}
                onChange={(e) => setScheduleForm((prev) => ({ ...prev, description: e.target.value }))}
                className="w-full resize-none rounded border p-2"
                rows={4}
              />
            </div>
            <div className="flex justify-end">
              <Button onClick={handleAddSchedule}>保存</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

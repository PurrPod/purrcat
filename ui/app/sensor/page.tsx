'use client'

import React from 'react'
import { Eye, Construction, Radio, Wifi, Zap } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function SensorPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full bg-background p-6">
      <div className="max-w-md w-full space-y-8 text-center">
        <div className="relative inline-block">
          <div className="size-24 bg-muted rounded-full flex items-center justify-center mx-auto mb-6">
            <Eye className="size-12 text-muted-foreground/30" />
          </div>
          <Construction className="absolute -bottom-2 -right-2 size-10 text-primary border-4 border-background rounded-full bg-background p-1.5" />
        </div>

        <div className="space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">Sensor Hub</h1>
          <p className="text-muted-foreground text-lg">
            Real-time environmental awareness is coming soon.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4 mt-8">
          {[
            { name: 'Vision', icon: Eye, desc: 'Camera & screen perception' },
            { name: 'Audio', icon: Radio, desc: 'Speech & sound analysis' },
            { name: 'Network', icon: Wifi, desc: 'Connectivity monitoring' },
            { name: 'System', icon: Zap, desc: 'Hardware performance' }
          ].map((sensor) => (
            <Card key={sensor.name} className="bg-muted/10 border-dashed border-2 opacity-50 grayscale">
              <CardHeader className="p-4 flex flex-col items-center">
                <sensor.icon className="size-6 mb-2 text-muted-foreground" />
                <CardTitle className="text-sm font-bold">{sensor.name}</CardTitle>
                <CardDescription className="text-[10px]">{sensor.desc}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>

        <div className="p-4 bg-primary/5 rounded-lg border border-primary/10 mt-8">
          <p className="text-xs text-primary/60 font-medium uppercase tracking-widest">
            Module status: Under development
          </p>
        </div>
      </div>
    </div>
  )
}

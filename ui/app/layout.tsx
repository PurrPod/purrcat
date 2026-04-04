import type { Metadata } from 'next'
import { Analytics } from '@vercel/analytics/next'
import { Navbar } from '@/components/navbar'
import { AppSidebar } from '@/components/app-sidebar'
import { StoreInitializer } from '@/components/store-initializer'
import './globals.css'

export const metadata: Metadata = {
  title: 'Agent UI - AI Agent 控制面板',
  description: 'AI Agent 交互与管理界面',
  generator: 'v0.app',
  icons: {
    icon: [
      {
        url: '/icon-light-32x32.png',
        media: '(prefers-color-scheme: light)',
      },
      {
        url: '/icon-dark-32x32.png',
        media: '(prefers-color-scheme: dark)',
      },
      {
        url: '/icon.svg',
        type: 'image/svg+xml',
      },
    ],
    apple: '/apple-icon.png',
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="zh-CN">
      <body className="font-sans antialiased min-h-screen bg-background overflow-hidden flex flex-col">
        <StoreInitializer />
        <Navbar />
        <div className="flex flex-1 overflow-hidden">
          <AppSidebar />
          <main className="flex-1 overflow-hidden p-0 relative">
            {children}
          </main>
        </div>
        <Analytics />
      </body>
    </html>
  )
}

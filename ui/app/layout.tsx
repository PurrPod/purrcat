import type { Metadata } from 'next'
import { Analytics } from '@vercel/analytics/next'
import { StoreInitializer } from '@/components/store-initializer'
import { SidebarWrapper } from '@/components/sidebar-wrapper'
import { TopBar } from '@/components/top-bar'
import './globals.css'

export const metadata: Metadata = {
  title: 'Cat In Cup',
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
        <div className="flex flex-1 overflow-hidden">
          <SidebarWrapper />
          <div className="flex-1 flex flex-col overflow-hidden">
            <TopBar />
            <main className="flex-1 overflow-hidden p-0 relative">
              {children}
            </main>
          </div>
        </div>
        <Analytics />
      </body>
    </html>
  )
}

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
// Playfair Display 本地自托管（@fontsource）：原先 index.css 里的 Google Fonts
// @import 是渲染阻塞请求，国内网络访问 fonts.googleapis.com 会挂起导致首屏白屏
import '@fontsource/playfair-display/400.css'
import '@fontsource/playfair-display/600.css'
import '@fontsource/playfair-display/700.css'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { BackendGate } from './components/Setup/BackendGate'
import './styles/globals.css'

// 로컬 폰트 번들
import '@fontsource/pretendard/400.css'
import '@fontsource/pretendard/500.css'
import '@fontsource/pretendard/600.css'
import '@fontsource/pretendard/700.css'
import '@fontsource-variable/inter'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import '@fontsource/space-grotesk/600.css'
import '@fontsource/space-grotesk/700.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BackendGate>
      <App />
    </BackendGate>
  </React.StrictMode>
)

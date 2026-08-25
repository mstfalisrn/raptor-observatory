import { useEffect, useState } from 'react'
import { api, apiBase, openSSE } from './api'
import { Dashboard, RunsPage, ApprovalsPage, ContextPage, MemoryPage,
         SourcesPage, TechnocorePage, TelegramPage, SettingsPage, AuditPage } from './pages'

type PageKey = 'dashboard'|'runs'|'approvals'|'context'|'memory'|'sources'|'technocore'|'telegram'|'settings'|'audit'

const NAV: [PageKey, string][] = [
  ['dashboard','📊 Dashboard'], ['runs','▶️ Runs'], ['approvals','🕐 Approvals'],
  ['context','🧩 Context'], ['memory','🧠 Memory'], ['sources','📡 Sources'],
  ['technocore','🛰️ Technocore'], ['telegram','✈️ Telegram'], ['settings','⚙️ Settings'],
  ['audit','📜 Audit'],
]

export default function App() {
  const [tab, setTab] = useState<PageKey>('dashboard')
  const [live, setLive] = useState<any>(null)

  useEffect(() => openSSE((e) => setLive(e)), [])

  return (
    <div className="app">
      <aside className="nav">
        <div className="brand">🐦 RAPTOR</div>
        {NAV.map(([k,label]) => (
          <button key={k} className={tab===k?'active':''} onClick={() => setTab(k)}>{label}</button>
        ))}
      </aside>
      <main className="content">
        {tab==='dashboard' && <Dashboard live={live} onOpen={(k:any)=>setTab(k)} />}
        {tab==='runs' && <RunsPage />}
        {tab==='approvals' && <ApprovalsPage />}
        {tab==='context' && <ContextPage />}
        {tab==='memory' && <MemoryPage />}
        {tab==='sources' && <SourcesPage />}
        {tab==='technocore' && <TechnocorePage />}
        {tab==='telegram' && <TelegramPage />}
        {tab==='settings' && <SettingsPage />}
        {tab==='audit' && <AuditPage />}
      </main>
    </div>
  )
}
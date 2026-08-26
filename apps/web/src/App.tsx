import { useEffect, useState, useRef } from 'react'
import { api, openSSE, getToken, setToken, setOnUnauthorized } from './api'
import type { SSEState } from './api'
import {
  Dashboard, RunsPage, RunDetailPage, ApprovalsPage, ContextPage, MemoryPage,
  SourcesPage, TechnocorePage, TelegramPage, SettingsPage, AuditPage, CommandCenter, LoginPage
} from './pages'

type PageKey = 'dashboard'|'runs'|'run-detail'|'approvals'|'context'|'memory'|'sources'|'technocore'|'telegram'|'settings'|'audit'
type NavKey = Exclude<PageKey,'run-detail'>

const NAV: [NavKey, string][] = [
  ['dashboard','📊 Dashboard'], ['runs','▶️ Runs'], ['approvals','🕐 Approvals'],
  ['context','🧩 Context'], ['memory','🧠 Memory'], ['sources','📡 Sources'],
  ['technocore','🛰️ Technocore'], ['telegram','✈️ Telegram'], ['settings','⚙️ Settings'],
  ['audit','📜 Audit'],
]

export default function App() {
  const [tab, setTab] = useState<NavKey>('dashboard')
  const [runId, setRunId] = useState<string>('')
  const [live, setLive] = useState<any>(null)
  const [sseState, setSseState] = useState<SSEState>('connecting')
  const [lastId, setLastId] = useState('')
  const [toast, setToast] = useState('')
  const [session, setSession] = useState<{ email: string, role: string } | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const liveRef = useRef(live)

  useEffect(() => { liveRef.current = live }, [live])

  // Auth: token varsa /auth/me ile doğrula; 401'de oturumu düşür
  useEffect(() => {
    setOnUnauthorized(() => { setToken(''); setSession(null) })
    if (!getToken()) { setAuthLoading(false); return }
    api<any>('/v1/auth/me')
      .then(u => setSession({ email: u.username, role: u.role }))
      .catch(() => { setToken(''); setSession(null) })
      .finally(() => setAuthLoading(false))
  }, [])

  // SSE yalnızca oturum açıkken bağlanır
  useEffect(() => {
    if (!session) return
    const stop = openSSE((e, id) => {
      setLive(e)
      if (id) setLastId(id)
    }, (s) => setSseState(s))
    return stop
  }, [session])

  function logout() { setToken(''); setSession(null); setTab('dashboard') }

  if (authLoading) return <div className="muted" style={{ padding: 40 }}>yükleniyor…</div>

  if (!session) {
    return <div className="content"><LoginPage onLogin={(u) => setSession(u)} /></div>
  }

  return (
    <div className="app">
      <aside className="nav">
        <div className="brand">🐦 RAPTOR</div>
        <div className={`sse-badge sse-${sseState}`} title={lastId ? `Last-Event-ID: ${lastId}` : ''}>
          <span className="dot" /> {sseState==='open'?'● canlı': sseState==='connecting'?'◌ bağlanıyor': sseState==='error'?'⚠ yeniden bağlanıyor':'○ kapalı'}
          {lastId && <span className="muted" style={{marginLeft:6, fontSize:11}}>#{lastId}</span>}
        </div>
        {NAV.map(([k,label]) => (
          <button key={k} className={tab===k?'active':''} onClick={() => setTab(k)}>{label}</button>
        ))}
        <div className="nav-foot muted">
          <div>SSE: {SSEStateLabel(sseState)}</div>
          <div style={{ marginTop: 8 }}>
            <span className="muted">{session.email} · {session.role}</span>
          </div>
          <button onClick={logout} style={{ width: '100%', marginTop: 8 }}>↪ Çıkış</button>
        </div>
      </aside>
      <main className="content">
        {toast && <div className="toast ok" onClick={()=>setToast('')}>{toast}</div>}
        {/* Command Center always visible on dashboard + as top bar */}
        {(tab==='dashboard') && (
          <CommandCenter onCreated={(id)=>{ setRunId(id); setToast(`Run oluşturuldu: ${id.slice(0,8)}`); setTab('runs') }} />
        )}
        {tab==='dashboard' && <Dashboard live={live} sseState={sseState} lastId={lastId} onOpen={(k:any)=>setTab(k)} onOpenRun={(id)=>{ setRunId(id); setTab('runs')}} />}

        {tab==='runs' && (
          runId ? <RunsWithDetail runId={runId} onBack={()=>setRunId('')} onOpenDetail={(id)=>setRunId(id)} />
                   : <RunsPage onOpenDetail={(id)=>setRunId(id)} />
        )}
        {tab==='approvals' && <ApprovalsPage />}
        {tab==='context' && <ContextPage initialRunId={runId} />}
        {tab==='memory' && <MemoryPage />}
        {tab==='sources' && <SourcesPage />}
        {tab==='technocore' && <TechnocorePage />}
        {tab==='telegram' && <TelegramPage />}
        {tab==='settings' && <SettingsPage />}
        {tab==='audit' && <AuditPage />}

        {/* compact command bar on non-dashboard pages */}
        {tab!=='dashboard' && (
          <div className="card" style={{marginTop:18, opacity:0.98}}>
            <CommandCenter compact onCreated={(id)=>{ setRunId(id); setToast(`Run oluşturuldu: ${id.slice(0,8)}`); setTab('runs') }} />
          </div>
        )}
      </main>
    </div>
  )
}

function SSEStateLabel(s: SSEState){ return s==='open'?'bağlı': s==='connecting'?'bağlanıyor': s==='error'?'hata/yeniden deneme':'kapalı' }

function RunsWithDetail({ runId, onBack, onOpenDetail }: { runId:string, onBack:()=>void, onOpenDetail:(id:string)=>void }) {
  const [showDetail, setShowDetail] = useState(true)
  useEffect(()=>{ setShowDetail(true)},[runId])
  if (showDetail) return <RunDetailPage runId={runId} onBack={()=>{ setShowDetail(false); onBack() }} />
  return <RunsPage onOpenDetail={(id)=>{ onOpenDetail(id); setShowDetail(true)}} />
}

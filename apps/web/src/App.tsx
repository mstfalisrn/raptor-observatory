import { useEffect, useState, useRef } from 'react'
import { api, openSSE } from './api'
import type { SSEState } from './api'
import {
  Dashboard, RunsPage, RunDetailPage, ApprovalsPage, ContextPage, MemoryPage,
  SourcesPage, TechnocorePage, TelegramPage, SettingsPage, AuditPage, CommandCenter
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
  const liveRef = useRef(live)

  useEffect(() => { liveRef.current = live }, [live])

  useEffect(() => {
    const stop = openSSE((e, id) => {
      setLive(e)
      if (id) setLastId(id)
    }, (s) => setSseState(s))
    return stop
  }, [])

  function openRun(id: string) { setRunId(id); setTab('runs' as any); // stay on runs but detail mode
    // use custom event to signal detail
    setTimeout(()=> setTab('runs'),0)
    // store detail id separately
    ;(window as any).__raptor_run_detail = id
    setTab('runs')
  }

  // expose detail id via state instead of window
  const detailId = runId

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
        <div className="nav-foot muted">SSE: {SSEStateLabel(sseState)}</div>
      </aside>
      <main className="content">
        {toast && <div className="toast ok" onClick={()=>setToast('')}>{toast}</div>}
        {/* Command Center always visible on dashboard + as top bar */}
        {(tab==='dashboard') && (
          <CommandCenter onCreated={(id)=>{ setRunId(id); setToast(`Run oluşturuldu: ${id.slice(0,8)}`); setTab('runs') }} />
        )}
        {tab==='dashboard' && <Dashboard live={live} sseState={sseState} lastId={lastId} onOpen={(k:any)=>setTab(k)} onOpenRun={(id)=>{ setRunId(id); setTab('runs')}} />}

        {tab==='runs' && (
          detailId ? <RunsWithDetail runId={detailId} onBack={()=>setRunId('')} onOpenDetail={(id)=>setRunId(id)} />
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

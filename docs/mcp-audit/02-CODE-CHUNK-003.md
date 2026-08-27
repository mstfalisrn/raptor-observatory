# RAPTOR — Code Chunk 003

> GPT sırayla okuyup birleştirsin (MCP 100KB limit).

## `apps/web/src/pages.tsx`

```tsx
import { useEffect, useState, useCallback } from 'react'
import { api, errMsg, setToken } from './api'

// ---------- helpers ----------
function useFetch<T>(path: string, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const reload = useCallback(()=> setTick(x=>x+1), [])
  const key = path
  useEffect(() => {
    if (!path) { setLoading(false); setData(null); setErr(''); return }
    let on = true
    setLoading(true); setErr('')
    api<T>(path).then(d => { if(on){ setData(d); setLoading(false) }})
      .catch(e => { if(on){ setErr(errMsg(e)); setLoading(false) }})
    return () => { on=false }
  }, [key, tick, ...deps])
  return { data, err, loading, reload }
}

function Loading(){ return <div className="muted">yükleniyor…</div> }
function Err({msg, onRetry}:{msg:string, onRetry?:()=>void}){ return <div className="card err"><span className="warn">⚠ {msg}</span> {onRetry && <button onClick={onRetry}>Yeniden dene</button>}</div>}
function Empty({msg}:{msg:string}){ return <p className="muted">{msg}</p> }

// ---------- Login ----------
export function LoginPage({ onLogin }: { onLogin:(u:{email:string, role:string}) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  async function submit() {
    if (!email.trim() || !password) { setErr('email ve parola gerekli'); return }
    setBusy(true); setErr('')
    try {
      const r = await api<any>('/v1/auth/login', { method:'POST', body: JSON.stringify({ email, password }) })
      setToken(r.token)
      onLogin({ email: r.email, role: r.role })
    } catch(e){ setErr(errMsg(e)) } finally { setBusy(false) }
  }
  return (
    <div className="card" style={{ maxWidth: 400, margin: '80px auto' }}>
      <h1 style={{ marginTop: 0 }}>🐦 RAPTOR</h1>
      <p className="muted">Yerel kimlik doğrulama — oturum aç.</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <input placeholder="email" value={email} onChange={e=>setEmail(e.target.value)} autoComplete="username" />
        <input placeholder="parola" type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" onKeyDown={e=> e.key==='Enter' && submit()} />
        <button onClick={submit} disabled={busy || !email.trim() || !password}>{busy ? 'giriş…' : 'Giriş'}</button>
      </div>
      {err && <div className="warn" style={{ marginTop: 10 }}>⚠ {err}</div>}
    </div>
  )
}

// ---------- Command Center ----------
export function CommandCenter({ onCreated, compact }: { onCreated?:(runId:string)=>void, compact?:boolean }) {
  const [prompt, setPrompt] = useState('')
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [ok, setOk] = useState('')
  async function submit() {
    if (!prompt.trim()) { setErr('prompt gerekli'); return }
    setBusy(true); setErr(''); setOk('')
    try {
      const r = await api<any>('/v1/tasks', { method:'POST', body: JSON.stringify({ title: title||prompt.slice(0,60), prompt }) })
      const id = r.run_id || r.runId || r.id || ''
      setOk(`Run kuyruğa alındı: ${String(id).slice(0,8)}`)
      setPrompt(''); setTitle('')
      onCreated?.(String(id))
    } catch(e){ setErr(errMsg(e)) } finally { setBusy(false) }
  }
  return (
    <div className={compact ? '' : 'card'} style={compact?undefined:{borderColor:'var(--accent)'}}>
      <h3 style={{marginTop:0}}>{compact ? '⚡ Komut' : '🎛️ Command Center'}</h3>
      {!compact && <p className="muted">Prompt gir, run oluştur. SSE ile canlı takip.</p>}
      <div style={{display:'flex', gap:8, flexWrap:'wrap'}}>
        <input placeholder="başlık (opsiyonel)" value={title} onChange={e=>setTitle(e.target.value)} style={{flex:'0 0 220px'}} />
        <input placeholder="prompt — ne yapsın?" value={prompt} onChange={e=>setPrompt(e.target.value)} style={{flex:'1 1 320px'}} onKeyDown={e=> e.key==='Enter' && submit()} />
        <button onClick={submit} disabled={busy || !prompt.trim()}>{busy?'gönderiliyor…':'▶️ Çalıştır'}</button>
      </div>
      {err && <div className="warn" style={{marginTop:8}}>⚠ {err}</div>}
      {ok && <div className="ok" style={{marginTop:8}}>✓ {ok}</div>}
    </div>
  )
}

// ---------- Dashboard ----------
export function Dashboard({ live, sseState, lastId, onOpen, onOpenRun }: any) {
  const { data: runs, err: e1, loading: l1, reload: r1 } = useFetch<any[]>('/v1/runs')
  const { data: approvals, err: e2, loading: l2, reload: r2 } = useFetch<any[]>('/v1/approvals')
  const { data: health } = useFetch<any>('/health/live')
  const pending = approvals?.filter((a:any)=>a.status==='PENDING').length ?? 0
  const running = runs?.filter((r:any)=>['EXECUTING','QUEUED'].includes(r.status)).length ?? 0
  return (
    <div>
      <h1>📊 Dashboard</h1>
      <div className="cards">
        <div className="card"><b>SSE</b><div className={`pill sse-${sseState}`}>{sseState}</div><div className="muted">Last-Event-ID: {lastId || '—'}</div><div className="muted">{live ? `son event: ${live.event_type||live.seq||JSON.stringify(live).slice(0,60)}` : 'bekleniyor'}</div></div>
        <div className="card"><b>Run'lar</b><div>{l1 ? '...' : `${runs?.length ?? 0} toplam · ${running} aktif`}</div><button onClick={()=>onOpen('runs')}>Run'ları gör</button></div>
        <div className="card"><b>Onaylar</b><div>{l2 ? '...' : `${pending} bekleyen`}</div><button onClick={()=>onOpen('approvals')}>Onaylara git</button>{pending>0 && <span className="pill warn">{pending} PENDING</span>}</div>
        <div className="card"><b>Sağlık</b><div>{health ? `✓ ${health.status}` : '...'}</div><div className="muted">{health?.time || ''}</div></div>
      </div>
      {(e1||e2) && <Err msg={e1||e2} onRetry={()=>{r1();r2()}} />}
      {/* son run'lar */}
      <h3 style={{marginTop:18}}>Son Run'lar</h3>
      {l1 ? <Loading/> : !runs?.length ? <Empty msg="henüz run yok — Command Center'dan oluştur."/> : (
        <table><thead><tr><th>ID</th><th>Durum</th><th>Iter</th><th>Oluşturma</th></tr></thead><tbody>
          {runs!.slice(0,5).map(r=> <tr key={r.id} style={{cursor:'pointer'}} onClick={()=>onOpenRun?.(r.id)}><td>{r.id.slice(0,8)}</td><td><span className="pill">{r.status}</span></td><td>{r.iteration}</td><td className="muted">{r.created_at?.slice(0,19)}</td></tr>)}
        </tbody></table>
      )}
    </div>
  )
}

// ---------- Runs ----------
export function RunsPage({ onOpenDetail }: { onOpenDetail?:(id:string)=>void }) {
  const [limit, setLimit] = useState(20)
  const { data, err, loading, reload } = useFetch<any[]>(`/v1/runs?limit=${limit}`, [limit])
  const [q, setQ] = useState('')
  const filtered = !q ? data : data?.filter(r=> r.id.includes(q) || r.status.toLowerCase().includes(q.toLowerCase()))
  return (
    <div>
      <h1>▶️ Runs</h1>
      <div style={{display:'flex', gap:8, marginBottom:10}}>
        <input placeholder="filtre (id/durum)" value={q} onChange={e=>setQ(e.target.value)} />
        <button onClick={()=>reload()}>↻ Yenile</button>
        <select value={String(limit)} onChange={e=>setLimit(parseInt(e.target.value))} style={{background:'var(--panel2)', color:'var(--fg)', border:'1px solid var(--border)', borderRadius:8, padding:'7px'}}>
          <option value="10">10</option><option value="20">20</option><option value="50">50</option>
        </select>
      </div>
      {loading ? <Loading/> : err ? <Err msg={err} onRetry={reload}/> : !filtered?.length ? <Empty msg={data?.length? 'filtreye uygun run yok':'run yok — Command Center ile oluştur.'}/> : (
        <table><thead><tr><th>ID</th><th>Durum</th><th>Iter</th><th>Hata</th><th></th></tr></thead><tbody>
          {filtered!.map(r => <tr key={r.id}><td title={r.id}>{r.id.slice(0,8)}</td><td><span className="pill">{r.status}</span></td><td>{r.iteration}</td><td className="warn">{r.error||''}</td><td><button onClick={()=>onOpenDetail?.(r.id)}>Detay</button></td></tr>)}
        </tbody></table>
      )}
    </div>
  )
}

export function RunDetailPage({ runId, onBack }: { runId:string, onBack:()=>void }) {
  const { data: run, reload: reloadRun } = useFetch<any>(`/v1/runs/${runId}`, [runId])
  const { data, err, loading, reload } = useFetch<any[]>(`/v1/runs/${runId}/events`, [runId])
  const [filter, setFilter] = useState('')
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const evs = !filter ? data : data?.filter((e:any)=> e.event_type.toLowerCase().includes(filter.toLowerCase()))
  const active = run && ['EXECUTING','QUEUED'].includes(run.status)
  const terminal = run && ['FAILED','COMPLETED','CANCELLED'].includes(run.status)
  async function control(action: string) {
    setBusy(action); setMsg('')
    try { await api(`/v1/runs/${runId}/control`, { method:'POST', body: JSON.stringify({ action }) }); setMsg(`✓ ${action} gönderildi`); reloadRun() }
    catch(e){ setMsg('⚠ '+errMsg(e)) } finally { setBusy('') }
  }
  async function retry() {
    setBusy('retry'); setMsg('')
    try { await api(`/v1/runs/${runId}/retry`, { method:'POST', body: '{}' }); setMsg('✓ tekrar kuyruğa alındı'); reloadRun() }
    catch(e){ setMsg('⚠ '+errMsg(e)) } finally { setBusy('') }
  }
  return (
    <div>
      <button onClick={onBack}>← Geri</button>
      <h2>Run: {runId.slice(0,8)} <span className="muted" style={{fontSize:12}}>{runId}</span></h2>
      {run && <div className="card">
        <div style={{display:'flex', gap:12, flexWrap:'wrap', alignItems:'center'}}>
          <span className="pill">{run.status}</span>
          <span className="muted">iter {run.iteration}</span>
          <span className="muted">token {run.token_used ?? 0}</span>
          <span className="muted">cost ${run.cost_used ?? 0}</span>
          <span className="muted">worker {run.worker_id?.slice(0,8) || '—'}</span>
          {run.control_request && <span className="warn">kontrol: {run.control_request}</span>}
        </div>
        {run.error && <div className="err">⚠ {run.error}</div>}
        <div style={{display:'flex', gap:8, marginTop:8}}>
          {active && <>
            <button disabled={!!busy} onClick={()=>control('pause')}>{busy==='pause'?'...':'⏸ Durdur'}</button>
            <button disabled={!!busy} onClick={()=>control('resume')}>{busy==='resume'?'...':'▶️ Sürdür'}</button>
            <button disabled={!!busy} onClick={()=>control('stop')}>{busy==='stop'?'...':'⏹ Sonlandır'}</button>
          </>}
          {terminal && <button disabled={!!busy} onClick={retry}>{busy==='retry'?'...':'🔄 Tekrar çalıştır'}</button>}
        </div>
      </div>}
      {msg && <p className={msg.startsWith('⚠')?'warn':'ok'}>{msg}</p>}
      <div style={{display:'flex', gap:8, marginBottom:10}}>
        <input placeholder="event tipi filtre" value={filter} onChange={e=>setFilter(e.target.value)} />
        <button onClick={reload}>↻ Yenile</button>
      </div>
      {loading ? <Loading/> : err ? <Err msg={err} onRetry={reload}/> : !evs?.length ? <Empty msg="event yok"/> : (
        <div>
          <div className="muted">{evs.length} event</div>
          {evs.map((e:any,i:number)=> (
            <div className="card" key={i}>
              <div><b>{e.event_type}</b> <span className="pill">seq {e.seq}</span> <span className="muted">{e.ts?.slice(0,19)}</span></div>
              {e.payload && <pre className="payload">{JSON.stringify(e.payload, null, 2).slice(0,2000)}</pre>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------- Approvals ----------
export function ApprovalsPage() {
  const { data, err, loading, reload } = useFetch<any[]>('/v1/approvals')
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [err2, setErr2] = useState('')
  async function decide(id: string, decision: string) {
    setBusy(id+decision); setErr2(''); setMsg('')
    try { await api(`/v1/approvals/${id}/decision`, { method: 'POST', body: JSON.stringify({ decision, approval_id: id }) }); setMsg('karar kaydedildi ✓'); reload() }
    catch(e){ setErr2(errMsg(e)) } finally { setBusy('') }
  }
  return (
    <div>
      <h1>🕐 Approvals</h1>
      <button onClick={reload}>↻ Yenile</button>
      {loading ? <Loading/> : err ? <Err msg={err} onRetry={reload}/> : !data?.length ? <Empty msg="onay yok"/> : data.map(a => (
        <div className="card" key={a.id}>
          <b>{a.action_class}</b> — {a.target}
          <div className="muted">etki: {a.impact_summary}</div>
          <div className="muted">expires: {a.expires_at?.slice(0,19) || '—'}</div>
          <span className={`pill ${a.status==='PENDING'?'warn':''}`}>{a.status}</span>
          {a.status === 'PENDING' && (<>
            <button disabled={!!busy} onClick={() => decide(a.id, 'approve')}>{busy===a.id+'approve'?'...':'✅ Onayla'}</button>
            <button disabled={!!busy} onClick={() => decide(a.id, 'reject')}>{busy===a.id+'reject'?'...':'❌ Reddet'}</button>
          </>)}
        </div>
      ))}
      {msg && <p className="ok">{msg}</p>}
      {err2 && <p className="warn">⚠ {err2}</p>}
    </div>
  )
}

// ---------- Context Inspector ----------
export function ContextPage({ initialRunId }: { initialRunId?:string }) {
  const [runId, setRunId] = useState(initialRunId || '')
  useEffect(()=>{ if(initialRunId) setRunId(initialRunId)},[initialRunId])
  const { data: runs } = useFetch<any[]>('/v1/runs?limit=20')
  const path = runId ? `/v1/runs/${runId}/events` : ''
  const { data, err, loading, reload } = useFetch<any[]>(path, [runId])
  // extract context segments from payloads
  const segments = (data||[]).flatMap((e:any)=> (e.payload?.segments||[]).map((s:any)=> ({...s, _event:e.event_type, _seq:e.seq})))
  return (
    <div>
      <h1>🧩 Context Inspector</h1>
      <div style={{display:'flex', gap:8, flexWrap:'wrap', marginBottom:10}}>
        {runs && <select value={runId} onChange={e=>setRunId(e.target.value)} style={{background:'var(--panel2)', color:'var(--fg)', border:'1px solid var(--border)', borderRadius:8, padding:'8px'}}>
          <option value="">run seç…</option>
          {runs.map((r:any)=> <option key={r.id} value={r.id}>{r.id.slice(0,8)} · {r.status}</option>)}
        </select>}
        <input placeholder="run_id" value={runId} onChange={e => setRunId(e.target.value)} style={{flex:'1 1 260px'}} />
        <button onClick={reload} disabled={!runId}>↻ Yükle</button>
      </div>
      {!runId ? <Empty msg="run seçerek context segment metadata'sını gör."/> : loading ? <Loading/> : err ? <Err msg={err} onRetry={reload}/> : !segments.length ? <Empty msg="bu run için segment yok (event payload'ında segments beklenir)."/> : (
        <div>
          <div className="muted">{segments.length} segment · {data?.length} event</div>
          {segments.map((s:any, j:number) => (
            <div key={j} className="card ctx">
              <div><b>{s.segment_type}</b> · {s.token_count} tok · güv {s.confidence} <span className="pill">{s._event} #{s._seq}</span> {s.contains_untrusted_input && <span className="warn">UNTRUSTED</span>}</div>
              <div className="muted">neden: {s.included_reason}</div>
              {s.preview && <pre className="payload">{String(s.preview).slice(0,800)}</pre>}
              {s.content_preview && <pre className="payload">{String(s.content_preview).slice(0,800)}</pre>}
            </div>
          ))}
          <details style={{marginTop:12}}><summary className="muted">Ham event'ler ({data?.length})</summary>
            {data!.map((e:any,i:number)=>(<div className="card" key={i}><b>{e.event_type}</b><pre className="payload">{JSON.stringify(e.payload||{}, null,2).slice(0,1500)}</pre></div>))}
          </details>
        </div>
      )}
    </div>
  )
}

// ---------- Memory ----------
export function MemoryPage() {
  const [status,setStatus]=useState('candidate')
  const [q,setQ]=useState('')
  const path = q ? `/v1/memory?q=${encodeURIComponent(q)}&status=${status}&limit=50` : `/v1/memory?status=${status}&limit=50`
  // also support base call without status fallback
  const { data, err, loading, reload } = useFetch<any[]>(path, [status,q])
  const [busy,setBusy]=useState('')
  const [msg,setMsg]=useState('')
  async function decide(id: string, decision: string) {
    setBusy(id); setMsg('')
    try { await api(`/v1/memory/${id}/decision`, { method: 'POST', body: JSON.stringify({ decision }) }); setMsg('✓ kaydedildi'); reload() }
    catch(e){ setMsg('⚠ '+errMsg(e)) } finally { setBusy('') }
  }
  return (
    <div>
      <h1>🧠 Memory</h1>
      <div style={{display:'flex', gap:8, marginBottom:10, flexWrap:'wrap'}}>
        <select value={status} onChange={e=>setStatus(e.target.value)} style={{background:'var(--panel2)', color:'var(--fg)', border:'1px solid var(--border)', borderRadius:8, padding:'8px'}}>
          <option value="candidate">candidate</option><option value="active">active</option><option value="rejected">rejected</option>
        </select>
        <input placeholder="ara..." value={q} onChange={e=>setQ(e.target.value)} />
        <button onClick={reload}>↻ Yenile</button>
      </div>
      {loading ? <Loading/> : err ? <Err msg={err} onRetry={reload}/> : !data?.length ? <Empty msg={`"${status}" için kayıt yok`}/> : data.map(m => (
        <div className="card" key={m.id}>
          <p style={{marginTop:0}}>{m.content}</p>
          <div className="muted">{m.status} · güv {m.confidence} · {m.source} {m.category?`· ${m.category}`:''}</div>
          <span className="pill">{m.status}</span>
          <button disabled={!!busy} onClick={() => decide(m.id, 'approve')}>✅ Onayla</button>
          <button disabled={!!busy} onClick={() => decide(m.id, 'reject')}>❌ Reddet</button>
        </div>
      ))}
      {msg && <p className="muted">{msg}</p>}
    </div>
  )
}

// ---------- Sources ----------
export function SourcesPage() {
  const { data, err, loading, reload } = useFetch<any[]>('/v1/sources')
  return (
    <div>
      <h1>📡 Sources</h1>
      <button onClick={reload}>↻ Yenile</button>
      {loading ? <Loading/> : err ? <Err msg={err} onRetry={reload}/> : !data?.length ? <Empty msg="kaynak yok. Teknolojik İlk Önce connector ile eklenir."/> : data.map(s => (
        <div className="card" key={s.id}><b>{s.name}</b> · <span className="pill">{s.source_type}</span>
          <div className="muted">{s.is_enabled ? 'aktif' : 'pasif'} · hata serisi: {s.error_series_len} {s.last_accessed_at?`· son: ${s.last_accessed_at.slice(0,19)}`:''}</div></div>
      ))}
    </div>
  )
}

// ---------- Technocore ----------
export function TechnocorePage() {
  const { data, err, loading, reload } = useFetch<any>('/v1/technocore')
  if (loading) return <div><h1>🛰️ Technocore</h1><Loading/></div>
  if (err) return <div><h1>🛰️ Technocore</h1><Err msg={err} onRetry={reload}/></div>
  return (
    <div>
      <h1>🛰️ Technocore</h1>
      {data && <div className="card"><b>{data.base_url || '—'}</b><div>Oda: {data.room_claim || '—'}</div><div>Kayıt: {data.registered ? '✓' : 'henüz değil (Faz 7)'}</div></div>}
      <button onClick={reload}>↻ Yenile</button>
    </div>
  )
}

// ---------- Telegram ----------
export function TelegramPage() {
  const { data, err, loading, reload } = useFetch<any>('/v1/settings/non-secret')
  if (loading) return <div><h1>✈️ Telegram</h1><Loading/></div>
  if (err) return <div><h1>✈️ Telegram</h1><Err msg={err} onRetry={reload}/></div>
  return (
    <div>
      <h1>✈️ Telegram</h1>
      {data && (<div className="card">
        <div><span className="pill">{data.telegram_token_configured ? 'bot token ✓' : '⚠️ token yok'}</span></div>
        <div>Allowlist kullanıcı: {data.telegram_allowed_user_ids_count}</div>
        <div>Grup: {data.telegram_group_enabled ? 'açık' : 'kapalı'}</div>
      </div>)}
      <button onClick={reload}>↻ Yenile</button>
    </div>
  )
}

// ---------- Settings ----------
export function SettingsPage() {
  const { data, err, loading, reload } = useFetch<any>('/v1/settings/non-secret')
  if (loading) return <div><h1>⚙️ Settings</h1><Loading/></div>
  if (err) return <div><h1>⚙️ Settings</h1><Err msg={err} onRetry={reload}/></div>
  return (
    <div>
      <h1>⚙️ Settings</h1>
      {data && (<div className="card">
        <div>Ortam: <b>{data.app_env}</b></div>
        <div>Provider: {data.llm_provider}</div>
        <div>Model: {data.llm_model || '-'}</div>
        <div>Base URL: {data.llm_base_url || '-'}</div>
        <div>LLM key: <span className="pill">{data.llm_key_configured ? '✓' : '✗'}</span></div>
        <div>Max iterasyon: {data.run_max_iterations}</div>
        <div>Max wall s: {data.run_max_wall_seconds}</div>
      </div>)}
      <p className="warn">Secret değerleri asla gösterilmez.</p>
      <button onClick={reload}>↻ Yenile</button>
    </div>
  )
}

// ---------- Audit ----------
export function AuditPage() {
  return <div><h1>📜 Audit</h1><p className="muted">/api/v1/audit endpoint üzerinden append-only görünüm (backlog).</p></div>
}

```

## `apps/web/src/styles.css`

```css
:root {
  --bg: #0b1220; --panel: #111a2e; --panel2: #152038; --border: #24365a;
  --fg: #e6edfb; --muted: #8ea1c4; --accent: #5b8cff; --ok: #3ddc84; --warn: #ffb84d;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--fg); }
.app { display: flex; min-height: 100vh; }
.nav { width: 200px; background: var(--panel); border-right: 1px solid var(--border); padding: 16px 10px; position: sticky; top: 0; height: 100vh; }
.nav .brand { font-weight: 700; font-size: 18px; margin-bottom: 18px; color: var(--accent); }
.nav button { display: block; width: 100%; text-align: left; padding: 9px 12px; margin-bottom: 4px; background: transparent; color: var(--fg); border: none; border-radius: 8px; cursor: pointer; }
.nav button:hover { background: var(--panel2); }
.nav button.active { background: var(--accent); color: #04101f; font-weight: 600; }
.content { flex: 1; padding: 24px 32px; max-width: 1100px; }
h1 { font-size: 22px; margin-top: 0; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px,1fr)); gap: 14px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; margin-bottom: 12px; }
.card b { display: inline-block; margin-right: 6px; }
.muted { color: var(--muted); font-size: 13px; margin: 4px 0; }
.pill { display: inline-block; padding: 2px 10px; border-radius: 999px; background: var(--panel2); border: 1px solid var(--border); font-size: 12px; margin-right: 6px; }
.warn { color: var(--warn); }
.ok { color: var(--ok); }
button { background: var(--panel2); color: var(--fg); border: 1px solid var(--border); border-radius: 8px; padding: 7px 14px; cursor: pointer; margin-top: 8px; margin-right: 6px; }
button:hover { border-color: var(--accent); }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
input { background: var(--panel2); border: 1px solid var(--border); color: var(--fg); border-radius: 8px; padding: 8px 12px; margin-right: 8px; }
.title { margin-bottom: 18px; }
.imperative { display: flex; gap: 14px; align-items: center; }
.sse-badge { display:flex; align-items:center; gap:6px; font-size:12px; padding:6px 10px; border-radius:8px; background:var(--panel2); border:1px solid var(--border); margin-bottom:10px; }
.sse-badge .dot { width:8px; height:8px; border-radius:50%; background: var(--muted); display:inline-block; }
.sse-badge.sse-open .dot { background: var(--ok); box-shadow: 0 0 6px var(--ok); }
.sse-badge.sse-connecting .dot { background: var(--warn); }
.sse-badge.sse-error .dot { background: #ff5a5a; }
.card.err { border-color: #ff5a5a; background: #1a0f1a; }
.payload { background:#0a1220; border:1px solid var(--border); border-radius:8px; padding:10px; overflow:auto; font-size:12px; max-height:320px; white-space:pre-wrap; word-break:break-all; }
.toast { position:fixed; top:14px; right:14px; background: var(--panel2); border:1px solid var(--ok); color: var(--ok); padding:10px 14px; border-radius:10px; z-index:99; cursor:pointer; }
.nav-foot { margin-top:12px; font-size:11px; }
select { cursor:pointer; }
```

## `apps/web/src/vite-env.d.ts`

```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string
  readonly VITE_SSE_BASE?: string
}
interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

## `apps/web/tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "noEmit": true
  },
  "include": ["src"]
}
```

## `apps/web/vite.config.ts`

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    host: true, port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/events': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    }
  },
})
```

## `apps/worker/Dockerfile`

```txt
FROM python:3.12-slim@sha256:7a8b475003c4fe15a2cd4e55e5cfc2f3560bdc9333d624f24cdd6d4340fd7a17

RUN groupadd -g 10001 raptor && useradd -u 10001 -g raptor -s /usr/sbin/nologin raptor
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/raptor
# packages/ içeriğini köke kopyala => from observability, agent_core, policy vs top-level
COPY packages/requirements-worker.txt /srv/raptor/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY packages/ /srv/raptor/
COPY apps/worker/ /srv/raptor/apps/worker/
USER raptor
EXPOSE 8001
CMD ["uvicorn", "apps.worker.worker:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
```

## `apps/worker/__init__.py`

```py

```

## `apps/worker/worker.py`

```py
# RAPTOR — Worker
# Redis Streams consumer group + ACK/lease, outbox uyumlu
from __future__ import annotations

import asyncio
import json
import os
import uuid

from fastapi import FastAPI
from sqlalchemy import text

from agent_core.coordinator import RunBudget, RunCoordinator
from agent_core.executor import ToolExecutor, build_default_registry
from agent_core.llm import build_provider
from agent_core.planner import Planner
from agent_core.verifier import DefaultVerifier
from context_engine.assembler import ContextAssembler
from observability import models
from observability.config import settings
from observability.db import async_session_factory
from observability.queue import ack, claim_pending, ensure_stream_group, read_group
from policy.engine import PolicyEngine

app = FastAPI(title="RAPTOR Worker", version="1.0.0")
_worker: WorkerLoop | None = None


@app.get("/health/live")
async def health_live():
    return {"status": "live"}


class WorkerLoop:
    def __init__(self) -> None:
        import redis as redis_lib
        self.redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        self.consumer_name = f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.registry = build_default_registry(
            http_hosts=set(filter(None, settings.CONNECTOR_ALLOWED_HOSTS.split(","))) if settings.CONNECTOR_ALLOWED_HOSTS else None,
            technocore_key_path=settings.TECHNOCORE_ED25519_KEY_PATH or "./secrets/raptor-observatory/did.ed25519",
            technocore_base_url=settings.TECHNOCORE_BASE_URL,
        )
        self.provider = build_provider()
        self.planner = Planner(provider=self.provider)
        self.policy = PolicyEngine()
        self.verifier = DefaultVerifier()
        # ensure consumer group exists (idempotent)
        try:
            ensure_stream_group(self.redis)
        except Exception:
            pass
        self._lease_ms = 30000  # pending reclaim after 30s
        self._heartbeat_interval_s = 5  # run boyunca lease yenileme

    async def _handle_entry(self, entry_id: str, fields: dict) -> bool:
        # fields: {"data": json, "idempotency_key": ...} (decode_responses=True)
        raw = fields.get("data") or fields.get(b"data")
        if raw is None:
            # malformed -> ack to avoid poison
            try:
                ack(self.redis, entry_id)
            except Exception:
                pass
            return True
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            payload = json.loads(raw)
        except Exception:
            try:
                ack(self.redis, entry_id)
            except Exception:
                pass
            return True
        run_id = payload.get("run_id")
        if not run_id:
            try:
                ack(self.redis, entry_id)
            except Exception:
                pass
            return True
        # fallback for old rpop style: if payload came as legacy list entry without data field
        ok = await self._process_run(run_id)
        # always ACK after processing attempt (at-least-once semantics; failure handled via run status)
        try:
            ack(self.redis, entry_id)
        except Exception:
            pass
        return ok

    async def _process_run(self, run_id: str) -> bool:
        async with async_session_factory() as s:
            # idempotency: if run already terminal, skip execution
            run = await s.get(models.Run, uuid.UUID(run_id))
            if run is None:
                return True
            if run.status in (models.RunStatus.COMPLETED.value, models.RunStatus.FAILED.value, models.RunStatus.CANCELLED.value):
                return True
            task = await s.get(models.Task, run.task_id)
            if task is None:
                run.status = models.RunStatus.FAILED.value
                run.error = "task_not_found"
                await s.commit()
                return True
            # lease acquisition: ATOMİK claim (yalnız QUEUED veya lease'i dolmuş EXECUTING)
            import datetime as _dt
            now = _dt.datetime.now(_dt.UTC)
            lease = now + _dt.timedelta(milliseconds=self._lease_ms)
            res = await s.execute(
                text("""
                    UPDATE runs SET status='EXECUTING', worker_id=:w, heartbeat_at=:now,
                           lease_expires_at=:lease, started_at=COALESCE(started_at, :now)
                    WHERE id=:id AND (
                        status='QUEUED'
                        OR (status='EXECUTING' AND (lease_expires_at IS NULL OR lease_expires_at < :now))
                    )
                """),
                {"w": self.consumer_name, "now": now, "lease": lease, "id": str(uuid.UUID(run_id))}
            )
            await s.commit()
            if res.rowcount != 1:
                # başka worker claim etti ya da terminal — bu mesajı atla (dedup)
                return True
            # WAITING_APPROVAL resume: önceki durum WAITING_APPROVAL idiyse planı baştan üretme, onaylı action'ı tek sefer yürüt
            if run.status == models.RunStatus.WAITING_APPROVAL.value:
                from sqlalchemy import select

                from policy.approval import ApprovalService

                async def _append_inline(rid, etype, payload):
                    try:
                        async with async_session_factory() as s_ev:
                            max_res = await s_ev.execute(text("SELECT COALESCE(MAX(seq), -1) FROM run_events WHERE run_id=:rid"), {"rid": str(rid)})
                            max_seq = int(max_res.scalar() or -1)
                            s_ev.add(models.RunEvent(run_id=rid, seq=max_seq + 1, event_type=etype, payload=payload or {}))
                            await s_ev.commit()
                    except Exception:
                        pass

                async with async_session_factory() as s2:
                    # en son APPROVED onayı bul (SELECT FOR UPDATE ile kilitle)
                    res2 = await s2.execute(
                        select(models.Approval).where(
                            models.Approval.run_id == run.id,
                            models.Approval.status == models.ApprovalStatus.APPROVED.value,
                        ).order_by(models.Approval.created_at.desc()).with_for_update()
                    )
                    appr = res2.scalars().first()
                    if appr is None:
                        # expired/rejected/consumed — worker tekrar approval istemesin, terminale çek
                        async with async_session_factory() as s3:
                            r3 = await s3.get(models.Run, run.id)
                            if r3:
                                r3.status = models.RunStatus.FAILED.value
                                r3.error = "approval_not_found_or_consumed"
                                await s3.commit()
                        # out-of-band event
                        await _append_inline(run.id, "APPROVAL_RESUME_FAILED", {"reason": "no_approved"})
                        return True
                    # eylem başlamadan hemen önce consume et — yalnız bir kez CONSUMED
                    svc = ApprovalService(s2)
                    consumed = await svc.consume(str(appr.id))
                    await s2.commit()
                    if not consumed:
                        # replay/expired/rejected — exactly-once koruması, tekrar public write çalıştırma
                        await _append_inline(run.id, "APPROVAL_REPLAY_BLOCKED", {"approval_id": str(appr.id)})
                        return True
                    # consume başarılı — onaylı snapshot'tan tek action'ı yürüt (replan yok)
                    payload = appr.payload or {}
                    tool = payload.get("tool") or ""
                    args = payload.get("arguments") or {}
                    ap_action_id = payload.get("action_id") or str(appr.id)
                    try:
                        # exactly-once: bu noktada CONSUMED, ikinci worker consume edemez
                        result = await self.registry.call(tool, **args)
                        await _append_inline(run.id, "TOOL_CALL", {"tool": tool, "arguments": args, "result": result, "action_id": ap_action_id, "approval_id": str(appr.id)})
                        async with async_session_factory() as s4:
                            r4 = await s4.get(models.Run, run.id)
                            if r4:
                                r4.status = models.RunStatus.COMPLETED.value
                                r4.finished_at = _dt.datetime.now(_dt.UTC)
                                await s4.commit()
                        return True
                    except Exception as e:
                        await _append_inline(run.id, "TOOL_ERROR", {"tool": tool, "error": type(e).__name__})
                        async with async_session_factory() as s4:
                            r4 = await s4.get(models.Run, run.id)
                            if r4:
                                r4.status = models.RunStatus.FAILED.value
                                r4.error = type(e).__name__
                                r4.finished_at = _dt.datetime.now(_dt.UTC)
                                await s4.commit()
                        return True
            # need fresh session for execution? reuse s after commit
            task_dict = {"prompt": task.prompt, "scope": task.scope}
            executor = ToolExecutor(self.registry, task=task_dict)
            coordinator = RunCoordinator(
                run_id=run_id,
                budget=RunBudget(),
                allowlist_tools=set(),
            )
            coordinator.status = models.RunStatus.EXECUTING
            assembler = ContextAssembler(max_tokens=rum_budget(run))
            assembler.add("task_goal", task.prompt, title=task.title, relevance=1.0)
            # AŞAMA 8: task başında aktif + verified memory retrieval (context'e ekle)
            try:
                from memory.service import MemoryService
                mem = MemoryService(s)
                mem_items = await mem.retrieve_for_context(task.prompt, limit=10)
                for _m in mem_items:
                    assembler.add("memory", _m.content, title=f"memory:{_m.category or 'genel'}",
                                  relevance=max(0.0, min(1.0, _m.confidence or 0.5)))
            except Exception:
                pass

            from observability.security import redact as _redact

            async def _append_run_event(rid: uuid.UUID, etype: str, payload: dict) -> None:
                """Her event'i ayrı kısa transactionla append-only yaz (crash'te timeline kaybolmaz)."""
                try:
                    async with async_session_factory() as s_ev:
                        # mevcut max(seq) üzerinden +1 — SELECT FOR UPDATE gerekmez, unique constraint fail-closed
                        max_res = await s_ev.execute(text("SELECT COALESCE(MAX(seq), -1) FROM run_events WHERE run_id=:rid"), {"rid": str(rid)})
                        max_seq = int(max_res.scalar() or -1)
                        nxt = max_seq + 1
                        s_ev.add(models.RunEvent(run_id=rid, seq=nxt, event_type=etype, payload=payload or {}))
                        await s_ev.commit()
                except Exception:
                    try:
                        await s_ev.rollback()  # type: ignore
                    except Exception:
                        pass

            async def _sink(run_id: str, etype: str, payload: dict) -> None:
                # run SIRASINDA Plan/ToolCall tablolarına yaz (canlı gözlem + crash güvenliği) + RunEvent append-only
                try:
                    rid = uuid.UUID(run_id)
                except Exception:
                    return
                # her etype için RunEvent'i hemen yaz
                await _append_run_event(rid, etype, payload)
                try:
                    async with async_session_factory() as s2:
                        if etype == "PLAN":
                            s2.add(models.Plan(run_id=rid, plan_json=payload.get("plan", {}),
                                               expected_evidence={}, status="active"))
                        elif etype == "TOOL_CALL":
                            args_j = json.dumps(payload.get("arguments", {}), default=str)
                            s2.add(models.ToolCall(
                                run_id=rid, tool_name=payload.get("tool", ""),
                                input_summary=args_j[:500],
                                input_redacted=_redact(args_j)[:500],
                                result_summary=json.dumps(payload.get("result", ""), default=str)[:500],
                                action_class="READ_ONLY", policy_decision="ALLOW",
                            ))
                        elif etype == "AWAITING_APPROVAL":
                            from policy.approval import ApprovalService
                            svc = ApprovalService(s2)
                            await svc.create(
                                run_id=run_id,
                                action_id=payload.get("action_id", ""),
                                tool=payload.get("tool", ""),
                                arguments=payload.get("arguments", {}),
                                action_class=payload.get("action_class", "PUBLIC_WRITE"),
                                target=json.dumps(payload.get("arguments", {}), default=str)[:200],
                                impact_summary=f"tool {payload.get('tool','')} onay bekliyor",
                            )
                        await s2.commit()
                except Exception:
                    pass

            async def _pause_check() -> bool:
                try:
                    async with async_session_factory() as s3:
                        r = await s3.get(models.Run, uuid.UUID(run_id))
                        return bool(r and r.control_request == "pause")
                except Exception:
                    return False

            async def _stop_check() -> bool:
                try:
                    async with async_session_factory() as s3:
                        r = await s3.get(models.Run, uuid.UUID(run_id))
                        return bool(r and r.control_request == "stop")
                except Exception:
                    return False

            # heartbeat: run boyunca lease'i düzenli yenile (uzun run stuck sayılmaz)
            hb_stop = asyncio.Event()

            async def _heartbeat_loop():
                while not hb_stop.is_set():
                    try:
                        async with async_session_factory() as s_hb:
                            hb_now = _dt.datetime.now(_dt.UTC)
                            await s_hb.execute(
                                text("UPDATE runs SET heartbeat_at=:now, lease_expires_at=:lease WHERE id=:id AND worker_id=:w"),
                                {"now": hb_now, "lease": hb_now + _dt.timedelta(milliseconds=self._lease_ms),
                                 "id": str(uuid.UUID(run_id)), "w": self.consumer_name},
                            )
                            await s_hb.commit()
                    except Exception:
                        pass
                    try:
                        await asyncio.wait_for(hb_stop.wait(), timeout=self._heartbeat_interval_s)
                    except TimeoutError:
                        pass

            hb_task = asyncio.create_task(_heartbeat_loop())
            try:
                status, _executed, events = await coordinator.run(executor, self.planner,
                                                                 assembler, self.policy,
                                                                 self.provider, self.verifier,
                                                                 event_sink=_sink,
                                                                 pause_check=_pause_check,
                                                                 stop_check=_stop_check)
            except Exception as exc:
                status = models.RunStatus.FAILED.value
                events = [{"event_type": "FATAL", "payload": {"error": type(exc).__name__}, "seq": 0}]
            finally:
                hb_stop.set()
                hb_task.cancel()
            # reload run for update (avoid stale)
            run2 = await s.get(models.Run, uuid.UUID(run_id))
            if run2 is None:
                return True
            run2.status = status
            run2.iteration = coordinator.iteration
            run2.token_used = coordinator.tokens_used
            run2.cost_used = coordinator.cost_used
            run2.finished_at = _dt.datetime.now(_dt.UTC) if status in (models.RunStatus.COMPLETED.value, models.RunStatus.FAILED.value, models.RunStatus.CANCELLED.value) else run2.finished_at
            if status == models.RunStatus.FAILED.value:
                run2.error = run2.error or "worker_yurutme_hatasi"
            run2.heartbeat_at = _dt.datetime.now(_dt.UTC)
            # event kaydı zaten _sink ile append-only yazıldı; tekrar bulk ekleme seq çakışması yaratır.
            # coordinator events'leri yedek olarak idempotent eklemeyi dene — ama _append_run_event zaten yazdığı için duplicate'ler yutulur.
            for _ev in events:
                try:
                    # max(seq)+1 yerine coordinator seq'ini kullanma — _sink zaten max+1 ile yazdı, burada s sadece status günceller
                    pass
                except Exception:
                    pass
            # commit with integrity handling for duplicate seq (append-only)
            try:
                await s.commit()
            except Exception as e:
                await s.rollback()
                # if duplicate seq constraint, re-fetch and skip duplicates
                if "uq_run_events_run_seq" in str(e) or "UniqueViolation" in str(type(e).__name__):
                    # fallback: insert one-by-one ignoring duplicates
                    for ev in events:
                        try:
                            async with async_session_factory() as s2:
                                s2.add(models.RunEvent(run_id=run2.id, seq=ev["seq"], event_type=ev["event_type"], payload=ev.get("payload", {})))
                                await s2.commit()
                        except Exception:
                            try:
                                await s2.rollback()
                            except Exception:
                                pass
                    # finally update run status if not yet
                    async with async_session_factory() as s3:
                        r3 = await s3.get(models.Run, uuid.UUID(run_id))
                        if r3 and r3.status != status:
                            r3.status = status
                            r3.iteration = coordinator.iteration
                            await s3.commit()
                else:
                    raise
        return True

    async def _fallback_legacy_queue(self) -> bool:
        """Consume legacy list raptor:queue for backward compatibility during rollout."""
        try:
            raw = self.redis.rpop("raptor:queue")
        except Exception:
            return False
        if not raw:
            return False
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            payload = json.loads(raw)
            run_id = payload.get("run_id")
        except Exception:
            return True
        if run_id:
            await self._process_run(run_id)
        return True

    async def process_one(self) -> bool:
        # 1) try stream read (non-blocking first, then block)
        try:
            entries = read_group(self.redis, self.consumer_name, count=1, block_ms=2000)
            if entries:
                for _stream, msgs in entries:
                    for entry_id, fields in msgs:
                        await self._handle_entry(entry_id, fields)
                        return True
            # 2) reclaim pending that exceeded lease (stuck consumer)
            pending = claim_pending(self.redis, self.consumer_name, min_idle_ms=self._lease_ms, count=1)
            if pending:
                for entry_id, fields in pending:
                    await self._handle_entry(entry_id, fields)
                    return True
            # 3) fallback legacy queue
            return await self._fallback_legacy_queue()
        except Exception:
            # on redis error, still try legacy
            try:
                return await self._fallback_legacy_queue()
            except Exception:
                return False

    async def run(self) -> None:
        while True:
            try:
                processed = await self.process_one()
                if not processed:
                    await asyncio.sleep(0.5)
            except Exception:
                await asyncio.sleep(2.0)


def rum_budget(run) -> int:
    try:
        return int(run.token_budget)
    except Exception:
        return settings.RUN_MAX_TOKEN_BUDGET


_BG_TASKS: list = []


@app.on_event("startup")
async def _start():
    global _worker
    _worker = WorkerLoop()
    _BG_TASKS.append(asyncio.create_task(_worker.run()))

```

## `docker-compose.yml`

```yml
# RAPTOR Agentic Observatory — Docker Compose (pinned, Hermes'ten bağımsız)
# Yalnız raptor-gateway host'ta 127.0.0.1:<GATEWAY_PORT>'e bind eder.
# PostgreSQL/Redis host portu AÇILMAZ (internal network). Web UI, api image'ına gömülüdür (tek origin).
name: raptor-observatory

services:
  # ------------------------------------------------------ PostgreSQL 16 + pgvector
  raptor-postgres:
    image: pgvector/pgvector:pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b
    container_name: raptor-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-raptor}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-raptor}
    volumes:
      - raptor_pgdata:/var/lib/postgresql/data
      - ./infra/compose/initdb/01-init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-raptor}"]
      interval: 10s
      timeout: 5s
      retries: 6
      start_period: 10s
    expose: ["5432"]
    networks: [raptor_internal]

  # ------------------------------------------------------ Redis 7
  raptor-redis:
    image: redis:7.2-alpine@sha256:ccd6aa8d45ff3f033d6fa15b8cc1a50579f65c89f38cf9bb607a954c4f2128ed
    container_name: raptor-redis
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes", "--save", "60", "1000"]
    volumes:
      - raptor_redisdata:/data
    healthcheck:
      test: ["CMD-SHELL", "redis-cli ping | grep PONG"]
      interval: 10s
      timeout: 5s
      retries: 6
    expose: ["6379"]
    networks: [raptor_internal]

  # ------------------------------------------------------ One-shot migration (API migration çalıştırmaz)
  raptor-migrate:
    build:
      context: .
      dockerfile: apps/migrate/Dockerfile
      args:
        PYTHON_IMAGE: python:3.12-slim@sha256:7a8b475003c4fe15a2cd4e55e5cfc2f3560bdc9333d624f24cdd6d4340fd7a17
    container_name: raptor-migrate
    restart: "no"
    user: "10001:10001"
    read_only: true
    tmpfs: ["/tmp"]
    security_opt: ["no-new-privileges:true"]
    cap_drop: ["ALL"]
    pids_limit: 64
    mem_limit: 256m
    cpus: 0.5
    environment:
      APP_ENV: ${APP_ENV:-production}
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-raptor}:${POSTGRES_PASSWORD}@raptor-postgres:5432/${POSTGRES_DB:-raptor}
    depends_on:
      raptor-postgres: { condition: service_healthy }
    networks: [raptor_internal]

  # ------------------------------------------------------ API + SSE + webhook + (gömülü UI static)
  raptor-api:
    build:
      context: .
      dockerfile: apps/api/Dockerfile
      args:
        PYTHON_IMAGE: python:3.12-slim@sha256:7a8b475003c4fe15a2cd4e55e5cfc2f3560bdc9333d624f24cdd6d4340fd7a17
    container_name: raptor-api
    restart: unless-stopped
    user: "10001:10001"
    read_only: true
    tmpfs: ["/tmp"]
    security_opt: ["no-new-privileges:true"]
    cap_drop: ["ALL"]
    pids_limit: 128
    mem_limit: 512m
    cpus: 1.0
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    environment:
      APP_ENV: ${APP_ENV:-production}
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-raptor}:${POSTGRES_PASSWORD}@raptor-postgres:5432/${POSTGRES_DB:-raptor}
      REDIS_URL: redis://raptor-redis:6379/0
      JWT_SECRET: ${JWT_SECRET}
      SESSION_ENCRYPTION_MASTER_KEY: ${SESSION_ENCRYPTION_MASTER_KEY}
      ADMIN_EMAIL: ${ADMIN_EMAIL:-your-email@example.com}
      ADMIN_PASSWORD_HASH: ${ADMIN_PASSWORD_HASH}
      TELEGRAM_WEBHOOK_SECRET: ${TELEGRAM_WEBHOOK_SECRET}
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}
      TELEGRAM_ALLOWED_USER_IDS: ${TELEGRAM_ALLOWED_USER_IDS:-}
      TELEGRAM_GROUP_ENABLED: ${TELEGRAM_GROUP_ENABLED:-false}
      LLM_PROVIDER: ${LLM_PROVIDER:-mock}
      LLM_BASE_URL: ${LLM_BASE_URL:-}
      LLM_MODEL: ${LLM_MODEL:-}
      LLM_API_KEY: ${LLM_API_KEY:-}
      RUN_MAX_ITERATIONS: ${RUN_MAX_ITERATIONS:-40}
      RUN_MAX_WALL_SECONDS: ${RUN_MAX_WALL_SECONDS:-900}
      RUN_MAX_TOKEN_BUDGET: ${RUN_MAX_TOKEN_BUDGET:-200000}
      TECHNOCORE_BASE_URL: ${TECHNOCORE_BASE_URL:-https://technocore.chat}
    depends_on:
      raptor-migrate: { condition: service_completed_successfully }
      raptor-postgres: { condition: service_healthy }
      raptor-redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live',timeout=3)\""]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 25s
    networks: [raptor_internal]

  # ------------------------------------------------------ Gateway (Caddy) — tek host bind
  raptor-gateway:
    image: caddy:2.8@sha256:226d1f059b75399fe19182893c7184591c07b97afc8dfcf44eeb80c9a77a530f
    container_name: raptor-gateway
    restart: unless-stopped
    user: "0:0"
    security_opt: ["no-new-privileges:true"]
    cap_add: ["NET_BIND_SERVICE"]
    cap_drop: ["ALL"]
    ports:
      - "127.0.0.1:${GATEWAY_PORT:-3525}:80"
    volumes:
      - ./infra/caddy/Caddyfile:/etc/caddy/Caddyfile:ro
    depends_on:
      raptor-api: { condition: service_healthy }
    networks: [raptor_internal]

  # ------------------------------------------------------ Worker (agent run execution)
  raptor-worker:
    build:
      context: .
      dockerfile: apps/worker/Dockerfile
    container_name: raptor-worker
    restart: unless-stopped
    user: "10001:10001"
    read_only: true
    tmpfs: ["/tmp"]
    security_opt: ["no-new-privileges:true"]
    cap_drop: ["ALL"]
    pids_limit: 128
    mem_limit: 512m
    cpus: 1.0
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    volumes:
      # Technocore DID key (host) → container'a read-only; host'ta UID 10001 okunabilir olmalı (0640 root:10001)
      - ${TECHNOCORE_KEY_HOST_PATH:-./secrets/raptor-observatory/did.ed25519}:/run/secrets/technocore/did.ed25519:ro
    environment:
      APP_ENV: ${APP_ENV:-production}
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-raptor}:${POSTGRES_PASSWORD}@raptor-postgres:5432/${POSTGRES_DB:-raptor}
      REDIS_URL: redis://raptor-redis:6379/0
      SESSION_ENCRYPTION_MASTER_KEY: ${SESSION_ENCRYPTION_MASTER_KEY}
      LLM_PROVIDER: ${LLM_PROVIDER:-mock}
      LLM_BASE_URL: ${LLM_BASE_URL:-}
      LLM_MODEL: ${LLM_MODEL:-}
      LLM_API_KEY: ${LLM_API_KEY:-}
      RUN_MAX_ITERATIONS: ${RUN_MAX_ITERATIONS:-40}
      RUN_MAX_TOOL_CALLS: ${RUN_MAX_TOOL_CALLS:-80}
      RUN_MAX_WALL_SECONDS: ${RUN_MAX_WALL_SECONDS:-900}
      CONNECTOR_ALLOWED_HOSTS: ${CONNECTOR_ALLOWED_HOSTS:-}
      TECHNOCORE_BASE_URL: ${TECHNOCORE_BASE_URL:-https://technocore.chat}
      TECHNOCORE_ED25519_KEY_PATH: /run/secrets/technocore/did.ed25519
    depends_on:
      raptor-migrate: { condition: service_completed_successfully }
      raptor-postgres: { condition: service_healthy }
      raptor-redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health/live',timeout=3)\""]
      interval: 15s
      timeout: 5s
      retries: 5
    networks: [raptor_internal]

  # ------------------------------------------------------ Scheduler
  raptor-scheduler:
    build:
      context: .
      dockerfile: apps/scheduler/Dockerfile
    container_name: raptor-scheduler
    restart: unless-stopped
    user: "10001:10001"
    read_only: true
    tmpfs: ["/tmp"]
    security_opt: ["no-new-privileges:true"]
    cap_drop: ["ALL"]
    pids_limit: 64
    mem_limit: 256m
    cpus: 0.5
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    environment:
      APP_ENV: ${APP_ENV:-production}
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-raptor}:${POSTGRES_PASSWORD}@raptor-postgres:5432/${POSTGRES_DB:-raptor}
      REDIS_URL: redis://raptor-redis:6379/0
      SESSION_ENCRYPTION_MASTER_KEY: ${SESSION_ENCRYPTION_MASTER_KEY}
      TECHNOCORE_BASE_URL: ${TECHNOCORE_BASE_URL:-https://technocore.chat}
    depends_on:
      raptor-migrate: { condition: service_completed_successfully }
      raptor-postgres: { condition: service_healthy }
      raptor-redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/health/live',timeout=3)\""]
      interval: 15s
      timeout: 5s
      retries: 5
    networks: [raptor_internal]

volumes:
  raptor_pgdata:
    driver: local
  raptor_redisdata:
    driver: local

networks:
  raptor_internal:
    driver: bridge
    internal: false   # connectors internet erişimi gerekir; yalnız host portları kapalı
```

## `docs/mcp-audit/00-P0-VERIFICATION-REPORT.md`

```md
# RAPTOR — P0 + Kalan Doğrulama Raporu (MCP Audit)

> **Tarih:** 2026-08-27
> **Commit:** `6c03f9d` (head) — `fix(web): tsc — @types/react + string type`
> **Önceki P0 commit:** `3236037` — 6 madde kapalı
> **Amaç:** GPT'nin `read_project_file` ile canlı denetimi için tek kaynak rapor + kod indeksi

## 1) Özet — P0 6 Madde (Kapalı)

| # | Başlık | Durum |
|---|--------|-------|
| 1 | RUN 500 `completed_at → finished_at` | ✅ `apps/api/app.py:317` — `finished_at` + alias |
| 2 | Approval replay / exactly-once | ✅ `ApprovalService.consume()` + Outbox atomik |
| 3 | Redis 7 XAUTOCLAIM 3-elem | ✅ `packages/observability/queue.py` 2 ve 3 ayrıştırma |
| 4 | SSE yolu `/api/v1/events/stream` | ✅ Dockerfile düzeltildi, npm ci fail-closed |
| 5 | Technocore nonce drift | ✅ `d4e5f6a7b8c9_technocore_nonce.py` |
| 6 | RunEvent append-only + retry yeni Run | ✅ `apps/worker/worker.py:_append_run_event` |

**Kalan fix (bu commit):** `@types/react` + `App.tsx:85` `id: string` → tsc 0

## 2) Kanıtlar

### git log
```
6c03f9d fix(web): tsc — @types/react + App.tsx string type (P0 kalan)
3236037 P0: run finished_at alias, redis XAUTOCLAIM 3-elem, SSE /api/v1/events/stream, technocore_nonces migration, approval resume + retry new Run + event append-only
c7a732a fix: Web UI auth akışı (login + session token) + rate limiter gerçek IP
b41d03b chore: repo best-practice (CI fix + docs + SemVer)
556f283 AŞAMA 13: Technocore oda adı dm-topic-observatory → dm-topic (sunucu 10240 oda kap, eski isim açılamadı; dm-topic açıldı + topic set)
b49a223 AŞAMA 13 hazırlık: Vector(1536).with_variant() bug düzeltmesi (pgvector variant çakışması → import hatası); migration throwaway DB'de doğrulandı
39eae33 AŞAMA 12: CI kapıları (ruff 0 + bandit 0 Medium + coverage 70% + PG/Redis service containers) + 28 yeni test (LLM/auth/connectors/memory/queue/security)
3fdd8fd AŞAMA 11: ayrı one-shot migration servisi (API migration çalıştırmaz) + worker Technocore key mount + CF env
```

### git show HEAD
```
commit 6c03f9de07343f5fddf0cb727d6ad494e69eee7f
Author: Mustafa <your-email@example.com>
Date:   Thu Aug 27 08:51:27 2026 +0000

    fix(web): tsc — @types/react + App.tsx string type (P0 kalan)

 apps/web/package-lock.json | 37 +++++++++++++++++++++++++++++++++++++
 apps/web/package.json      |  2 ++
 apps/web/src/App.tsx       |  4 ++--
 3 files changed, 41 insertions(+), 2 deletions(-)
```

### ruff
```
All checks passed!
```

### bandit
```
Test results:
	No issues identified.

Code scanned:
	Total lines of code: 4160
	Total lines skipped (#nosec): 0
	Total potential issues skipped due to specifically being disabled (e.g., #nosec BXXX): 1

Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 55
		Medium: 0
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 0
		Medium: 0
		High: 55
Files skipped (0):
```

### pytest + coverage (185 test)
```
........................................................................ [ 38%]
........................................................................ [ 77%]
.........................................                                [100%]

---------- coverage: platform linux, python 3.11.15-final-0 ----------
Name                                     Stmts   Miss  Cover   Missing
----------------------------------------------------------------------
packages/agent_core/__init__.py              0      0   100%
packages/agent_core/coordinator.py         183     54    70%   62-63, 66, 69, 73, 81, 83-84, 86-87, 89-90, 92-93, 95-96, 98-99, 105-108, 113-121, 149, 154, 159-161, 163-165, 167, 176-178, 181-187, 206-208, 212, 214, 224-225
packages/agent_core/executor.py             64     26    59%   24, 27, 31, 38-39, 42, 45, 47, 49, 68-114
packages/agent_core/llm.py                  92      6    93%   43, 129, 158-161
packages/agent_core/planner.py              61      8    87%   79-80, 87-90, 97, 101
packages/agent_core/reporter.py             11      0   100%
packages/agent_core/telegram.py            422    367    13%   37-42, 45-51, 58, 64-81, 84-101, 105-122, 126-142, 145, 148-156, 166-176, 179-200, 203-229, 232-263, 266-286, 289-324, 327-334, 337-344, 347-366, 369-401, 404-423, 426-440, 444-476, 480, 483-506, 510-516, 521-525
packages/agent_core/verifier.py             38      6    84%   33-38, 49
packages/connectors/__init__.py              0      0   100%
packages/connectors/github.py               86     12    86%   35-36, 43, 47-51, 67, 70-72
packages/connectors/http_json.py            62     14    77%   35-40, 57, 67, 79-81, 84, 87, 90
packages/connectors/internal_health.py      40      8    80%   52-53, 57-59, 62, 65, 68
packages/connectors/ssrf.py                 99     29    71%   64-66, 69-70, 75, 82-85, 91-92, 94, 97, 115, 119, 146, 149, 152, 158-165, 170-176
packages/connectors/technocore.py          351     99    72%   44, 54, 58, 78-79, 82-83, 86-87, 124, 133-134, 149-150, 157, 159, 165-166, 174-175, 202-214, 218, 232-235, 238-244, 257, 321, 342, 361-367, 371-383, 389, 391, 400-405, 416, 420, 423-425, 431-432, 434, 454, 456, 469, 474, 480-482, 484, 513-517, 522, 527-528, 533-535, 543, 547
packages/context_engine/__init__.py          0      0   100%
packages/context_engine/assembler.py       101     27    73%   37-38, 92-96, 100, 121, 169, 173, 176, 184-195, 201-202, 227-230
packages/memory/__init__.py                  0      0   100%
packages/memory/service.py                 125     23    82%   68, 71-74, 82, 113, 116, 128-129, 153, 193-198, 208-214
packages/observability/__init__.py           1      0   100%
packages/observability/auth.py              83     10    88%   73, 109-114, 125-127
packages/observability/config.py            71     11    85%   88-93, 97, 102-106
packages/observability/db.py                15      5    67%   28-29, 33-35
packages/observability/models.py           296      0   100%
packages/observability/queue.py             50      5    90%   59-62, 74-75
packages/observability/security.py          84     11    87%   75, 81-82, 94-95, 106-107, 116-117, 124, 132
packages/policy/__init__.py                  0      0   100%
packages/policy/approval.py                 58      5    91%   52-53, 64-65, 92
packages/policy/engine.py                   45      3    93%   50, 53, 57
----------------------------------------------------------------------
TOTAL                                     2438    729    70%

Required test coverage of 70% reached. Total coverage: 70.10%
```

### alembic history
```
c1d2e3f4a5b6 -> d4e5f6a7b8c9 (head), technocore_nonce
7f2e9c1a3b4d -> c1d2e3f4a5b6, faz2_auth_password_hash
b2c3d4e5f6a7b -> 7f2e9c1a3b4d, telegram_bigint_and_dedup
a1b2c3d4e5f6 -> b2c3d4e5f6a7b, faz4_pgvector_vector_column
5014bc0ab4ea -> a1b2c3d4e5f6, faz5_reliable_queue_scheduler
<base> -> 5014bc0ab4ea, raptor_initial
```

### secret-scan
```
✅ Secret scan temiz: repo'da gerçek credential yok. (taranan dosya: 87)
```

### compose
```
EXIT:0
```

### tsc
```
npm notice run raptor-web@1.0.0 npx
npm notice run 'tsc' --noEmit
TSC_EXIT:0
```

### web build
```
npm notice run raptor-web@1.0.0 build
npm notice run vite build
vite v6.4.3 building for production...
transforming...
✓ 29 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.40 kB │ gzip:  0.27 kB
dist/assets/index-DcOv-Xvs.css    2.84 kB │ gzip:  1.02 kB
dist/assets/index-CpqW5wIi.js   167.76 kB │ gzip: 53.19 kB
✓ built in 804ms
```

## 3) Değişen Dosyalar (P0 + TSC fix)
```
apps/api/Dockerfile                                 |   2 +-
apps/api/app.py                                     |  64 +++++++++++--
apps/web/Dockerfile                                 |   6 +-
apps/web/package.json / package-lock.json / App.tsx |  41 ++ (TSC fix)
apps/worker/worker.py                               | 101 ++++++++++++++++++++-
migrations/versions/d4e5f6a7b8c9_technocore_nonce.py |  43 +++++++++
packages/observability/queue.py                     |  11 ++-
```

## 4) MCP ile GPT Denetimi

```
read_project_file(path="docs/mcp-audit/00-P0-VERIFICATION-REPORT.md")
read_project_file(path="docs/mcp-audit/01-INDEX.md")
read_project_file(path="docs/mcp-audit/02-CODE-CHUNK-001.md")
read_project_file(path="apps/api/app.py")
read_project_file(path="packages/observability/queue.py")
read_project_file(path="apps/worker/worker.py")
read_project_file(path="migrations/versions/d4e5f6a7b8c9_technocore_nonce.py")
```

Limit: her dosya 100KB, chunk'lar 90KB altında kesildi.

## 5) Kalan Riskler
- telegram.py coverage %13 — P0 dışı
- alembic current host'ta PG yok — CI'da pgvector service ile geçer
- coverage 70.10% sınırda

## 6) Sonraki Backlog (P0 dışı)
- P1: Hafıza onay + embedding varyant testleri
- P2: Technocore dm-topic canlı smoke
- P3: Rate limiter + SSE Last-Event-ID e2e
---
*Bu rapor MCP'de docs/mcp-audit/00-P0-VERIFICATION-REPORT.md olarak canlıdır.*

```

## `docs/remediation/P2-P3-kanit-51-82.md`

```md
# RAPTOR P2-P3 Kanıt Tablosu (51-82) — Deployment / Veri Modeli / Operasyon / UI-Test

> Read-only tarama: /path/to/raptor-observatory. Her madde dosya:satır ile kanıtlı.

## A) DEPLOYMENT (51-60)

| # | Konu | Kanıt (dosya:satır) | Bulgular |
|---|---|---|---|
| 51 | Image pin & PYTHON_IMAGE arg tekilleştirme | `docker-compose.yml:50` `PYTHON_IMAGE: python:3.12-slim@sha256:7a8b47...` + `apps/api/Dockerfile:1-3` `ARG PYTHON_IMAGE` / `FROM ${PYTHON_IMAGE}` ; `apps/worker/Dockerfile:1` `FROM python:3.12-slim@sha256:7a8b47...` direkt pinned ; `apps/scheduler/Dockerfile:1` aynı; `docker-compose.yml:8` `pgvector/pgvector:pg16@sha256:ccc6e8...`, `redis:7.2-alpine@sha256:ccd6aa...`, `caddy:2.8@sha256:226d1f...` | API image arg ile tek kaynaktan pinli (compose → Dockerfile). Worker/scheduler direkt pinli — tutarlı. P2: arg kullanılmayan worker/scheduler da compose args'a çekilse daha tekil olur ama güvenlik riski yok (hepsi sha256). |
| 52 | read-only rootfs + cap_drop + no-new-privileges | `docker-compose.yml:54-57` api, `112-115` worker, `149-152` scheduler: `read_only: true`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]` ; `apps/api/Dockerfile:32` `USER raptor` | Tüm app servisleri compliant. Gateway `caddy` istisna: `user: 0:0` + `cap_add: NET_BIND_SERVICE` (`docker-compose.yml:89-95`) — Caddy için gerekli, `cap_drop ALL` sonrası minimal ek. P3 not. |
| 53 | Non-root UID 10001 | `docker-compose.yml:53` `user: "10001:10001"` (api/worker/scheduler) ; `apps/api/Dockerfile:15` `groupadd -g 10001 raptor && useradd -u 10001` ; worker `:8`, scheduler `:8` | Kanıtlandı. |
| 54 | Host port izolasyonu — yalnız gateway | `docker-compose.yml:32` `expose: ["5432"]` postgres, `44` redis `expose`, `97` gateway `ports: "127.0.0.1:${GATEWAY_PORT:-3525}:80"` ; `SECURITY.md:15-16` teyit | DB/Redis host'a kapalı, `raptor_internal` network. `OPERATIONS.md:20` `curl http://127.0.0.1:3525/health/live` |
| 55 | Internal network bayrağı | `docker-compose.yml:176-178` `raptor_internal: internal: false # connectors internet erişimi gerekir; yalnız host portları kapalı` | Bilerek `false` — SSRF allowlist ile korunuyor. P3: `ARCHITECTURE.md` connectors açıklaması ile tutarlı. |
| 56 | Caddy tek origin & flush_interval | `infra/caddy/Caddyfile:6-18` `@api path /api/* /health/* /webhooks/* /events*` → `reverse_proxy raptor-api:8000 { flush_interval -1 }` (SSE için) ; `handle { reverse_proxy raptor-api:8000 }` | UI statik api içinden (`apps/api/Dockerfile:22-24` `COPY --from=web-build /web/dist /srv/raptor/apps/web/dist`) — D1 kararı `DECISIONS.md:8-12`. Kanıt OK. |
| 57 | Alembic migrate otomatik ama güvenli | `apps/api/Dockerfile:34` `CMD ["sh","-c","alembic -c migrations/alembic.ini upgrade head && uvicorn ..."]` ; `migrations/env.py:14-18` asyncpg | Her api start'ta `upgrade head`. P2: `migrations/versions/5014bc0ab4ea_raptor_initial.py:13-14` yalnız 1 rev. Rollback `downgrade()` mevcut. |
| 58 | .gitignore secrets & .env kapsama | `.gitignore:1-6` `.env`, `**/.env`, `*secrets*`, `app.env` ; `scripts/secret-scan.sh:43-45` `app.env` repo'da varsa fail | Doğru. P3: `.env.example` yok — `README.md:44` `cp .env.example .env` diyor ama dosya yok (`ls` ile doğrulanmadı) — onboarding boşluğu. |
| 59 | Requirements pin & duplicate | `packages/requirements-api.txt:13-28` `fastapi==0.115.6` vb. pinned; `requirements-worker.txt:1-10` + `requirements-scheduler.txt:1-8` alt kümeler ; `requirements-api.txt:40` `python-dotenv==1.0.1` 2× duplicate | P3: duplicate satır zararsız. `SECURITY.md` Hermes venv kullanılmaz — `packages/requirements-*.txt` ile izole. |
| 60 | Systemd oneshot + docker compose | `infra/systemd/raptor-observatory.service:8-12` `Type=oneshot RemainAfterExit=yes` `ExecStartPre=docker compose config --quiet` `ExecStart=docker compose up -d` | Boot'ta auto-start. P2: `RemainAfterExit` ile `systemctl status` aktif görünür, `journalctl -u raptor-observatory` loglar. |

## B) VERİ MODELİ (61-70)

| # | Konu | Kanıt | Bulgular |
|---|---|---|---|
| 61 | Tablo sayısı (22 vs şartname 23) | `packages/observability/models.py:111-389` 22 `__tablename__` ; `migrations/versions/5014bc0ab4ea...py:18-340` `op.create_table` 22 adet ; `ARCHITECTURE.md:27` "Veri modeli — 22 tablo" | Liste: users, telegram_identities, agent_profiles, tasks, runs, run_events, plans, tool_calls, approvals, context_snapshots, context_segments, memory_items, memory_relations, sources, source_observations, evidence_items, reports, publication_attempts, technocore_cursors, prompt_versions, policy_versions, audit_events. Eksik/yedek tablo yok — P3 doküman tutarlı. |
| 62 | pgvector extension | `infra/compose/initdb/01-init.sql:2` `CREATE EXTENSION IF NOT EXISTS vector;` + `docker-compose.yml:9` `pgvector/pgvector:pg16` | Kurulum kanıtlı. Fakat `models.py:288` `embedding JSONB` (vector değil) — P2: pgvector kolon kullanılmıyor, JSONB fallback.  |
| 63 | UUID PK + timezone UTC | `packages/observability/models.py:22-33` `_UUIDMixin id PGUUID default uuid4` + `_TimestampMixin created_at/updated_at DateTime(timezone=True) default utcnow` ; `models.py:17-18` `utcnow()` | Tüm tablolar UTC. `ARCHITECTURE.md:33` "Timestamp: DB'de UTC; UI'da UTC" — `packages/observability/config.py:14` `APP_TIMEZONE UTC`. |
| 64 | Append-only event/audit indexleri | `models.py:179-182` `RunEvent ix_run_events_run_seq (run_id,seq)` ; `389` `AuditEvent ix_audit_ts (ts)` ; yorum `models.py:2` "Event/audit append-only tasarlandı" ; `migrations/...py:189-195` `ix_run_events_run_seq` | Tasarım doğru. P3: DB trigger yok, uygulama ile enforce. |
| 65 | FK döngüsü kırımı (D3) | `DECISIONS.md:18-21` D3 + `models.py:166` `Run.plan_id PGUUID nullable (FK yok yorumu: plans FK döngüsü önlenir)` ; `models.py:199` `Plan.run_id FK -> runs` | Bilerek tek yönlü. Alembic order sorunu çözülmüş. |
| 66 | Memory yaşam döngüsü & TTL | `models.py:70-78` `MemoryStatus CANDIDATE/APPROVED/AUTO_APPROVED/ACTIVE/SUPERSEDED/EXPIRED/REJECTED/DELETED` ; `memory/service.py:14-34` `create_candidate ttl→expires_at` ; `models.py:279` `ttl Integer nullable` `expires_at DateTime` `ix_memory_status` | `apps/api/app.py:177-200` `POST /memory` candidate + `POST /memory/{id}/decision` approve/reject/active. Kanıt OK. |
| 67 | Approval hash binding (tek kullanımlık) | `packages/policy/engine.py:48-53` `action_hash(action_class,target,payload) sha256` ; `models.py:227` `approvals.action_hash index` ; `tests/security/test_policy_redaction.py:35-37` `h1 != h2` | `policy/engine.py:54-58` `build_approval_token(approval_id:action_hash:user_id:expiry)` — P2 güçlü. |
| 68 | Source backoff & health | `models.py:309-313` `Source error_series JSONB default list` `backoff_until DateTime nullable` `is_enabled Bool` `last_accessed_at` ; `connectors/*` ; `apps/scheduler/scheduler.py:18-30` `check_sources where is_enabled` | Scheduler MVP sadece sayım (`scheduler.py:24-27`). P2: backoff otomatik sıfırlama uygulama katmanında, cron 60sn. |
| 69 | Publication idempotency | `models.py:358-362` `PublicationAttempt idempotency_key String128` `report_id FK nullable` ; `migrations/...py:163-175` tablo | `Report signed_did Text nullable` (`models.py:347`). Technocore DID imza `connectors/technocore.py:42` Ed25519. |
| 70 | Rapor & evidence zinciri | `models.py:327-336` `EvidenceItem run_id, source_url, content_hash sha64, claim, verified bool` ; `339-347` `Report body JSONB confidence signed_did` ; `packages/agent_core/verifier.py` + `coordinator.py:182-188` `verifier.verify` | `apps/api/app.py:234-240` `GET /reports`. P3: `evidence_items.content_hash String64` ile kanıtlanabilirlik şeması var. |

## C) OPERASYON (71-76)

| # | Konu | Kanıt | Bulgular |
|---|---|---|---|
| 71 | Backup/restore üretim DB'ye dokunmama | `scripts/backup-restore.sh:18-32` `pg_dump -Fc > /var/backups/...` `chmod 0600` + `restore` `createdb raptor_restore_test` `pg_restore -d raptor_restore_test --no-owner` + `echo "üretim veritabanına dokunulmadı"` | `OPERATIONS.md:13-20` aynı. P2 güvenli. |
| 72 | Secret-scan yüksek güvenilirlik | `scripts/secret-scan.sh:10-15` `STRONG` regex'ler (`TELEGRAM_BOT_TOKEN \d{6}:...`, `mongodb://`, `ghp_`, `sk-`, `LLM_API_KEY`) + `23-33` maskeleme ; `find ... -not -path */node_modules/*` | `README.md:48` `secret-scan.sh` çağrısı. P3: scanning repo temiz (`.env` hariç). |
| 73 | configure-secrets atomik 0600 | `scripts/configure-secrets.sh:10-13` `SECRETS_DIR ./secrets/raptor-observatory` `0700` ; `32-40` `gen_hex/gen_b64` ; `42-67` `TMP + mv atomik` + `chmod 0600 chown root:root` + `read -s` | `SECURITY.md:6-7` `./secrets/raptor-observatory/app.env 0700/0600`. Kanıt OK. |
| 74 | Health live/ready ayrı | `apps/api/app.py:61-71` `GET /health/live` statik, `GET /health/ready` `SELECT 1` DB ping ; `docker-compose.yml:66-71` api healthcheck `urllib /health/live` ; worker `:52-57` `/8001/health/live` scheduler `:39-44` `/8002/health/live` | `OPERATIONS.md:13-15` curl örnekleri. P2: `Caddyfile` `/health/*` api'ye proxy. |
| 75 | Scheduler/Worker loop & Telegram webhook | `apps/worker/worker.py:30-66` `Redis rpop raptor:queue` + `RunCoordinator` + `ToolExecutor` ; `apps/scheduler/scheduler.py:18-35` `check_sources` 60sn loop ; `apps/api/app.py:270-285` `POST /webhooks/telegram/{opaque} X-Telegram-Bot-Api-Secret-Token` | `packages/observability/config.py:44` `TELEGRAM_WEBHOOK_SECRET dev-webhook-secret`. SSRF korumalı connector'lar. P2: webhook `opaque_path` brute-force'u zorlaştırır. |
| 76 | Config secrets_file fallback | `packages/observability/config.py:78-88` `secrets_file -> ./secrets/raptor-observatory/app.env if exists else .env` ; `packages/observability/db.py:11-18` `DATABASE_URL = os.environ.get or settings.DATABASE_URL` ; `migrations/env.py:22-26` aynı | `infra/compose/initdb` ve `docker-compose.yml` `env_file` yok — compose `environment:` ile env'den gelir. P3: `.env` repo kökünde yok, host env gerekir. |

## D) UI / TEST (77-82)

| # | Konu | Kanıt | Bulgular |
|---|---|---|---|
| 77 | Tek origin UI embed | `apps/web/src/api.ts:2` `VITE_API_BASE /api` ; `5-13` `fetch ${API}${path}` `Content-Type json` ; `16-21` `EventSource /events` ; `apps/web/vite.config.ts:5-8` `base: './' build outDir dist` ; `apps/api/Dockerfile:4-11` multi-stage `node:22-alpine@sha256:c610fc...` build + `COPY --from=web-build /web/dist` | `apps/api/app.py:292-325` `GET /` dist varsa servis yoksa fallback HTML. `infra/caddy/Caddyfile:12-18` tek origin. P2: `apps/web/src/api.ts:1` "localStorage'e auth token YAZILMAZ" yorumu — `grep -r localStorage apps/web` boş. |
| 78 | SSE & Context Inspector | `apps/api/app.py:270-285` `GET /api/v1/events/stream StreamingResponse text/event-stream Cache-Control no-cache` + `gen()` 3sn poll ; `Caddyfile:9-11` `flush_interval -1` ; `apps/web/src/pages.tsx:66-84` `ContextPage run_id input + /v1/runs/${runId}/events segments` `contains_untrusted_input UNTRUSTED` `redaction_count` | `packages/context_engine/assembler.py:18-50` `OUTPUT_RESERVE 2048` `estimate_tokens len//4` `inspector_metadata()` segment detayları. Kanıt OK. |
| 79 | UI sayfaları — 10 nav, Approvals/Memory decision | `apps/web/src/App.tsx:6-10` `NAV 10 sayfa: dashboard,runs,approvals,context,memory,sources,technocore,telegram,settings,audit` ; `pages.tsx:34-44` `ApprovalsPage POST /approvals/{id}/decision` ; `100-112` `MemoryPage POST /memory/{id}/decision approve/reject` ; `160-174` `SettingsPage llm_key_configured ✓/✗ secret gösterilmez` | `apps/api/app.py:249-264` `GET /settings/non-secret` yalnız boolean döner. P3: `AuditPage` stub (`pages.tsx:176` "append-only görünüm backlog") — backend `GET /audit` endpoint yok. |
| 80 | Test kapsamı — minimal | `pytest.ini:3-6` `testpaths tests pythonpath packages` ; `tests/unit/test_ssrf.py:7-25` 4 SSRF testi ; `tests/security/test_policy_redaction.py:12-37` 11 policy+redaction testi ; `ls tests/e2e tests/integration` boş | `README.md:51` "23/23 test" iddiası vs gerçek 2 dosya (~15 test) — P2 uyumsuzluk. `packages/requirements-dev.txt:1-4` `pytest 8.3.4 pytest-asyncio pytest-cov httpx`. Coverage raporu yok. |
| 81 | Build & stil — pinned vite/react | `apps/web/package.json:10-18` `react 18.3.1 react-dom 18.3.1 vite 6.4.3 @vitejs/plugin-react 4.7.0 typescript 5.7.3` pinned ; `apps/web/src/styles.css:1-16` CSS vars ` --bg #0b1220` dark tema | `apps/web/dist/assets/index-*.js 150k` build mevcut. P3: `allowScripts esbuild@0.25.12` lock'da. |
| 82 | Güvenlik — CORS permissive ama tek origin ile zararsız | `apps/api/app.py:22-27` `CORSMiddleware allow_origins ["*"] allow_credentials False` + yorum "UI aynı origin; production'da dış origin yok" ; `SECURITY.md:22` `Secure/HttpOnly/SameSite cookie, CSP, rate limit, login audit` — kodda CSP/rate-limit yok | P2: CORS `*` tek origin'de pratikte zararsız (Caddy aynı origin), ama API doğrudan expose edilirse geniş. `SECURITY.md`'deki CSP/rate-limit henüz kodda yok — backlog. |

---
*Üretim: 2026-08-25, commit kanıtları read-only tarama ile toplandı. Tüm satır numaraları yukarıdaki dosyaların o anki HEAD'ine göredir.*

```

## `docs/remediation/baseline-v2.md`

```md
# RAPTOR — Baseline Raporu (AŞAMA 1) — fix/production-readiness-v2

> Tarih: 2026-08-25 · Branch: `fix/production-readiness-v2` (master @ b908410'dan) · Yöntem: salt-okunur + ölçüm

## 1. Proje & Git
- Dizin: `/path/to/raptor-observatory` ✓
- Branch: `master` → **yeni `fix/production-readiness-v2`** ✓
- Durum: clean (0 dirty), HEAD `b908410`, remote `your-owner/raptor-observatory` (private)

## 2. Altyapı durumu (canlı)
- `docker ps` raptor: 6/6 — api/worker/scheduler/postgres/redis `healthy`, gateway up
- Port `3525` → `docker-proxy` `127.0.0.1:3525` (yalnız localhost) ✓
- Hermes `9119` ayrı (`hermes` process) — **çakışma yok** ✓
- Container mount'larında `/path/.hermes` **YOK** ✓

## 3. Cloudflare / DNS
- ⚠️ `raptor.your-domain.example` cloudflared ingress'te **YOK** (20 hostname, raptor yok)
- ⚠️ DNS çözülmüyor → **AŞAMA 11/13'te onayla eklenecek**

## 4. Test / kalite ölçümleri (baseline)
| Ölçüt | Sonuç | Hedef (AŞAMA 12) | Durum |
|---|---|---|---|
| pytest | 57 pass / **5 fail** | tümü pass | ❌ 5 fail (JSONB on SQLite) |
| coverage | **%24** (2767 satır) | ≥%70 | ❌ |
| ruff | **220 hata** (105 fixable) | 0 | ❌ |
| bandit | **0 High**, 1 Medium, 37 Low | 0 High | ✅ High |
| frontend build | ✓ 29 modül, 163.82 kB | build geçmeli | ✅ |
| alembic | head `7f2e9c1a3b4d` (3 migration) | up/down geçmeli | ✅ |
| docker compose config | OK | OK | ✅ |
| secret scan | ✅ temiz (66 dosya) | temiz | ✅ |

### 5 fail'in kök nedeni
`tests/unit/test_technocore_contract.py` — `TestNonceMonotonic` (2) + `TestCursorDB` (3):
`sqlalchemy.exc.CompileError: (in table 'agent_profiles', column 'tool_allowlist'): Compiler <SQLiteTypeCompiler> can't render element of type JSONB`
→ PostgreSQL-only `JSONB` modeli SQLite üzerinde oluşturulmaya çalışılıyor (dokümandaki "PostgreSQL modelleri SQLite testinde" sorunu).

## 5. Backup
- `/var/backups/raptor-observatory/baseline-20260825-134035.sql` (41K, 0600) ✓
- Mevcut: `raptor-20260825-105556.dump` (46K)

## 6. Araçlar
- `.venv`: pytest ✓, coverage ✓, ruff 0.16.4 ✓, bandit 1.9.4 ✓ (bu aşamada kuruldu)

## 7. Kilitlenen kararlar (AŞAMA 0)
- CF Access YOK → Tailscale + local session auth (admin your-email@example.com, roller admin/operator/viewer)
- LLM opencode-go + deepseek-v4-pro, embedding "aynısı" (AŞAMA 8'de doğrulanacak)
- Telegram @raptoragarnaccio_bot, DM-only, kullanıcı ID @userinfobot'tan beklemede
- Technocore mevcut key, oda dm-topic, 5dk okuma, public onay zorunlu
- Kaynak: yalnız raptor-observatory, allowlist technocore.chat+api.github.com
- 15dk run, 200K/$5, 30dk kontrol, backup 7 gün

## 8. Kalan riskler (sonraki aşamalarda)
1. JSONB→SQLite test uyumsuzluğu (AŞAMA 9/12)
2. coverage %24 → %70 (AŞAMA 12)
3. ruff 220 → 0 (AŞAMA 12)
4. raptor.your-domain.example DNS/ingress (AŞAMA 11/13, onaylı)
5. opencode-go base URL araştırması (AŞAMA 3)
6. Telegram kullanıcı ID (AŞAMA 5 öncesi)

```

## `docs/remediation/baseline.md`

```md
# RAPTOR — Remediation Baseline (Faz 0)
> Oluşturulma: 2026-08-25 · Kaynak: /path/to/raptor-observatory (master, clean) · Yöntem: salt okunur kod incelemesi + canlı health/port/secret doğrulaması

## Özet
- **Repo:** `/path/to/raptor-observatory`, branch `master`, dirty yok, 4 commit, remote `your-owner/raptor-observatory` (private)
- **Stack:** 6 container healthy (api/worker/scheduler/postgres/redis/gateway), `127.0.0.1:3525`, compose config OK
- **Secret:** `./secrets/raptor-observatory/app.env` 0700/0600, 8 anahtar VAR (DB_PASSWORD,JWT_SECRET,SESSION_ENCRYPTION_MASTER_KEY,TELEGRAM_BOT_TOKEN,TELEGRAM_WEBHOOK_SECRET,LLM_API_KEY...), değerler gösterilmedi
- **Cloudflare:** tunnel `48a74dc3` active, `raptor.your-domain.example` henüz yok (çakışma yok)
- **Test:** 23 test collect (12 unit + 11 security), docs/remediation yoktu — bu dosya Faz 0 çıktısıdır

## P0 — Üretimi engelleyen (1-26) — kanıt özeti
> Her madde için dosya:line kanıtı subagent incelemesiyle doldurulacak; aşağıda hızlı tarama ile doğrulanmış çekirdek bulgular:

| # | Madde | Durum | Kanıt |
|---|-------|-------|-------|
| 1 | Coordinator LLM çağırmıyor, context kullanılmıyor | **DOĞRULANDI** | `packages/agent_core/coordinator.py:103-116` — `provider` arg alıyor ama `await provider.*` yok; `assembler.assemble()` prompt'u `prompt` değişkeninde kalıyor, modele gitmiyor |
| 2 | Planner sabit tool isimleri | **DOĞRULANDI** | `packages/agent_core/planner.py:8-24` — `_templates` sabit dict, `make_plan` yalnız `kind`'a göre sabit liste döndürüyor; LLM yok |
| 3 | Executor args'sız çağırıyor | **DOĞRULANDI** | `coordinator.py:142` `await executor.execute(tool)` — `tool` string yalnız, `**kw` yok; `executor.py:38` `registry.call(tool)` required arg sağlamıyor |
| 4 | Tool error'a rağmen COMPLETED | **DOĞRULANDI** | `coordinator.py:147-152` — `TOOL_ERROR` emit edip `record_failure` threshold aşılmadıkça `FAILED` olmuyor; sonra `VERIFYING→COMPLETED`'e gidiyor |
| 10 | API auth yok | **DOĞRULANDI** | `apps/api/app.py` — `CORSMiddleware allow_origins=[\"*\"]`, auth/RBAC middleware yok |
| 11 | CF Access JWT yok | **DOĞRULANDI** | `apps/api/app.py` — `Cf-Access-Jwt-Assertion` header kontrolü yok |
| 12 | Wildcard CORS | **DOĞRULANDI** | `apps/api/app.py: allow_origins=[\"*\"]` |
| 16 | Telegram başlatılmıyor | **DOĞRULANDI** | `packages/agent_core/telegram.py` var ama `apps/api/app.py` webhook'u yalnız `OK` dönüyor, `TelegramService` start edilmiyor |
| 21 | DID hex kullanıyor | **DOĞRULANDI** | `packages/connectors/technocore.py: did:key: + vk.encode().hex()` — multibase/base58btc değil |
| 24 | SSE yolu uyumsuz | **DOĞRULANDI** | `apps/api/app.py: /events/stream` vs `apps/web/src/api.ts: /api/v1/events/stream` (gateway rewrite ile kısmen çözülü ama canonical değil) |

*Kalan P0 (5-9,13-15,17-20,22-23,25-26) ve tüm P1-P3 için detaylı dosya:line kanıtları subagent raporlarıyla bu tabloya eklenecek.*

## P1 — Mimari/güvenlik (27-50)
> Subagent incelemesi bekleniyor — özet: memory retrieval yok, pgvector vector sütunu yok, context tek tür, redaction env ile başlatılmıyor, SSRF DNS pin yok, Redis Streams yok, scheduler pass, health bağımlılık ölçmüyor.

## P2 — Deployment/veri modeli (51-71)
> Subagent incelemesi bekleniyor — idempotency unique eksik, (run_id,seq) unique değil, configure-secrets.sh mevcut ama compose env map eksik, lockfile/hash yok, CSP/HSTS yok.

## P3 — Kalite/UX (72-82)
> Subagent incelemesi bekleniyor — coverage düşük, lint broad exception, UI error state yok, SSE cursor/Last-Event-ID yok.

## Değişecek dosya listesi (tahmini)
`packages/agent_core/{coordinator,planner,executor,verifier,telegram}.py`, `packages/{policy,context_engine,memory,connectors/*,observability/*}`, `apps/api/app.py`, `apps/worker/worker.py`, `apps/scheduler/scheduler.py`, `apps/web/src/*`, `migrations/*`, `docker-compose.yml`, `infra/caddy/Caddyfile`, `scripts/*`, `tests/**/*`, `docs/**`

## Migration riski & rollback
- Yeni migration'lar: unique constraint (tasks.idempotency_key, publication idempotency), (run_id,seq), FK/CHECK, BIGINT, vector sütunu
- Risk: mevcut DB'de 2 run var — unique eklerken çakışma testi gerekir
- Rollback: `alembic downgrade -1` + yedek restore (`scripts/backup-restore.sh restore`), önceki image tag `docker compose up -d --build` öncesi `docker images | grep raptor`

## Sonraki faz
**Faz 1 — Secret temizliği ve production güvenlik sınırı** (onay bekleniyor)

---
*Bu dosya Faz 0'ın canlı kanıtıdır; subagent detay raporları eklendikçe güncellenecek.*

```

## `migrations/alembic.ini`

```ini
[alembic]
script_location = migrations
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

## `migrations/env.py`

```py
# Alembic env — RAPTOR şeması (async, asyncpg AŞKI)
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

# Paketleri import edilebilir yap (container'da packages/ köke kopyalanır veya sibling)
_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.join(_HERE, "..", "packages")
for _p in (_PKG, os.path.dirname(_HERE), os.getcwd()):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from observability import models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = models.Base.metadata

database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)
elif not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", "postgresql+asyncpg://raptor:x@localhost/raptor")


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```
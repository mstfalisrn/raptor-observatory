import { useEffect, useState, useCallback } from 'react'
import { api, errMsg, setToken } from './api'

// ---------- types ----------
type Report = {
  id: string
  report_type: string
  subject: string
  confidence: number
  created_at: string
  summary: string
  body?: unknown
}
type Run = {
  id: string
  status: string
  iteration: number
  created_at: string
  error?: string | null
  token_used?: number
  cost_used?: number
  worker_id?: string | null
  control_request?: string | null
}
type RunEvent = {
  seq: number
  event_type: string
  payload: Record<string, unknown> & { segments?: Segment[] }
  ts: string
}
type Segment = {
  segment_type: string
  token_count: number
  confidence: number
  included_reason: string
  preview?: string
  content_preview?: string
  contains_untrusted_input?: boolean
  _event?: string
  _seq?: number
}
type Approval = {
  id: string
  action_class: string
  target: string
  status: string
  impact_summary: string
  expires_at: string | null
}
type MemoryItem = {
  id: string
  content: string
  status: string
  confidence: number
  source: string
  category?: string | null
  expires_at?: string | null
  created_at: string
}
type SourceItem = {
  id: string
  name: string
  source_type: string
  is_enabled: boolean
  last_accessed_at: string | null
  error_series_len: number
}
type LoginResponse = { token: string; email: string; role: string }
type TaskCreateResponse = { run_id?: string; runId?: string; id?: string }

// ---------- helpers ----------
function useFetch<T>(path: string, deps: unknown[] = []) {
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
      const r = await api<LoginResponse>('/v1/auth/login', { method:'POST', body: JSON.stringify({ email, password }) })
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
      const r = await api<TaskCreateResponse>('/v1/tasks', { method:'POST', body: JSON.stringify({ title: title||prompt.slice(0,60), prompt }) })
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
type DashboardProps = {
  live: Record<string, unknown> | null
  sseState: string
  lastId: string
  onOpen: (k:string)=>void
  onOpenRun?: (id:string)=>void
}
export function Dashboard({ live, sseState, lastId, onOpen, onOpenRun }: DashboardProps) {
  const { data: runs, err: e1, loading: l1, reload: r1 } = useFetch<Run[]>('/v1/runs')
  const { data: approvals, err: e2, loading: l2, reload: r2 } = useFetch<Approval[]>('/v1/approvals')
  const { data: health } = useFetch<{status:string, time?:string}>('/health/live')
  const pending = approvals?.filter((a)=>a.status==='PENDING').length ?? 0
  const running = runs?.filter((r)=>['EXECUTING','QUEUED'].includes(r.status)).length ?? 0
  return (
    <div>
      <h1>📊 Dashboard</h1>
      <div className="cards">
        <div className="card"><b>SSE</b><div className={`pill sse-${sseState}`}>{sseState}</div><div className="muted">Last-Event-ID: {lastId || '—'}</div><div className="muted">{live ? `son event: ${String((live as Record<string,unknown>).event_type || (live as Record<string,unknown>).seq || JSON.stringify(live).slice(0,60))}` : 'bekleniyor'}</div></div>
        <div className="card"><b>Run&apos;lar</b><div>{l1 ? '...' : `${runs?.length ?? 0} toplam · ${running} aktif`}</div><button onClick={()=>onOpen('runs')}>Run&apos;ları gör</button></div>
        <div className="card"><b>Onaylar</b><div>{l2 ? '...' : `${pending} bekleyen`}</div><button onClick={()=>onOpen('approvals')}>Onaylara git</button>{pending>0 && <span className="pill warn">{pending} PENDING</span>}</div>
        <div className="card"><b>Sağlık</b><div>{health ? `✓ ${health.status}` : '...'}</div><div className="muted">{health?.time || ''}</div></div>
      </div>
      {(e1||e2) && <Err msg={e1||e2} onRetry={()=>{r1();r2()}} />}
      {/* son run'lar */}
      <h3 style={{marginTop:18}}>Son Run&apos;lar</h3>
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
  const [offset, setOffset] = useState(0)
  const { data, err, loading, reload } = useFetch<Run[]>(`/v1/runs?limit=${limit}&offset=${offset}`, [limit, offset])
  const [q, setQ] = useState('')
  const filtered = !q ? data : data?.filter(r=> r.id.includes(q) || r.status.toLowerCase().includes(q.toLowerCase()))
  const hasNext = (data?.length ?? 0) >= limit
  const hasPrev = offset > 0
  function goNext(){ if(hasNext) setOffset(o=>o+limit) }
  function goPrev(){ setOffset(o=>Math.max(0, o-limit)) }
  // limit değişince offset sıfırla
  function onLimitChange(v:number){ setLimit(v); setOffset(0) }
  return (
    <div>
      <h1>▶️ Runs</h1>
      <div style={{display:'flex', gap:8, marginBottom:10, flexWrap:'wrap', alignItems:'center'}}>
        <input placeholder="filtre (id/durum)" value={q} onChange={e=>setQ(e.target.value)} />
        <button onClick={()=>reload()}>↻ Yenile</button>
        <select value={String(limit)} onChange={e=>onLimitChange(parseInt(e.target.value))} style={{background:'var(--panel2)', color:'var(--fg)', border:'1px solid var(--border)', borderRadius:8, padding:'7px'}}>
          <option value="10">10</option><option value="20">20</option><option value="50">50</option>
        </select>
        <span className="pill">offset {offset} · limit {limit}{data ? ` · ${data.length} kayıt` : ''}</span>
        <button disabled={!hasPrev} onClick={goPrev}>← Geri</button>
        <button disabled={!hasNext} onClick={goNext}>İleri →</button>
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
  const { data: run, reload: reloadRun } = useFetch<Run>(`/v1/runs/${runId}`, [runId])
  const { data, err, loading, reload } = useFetch<RunEvent[]>(`/v1/runs/${runId}/events`, [runId])
  const [filter, setFilter] = useState('')
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const evs = !filter ? data : data?.filter((e)=> e.event_type.toLowerCase().includes(filter.toLowerCase()))
  const active = run && ['EXECUTING','QUEUED'].includes(run.status)
  const terminal = run && ['FAILED','COMPLETED','CANCELLED'].includes(run.status)
  async function control(action: string) {
    setBusy(action); setMsg('')
    try { await api(`/v1/runs/${runId}/control`, { method:'POST', body: JSON.stringify({ action }) }); setMsg(`✓ ${action} gönderildi`); reloadRun() }
    catch(e){ setMsg('⚠ '+errMsg(e)) } finally { setBusy('') }
  }
  async function retry() {
    setBusy('retry'); setMsg('')
    const idem = typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? `retry:${runId}:${(crypto as Crypto).randomUUID()}`
      : `retry:${runId}:${Date.now()}`
    try { await api(`/v1/runs/${runId}/retry`, { method:'POST', body: '{}', headers: { 'Idempotency-Key': idem } }); setMsg('✓ tekrar kuyruğa alındı'); reloadRun() }
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
          {evs.map((e,i)=> (
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
  const { data, err, loading, reload } = useFetch<Approval[]>('/v1/approvals')
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
  const { data: runs } = useFetch<Run[]>('/v1/runs?limit=20')
  const path = runId ? `/v1/runs/${runId}/events` : ''
  const { data, err, loading, reload } = useFetch<RunEvent[]>(path, [runId])
  // extract context segments from payloads
  const segments: Segment[] = (data||[]).flatMap((e)=> (e.payload?.segments as Segment[] | undefined ||[]).map((s)=> ({...s, _event:e.event_type, _seq:e.seq})))
  return (
    <div>
      <h1>🧩 Context Inspector</h1>
      <div style={{display:'flex', gap:8, flexWrap:'wrap', marginBottom:10}}>
        {runs && <select value={runId} onChange={e=>setRunId(e.target.value)} style={{background:'var(--panel2)', color:'var(--fg)', border:'1px solid var(--border)', borderRadius:8, padding:'8px'}}>
          <option value="">run seç…</option>
          {runs.map((r)=> <option key={r.id} value={r.id}>{r.id.slice(0,8)} · {r.status}</option>)}
        </select>}
        <input placeholder="run_id" value={runId} onChange={e => setRunId(e.target.value)} style={{flex:'1 1 260px'}} />
        <button onClick={reload} disabled={!runId}>↻ Yükle</button>
      </div>
      {!runId ? <Empty msg="run seçerek context segment metadata'sını gör."/> : loading ? <Loading/> : err ? <Err msg={err} onRetry={reload}/> : !segments.length ? <Empty msg="bu run için segment yok (event payload'ında segments beklenir)."/> : (
        <div>
          <div className="muted">{segments.length} segment · {data?.length} event</div>
          {segments.map((s, j) => (
            <div key={j} className="card ctx">
              <div><b>{s.segment_type}</b> · {s.token_count} tok · güv {s.confidence} <span className="pill">{s._event} #{s._seq}</span> {s.contains_untrusted_input && <span className="warn">UNTRUSTED</span>}</div>
              <div className="muted">neden: {s.included_reason}</div>
              {s.preview && <pre className="payload">{String(s.preview).slice(0,800)}</pre>}
              {s.content_preview && <pre className="payload">{String(s.content_preview).slice(0,800)}</pre>}
            </div>
          ))}
          <details style={{marginTop:12}}><summary className="muted">Ham event&apos;ler ({data?.length})</summary>
            {data!.map((e,i)=>(<div className="card" key={i}><b>{e.event_type}</b><pre className="payload">{JSON.stringify(e.payload||{}, null,2).slice(0,1500)}</pre></div>))}
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
  const { data, err, loading, reload } = useFetch<MemoryItem[]>(path, [status,q])
  const [busy,setBusy]=useState('')
  const [msg,setMsg]=useState('')
  // create form
  const [content,setContent]=useState('')
  const [source,setSource]=useState('')
  const [confidence,setConfidence]=useState('0.7')
  const [category,setCategory]=useState('')
  const [creating,setCreating]=useState(false)
  async function decide(id: string, decision: string) {
    setBusy(id); setMsg('')
    try { await api(`/v1/memory/${id}/decision`, { method: 'POST', body: JSON.stringify({ decision }) }); setMsg('✓ kaydedildi'); reload() }
    catch(e){ setMsg('⚠ '+errMsg(e)) } finally { setBusy('') }
  }
  async function createCandidate(e: React.FormEvent){
    e.preventDefault()
    if(!content.trim()){ setMsg('⚠ content gerekli'); return }
    const conf = parseFloat(confidence)
    if(isNaN(conf) || conf<0 || conf>1){ setMsg('⚠ confidence 0-1 arası olmalı'); return }
    setCreating(true); setMsg('')
    try{
      await api('/v1/memory', { method:'POST', body: JSON.stringify({ content: content.trim(), source: source.trim()||undefined, confidence: conf, category: category.trim()||null }) })
      setMsg('✓ candidate oluşturuldu'); setContent(''); setSource(''); setCategory(''); setConfidence('0.7'); reload()
    }catch(ex){ setMsg('⚠ '+errMsg(ex)) } finally { setCreating(false) }
  }
  return (
    <div>
      <h1>🧠 Memory</h1>
      <form onSubmit={createCandidate} className="card" style={{borderColor:'var(--accent)', display:'flex', flexDirection:'column', gap:8}}>
        <b>Yeni candidate oluştur (POST /v1/memory)</b>
        <textarea placeholder="content (gerekli)" value={content} onChange={e=>setContent(e.target.value)} rows={3} style={{background:'var(--panel2)', color:'var(--fg)', border:'1px solid var(--border)', borderRadius:8, padding:'8px'}} />
        <div style={{display:'flex', gap:8, flexWrap:'wrap'}}>
          <input placeholder="source (opsiyonel)" value={source} onChange={e=>setSource(e.target.value)} style={{flex:'1 1 160px'}} />
          <input placeholder="category (opsiyonel)" value={category} onChange={e=>setCategory(e.target.value)} style={{flex:'1 1 160px'}} />
          <input type="number" min={0} max={1} step={0.1} placeholder="confidence 0-1" value={confidence} onChange={e=>setConfidence(e.target.value)} style={{flex:'0 0 120px'}} />
          <button type="submit" disabled={creating || !content.trim()}>{creating?'oluşturuluyor…':'＋ Oluştur'}</button>
        </div>
      </form>
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
      {msg && <p className={msg.startsWith('⚠')?'warn':'ok'}>{msg}</p>}
    </div>
  )
}

// ---------- Sources ----------
export function SourcesPage() {
  const { data, err, loading, reload } = useFetch<SourceItem[]>('/v1/sources')
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
  const { data, err, loading, reload } = useFetch<{base_url:string, room_claim:string, registered:boolean}>('/v1/technocore')
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
  const { data, err, loading, reload } = useFetch<{telegram_token_configured:boolean, telegram_allowed_user_ids_count:number, telegram_group_enabled:boolean}>('/v1/settings/non-secret')
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
  const { data, err, loading, reload } = useFetch<{app_env:string, llm_provider:string, llm_model:string, llm_base_url:string, llm_key_configured:boolean, run_max_iterations:number, run_max_wall_seconds:number}>('/v1/settings/non-secret')
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

// ---------- Reports ----------
export function ReportsPage() {
  const { data, err, loading, reload } = useFetch<Report[]>('/v1/reports?limit=50')
  const [selected, setSelected] = useState<Report | null>(null)
  return (
    <div>
      <h1>📄 Reports</h1>
      <div style={{display:'flex', gap:8, marginBottom:10}}>
        <button onClick={reload}>↻ Yenile</button>
        {selected && <button onClick={()=>setSelected(null)}>← Listeye dön</button>}
        <span className="pill">{data ? `${data.length} rapor` : ''}</span>
      </div>
      {selected ? (
        <div className="card" style={{borderColor:'var(--accent)'}}>
          <h3 style={{marginTop:0}}>{selected.subject || '(konu yok)'} <span className="pill">{selected.report_type}</span></h3>
          <div className="muted">id {selected.id} · {selected.created_at?.slice(0,19)} · güven {selected.confidence}</div>
          <div style={{marginTop:10}}><b>Özet</b><p>{selected.summary || '—'}</p></div>
          <div><b>Body</b><pre className="payload" style={{whiteSpace:'pre-wrap', wordBreak:'break-word'}}>{selected.body ? JSON.stringify(selected.body, null, 2) : (selected.summary || '—')}</pre></div>
          <div className="muted" style={{marginTop:8}}>report_type: {selected.report_type} · subject: {selected.subject} · confidence: {selected.confidence}</div>
        </div>
      ) : loading ? <Loading/> : err ? <Err msg={err} onRetry={reload}/> : !data?.length ? <Empty msg="rapor yok."/> : (
        <div>
          {data.map(r=> (
            <div className="card" key={r.id} style={{cursor:'pointer'}} onClick={()=>setSelected(r)}>
              <div><b>{r.report_type}</b> — {r.subject || '(konu yok)'} <span className="pill">güven {r.confidence}</span></div>
              <div className="muted">{r.id.slice(0,8)} · {r.created_at?.slice(0,19)}</div>
              <div style={{marginTop:6, fontSize:13}}>{r.summary?.slice(0,200) || '—'}</div>
              <button onClick={(e)=>{e.stopPropagation(); setSelected(r)}} style={{marginTop:6}}>Detay</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------- Audit (now backed by /v1/reports, keeps legacy route) ----------
export function AuditPage() {
  const { data, err, loading, reload } = useFetch<Report[]>('/v1/reports?limit=50')
  const [selected, setSelected] = useState<Report | null>(null)
  return (
    <div>
      <h1>📜 Audit</h1>
      <p className="muted">GET /api/v1/reports — raporlar append-only listesi.</p>
      <div style={{display:'flex', gap:8, marginBottom:10}}>
        <button onClick={reload}>↻ Yenile</button>
        {selected && <button onClick={()=>setSelected(null)}>← Listeye dön</button>}
        <span className="pill">{data ? `${data.length} rapor` : ''}</span>
      </div>
      {selected ? (
        <div className="card" style={{borderColor:'var(--accent)'}}>
          <h3 style={{marginTop:0}}>{selected.subject || '(konu yok)'} <span className="pill">{selected.report_type}</span></h3>
          <div className="muted">id {selected.id} · {selected.created_at?.slice(0,19)} · güven {selected.confidence}</div>
          <div style={{marginTop:10}}><b>Özet</b><p>{selected.summary || '—'}</p></div>
          <div><b>Body</b><pre className="payload" style={{whiteSpace:'pre-wrap', wordBreak:'break-word'}}>{selected.body ? JSON.stringify(selected.body, null, 2) : (selected.summary || '—')}</pre></div>
          <div className="muted" style={{marginTop:8}}>report_type: {selected.report_type} · subject: {selected.subject} · confidence: {selected.confidence}</div>
        </div>
      ) : loading ? <Loading/> : err ? <Err msg={err} onRetry={reload}/> : !data?.length ? <Empty msg="rapor yok."/> : (
        <div>
          {data.map(r=> (
            <div className="card" key={r.id} style={{cursor:'pointer'}} onClick={()=>setSelected(r)}>
              <div><b>{r.report_type}</b> — {r.subject || '(konu yok)'} <span className="pill">güven {r.confidence}</span></div>
              <div className="muted">{r.id.slice(0,8)} · {r.created_at?.slice(0,19)}</div>
              <div style={{marginTop:6, fontSize:13}}>{r.summary?.slice(0,200) || '—'}</div>
              <button onClick={(e)=>{e.stopPropagation(); setSelected(r)}} style={{marginTop:6}}>Detay</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

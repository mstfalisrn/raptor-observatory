import { useEffect, useState } from 'react'
import { api } from './api'

function useFetch<T>(path: string, dep: any = '') {
  const [data, setData] = useState<T | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { let on = true; api<T>(path).then(d => on && setData(d)).catch(e => on && setErr(String(e))); return () => { on = false } }, [path, dep])
  return { data, err }
}

// ---------- Dashboard ----------
export function Dashboard({ live, onOpen }: any) {
  return (
    <div>
      <h1>📊 Dashboard</h1>
      <div className="cards">
        <div className="card"><b>Canlı SSE</b><div>{live ? 'bağlı' : 'bekleniyor'}</div></div>
      </div>
      <p><button onClick={() => onOpen('runs')}>▶️ Run'ları gör</button></p>
    </div>
  )
}

// ---------- Runs ----------
export function RunsPage() {
  const { data } = useFetch<any[]>('/v1/runs')
  return (
    <div>
      <h1>▶️ Runs</h1>
      {!data ? <p>yükleniyor…</p> : data.length === 0 ? <p>run yok</p> : (
        <table><thead><tr><th>ID</th><th>Durum</th><th>Iter</th><th>Hata</th></tr></thead><tbody>
          {data.map(r => <tr key={r.id}><td>{r.id.slice(0,8)}</td><td>{r.status}</td><td>{r.iteration}</td><td>{r.error||''}</td></tr>)}
        </tbody></table>
      )}
    </div>
  )
}

// ---------- Approvals ----------
export function ApprovalsPage() {
  const { data } = useFetch<any[]>('/v1/approvals')
  const [done, setDone] = useState('')
  async function decide(id: string, decision: string) {
    await api(`/v1/approvals/${id}/decision`, { method: 'POST', body: JSON.stringify({ decision, approval_id: id }) })
    setDone('karar kaydedildi')
  }
  return (
    <div>
      <h1>🕐 Approvals</h1>
      {!data ? <p>yükleniyor…</p> : data.length === 0 ? <p>onay yok</p> : data.map(a => (
        <div className="card" key={a.id}>
          <b>{a.action_class}</b> — {a.target}
          <div className="muted">etki: {a.impact_summary}</div>
          <span className="pill">{a.status}</span>
          {a.status === 'PENDING' && (<>
            <button onClick={() => decide(a.id, 'approve')}>✅ Onayla</button>
            <button onClick={() => decide(a.id, 'reject')}>❌ Reddet</button>
          </>)}
        </div>
      ))}
      {done && <p className="ok">{done}</p>}
    </div>
  )
}

// ---------- Context Inspector ----------
export function ContextPage() {
  const [runId, setRunId] = useState('')
  const { data } = useFetch<any[]>(runId ? `/v1/runs/${runId}/events` : '', runId)
  return (
    <div>
      <h1>🧩 Context Inspector</h1>
      <input placeholder="run_id" value={runId} onChange={e => setRunId(e.target.value)} />
      {data?.length ? data.map((e, i) => (
        <div className="card" key={i}><b>{e.event_type}</b>
          {e.payload?.segments?.map((s: any, j: number) => (
            <div key={j} className="ctx">
              <div><b>{s.segment_type}</b> · {s.token_count} tok · güv {s.confidence}</div>
              <div className="muted">neden: {s.included_reason}</div>
              {s.contains_untrusted_input && <span className="warn">UNTRUSTED</span>}
            </div>
          ))}
        </div>
      )) : <p>run_id girerek context segment metadata'sını gör.</p>}
    </div>
  )
}

// ---------- Memory ----------
export function MemoryPage() {
  const { data } = useFetch<any[]>('/v1/memory?limit=50')
  async function decide(id: string, decision: string) {
    await api(`/v1/memory/${id}/decision`, { method: 'POST', body: JSON.stringify({ decision }) })
  }
  return (
    <div>
      <h1>🧠 Memory</h1>
      {!data ? <p>yükleniyor…</p> : data.length === 0 ? <p>aday hafıza yok</p> : data.map(m => (
        <div className="card" key={m.id}>
          <p>{m.content}</p>
          <div className="muted">{m.status} · güv {m.confidence} · {m.source}</div>
          <span className="pill">{m.status}</span>
          <button onClick={() => decide(m.id, 'approve')}>✅</button>
          <button onClick={() => decide(m.id, 'reject')}>❌</button>
        </div>
      ))}
    </div>
  )
}

// ---------- Sources ----------
export function SourcesPage() {
  const { data } = useFetch<any[]>('/v1/sources')
  return (
    <div>
      <h1>📡 Sources</h1>
      {!data ? <p>yükleniyor…</p> : data.length === 0 ? <p>kaynak yok. Teknolojik İlk Önce connector ile eklenir.</p> : data.map(s => (
        <div className="card" key={s.id}><b>{s.name}</b> · <span className="pill">{s.source_type}</span>
          <div className="muted">{s.is_enabled ? 'aktif' : 'pasif'} · hata serisi: {s.error_series_len}</div></div>
      ))}
    </div>
  )
}

// ---------- Technocore ----------
export function TechnocorePage() {
  const { data } = useFetch<any>('/v1/technocore')
  return (
    <div>
      <h1>🛰️ Technocore</h1>
      {data && <div className="card"><b>{data.base_url}</b><div>Oda: {data.room_claim}</div><div>Kayıt: {data.registered ? '✓' : 'henüz değil (Faz 7)'}</div></div>}
    </div>
  )
}

// ---------- Telegram ----------
export function TelegramPage() {
  const { data } = useFetch<any>('/v1/settings/non-secret')
  return (
    <div>
      <h1>✈️ Telegram</h1>
      {data && (<div className="card">
        <div><span className="pill">{data.telegram_token_configured ? 'bot token ✓' : '⚠️ token yok'}</span></div>
        <div>Allowlist kullanıcı: {data.telegram_allowed_user_ids_count}</div>
        <div>Grup: {data.telegram_group_enabled ? 'açık' : 'kapalı'}</div>
      </div>)}
    </div>
  )
}

// ---------- Settings ----------
export function SettingsPage() {
  const { data } = useFetch<any>('/v1/settings/non-secret')
  return (
    <div>
      <h1>⚙️ Settings</h1>
      {data && (<div className="card">
        <div>Ortam: <b>{data.app_env}</b></div>
        <div>Provider: {data.llm_provider}</div>
        <div>Model: {data.llm_model || '-'}</div>
        <div>LLM key: <span className="pill">{data.llm_key_configured ? '✓' : '✗'}</span></div>
        <div>Max iterasyon: {data.run_max_iterations}</div>
      </div>)}
      <p className="warn">Secret değerleri asla gösterilmez.</p>
    </div>
  )
}

// ---------- Audit ----------
export function AuditPage() {
  return <div><h1>📜 Audit</h1><p className="muted">/api/v1/audit endpoint üzerinden append-only görünüm (backlog).</p></div>
}
import { useEffect, useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import { api, errMsg, setToken } from './api'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Activity,
  CheckCircle2,
  Clock,
  Layers,
  TrendingUp,
  Zap,
  AlertCircle,
  RefreshCw,
  Search,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'

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

function statusVariant(s: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  const v = s.toUpperCase()
  if (['COMPLETED','ACTIVE','APPROVED','AUTO_APPROVED'].includes(v)) return 'default'
  if (['FAILED','REJECTED','EXPIRED','CANCELLED'].includes(v)) return 'destructive'
  if (['QUEUED','EXECUTING','CONTEXT_BUILDING','PLANNING','POLICY_CHECK','VERIFYING','PERSISTING','PENDING','PAUSED','WAITING_APPROVAL'].includes(v)) return 'secondary'
  return 'outline'
}
function runStatusVariant(s: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  const u = s.toUpperCase()
  if (u === 'COMPLETED') return 'default'
  if (u === 'FAILED' || u === 'CANCELLED') return 'destructive'
  if (u === 'EXECUTING' || u === 'QUEUED') return 'secondary'
  return 'outline'
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={'animate-pulse rounded-md bg-muted ' + className} />
}
function Loading(){
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[0,1,2,3].map(i=> <Skeleton key={i} className="h-[96px] w-full" />)}
      </div>
      <Skeleton className="h-6 w-40" />
      <div className="space-y-2">
        {[0,1,2].map(i=> <Skeleton key={i} className="h-12 w-full" />)}
      </div>
    </div>
  )
}
function TableSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      <Skeleton className="h-10 w-full" />
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
    </div>
  )
}
function Err({msg, onRetry}:{msg:string, onRetry?:()=>void}){
  return (
    <Card className="border-destructive/40 bg-destructive/5">
      <CardContent className="flex items-center justify-between gap-3 p-4">
        <span className="flex items-center gap-2 text-sm text-destructive"><AlertCircle className="h-4 w-4" /> {msg}</span>
        {onRetry && <Button variant="outline" size="sm" onClick={onRetry}><RefreshCw className="h-3.5 w-3.5" /> Yeniden dene</Button>}
      </CardContent>
    </Card>
  )
}
function Empty({msg}:{msg:string}){ return <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">{msg}</div> }

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
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Giriş</h2>
        <p className="text-sm text-muted-foreground">Yerel kimlik doğrulama — oturum aç.</p>
      </div>
      <div className="flex flex-col gap-3">
        <Input placeholder="email" value={email} onChange={e=>setEmail(e.target.value)} autoComplete="username" />
        <Input placeholder="parola" type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" onKeyDown={e=> e.key==='Enter' && submit()} />
        <Button onClick={submit} disabled={busy || !email.trim() || !password} className="w-full">{busy ? 'giriş…' : 'Giriş'}</Button>
      </div>
      {err && <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"><AlertCircle className="h-4 w-4" /> {err}</div>}
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
    <div className={compact ? '' : ''}>
      <div className="mb-3 flex items-center gap-2">
        <h3 className="text-sm font-semibold tracking-tight">{compact ? '⚡ Komut' : '🎛️ Command Center'}</h3>
        {!compact && <Badge variant="secondary" className="text-[10px]">SSE canlı</Badge>}
      </div>
      {!compact && <p className="mb-3 text-sm text-muted-foreground">Prompt gir, run oluştur. SSE ile canlı takip.</p>}
      <div className="flex flex-wrap gap-2">
        <Input placeholder="başlık (opsiyonel)" value={title} onChange={e=>setTitle(e.target.value)} className="flex-none sm:w-[220px]" />
        <Input placeholder="prompt — ne yapsın?" value={prompt} onChange={e=>setPrompt(e.target.value)} className="min-w-[220px] flex-1" onKeyDown={e=> e.key==='Enter' && submit()} />
        <Button onClick={submit} disabled={busy || !prompt.trim()}>{busy?'gönderiliyor…':'▶️ Çalıştır'}</Button>
      </div>
      {err && <div className="mt-2 text-sm text-destructive">⚠ {err}</div>}
      {ok && <div className="mt-2 text-sm text-emerald-600 dark:text-emerald-400">✓ {ok}</div>}
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
  const total = runs?.length ?? 0
  const completed = runs?.filter(r=> r.status==='COMPLETED').length ?? 0
  const successPct = total ? ((completed/total)*100).toFixed(1) : '—'
  const avgTokens = (() => {
    if (!runs?.length) return '—'
    const withTok = runs.filter(r=> typeof r.token_used === 'number' && r.token_used>0)
    if (!withTok.length) return '—'
    const sum = withTok.reduce((a,b)=> a + (b.token_used||0), 0)
    return Math.round(sum/withTok.length).toString()
  })()
  // KPI card pulse for SSE
  const sseColor = sseState==='open' ? 'bg-emerald-500' : sseState==='connecting' ? 'bg-amber-500' : sseState==='error' ? 'bg-red-500' : 'bg-zinc-400'

  if (l1 || l2) {
    // skeleton while loading essential
    if (!runs && !approvals) return <Loading/>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-tight">📊 Dashboard</h1>
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            {sseState==='open' && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />}
            <span className={'relative inline-flex h-2.5 w-2.5 rounded-full ' + sseColor + (sseState==='open' ? ' shadow-[0_0_8px_theme(colors.emerald.500)]' : '')} />
          </span>
          <Badge variant={sseState==='open' ? 'default' : sseState==='error' ? 'destructive' : 'secondary'} className="capitalize">{sseState}</Badge>
          <span className="hidden text-xs text-muted-foreground sm:inline">#{lastId?.slice(0,8) || '—'}</span>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5"><Layers className="h-3.5 w-3.5" /> Toplam Run</CardDescription>
            <CardTitle className="text-2xl">{l1 ? <Skeleton className="h-7 w-12" /> : total}</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-xs text-muted-foreground">{running} aktif · {completed} tamamlandı</p>
            <Button variant="ghost" size="sm" className="mt-2 h-7 px-2 text-xs" onClick={()=>onOpen('runs')}>Run&apos;ları gör →</Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5"><TrendingUp className="h-3.5 w-3.5" /> Başarı %</CardDescription>
            <CardTitle className="text-2xl">{l1 ? <Skeleton className="h-7 w-16" /> : `${successPct}%`}</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-xs text-muted-foreground">{completed}/{total} tamamlandı</p>
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <motion.div initial={{ width: 0 }} animate={{ width: total ? `${(completed/total)*100}%` : '0%' }} transition={{ duration: 0.6 }} className="h-full bg-emerald-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5"><Activity className="h-3.5 w-3.5" /> Kuyruk derinliği</CardDescription>
            <CardTitle className="text-2xl">{l1 ? <Skeleton className="h-7 w-10" /> : running}</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-xs text-muted-foreground">QUEUED + EXECUTING</p>
            <Badge variant="outline" className="mt-2 text-[11px]">{running ? 'aktif iş var' : 'boşta'}</Badge>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5"><Zap className="h-3.5 w-3.5" /> Ort. Token</CardDescription>
            <CardTitle className="text-2xl">{l1 ? <Skeleton className="h-7 w-14" /> : avgTokens}</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-xs text-muted-foreground">run başına ortalama</p>
            <span className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground"><Clock className="h-3 w-3" /> {health?.status ? `sağlık: ${health.status}` : 'sağlık kontrol…'}</span>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">Son Run&apos;lar — timeline</CardTitle>
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={()=>onOpen('runs')}>Tümü</Button>
            </div>
            <CardDescription>En son 5 run · SSE canlı akış ile senkron</CardDescription>
          </CardHeader>
          <CardContent>
            {(e1||e2) && <div className="mb-3"><Err msg={(e1||e2) as string} onRetry={()=>{r1();r2()}} /></div>}
            {l1 ? <TableSkeleton rows={5} /> : !runs?.length ? <Empty msg="henüz run yok — Command Center'dan oluştur."/> : (
              <div className="relative">
                <div className="absolute bottom-0 left-[11px] top-2 w-px bg-border" />
                <div className="space-y-3">
                  {runs!.slice(0,5).map(r=> (
                    <div key={r.id} onClick={()=>onOpenRun?.(r.id)} className="relative flex cursor-pointer items-center gap-3 rounded-lg border bg-card p-3 pl-7 transition-colors hover:bg-accent/50">
                      <span className="absolute left-0 top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-background bg-primary shadow" style={{ left: '5px' }} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate font-mono text-xs">{r.id.slice(0,8)}</span>
                          <Badge variant={runStatusVariant(r.status)} className="text-[10px]">{r.status}</Badge>
                          <span className="text-xs text-muted-foreground">iter {r.iteration}</span>
                        </div>
                        <div className="text-xs text-muted-foreground">{r.created_at?.slice(0,19)} {r.error && <span className="text-destructive">· {r.error.slice(0,60)}</span>}</div>
                      </div>
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </div>
                  ))}
                </div>
              </div>
            )}
            {/* SSE live pulse detail */}
            <div className="mt-4 flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-xs">
              <motion.span animate={sseState==='open' ? { scale:[1,1.2,1]} : {}} transition={{ repeat: Infinity, duration: 1.2 }} className={'h-2 w-2 rounded-full ' + sseColor} />
              <span className="text-muted-foreground">SSE</span>
              <Badge variant="outline" className="h-5 text-[10px]">{sseState}</Badge>
              <span className="truncate text-muted-foreground">{live ? `son event: ${String((live as any).event_type || (live as any).seq || JSON.stringify(live).slice(0,60))}` : 'bekleniyor'}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm"><CheckCircle2 className="h-4 w-4" /> Onaylar</CardTitle>
            <CardDescription>{pending} bekleyen · hızlı bakış</CardDescription>
          </CardHeader>
          <CardContent>
            {l2 ? <div className="space-y-2"><Skeleton className="h-12 w-full"/><Skeleton className="h-12 w-full"/></div> : !approvals?.length ? <Empty msg="onay yok" /> : (
              <div className="space-y-2">
                {approvals!.slice(0,4).map(a=> (
                  <div key={a.id} className="rounded-lg border p-3">
                    <div className="flex items-center gap-2">
                      <Badge variant={statusVariant(a.status)} className="text-[10px]">{a.status}</Badge>
                      <span className="truncate text-sm font-medium">{a.action_class}</span>
                    </div>
                    <div className="truncate text-xs text-muted-foreground">{a.target.slice(0,80)}</div>
                  </div>
                ))}
                <Button variant="outline" size="sm" className="w-full" onClick={()=>onOpen('approvals')}>Onaylara git {pending>0 && <Badge variant="destructive" className="ml-2 h-5 text-[10px]">{pending}</Badge>}</Button>
              </div>
            )}
            <div className="mt-4 rounded-md border bg-card p-3">
              <div className="text-xs font-medium">Sağlık</div>
              <div className="text-sm">{health ? `✓ ${health.status}` : '...'}</div>
              <div className="text-xs text-muted-foreground">{health?.time?.slice(0,19) || ''}</div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ---------- Runs ----------
export function RunsPage({ onOpenDetail }: { onOpenDetail?:(id:string)=>void }) {
  const [limit, setLimit] = useState(20)
  const [offset, setOffset] = useState(0)
  const [statusFilter, setStatusFilter] = useState('ALL')
  const { data, err, loading, reload } = useFetch<Run[]>(`/v1/runs?limit=${limit}&offset=${offset}`, [limit, offset])
  const [q, setQ] = useState('')
  const filtered = (() => {
    let out = data || []
    if (q) out = out.filter(r=> r.id.includes(q) || r.status.toLowerCase().includes(q.toLowerCase()))
    if (statusFilter!=='ALL') out = out.filter(r=> r.status.toUpperCase()===statusFilter)
    return out
  })()
  const hasNext = (data?.length ?? 0) >= limit
  const hasPrev = offset > 0
  function goNext(){ if(hasNext) setOffset(o=>o+limit) }
  function goPrev(){ setOffset(o=>Math.max(0, o-limit)) }
  function onLimitChange(v:number){ setLimit(v); setOffset(0) }

  const statuses = ['ALL','QUEUED','EXECUTING','COMPLETED','FAILED','CANCELLED','PAUSED']

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold tracking-tight">▶️ Runs</h1>
        <Badge variant="outline" className="text-xs">offset {offset} · limit {limit}{data ? ` · ${data.length} kayıt` : ''}</Badge>
      </div>

      <Card>
        <CardContent className="p-3 sm:p-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[180px]">
              <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="filtre (id/durum)" value={q} onChange={e=>setQ(e.target.value)} className="pl-8" />
            </div>
            <select value={statusFilter} onChange={e=>setStatusFilter(e.target.value)} className="h-9 rounded-md border border-input bg-background px-3 text-sm">
              {statuses.map(s=> <option key={s} value={s}>{s==='ALL' ? 'Tüm durumlar' : s}</option>)}
            </select>
            <Button variant="outline" size="sm" onClick={()=>reload()}><RefreshCw className="h-4 w-4" /> Yenile</Button>
            <select value={String(limit)} onChange={e=>onLimitChange(parseInt(e.target.value))} className="h-9 rounded-md border border-input bg-background px-2 text-sm">
              <option value="10">10</option><option value="20">20</option><option value="50">50</option>
            </select>
          </div>
        </CardContent>
      </Card>

      {loading ? <TableSkeleton rows={5} /> : err ? <Err msg={err} onRetry={reload}/> : !filtered?.length ? <Empty msg={data?.length? 'filtreye uygun run yok':'run yok — Command Center ile oluştur.'}/> : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
                  <tr><th className="px-3 py-2 text-left">ID</th><th className="px-3 py-2 text-left">Durum</th><th className="px-3 py-2 text-left">Iter</th><th className="px-3 py-2 text-left">Hata</th><th className="px-3 py-2 text-right"></th></tr>
                </thead>
                <tbody>
                  {filtered!.map(r => (
                    <tr key={r.id} className="border-b last:border-0 hover:bg-muted/40">
                      <td className="px-3 py-2 font-mono text-xs" title={r.id}>{r.id.slice(0,8)}</td>
                      <td className="px-3 py-2"><Badge variant={runStatusVariant(r.status)} className="text-[10px]">{r.status}</Badge></td>
                      <td className="px-3 py-2 text-muted-foreground">{r.iteration}</td>
                      <td className="max-w-[260px] truncate px-3 py-2 text-xs text-destructive">{r.error||''}</td>
                      <td className="px-3 py-2 text-right"><Button size="sm" variant="outline" className="h-7 text-xs" onClick={()=>onOpenDetail?.(r.id)}>Detay</Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between border-t p-3">
              <span className="text-xs text-muted-foreground">{filtered.length} gösteriliyor{data && statusFilter!=='ALL' ? ` (filtreli)`:''}</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={!hasPrev} onClick={goPrev}><ChevronLeft className="h-4 w-4" /> Geri</Button>
                <Button variant="outline" size="sm" disabled={!hasNext} onClick={goNext}>İleri <ChevronRight className="h-4 w-4" /></Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

const RUN_STEPS = ['QUEUED','EXECUTING','VERIFYING','COMPLETED'] as const
function Stepper({ status }: { status: string }) {
  const upper = status.toUpperCase()
  const idx = RUN_STEPS.indexOf(upper as any)
  const isTerminalFail = ['FAILED','CANCELLED'].includes(upper)
  const activeIdx = idx >=0 ? idx : (upper==='FAILED' || upper==='CANCELLED' ? 1 : 0)
  return (
    <div className="flex items-center gap-1 sm:gap-2">
      {RUN_STEPS.map((s,i)=> {
        const done = i < activeIdx
        const active = i===activeIdx && !isTerminalFail
        const fail = isTerminalFail && i===activeIdx
        return (
          <div key={s} className="flex items-center gap-1 sm:gap-2">
            <div className={'flex h-7 w-7 items-center justify-center rounded-full text-[10px] font-bold ' + (done ? 'bg-emerald-500 text-white' : active ? 'bg-primary text-primary-foreground shadow' : fail ? 'bg-destructive text-destructive-foreground' : 'bg-muted text-muted-foreground')}>
              {done ? '✓' : i+1}
            </div>
            <span className={'hidden text-xs font-medium sm:inline ' + (active ? 'text-foreground' : 'text-muted-foreground')}>{s}</span>
            {i < RUN_STEPS.length-1 && <div className={'h-0.5 w-6 sm:w-10 ' + (done ? 'bg-emerald-500' : 'bg-border')} />}
          </div>
        )
      })}
      {isTerminalFail && <Badge variant="destructive" className="ml-2 text-[10px]">{upper}</Badge>}
    </div>
  )
}

export function RunDetailPage({ runId, onBack }: { runId:string, onBack:()=>void }) {
  const { data: run, reload: reloadRun } = useFetch<Run>(`/v1/runs/${runId}`, [runId])
  const { data, err, loading, reload } = useFetch<RunEvent[]>(`/v1/runs/${runId}/events`, [runId])
  const [filter, setFilter] = useState('')
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [tab, setTab] = useState<'overview'|'events'|'timeline'>('overview')
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
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onBack}><ChevronLeft className="h-4 w-4" /> Geri</Button>
        <h2 className="truncate text-lg font-semibold tracking-tight">Run: {runId.slice(0,8)} <span className="hidden font-mono text-xs font-normal text-muted-foreground sm:inline">{runId}</span></h2>
        {run && <Badge variant={runStatusVariant(run.status)}>{run.status}</Badge>}
      </div>

      {run && (
        <Card>
          <CardContent className="space-y-3 p-4">
            <Stepper status={run.status} />
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="outline" className="font-mono">{run.id.slice(0,8)}</Badge>
              <span className="text-muted-foreground">iter {run.iteration}</span>
              <span className="text-muted-foreground">token {run.token_used ?? 0}</span>
              <span className="text-muted-foreground">cost ${run.cost_used ?? 0}</span>
              <span className="text-muted-foreground">worker {run.worker_id?.slice(0,8) || '—'}</span>
              {run.control_request && <Badge variant="secondary">kontrol: {run.control_request}</Badge>}
            </div>
            {run.error && <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">⚠ {run.error}</div>}
            <div className="flex flex-wrap gap-2">
              {active && <>
                <Button size="sm" variant="outline" disabled={!!busy} onClick={()=>control('pause')}>{busy==='pause'?'...':'⏸ Durdur'}</Button>
                <Button size="sm" variant="outline" disabled={!!busy} onClick={()=>control('resume')}>{busy==='resume'?'...':'▶️ Sürdür'}</Button>
                <Button size="sm" variant="destructive" disabled={!!busy} onClick={()=>control('stop')}>{busy==='stop'?'...':'⏹ Sonlandır'}</Button>
              </>}
              {terminal && <Button size="sm" disabled={!!busy} onClick={retry}>{busy==='retry'?'...':'🔄 Tekrar çalıştır'}</Button>}
            </div>
          </CardContent>
        </Card>
      )}
      {msg && <div className={'rounded-md border px-3 py-2 text-sm ' + (msg.startsWith('⚠') ? 'border-destructive/30 bg-destructive/10 text-destructive' : 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200')}>{msg}</div>}

      {/* tabs */}
      <div className="flex gap-1 rounded-lg border bg-muted p-1 text-sm">
        {(['overview','events','timeline'] as const).map(t=> (
          <button key={t} onClick={()=>setTab(t)} className={'flex-1 rounded-md px-3 py-1.5 text-sm font-medium capitalize transition-colors ' + (tab===t ? 'bg-background shadow-sm' : 'text-muted-foreground hover:text-foreground')}>
            {t==='overview' ? 'Genel' : t==='events' ? `Eventler (${evs?.length ?? 0})` : 'Timeline'}
          </button>
        ))}
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="mb-3 flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="event tipi filtre" value={filter} onChange={e=>setFilter(e.target.value)} className="pl-8" />
            </div>
            <Button variant="outline" size="sm" onClick={reload}><RefreshCw className="h-4 w-4" /> Yenile</Button>
          </div>

          {tab==='overview' && (
            <div className="space-y-3">
              {loading ? <TableSkeleton/> : err ? <Err msg={err} onRetry={reload}/> : !evs?.length ? <Empty msg="event yok"/> : (
                <div className="space-y-2">
                  <div className="text-xs text-muted-foreground">{evs.length} event</div>
                  {evs.slice(0,5).map((e,i)=> (
                    <div className="rounded-lg border p-3" key={i}>
                      <div className="flex items-center gap-2"><Badge variant="secondary" className="text-[10px]">{e.event_type}</Badge> <span className="text-xs text-muted-foreground">seq {e.seq}</span> <span className="text-xs text-muted-foreground">{e.ts?.slice(0,19)}</span></div>
                      {e.payload && <pre className="mt-2 max-h-40 overflow-auto rounded bg-muted p-2 text-xs">{JSON.stringify(e.payload, null, 2).slice(0,1200)}</pre>}
                    </div>
                  ))}
                  {evs.length>5 && <p className="text-center text-xs text-muted-foreground">… ve {evs.length-5} daha — Eventler sekmesine geç</p>}
                </div>
              )}
            </div>
          )}

          {tab==='events' && (
            loading ? <TableSkeleton/> : err ? <Err msg={err} onRetry={reload}/> : !evs?.length ? <Empty msg="event yok"/> : (
              <div className="space-y-2">
                <div className="text-xs text-muted-foreground">{evs.length} event</div>
                {evs.map((e,i)=> (
                  <div className="rounded-lg border p-3" key={i}>
                    <div className="flex items-center gap-2"><Badge variant="outline" className="text-[10px]">{e.event_type}</Badge> <Badge variant="secondary" className="text-[10px]">seq {e.seq}</Badge> <span className="text-xs text-muted-foreground">{e.ts?.slice(0,19)}</span></div>
                    {e.payload && <pre className="mt-2 max-h-48 overflow-auto rounded bg-muted p-2 text-xs">{JSON.stringify(e.payload, null, 2).slice(0,2000)}</pre>}
                  </div>
                ))}
              </div>
            )
          )}

          {tab==='timeline' && (
            loading ? <TableSkeleton/> : !evs?.length ? <Empty msg="event yok"/> : (
              <div className="relative pl-6">
                <div className="absolute bottom-0 left-[9px] top-2 w-px bg-border" />
                <div className="space-y-4">
                  {evs.map((e,i)=> (
                    <div key={i} className="relative">
                      <span className="absolute -left-6 top-1 h-3 w-3 rounded-full border-2 border-background bg-primary shadow" />
                      <div className="rounded-lg border bg-card p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold">{e.event_type}</span>
                          <Badge variant="outline" className="text-[10px]">#{e.seq}</Badge>
                          <span className="text-xs text-muted-foreground">{e.ts?.slice(0,19)}</span>
                        </div>
                        {e.payload && Object.keys(e.payload).length>0 && (
                          <details className="mt-2"><summary className="cursor-pointer text-xs text-muted-foreground">payload</summary><pre className="mt-1 max-h-40 overflow-auto rounded bg-muted p-2 text-xs">{JSON.stringify(e.payload, null, 2).slice(0,1500)}</pre></details>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          )}
        </CardContent>
      </Card>
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
    <div className="space-y-4">
      <div className="flex items-center justify-between"><h1 className="text-xl font-bold tracking-tight">🕐 Approvals</h1><Button variant="outline" size="sm" onClick={reload}><RefreshCw className="h-4 w-4" /> Yenile</Button></div>
      {loading ? <TableSkeleton/> : err ? <Err msg={err} onRetry={reload}/> : !data?.length ? <Empty msg="onay yok"/> : data.map(a => (
        <Card key={a.id}>
          <CardContent className="p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2"><Badge variant={statusVariant(a.status)}>{a.status}</Badge><span className="font-medium">{a.action_class}</span><span className="text-muted-foreground">— {a.target.slice(0,80)}</span></div>
                <div className="mt-1 text-sm text-muted-foreground">etki: {a.impact_summary}</div>
                <div className="text-xs text-muted-foreground">expires: {a.expires_at?.slice(0,19) || '—'}</div>
              </div>
              {a.status === 'PENDING' && (
                <div className="flex gap-2">
                  <Button size="sm" disabled={!!busy} onClick={() => decide(a.id, 'approve')}>{busy===a.id+'approve'?'...':'✅ Onayla'}</Button>
                  <Button size="sm" variant="destructive" disabled={!!busy} onClick={() => decide(a.id, 'reject')}>{busy===a.id+'reject'?'...':'❌ Reddet'}</Button>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      ))}
      {msg && <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">{msg}</div>}
      {err2 && <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">⚠ {err2}</div>}
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
  const segments: Segment[] = (data||[]).flatMap((e)=> (e.payload?.segments as Segment[] | undefined ||[]).map((s)=> ({...s, _event:e.event_type, _seq:e.seq})))
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold tracking-tight">🧩 Context Inspector</h1>
      <Card>
        <CardContent className="flex flex-wrap gap-2 p-3">
          {runs && <select value={runId} onChange={e=>setRunId(e.target.value)} className="h-9 rounded-md border border-input bg-background px-3 text-sm"><option value="">run seç…</option>{runs.map((r)=> <option key={r.id} value={r.id}>{r.id.slice(0,8)} · {r.status}</option>)}</select>}
          <Input placeholder="run_id" value={runId} onChange={e => setRunId(e.target.value)} className="min-w-[260px] flex-1" />
          <Button variant="outline" size="sm" onClick={reload} disabled={!runId}><RefreshCw className="h-4 w-4" /> Yükle</Button>
        </CardContent>
      </Card>
      {!runId ? <Empty msg="run seçerek context segment metadata'sını gör."/> : loading ? <TableSkeleton/> : err ? <Err msg={err} onRetry={reload}/> : !segments.length ? <Empty msg="bu run için segment yok (event payload'ında segments beklenir)."/> : (
        <div className="space-y-3">
          <div className="text-xs text-muted-foreground">{segments.length} segment · {data?.length} event</div>
          {segments.map((s, j) => (
            <Card key={j} className="border-l-2 border-l-primary">
              <CardContent className="p-3">
                <div className="flex flex-wrap items-center gap-2"><Badge>{s.segment_type}</Badge><span className="text-xs text-muted-foreground">{s.token_count} tok · güv {s.confidence}</span><Badge variant="outline" className="text-[10px]">{s._event} #{s._seq}</Badge> {s.contains_untrusted_input && <Badge variant="destructive" className="text-[10px]">UNTRUSTED</Badge>}</div>
                <div className="mt-1 text-xs text-muted-foreground">neden: {s.included_reason}</div>
                {s.preview && <pre className="mt-2 max-h-32 overflow-auto rounded bg-muted p-2 text-xs">{String(s.preview).slice(0,800)}</pre>}
                {s.content_preview && <pre className="mt-2 max-h-32 overflow-auto rounded bg-muted p-2 text-xs">{String(s.content_preview).slice(0,800)}</pre>}
              </CardContent>
            </Card>
          ))}
          <details className="rounded-lg border p-3"><summary className="cursor-pointer text-sm text-muted-foreground">Ham event&apos;ler ({data?.length})</summary>
            <div className="mt-3 space-y-2">{data!.map((e,i)=>(<Card key={i}><CardContent className="p-3"><Badge variant="outline" className="text-[10px]">{e.event_type}</Badge><pre className="mt-2 max-h-40 overflow-auto rounded bg-muted p-2 text-xs">{JSON.stringify(e.payload||{}, null,2).slice(0,1500)}</pre></CardContent></Card>))}</div>
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
    <div className="space-y-4">
      <h1 className="text-xl font-bold tracking-tight">🧠 Memory</h1>
      <Card className="border-primary/30">
        <CardHeader className="pb-3"><CardTitle className="text-sm">Yeni candidate oluştur</CardTitle><CardDescription>POST /v1/memory — yüksek güvenli (&gt;0.85) kayıtlar 2+ başarılı run sonrası otomatik onaylanır</CardDescription></CardHeader>
        <CardContent>
          <form onSubmit={createCandidate} className="flex flex-col gap-3">
            <textarea placeholder="content (gerekli)" value={content} onChange={e=>setContent(e.target.value)} rows={3} className="min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" />
            <div className="flex flex-wrap gap-2">
              <Input placeholder="source (opsiyonel)" value={source} onChange={e=>setSource(e.target.value)} className="min-w-[160px] flex-1" />
              <Input placeholder="category (opsiyonel)" value={category} onChange={e=>setCategory(e.target.value)} className="min-w-[160px] flex-1" />
              <Input type="number" min={0} max={1} step={0.1} value={confidence} onChange={e=>setConfidence(e.target.value)} className="w-[120px]" />
              <Button type="submit" disabled={creating || !content.trim()}>{creating?'oluşturuluyor…':'＋ Oluştur'}</Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-wrap gap-2 p-3">
          <select value={status} onChange={e=>setStatus(e.target.value)} className="h-9 rounded-md border border-input bg-background px-3 text-sm">
            <option value="candidate">candidate</option><option value="active">active</option><option value="rejected">rejected</option>
          </select>
          <div className="relative flex-1 min-w-[160px]">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input placeholder="ara..." value={q} onChange={e=>setQ(e.target.value)} className="pl-8" />
          </div>
          <Button variant="outline" size="sm" onClick={reload}><RefreshCw className="h-4 w-4" /> Yenile</Button>
        </CardContent>
      </Card>

      {loading ? <TableSkeleton/> : err ? <Err msg={err} onRetry={reload}/> : !data?.length ? <Empty msg={`"${status}" için kayıt yok`}/> : data.map(m => (
        <Card key={m.id}>
          <CardContent className="space-y-2 p-4">
            <p className="text-sm">{m.content}</p>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant={statusVariant(m.status)} className="text-[10px]">{m.status}</Badge>
              <span>güv {m.confidence}</span><span>· {m.source} {m.category?`· ${m.category}`:''}</span>
              {m.confidence>0.85 && <Badge variant="outline" className="border-emerald-300 text-emerald-700 dark:border-emerald-800 dark:text-emerald-300 text-[10px]">auto-promote aday</Badge>}
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={!!busy} onClick={() => decide(m.id, 'approve')}>✅ Onayla</Button>
              <Button size="sm" variant="destructive" disabled={!!busy} onClick={() => decide(m.id, 'reject')}>❌ Reddet</Button>
            </div>
          </CardContent>
        </Card>
      ))}
      {msg && <div className={'rounded-md border px-3 py-2 text-sm ' + (msg.startsWith('⚠') ? 'border-destructive/30 bg-destructive/10 text-destructive' : 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200')}>{msg}</div>}
    </div>
  )
}

// ---------- Sources ----------
export function SourcesPage() {
  const { data, err, loading, reload } = useFetch<SourceItem[]>('/v1/sources')
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between"><h1 className="text-xl font-bold tracking-tight">📡 Sources</h1><Button variant="outline" size="sm" onClick={reload}><RefreshCw className="h-4 w-4" /> Yenile</Button></div>
      {loading ? <TableSkeleton/> : err ? <Err msg={err} onRetry={reload}/> : !data?.length ? <Empty msg="kaynak yok. Teknolojik İlk Önce connector ile eklenir."/> : data.map(s => (
        <Card key={s.id}>
          <CardContent className="p-4">
            <div className="flex items-center gap-2"><span className="font-medium">{s.name}</span><Badge variant="outline" className="text-[10px]">{s.source_type}</Badge>{s.is_enabled ? <Badge className="bg-emerald-600 text-[10px]">aktif</Badge> : <Badge variant="secondary" className="text-[10px]">pasif</Badge>}</div>
            <div className="text-xs text-muted-foreground">hata serisi: {s.error_series_len} {s.last_accessed_at?`· son: ${s.last_accessed_at.slice(0,19)}`:''}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// ---------- Technocore ----------
export function TechnocorePage() {
  const { data, err, loading, reload } = useFetch<{base_url:string, room_claim:string, registered:boolean}>('/v1/technocore')
  if (loading) return <div className="space-y-4"><h1 className="text-xl font-bold tracking-tight">🛰️ Technocore</h1><TableSkeleton rows={2}/></div>
  if (err) return <div className="space-y-4"><h1 className="text-xl font-bold tracking-tight">🛰️ Technocore</h1><Err msg={err} onRetry={reload}/></div>
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold tracking-tight">🛰️ Technocore</h1>
      {data && <Card><CardContent className="space-y-2 p-4"><div className="font-medium">{data.base_url || '—'}</div><div className="text-sm text-muted-foreground">Oda: {data.room_claim || '—'}</div><div className="flex items-center gap-2 text-sm">Kayıt: {data.registered ? <Badge className="bg-emerald-600">✓</Badge> : <Badge variant="secondary">henüz değil (Faz 7)</Badge>}</div></CardContent></Card>}
      <Button variant="outline" size="sm" onClick={reload}><RefreshCw className="h-4 w-4" /> Yenile</Button>
    </div>
  )
}

// ---------- Telegram ----------
export function TelegramPage() {
  const { data, err, loading, reload } = useFetch<{telegram_token_configured:boolean, telegram_allowed_user_ids_count:number, telegram_group_enabled:boolean}>('/v1/settings/non-secret')
  if (loading) return <div className="space-y-4"><h1 className="text-xl font-bold tracking-tight">✈️ Telegram</h1><TableSkeleton rows={2}/></div>
  if (err) return <div className="space-y-4"><h1 className="text-xl font-bold tracking-tight">✈️ Telegram</h1><Err msg={err} onRetry={reload}/></div>
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold tracking-tight">✈️ Telegram</h1>
      {data && (<Card><CardContent className="space-y-2 p-4">
        <div><Badge variant={data.telegram_token_configured ? 'default' : 'destructive'} className={data.telegram_token_configured ? 'bg-emerald-600' : ''}>{data.telegram_token_configured ? 'bot token ✓' : '⚠️ token yok'}</Badge></div>
        <div className="text-sm">Allowlist kullanıcı: {data.telegram_allowed_user_ids_count}</div>
        <div className="text-sm">Grup: {data.telegram_group_enabled ? 'açık' : 'kapalı'}</div>
      </CardContent></Card>)}
      <Button variant="outline" size="sm" onClick={reload}><RefreshCw className="h-4 w-4" /> Yenile</Button>
    </div>
  )
}

// ---------- Settings ----------
export function SettingsPage() {
  const { data, err, loading, reload } = useFetch<{app_env:string, llm_provider:string, llm_model:string, llm_base_url:string, llm_key_configured:boolean, run_max_iterations:number, run_max_wall_seconds:number}>('/v1/settings/non-secret')
  if (loading) return <div className="space-y-4"><h1 className="text-xl font-bold tracking-tight">⚙️ Settings</h1><TableSkeleton rows={3}/></div>
  if (err) return <div className="space-y-4"><h1 className="text-xl font-bold tracking-tight">⚙️ Settings</h1><Err msg={err} onRetry={reload}/></div>
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold tracking-tight">⚙️ Settings</h1>
      {data && (<Card><CardContent className="space-y-1.5 p-4 text-sm">
        <div>Ortam: <Badge variant="outline">{data.app_env}</Badge></div>
        <div>Provider: <Badge variant="secondary">{data.llm_provider}</Badge></div>
        <div>Model: {data.llm_model || '-'}</div>
        <div>Base URL: {data.llm_base_url || '-'}</div>
        <div>LLM key: <Badge variant={data.llm_key_configured ? 'default' : 'outline'} className={data.llm_key_configured ? 'bg-emerald-600' : ''}>{data.llm_key_configured ? '✓' : '✗'}</Badge></div>
        <div>Max iterasyon: {data.run_max_iterations}</div>
        <div>Max wall s: {data.run_max_wall_seconds}</div>
      </CardContent></Card>)}
      <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">Secret değerleri asla gösterilmez.</div>
      <Button variant="outline" size="sm" onClick={reload}><RefreshCw className="h-4 w-4" /> Yenile</Button>
    </div>
  )
}

// ---------- Reports ----------
export function ReportsPage() {
  const { data, err, loading, reload } = useFetch<Report[]>('/v1/reports?limit=50')
  const [selected, setSelected] = useState<Report | null>(null)
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between"><h1 className="text-xl font-bold tracking-tight">📄 Reports</h1><div className="flex gap-2"><Button variant="outline" size="sm" onClick={reload}><RefreshCw className="h-4 w-4" /> Yenile</Button>{selected && <Button variant="ghost" size="sm" onClick={()=>setSelected(null)}>← Listeye dön</Button>}<Badge variant="outline">{data ? `${data.length} rapor` : ''}</Badge></div></div>
      {selected ? (
        <Card className="border-primary/30">
          <CardHeader><CardTitle className="flex items-center gap-2 text-base">{selected.subject || '(konu yok)'} <Badge>{selected.report_type}</Badge></CardTitle><CardDescription>id {selected.id} · {selected.created_at?.slice(0,19)} · güven {selected.confidence}</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            <div><span className="text-sm font-semibold">Özet</span><p className="text-sm text-muted-foreground">{selected.summary || '—'}</p></div>
            <div><span className="text-sm font-semibold">Body</span><pre className="mt-1 max-h-64 overflow-auto rounded bg-muted p-3 text-xs">{selected.body ? JSON.stringify(selected.body, null, 2) : (selected.summary || '—')}</pre></div>
            <div className="text-xs text-muted-foreground">report_type: {selected.report_type} · subject: {selected.subject} · confidence: {selected.confidence}</div>
          </CardContent>
        </Card>
      ) : loading ? <TableSkeleton/> : err ? <Err msg={err} onRetry={reload}/> : !data?.length ? <Empty msg="rapor yok."/> : (
        <div className="space-y-2">
          {data.map(r=> (
            <Card key={r.id} className="cursor-pointer transition-colors hover:bg-accent/30" onClick={()=>setSelected(r)}>
              <CardContent className="p-4">
                <div className="flex items-center gap-2"><Badge variant="outline" className="text-[10px]">{r.report_type}</Badge><span className="font-medium">{r.subject || '(konu yok)'}</span><Badge variant="secondary" className="text-[10px]">güven {r.confidence}</Badge></div>
                <div className="text-xs text-muted-foreground">{r.id.slice(0,8)} · {r.created_at?.slice(0,19)}</div>
                <div className="mt-1 line-clamp-2 text-sm text-muted-foreground">{r.summary?.slice(0,200) || '—'}</div>
                <Button size="sm" variant="ghost" className="mt-2 h-7 text-xs" onClick={(e)=>{e.stopPropagation(); setSelected(r)}}>Detay</Button>
              </CardContent>
            </Card>
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
    <div className="space-y-4">
      <h1 className="text-xl font-bold tracking-tight">📜 Audit</h1>
      <p className="text-sm text-muted-foreground">GET /api/v1/reports — raporlar append-only listesi.</p>
      <div className="flex gap-2"><Button variant="outline" size="sm" onClick={reload}><RefreshCw className="h-4 w-4" /> Yenile</Button>{selected && <Button variant="ghost" size="sm" onClick={()=>setSelected(null)}>← Listeye dön</Button>}<Badge variant="outline">{data ? `${data.length} rapor` : ''}</Badge></div>
      {selected ? (
        <Card className="border-primary/30">
          <CardHeader><CardTitle className="flex items-center gap-2 text-base">{selected.subject || '(konu yok)'} <Badge>{selected.report_type}</Badge></CardTitle><CardDescription>id {selected.id} · {selected.created_at?.slice(0,19)} · güven {selected.confidence}</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            <div><span className="text-sm font-semibold">Özet</span><p className="text-sm text-muted-foreground">{selected.summary || '—'}</p></div>
            <div><span className="text-sm font-semibold">Body</span><pre className="mt-1 max-h-64 overflow-auto rounded bg-muted p-3 text-xs">{selected.body ? JSON.stringify(selected.body, null, 2) : (selected.summary || '—')}</pre></div>
            <div className="text-xs text-muted-foreground">report_type: {selected.report_type} · subject: {selected.subject} · confidence: {selected.confidence}</div>
          </CardContent>
        </Card>
      ) : loading ? <TableSkeleton/> : err ? <Err msg={err} onRetry={reload}/> : !data?.length ? <Empty msg="rapor yok."/> : (
        <div className="space-y-2">
          {data.map(r=> (
            <Card key={r.id} className="cursor-pointer transition-colors hover:bg-accent/30" onClick={()=>setSelected(r)}>
              <CardContent className="p-4">
                <div className="flex items-center gap-2"><Badge variant="outline" className="text-[10px]">{r.report_type}</Badge><span className="font-medium">{r.subject || '(konu yok)'}</span><Badge variant="secondary" className="text-[10px]">güven {r.confidence}</Badge></div>
                <div className="text-xs text-muted-foreground">{r.id.slice(0,8)} · {r.created_at?.slice(0,19)}</div>
                <div className="mt-1 text-sm text-muted-foreground">{r.summary?.slice(0,200) || '—'}</div>
                <Button size="sm" variant="ghost" className="mt-2 h-7 text-xs" onClick={(e)=>{e.stopPropagation(); setSelected(r)}}>Detay</Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

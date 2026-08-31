import { useEffect, useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard,
  Play,
  Clock3,
  Puzzle,
  Brain,
  Radio,
  Satellite,
  Send,
  Settings,
  FileText,
  ScrollText,
  Menu,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Bird,
  PanelLeft,
} from 'lucide-react'
import { api, openSSE, getToken, setToken, setOnUnauthorized } from './api'
import type { SSEState } from './api'
import {
  Dashboard,
  RunsPage,
  RunDetailPage,
  ApprovalsPage,
  ContextPage,
  MemoryPage,
  SourcesPage,
  TechnocorePage,
  TelegramPage,
  SettingsPage,
  AuditPage,
  ReportsPage,
  CommandCenter,
  LoginPage,
} from './pages'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'

type PageKey = 'dashboard' | 'runs' | 'run-detail' | 'approvals' | 'context' | 'memory' | 'sources' | 'technocore' | 'telegram' | 'settings' | 'audit' | 'reports'
type NavKey = Exclude<PageKey, 'run-detail'>

const NAV: [NavKey, string, React.ElementType][] = [
  ['dashboard', 'Dashboard', LayoutDashboard],
  ['runs', 'Runs', Play],
  ['approvals', 'Approvals', Clock3],
  ['context', 'Context', Puzzle],
  ['memory', 'Memory', Brain],
  ['sources', 'Sources', Radio],
  ['technocore', 'Technocore', Satellite],
  ['telegram', 'Telegram', Send],
  ['settings', 'Settings', Settings],
  ['reports', 'Reports', FileText],
  ['audit', 'Audit', ScrollText],
]

function SSEDot({ state }: { state: SSEState }) {
  const color =
    state === 'open' ? 'bg-emerald-500' : state === 'connecting' ? 'bg-amber-500' : state === 'error' ? 'bg-red-500' : 'bg-zinc-400'
  return (
    <span className="relative flex h-2.5 w-2.5 shrink-0">
      {state === 'open' && (
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
      )}
      <span className={cn('relative inline-flex h-2.5 w-2.5 rounded-full', color, state === 'open' && 'shadow-[0_0_8px_theme(colors.emerald.500)]')} />
    </span>
  )
}

function SSEBadge({ state, lastId }: { state: SSEState; lastId: string }) {
  const label = state === 'open' ? 'canlı' : state === 'connecting' ? 'bağlanıyor' : state === 'error' ? 'yeniden bağlanıyor' : 'kapalı'
  const variant: 'default' | 'secondary' | 'destructive' | 'outline' =
    state === 'open' ? 'default' : state === 'error' ? 'destructive' : 'secondary'
  return (
    <div
      className="inline-flex items-center gap-2 rounded-full border bg-card px-2.5 py-1 text-xs font-medium shadow-sm"
      title={lastId ? `Last-Event-ID: ${lastId}` : undefined}
    >
      <SSEDot state={state} />
      <span className="capitalize tracking-tight">{label}</span>
      {lastId && <span className="hidden text-[10px] text-muted-foreground sm:inline">#{lastId.slice(0, 8)}</span>}
      <Badge variant={variant} className="ml-1 hidden h-5 px-1.5 text-[10px] font-semibold uppercase tracking-wider sm:inline-flex">
        SSE
      </Badge>
    </div>
  )
}

function NavButton({
  active,
  collapsed,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean
  collapsed: boolean
  icon: React.ElementType
  label: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      title={collapsed ? label : undefined}
      className={cn(
        'flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-sm font-medium transition-colors duration-150',
        'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
        active
          ? 'bg-sidebar-accent text-sidebar-accent-foreground shadow-sm'
          : 'text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground',
        collapsed && 'justify-center px-2'
      )}
    >
      <Icon className={cn('h-4 w-4 shrink-0', active && 'text-sidebar-primary')} />
      {!collapsed && <span className="truncate tracking-tight">{label}</span>}
    </button>
  )
}

export default function App() {
  const [tab, setTab] = useState<NavKey>('dashboard')
  const [runId, setRunId] = useState<string>('')
  const [live, setLive] = useState<Record<string, unknown> | null>(null)
  const [sseState, setSseState] = useState<SSEState>('connecting')
  const [lastId, setLastId] = useState('')
  const [toast, setToast] = useState('')
  const [session, setSession] = useState<{ email: string; role: string } | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const liveRef = useRef(live)

  useEffect(() => {
    liveRef.current = live
  }, [live])

  useEffect(() => {
    setOnUnauthorized(() => {
      setToken('')
      setSession(null)
    })
    if (!getToken()) {
      setAuthLoading(false)
      return
    }
    api<{ username: string; role: string }>('/v1/auth/me')
      .then((u) => setSession({ email: u.username, role: u.role }))
      .catch(() => {
        setToken('')
        setSession(null)
      })
      .finally(() => setAuthLoading(false))
  }, [])

  useEffect(() => {
    if (!session) return
    const stop = openSSE(
      (e, id) => {
        setLive(e as Record<string, unknown>)
        if (id) setLastId(id)
      },
      (s) => setSseState(s)
    )
    return stop
  }, [session])

  function logout() {
    setToken('')
    setSession(null)
    setTab('dashboard')
  }

  // auto-dismiss toast
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(''), 3000)
    return () => clearTimeout(t)
  }, [toast])

  if (authLoading)
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="h-2 w-2 animate-pulse rounded-full bg-violet-500" />
          yükleniyor…
        </div>
      </div>
    )

  if (!session) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
        <div className="w-full max-w-[420px]">
          <div className="mb-6 flex flex-col items-center gap-2 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-600 text-white shadow">
              <Bird className="h-5 w-5" />
            </div>
            <div className="text-sm font-semibold tracking-tight">RAPTOR OBSERVATORY</div>
            <div className="text-xs text-muted-foreground">Gözlem ve orkestrasyon</div>
          </div>
          <Card className="shadow-lg">
            <CardContent className="pt-6">
              <LoginPage onLogin={(u) => setSession(u)} />
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background text-foreground antialiased">
      {/* Topbar */}
      <header className="sticky top-0 z-40 flex h-14 items-center gap-2 border-b bg-background/80 px-3 backdrop-blur supports-[backdrop-filter]:bg-background/60 lg:px-4">
        {/* mobile menu */}
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="shrink-0 md:hidden" aria-label="Menüyü aç">
              <Menu className="h-5 w-5" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-[300px] p-0">
            <div className="flex h-full flex-col">
              <div className="flex h-14 items-center gap-2 border-b px-4">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-600 text-white">
                  <Bird className="h-4 w-4" />
                </div>
                <div>
                  <div className="text-sm font-semibold leading-none tracking-tight">RAPTOR</div>
                  <div className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground">Observatory</div>
                </div>
              </div>
              <div className="p-3">
                <SSEBadge state={sseState} lastId={lastId} />
              </div>
              <nav className="flex-1 space-y-1 overflow-y-auto px-2 py-2">
                {NAV.map(([k, label, Icon]) => (
                  <NavButton
                    key={k}
                    active={tab === k}
                    collapsed={false}
                    icon={Icon}
                    label={label}
                    onClick={() => {
                      setTab(k)
                      setMobileOpen(false)
                    }}
                  />
                ))}
              </nav>
              <div className="border-t p-3">
                <div className="mb-2 truncate text-xs font-medium">{session.email}</div>
                <Badge variant="secondary" className="mb-3 text-[10px] uppercase tracking-wider">
                  {session.role}
                </Badge>
                <Button variant="outline" size="sm" className="w-full justify-start gap-2" onClick={logout}>
                  <LogOut className="h-4 w-4" /> Çıkış
                </Button>
              </div>
            </div>
          </SheetContent>
        </Sheet>

        {/* brand */}
        <div className="flex items-center gap-2.5">
          <div className="hidden h-8 w-8 items-center justify-center rounded-lg bg-violet-600 text-white shadow-sm md:flex">
            <Bird className="h-4 w-4" />
          </div>
          <div className="hidden md:block">
            <div className="text-sm font-semibold leading-none tracking-tight">RAPTOR</div>
            <div className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground">Observatory</div>
          </div>
          <div className="flex items-center gap-1 md:hidden">
            <Bird className="h-4 w-4 text-violet-600" />
            <span className="text-sm font-semibold tracking-tight">RAPTOR</span>
          </div>
        </div>

        <div className="hidden items-center gap-2 lg:flex">
          <span className="mx-2 h-4 w-px bg-border" />
          <SSEBadge state={sseState} lastId={lastId} />
        </div>

        <div className="flex flex-1 items-center justify-end gap-2">
          {/* desktop SSE compact */}
          <div className="hidden items-center gap-2 sm:flex lg:hidden">
            <SSEDot state={sseState} />
            <span className="text-xs font-medium capitalize text-muted-foreground">{sseState === 'open' ? 'canlı' : sseState}</span>
          </div>

          <div className="hidden items-center gap-2 sm:flex">
            <div className="hidden flex-col items-end leading-none md:flex">
              <span className="max-w-[160px] truncate text-xs font-medium">{session.email}</span>
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{session.role}</span>
            </div>
            <Badge variant="secondary" className="hidden text-[10px] uppercase tracking-wider md:inline-flex">
              {session.role}
            </Badge>
          </div>

          <Button variant="ghost" size="sm" className="hidden gap-1.5 md:inline-flex" onClick={logout}>
            <LogOut className="h-4 w-4" /> Çıkış
          </Button>
          <Button variant="ghost" size="icon" className="md:hidden" onClick={logout} aria-label="Çıkış">
            <LogOut className="h-4 w-4" />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            className="hidden h-8 w-8 md:inline-flex"
            onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? 'Kenar çubuğunu genişlet' : 'Kenar çubuğunu daralt'}
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </Button>
        </div>
      </header>

      <div className="flex">
        {/* Sidebar desktop */}
        <aside
          className={cn(
            'sticky top-14 hidden h-[calc(100vh-3.5rem)] shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground md:flex',
            'transition-all duration-150',
            collapsed ? 'w-[64px]' : 'w-[240px]'
          )}
        >
          <div className={cn('flex h-10 items-center border-b px-2', collapsed ? 'justify-center' : 'justify-between gap-2 px-3')}>
            {!collapsed && (
              <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
                <PanelLeft className="h-3.5 w-3.5" /> Menü
              </span>
            )}
            {!collapsed && (
              <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
                {NAV.length}
              </Badge>
            )}
          </div>

          <nav className="flex-1 space-y-1 overflow-y-auto p-2">
            {NAV.map(([k, label, Icon]) => (
              <NavButton
                key={k}
                active={tab === k}
                collapsed={collapsed}
                icon={Icon}
                label={label}
                onClick={() => setTab(k)}
              />
            ))}
          </nav>

          <div className={cn('border-t p-3', collapsed && 'p-2')}>
            {!collapsed ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <SSEDot state={sseState} />
                  <span className="text-xs font-medium">SSE {sseState}</span>
                </div>
                <div className="truncate text-xs text-muted-foreground" title={session.email}>
                  {session.email}
                </div>
              </div>
            ) : (
              <div className="flex justify-center">
                <SSEDot state={sseState} />
              </div>
            )}
          </div>
        </aside>

        {/* Main */}
        <main className="min-w-0 flex-1 bg-muted/20">
          <div className="mx-auto max-w-[1200px] p-4 md:p-6 lg:p-8">
            {/* toast */}
            <AnimatePresence>
              {toast && (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.15 }}
                  onClick={() => setToast('')}
                  className="fixed right-4 top-[4rem] z-50 cursor-pointer rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm font-medium text-emerald-800 shadow-lg dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-100"
                >
                  {toast}
                </motion.div>
              )}
            </AnimatePresence>

            {/* grid container */}
            <div className="space-y-6">
              {tab === 'dashboard' && (
                <Card className="border-violet-200 bg-gradient-to-br from-violet-50 to-card dark:border-violet-900/30 dark:from-violet-950/20">
                  <CardContent className="p-4 md:p-6">
                    <CommandCenter
                      onCreated={(id: string) => {
                        setRunId(id)
                        setToast(`Run oluşturuldu: ${id.slice(0, 8)}`)
                        setTab('runs')
                      }}
                    />
                  </CardContent>
                </Card>
              )}

              {tab === 'dashboard' && (
                <Dashboard live={live} sseState={sseState} lastId={lastId} onOpen={(k: string) => setTab(k as NavKey)} onOpenRun={(id: string) => { setRunId(id); setTab('runs') }} />
              )}

              {tab === 'runs' &&
                (runId ? (
                  <RunsWithDetail runId={runId} onBack={() => setRunId('')} onOpenDetail={(id) => setRunId(id)} />
                ) : (
                  <RunsPage onOpenDetail={(id) => setRunId(id)} />
                ))}

              {tab === 'approvals' && <ApprovalsPage />}
              {tab === 'context' && <ContextPage initialRunId={runId} />}
              {tab === 'memory' && <MemoryPage />}
              {tab === 'sources' && <SourcesPage />}
              {tab === 'technocore' && <TechnocorePage />}
              {tab === 'telegram' && <TelegramPage />}
              {tab === 'settings' && <SettingsPage />}
              {tab === 'reports' && <ReportsPage />}
              {tab === 'audit' && <AuditPage />}

              {tab !== 'dashboard' && (
                <Card className="border-dashed">
                  <CardContent className="p-4">
                    <CommandCenter
                      compact
                      onCreated={(id) => {
                        setRunId(id)
                        setToast(`Run oluşturuldu: ${id.slice(0, 8)}`)
                        setTab('runs')
                      }}
                    />
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

function SSEStateLabel(s: SSEState) {
  return s === 'open' ? 'bağlı' : s === 'connecting' ? 'bağlanıyor' : s === 'error' ? 'hata/yeniden deneme' : 'kapalı'
}

function RunsWithDetail({ runId, onBack, onOpenDetail }: { runId: string; onBack: () => void; onOpenDetail: (id: string) => void }) {
  const [showDetail, setShowDetail] = useState(true)
  useEffect(() => {
    setShowDetail(true)
  }, [runId])
  if (showDetail) return <RunDetailPage runId={runId} onBack={() => { setShowDetail(false); onBack() }} />
  return <RunsPage onOpenDetail={(id) => { onOpenDetail(id); setShowDetail(true) }} />
}

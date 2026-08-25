// RAPTOR web — API client. localStorage'e auth token YAZILMAZ.
const API = (import.meta.env.VITE_API_BASE ?? '/api') as string

export async function api<T = any>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(opts?.headers || {}) },
    ...opts,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status}: ${body.slice(0, 160)}`)
  }
  return res.status === 204 ? (undefined as any) : (res.json() as Promise<T>)
}

export const apiBase = API

// SSE — events/stream'e EventSource bağlan
export function openSSE(onEvent: (e: any) => void): () => void {
  const es = new EventSource(`${import.meta.env.VITE_SSE_BASE ?? '/events'}`)
  es.onmessage = (msg) => {
    try { onEvent(JSON.parse(msg.data)) } catch { /* ignore */ }
  }
  return () => es.close()
}
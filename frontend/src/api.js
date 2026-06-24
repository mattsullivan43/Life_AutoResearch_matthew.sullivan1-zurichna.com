// Thin client over the FastAPI backend (proxied at /api by Vite).
import { getToken } from './auth'

const H = () => { const t = getToken(); return t ? { Authorization: `Bearer ${t}` } : {} }

export async function getStatus() {
  const r = await fetch('/api/status', { headers: H() })
  if (!r.ok) throw new Error('status failed')
  return r.json()
}

export async function getChannels() {
  const r = await fetch('/api/channels', { headers: H() })
  if (!r.ok) throw new Error('channels failed')
  return r.json()
}

export async function getChannelStatus(channel) {
  const r = await fetch(`/api/channel_status?channel=${channel}`, { headers: H() })
  if (!r.ok) throw new Error('channel_status failed')
  return r.json()
}

export async function runBaseline() {
  const r = await fetch('/api/baseline', { method: 'POST', headers: H() })
  if (!r.ok) throw new Error('baseline failed')
  return r.json()
}

export async function getBestPrompt(channel = 'emails') {
  const r = await fetch(`/api/best_prompt?channel=${channel}`, { headers: H() })
  if (!r.ok) throw new Error('best_prompt failed')
  return r.json()
}

export async function getNotebook(channel = 'emails') {
  const r = await fetch(`/api/notebook?channel=${channel}`, { headers: H() })
  if (!r.ok) throw new Error('notebook failed')
  return r.json()
}

export async function getSolution(channel = 'emails') {
  const r = await fetch(`/api/solution?channel=${channel}`, { headers: H() })
  if (!r.ok) throw new Error('solution failed')
  return r.json()
}

export async function postReview(runId, decision) {
  return fetch(`/api/review?run_id=${runId}&decision=${decision}`, { method: 'POST', headers: H() })
}

export async function uploadDocs(channel, fileList) {
  const fd = new FormData()
  fd.append('channel', channel)
  for (const f of fileList) fd.append('files', f)
  const r = await fetch('/api/upload', { method: 'POST', headers: H(), body: fd })
  if (!r.ok) throw new Error('upload failed')
  return r.json()
}

export async function resetPrompt(channel) {
  return fetch(`/api/reset?channel=${channel}`, { method: 'POST', headers: H() })
}

// Stream the optimization loop via Server-Sent Events. EventSource can't send
// headers, so the token rides as a query param (?access_token=).
export function streamRun({ channel = 'emails', iterations = 12, hitl = false, warm = true },
                          onEvent, onError, onDone) {
  const t = getToken()
  const auth = t ? `&access_token=${encodeURIComponent(t)}` : ''
  const es = new EventSource(`/api/run?channel=${channel}&iterations=${iterations}&hitl=${hitl}&warm=${warm}${auth}`)
  es.onmessage = (m) => {
    let ev
    try { ev = JSON.parse(m.data) } catch { return }
    onEvent(ev)
    if (ev.type === 'final' || ev.type === 'error') { es.close(); onDone && onDone(ev) }
  }
  es.onerror = () => { es.close(); onError && onError() }
  return es
}

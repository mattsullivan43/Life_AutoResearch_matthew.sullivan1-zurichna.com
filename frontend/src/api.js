// Thin client over the FastAPI backend (proxied at /api by Vite).
import { getToken } from './auth'

const H = () => { const t = getToken(); return t ? { Authorization: `Bearer ${t}` } : {} }

// Cognito access tokens expire after ~1h. A stale token skips the login screen
// and then every call 401s — which used to render as "cannot reach backend".
// On any 401: drop the token and reload, which lands on the login screen.
const guard = (r) => {
  if (r.status === 401 && getToken()) {
    localStorage.removeItem('access_token')
    window.location.reload()
  }
  return r
}

export async function getStatus() {
  const r = guard(await fetch('/api/status', { headers: H() }))
  if (!r.ok) throw new Error('status failed')
  return r.json()
}

export async function getChannels() {
  const r = guard(await fetch('/api/channels', { headers: H() }))
  if (!r.ok) throw new Error('channels failed')
  return r.json()
}

export async function getChannelStatus(channel) {
  const r = guard(await fetch(`/api/channel_status?channel=${channel}`, { headers: H() }))
  if (!r.ok) throw new Error('channel_status failed')
  return r.json()
}

export async function runBaseline() {
  const r = guard(await fetch('/api/baseline', { method: 'POST', headers: H() }))
  if (!r.ok) throw new Error('baseline failed')
  return r.json()
}

export async function getBestPrompt(channel = 'emails') {
  const r = guard(await fetch(`/api/best_prompt?channel=${channel}`, { headers: H() }))
  if (!r.ok) throw new Error('best_prompt failed')
  return r.json()
}

export async function getNotebook(channel = 'emails') {
  const r = guard(await fetch(`/api/notebook?channel=${channel}`, { headers: H() }))
  if (!r.ok) throw new Error('notebook failed')
  return r.json()
}

export async function getSolution(channel = 'emails') {
  const r = guard(await fetch(`/api/solution?channel=${channel}`, { headers: H() }))
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
  const r = guard(await fetch('/api/upload', { method: 'POST', headers: H(), body: fd }))
  if (!r.ok) throw new Error('upload failed')
  return r.json()
}

export async function listSubmissions() {
  const r = guard(await fetch('/api/submissions', { headers: H() }))
  if (!r.ok) throw new Error('submissions failed')
  return r.json()
}

export async function classifySubmission(id, live = false) {
  const r = guard(await fetch(`/api/classify_submission?submission_id=${encodeURIComponent(id)}&live=${live}`,
    { method: 'POST', headers: H() }))
  return r.json()
}

export async function getSubmissionText(id) {
  const r = guard(await fetch(`/api/submission_text?submission_id=${encodeURIComponent(id)}`, { headers: H() }))
  if (!r.ok) throw new Error('submission_text failed')
  return r.json()
}

export async function getScoreboard() {
  const r = guard(await fetch('/api/scoreboard', { headers: H() }))
  if (!r.ok) throw new Error('scoreboard failed')
  return r.json()
}

export async function getEngineSummary() {
  const r = guard(await fetch('/api/engine_summary', { headers: H() }))
  if (!r.ok) throw new Error('engine_summary failed')
  return r.json()
}

// SSE: fills in buckets/attachments as the model classifies them.
export function streamClassify(id, live, onEvent, onError) {
  const t = getToken()
  const auth = t ? `&access_token=${encodeURIComponent(t)}` : ''
  const es = new EventSource(`/api/classify_submission_stream?submission_id=${encodeURIComponent(id)}&live=${live}${auth}`)
  es.onmessage = (m) => {
    let ev
    try { ev = JSON.parse(m.data) } catch { return }
    onEvent(ev)
    if (ev.type === 'done' || ev.type === 'error') es.close()
  }
  es.onerror = () => { es.close(); onError && onError() }
  return es
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

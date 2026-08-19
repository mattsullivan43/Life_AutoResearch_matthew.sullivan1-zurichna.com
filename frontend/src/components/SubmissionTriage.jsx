import { useEffect, useRef, useState } from 'react'
import { listSubmissions, classifySubmission, uploadDocs } from '../api'

// BROKER SUBMISSION TRIAGE — the demo centrepiece for the Commercial
// Submissions group: pick (or drop) a broker email, see the 5-layer buckets +
// risk flags and the per-attachment doc-type index, with ground-truth ticks
// when the sample is labelled. "pre-processed" = served from cache, instant;
// "live" re-runs every channel's current best prompt (~20-60s).
export default function SubmissionTriage() {
  const [subs, setSubs] = useState([])
  const [sel, setSel] = useState('')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState('')
  const [uploadMsg, setUploadMsg] = useState('')
  const fileRef = useRef(null)

  const refresh = () => listSubmissions().then((d) => {
    setSubs(d.submissions)
    if (!sel && d.submissions.length) setSel(d.submissions[0].id)
  }).catch(() => {})
  useEffect(() => { refresh() }, [])

  async function run(live) {
    if (!sel) return
    setBusy(true); setErr(''); if (live) setRes(null)
    try {
      const r = await classifySubmission(sel, live)
      if (r.error) setErr(r.error); else { setRes(r); refresh() }
    } catch { setErr('classification failed — is the backend running?') }
    setBusy(false)
  }

  async function handleFiles(files) {
    const ok = [...files].filter((f) => /\.(eml|msg)$/i.test(f.name))
    if (!ok.length) { setUploadMsg('only .eml / .msg emails are accepted'); return }
    setUploadMsg(`ingesting ${ok.length} email(s)… (attachments extracted locally, PII anonymised)`)
    try {
      const r = await uploadDocs('submissions', ok)
      const first = r.ingested?.[0]
      setUploadMsg(r.ingested.map((i) => i.error
        ? `${i.id}: ${i.error}`
        : `${i.id}: ${i.attachments} attachments${i.warnings?.length ? ` · ⚠ ${i.warnings.length} warnings` : ''}${i.labelled ? '' : ' · no ground-truth labels (classify-only)'}`
      ).join(' · '))
      await refresh()
      if (first && !first.error) setSel(first.id)
    } catch { setUploadMsg('upload failed') }
  }

  const cur = subs.find((s) => s.id === sel)
  const badge = res && (res.mode === 'cached'
    ? <span className="tri-badge cached">pre-processed · instant</span>
    : <span className="tri-badge live">live run</span>)

  return (
    <div className="block">
      <div className="head">
        <h3>Broker submission triage</h3>
        <span className="sub">classify &amp; index one submission with the current best prompts</span>
      </div>
      <div className="body">
        <div className="tri-controls">
          <select value={sel} onChange={(e) => { setSel(e.target.value); setRes(null) }} disabled={busy}>
            {subs.map((s) => (
              <option key={s.id} value={s.id}>
                {s.id} · {s.attachments} att{s.cached ? ' · ready' : ''}{s.labelled ? '' : ' · unlabelled'}
              </option>
            ))}
          </select>
          <button className="btn btn-primary" onClick={() => run(false)} disabled={busy || !sel}>
            {busy ? 'Classifying…' : (cur?.cached ? 'Show triage (instant)' : 'Classify submission')}
          </button>
          <button className="btn btn-ghost" onClick={() => run(true)} disabled={busy || !sel}>re-run live</button>
          <span className="spacer" />
          <button className="btn btn-ghost" onClick={() => fileRef.current?.click()} disabled={busy}>+ drop a broker email (.eml/.msg)</button>
          <input ref={fileRef} type="file" multiple accept=".eml,.msg" style={{ display: 'none' }}
            onChange={(e) => { handleFiles(e.target.files); e.target.value = '' }} />
        </div>
        {uploadMsg && <div className="dz-msg" style={{ marginTop: 6 }}>{uploadMsg}</div>}
        {err && <div className="note err" style={{ marginTop: 10 }}><b>Error:</b> {err}</div>}

        {res && (
          <div className="tri-result">
            <div className="tri-head">
              <span className="code" style={{ fontWeight: 700 }}>{res.submission_id}</span>
              {badge}
              {res.labelled
                ? <span className="tri-score">{res.buckets.filter((b) => b.match).length}/{res.buckets.length} buckets · {res.attachments.filter((a) => a.match).length}/{res.attachments.length} attachments match ground truth</span>
                : <span className="tri-score">unlabelled — predictions only</span>}
            </div>

            <div className="tri-buckets">
              {res.buckets.map((b) => (
                <div className={'tri-bucket' + (b.match === false ? ' miss' : '')} key={b.channel}>
                  <div className="tri-lab">{b.label}{b.match != null && <span className={'mark ' + (b.match ? 'good' : 'bad')}> {b.match ? '✓' : '✗'}</span>}</div>
                  <div className="tri-val">
                    {(b.pred.length ? b.pred : ['(none)']).map((p) => <span className="tri-chip" key={p}>{p}</span>)}
                  </div>
                  {b.match === false && <div className="tri-gt">truth: {(b.gt || []).join(' | ') || '(none)'}</div>}
                </div>
              ))}
            </div>

            <div className="preds-wrap" style={{ marginTop: 14 }}>
              <table className="preds">
                <thead><tr><th style={{ width: 28 }}></th><th>attachment</th><th>indexed as</th><th>chars</th><th>warning</th></tr></thead>
                <tbody>
                  {res.attachments.map((a) => (
                    <tr key={a.filename} className={a.match === false ? 'wrong' : ''}>
                      <td className={'mark ' + (a.match == null ? '' : a.match ? 'good' : 'bad')}>{a.match == null ? '·' : a.match ? '✓' : '✗'}</td>
                      <td className="snip">{a.filename}</td>
                      <td className="code">{a.doc_type}{a.match === false && <span className="tri-gt"> (truth: {a.gt})</span>}</td>
                      <td className="code">{a.char_count.toLocaleString()}</td>
                      <td className="snip">{a.read_warning ? `⚠ ${a.read_warning}` : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

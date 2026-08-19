import { useEffect, useRef, useState } from 'react'
import { listSubmissions, getSubmissionText, streamClassify, uploadDocs } from '../api'

// BROKER SUBMISSION TRIAGE — the COO view. Left: the actual (anonymised)
// email + attachments the model reads. Right: buckets + doc-type index that
// FILL IN LIVE as each item is classified (SSE), or instantly from cache.
export default function SubmissionTriage() {
  const [subs, setSubs] = useState([])
  const [sel, setSel] = useState('')
  const [doc, setDoc] = useState(null)          // {cover_email_text, attachments[]}
  const [openAtt, setOpenAtt] = useState(null)  // which attachment text is expanded
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState(null)        // 'cached' | 'live'
  const [buckets, setBuckets] = useState(null)  // [{channel,label,pred?,gt?,match?}]
  const [attRes, setAttRes] = useState({})      // filename -> {doc_type, gt, match}
  const [err, setErr] = useState('')
  const [uploadMsg, setUploadMsg] = useState('')
  const fileRef = useRef(null)
  const esRef = useRef(null)

  const refresh = () => listSubmissions().then((d) => { setSubs(d.submissions); return d.submissions }).catch(() => [])

  // auto-load: first submission's document + its cached triage, so the tab is
  // never empty in front of an audience
  useEffect(() => {
    // default to the strongest sample, not the alphabetical first (alliance is the
    // adversarial worst case — its disputed labels make it the wrong opener)
    refresh().then((list) => {
      const pick = list.find((s) => s.id === 'tryon') || list[0]
      if (pick) select(pick.id, true)
    })
    return () => esRef.current && esRef.current.close()
  }, [])

  async function select(id, autorun) {
    esRef.current && esRef.current.close()
    setSel(id); setErr(''); setBuckets(null); setAttRes({}); setMode(null); setOpenAtt(null)
    try { setDoc(await getSubmissionText(id)) } catch { setDoc(null) }
    if (autorun) run(id, false)
  }

  function run(id, live) {
    setBusy(true); setErr(''); setMode(null)
    if (live) { setBuckets(null); setAttRes({}) }
    esRef.current = streamClassify(id, live, (ev) => {
      if (ev.type === 'start') {
        setMode('live')
        setBuckets(ev.buckets.map((b) => ({ ...b, pred: null })))
      } else if (ev.type === 'bucket') {
        setBuckets((bs) => (bs || []).map((b) => (b.channel === ev.channel ? { ...b, ...ev } : b)))
      } else if (ev.type === 'att') {
        setAttRes((a) => ({ ...a, [ev.filename]: ev }))
      } else if (ev.type === 'done') {
        setMode(ev.result.mode)
        setBuckets(ev.result.buckets)
        setAttRes(Object.fromEntries(ev.result.attachments.map((a) => [a.filename, a])))
        setBusy(false); refresh()
      } else if (ev.type === 'error') {
        setErr(ev.message); setBusy(false)
      }
    }, () => { setErr('stream interrupted'); setBusy(false) })
  }

  async function handleFiles(files) {
    const ok = [...files].filter((f) => /\.(eml|msg)$/i.test(f.name))
    if (!ok.length) { setUploadMsg('only .eml / .msg emails are accepted'); return }
    setUploadMsg(`ingesting ${ok.length} email(s)… (read locally, PII anonymised)`)
    try {
      const r = await uploadDocs('submissions', ok)
      const first = r.ingested?.find((i) => !i.error)
      setUploadMsg(r.ingested.map((i) => i.error ? `${i.id}: ${i.error}`
        : `${i.id}: ${i.attachments} attachments ingested${i.labelled ? '' : ' · unlabelled (predictions only)'}`).join(' · '))
      await refresh()
      if (first) { await select(first.id, false); run(first.id, true) }
    } catch { setUploadMsg('upload failed') }
  }

  const done = buckets && buckets.every((b) => b.pred != null) && doc
    && doc.attachments.every((a) => attRes[a.filename])
  const scored = buckets && buckets.some((b) => b.match != null)
  const chip = (p) => (p || []).length ? p.map((x) => <span className="tri-chip" key={x}>{x}</span>) : <span className="tri-chip">(none)</span>

  return (
    <div className="block">
      <div className="head">
        <h3>Broker submission triage</h3>
        <span className="sub">left: what the model reads · right: what it decides — live</span>
      </div>
      <div className="body">
        <div className="tri-controls">
          <select value={sel} onChange={(e) => select(e.target.value, true)} disabled={busy}>
            {subs.map((s) => (
              <option key={s.id} value={s.id}>{s.id} · {s.attachments} attachments{s.labelled ? '' : ' · unlabelled'}</option>
            ))}
          </select>
          <button className="btn btn-primary" onClick={() => run(sel, true)} disabled={busy || !sel}>
            {busy ? 'Classifying…' : 'Classify LIVE (watch it work)'}
          </button>
          {mode === 'cached' && <span className="tri-badge cached">pre-processed · instant</span>}
          {mode === 'live' && <span className="tri-badge live">{busy ? 'live — classifying' : 'live run'}</span>}
          <span className="spacer" />
          <button className="btn btn-ghost" onClick={() => fileRef.current?.click()} disabled={busy}>+ drop a new broker email</button>
          <input ref={fileRef} type="file" multiple accept=".eml,.msg" style={{ display: 'none' }}
            onChange={(e) => { handleFiles(e.target.files); e.target.value = '' }} />
        </div>
        {uploadMsg && <div className="dz-msg" style={{ marginTop: 6 }}>{uploadMsg}</div>}
        {err && <div className="note err" style={{ marginTop: 10 }}><b>Error:</b> {err}</div>}

        <div className="tri-split">
          {/* ── the document ── */}
          <div className="tri-doc">
            <div className="tri-doc-h">THE SUBMISSION EMAIL <span>(anonymised — exactly what the model reads)</span></div>
            <pre className="tri-cover">{doc ? doc.cover_email_text.slice(0, 2400) : 'loading…'}</pre>
            <div className="tri-doc-h" style={{ marginTop: 12 }}>ATTACHMENTS <span>click to read the extracted text</span></div>
            {doc && doc.attachments.map((a) => {
              const r = attRes[a.filename]
              const working = busy && mode === 'live' && !r
              return (
                <div className={'tri-att' + (openAtt === a.filename ? ' open' : '')} key={a.filename}>
                  <button className="tri-att-row" onClick={() => setOpenAtt(openAtt === a.filename ? null : a.filename)}>
                    <span className={'tri-dot' + (r ? (r.match === false ? ' bad' : ' ok') : working ? ' pulse' : '')} />
                    <span className="tri-att-name">{a.filename}</span>
                    <span className="tri-att-tag">
                      {r ? r.doc_type : working ? 'reading…' : `${(a.char_count / 1000).toFixed(1)}k chars`}
                    </span>
                  </button>
                  {openAtt === a.filename && (
                    <pre className="tri-att-text">{a.text.slice(0, 4000) || '(no text extracted)'}
                      {a.read_warning ? `\n\n⚠ ${a.read_warning}` : ''}</pre>
                  )}
                </div>
              )
            })}
          </div>

          {/* ── the decisions ── */}
          <div className="tri-out">
            <div className="tri-doc-h">THE TRIAGE DECISION {scored && done && (
              <span>{buckets.filter((b) => b.match).length}/{buckets.length} buckets · {Object.values(attRes).filter((a) => a.match).length}/{Object.keys(attRes).length} attachments match the human answer key</span>
            )}</div>
            <div className="tri-buckets">
              {(buckets || Array.from({ length: 6 }, (_, i) => ({ channel: i, label: '…', pred: null }))).map((b) => (
                <div className={'tri-bucket' + (b.match === false ? ' miss' : '') + (b.pred == null ? ' pending' : '')} key={b.channel}>
                  <div className="tri-lab">{b.label}{b.match != null && <span className={'mark ' + (b.match ? 'good' : 'bad')}> {b.match ? '✓' : '✗'}</span>}</div>
                  <div className="tri-val">{b.pred == null
                    ? <span className="tri-chip pending">{busy ? 'deciding…' : '—'}</span> : chip(b.pred)}</div>
                  {b.match === false && <div className="tri-gt">answer key: {(b.gt || []).join(' | ') || '(none)'}</div>}
                </div>
              ))}
            </div>
            <div className="hl-line" style={{ marginTop: 14 }}>
              Every attachment on the left gets its <b>document type</b> stamped as the model reads it — that's the
              index. The cards above are the <b>5-layer routing decision</b> for the whole submission.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

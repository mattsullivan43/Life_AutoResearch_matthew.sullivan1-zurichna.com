import { useEffect, useRef, useState } from 'react'
import {
  getStatus, getChannels, getChannelStatus, runBaseline, getBestPrompt, streamRun, postReview, uploadDocs, resetPrompt, getNotebook, getSolution,
} from './api'
import ScoreChart from './components/ScoreChart'
import LiveLog from './components/LiveLog'
import ResearchLog from './components/ResearchLog'
import SolutionPanel from './components/SolutionPanel'
import PredictionsTable from './components/PredictionsTable'
import ConfusionMatrix from './components/ConfusionMatrix'
import PerClassF1 from './components/PerClassF1'
import CoveragePanel from './components/CoveragePanel'
import PromptViewer from './components/PromptViewer'
import SubmissionTriage from './components/SubmissionTriage'
import Scoreboard from './components/Scoreboard'
import BucketFlow from './components/BucketFlow'
import Login from './components/Login'
import { authConfig, getToken, logout as cognitoLogout } from './auth'

const pct = (x) => (x == null ? '—' : `${Math.min(100, Math.max(0, x * 100)).toFixed(1)}%`)
const now = () => new Date().toLocaleTimeString('en-GB')

// ?focus=broker -> demo mode: ONLY the Broker Submissions tab, landing on it.
// The Zurich Life channels stay fully functional at the plain URL.
const BROKER_ONLY = typeof window !== 'undefined'
  && new URLSearchParams(window.location.search).get('focus') === 'broker'

export default function App() {
  const [status, setStatus] = useState(null)
  const [channels, setChannels] = useState([])
  const [channel, setChannel] = useState(BROKER_ONLY ? 'attachment_doc_type' : 'emails')
  const [chStatus, setChStatus] = useState(null)        // extract-channel schema/splits
  const [prompts, setPrompts] = useState({ seed: '', best: '' })
  const [baseline, setBaseline] = useState(null)
  const [iterations, setIterations] = useState(12)
  const [hitl, setHitl] = useState(false)
  const [warm, setWarm] = useState(true)
  const [running, setRunning] = useState(false)
  const [chart, setChart] = useState([])
  const [perClass, setPerClass] = useState(null)
  const [confusion, setConfusion] = useState(null)
  const [rows, setRows] = useState(null)
  const [split, setSplit] = useState(null)
  const [metrics, setMetrics] = useState(null)          // extract: {judge, field_accuracy}
  const [bestF1, setBestF1] = useState(null)
  const [finalScore, setFinalScore] = useState(null)   // honest score on unseen set
  const [finalInfo, setFinalInfo] = useState(null)     // {mf1, acc, n} — counts beat % at tiny n
  const [runResult, setRunResult] = useState(null)     // BEFORE -> AFTER on unseen, the run's verdict
  const [notebook, setNotebook] = useState([])         // persistent research log
  const [solution, setSolution] = useState(null)       // the editable artifact
  const [solStatus, setSolStatus] = useState('')
  const [log, setLog] = useState([])
  const [review, setReview] = useState(null)            // {runId, iter, cand, best}
  const [error, setError] = useState('')
  const [uploadMsg, setUploadMsg] = useState('')
  const [authChecked, setAuthChecked] = useState(false)
  const [needLogin, setNeedLogin] = useState(false)
  const [cognitoOn, setCognitoOn] = useState(false)
  const esRef = useRef(null)
  const runIdRef = useRef(null)
  const fileRef = useRef(null)
  const addLog = (l) => setLog((p) => [...p, { t: now(), ...l }])

  const task = channels.find((c) => c.id === channel)?.task || 'classify'
  const isEmails = channel === 'emails'
  const isSub = task === 'classify_sub'
  const shownChannels = BROKER_ONLY ? channels.filter((c) => c.group === 'Commercial Submissions') : channels
  const groups = [...new Set(shownChannels.map((c) => c.group || 'Channels'))]

  // resolve auth first (Cognito enabled? logged in?)
  useEffect(() => {
    authConfig().then((c) => {
      setCognitoOn(!!c.enabled)
      if (c.enabled && !getToken()) setNeedLogin(true)
      setAuthChecked(true)
    })
  }, [])

  const ready = authChecked && !needLogin
  useEffect(() => {
    if (!ready) return
    getChannels().then((d) => setChannels(d.channels)).catch(() => {})
    getStatus().then(setStatus).catch(() => setError('Cannot reach backend — start it with ./dev.sh (port 8000).'))
    return () => esRef.current && esRef.current.close()
  }, [ready])

  // when channel changes, reset run view + load that channel's prompt/schema
  useEffect(() => {
    if (!ready) return
    setChart([]); setRows(null); setConfusion(null); setPerClass(null); setMetrics(null)
    setBestF1(null); setSplit(null); setReview(null); setFinalScore(null); setFinalInfo(null); setRunResult(null)
    getBestPrompt(channel).then(setPrompts).catch(() => setPrompts({ seed: '', best: '' }))
    getNotebook(channel).then((d) => setNotebook(d.experiments || [])).catch(() => setNotebook([]))
    getSolution(channel).then((d) => { setSolution(d.solution); setSolStatus('current best') }).catch(() => setSolution(null))
    if (channel !== 'emails') getChannelStatus(channel).then(setChStatus).catch(() => setChStatus(null))
    else setChStatus(null)
  }, [channel, ready])

  const provider = status?.provider
  const keyOff = provider && !provider.key_present

  async function onBaseline() {
    setError(''); addLog({ kind: 'plain', text: '$ running keyword baseline (no API)…' })
    try {
      const r = await runBaseline()
      setBaseline(r); setConfusion(r.confusion); setPerClass(r.per_class)
      setRows(r.rows); setSplit('UNSEEN emails · keyword baseline')
      addLog({ kind: 'final', text: `simple keyword baseline: ${pct(r.mf1)} on unseen data (the floor to beat)` })
    } catch { setError('Baseline failed.'); addLog({ kind: 'err', text: 'baseline failed' }) }
  }

  function onRun() {
    setError(''); setChart([]); setPerClass(null); setConfusion(null); setRows(null)
    setMetrics(null); setBestF1(null); setFinalScore(null); setFinalInfo(null); setRunResult(null); setReview(null); setRunning(true)
    addLog({ kind: 'plain', text: `run ${channel} · ${iterations} iters${hitl ? ' · human-in-the-loop' : ''}` })
    esRef.current = streamRun({ channel, iterations, hitl, warm },
      (ev) => {
        if (ev.type === 'run_id') { runIdRef.current = ev.run_id }
        else if (ev.type === 'start') {
          addLog({ kind: 'plain', text: ev.warm_start ? 'continuing from the saved best prompt (cumulative)' : 'starting fresh from the seed prompt' })
          addLog({ kind: 'plain', text: `tune on ${ev.dev} ${isSub ? (channel === 'attachment_doc_type' ? 'attachments' : 'submissions') : task === 'extract' ? 'documents' : 'emails'} · at the END, the best prompt is scored ONCE on ${ev.test} UNSEEN ${isSub ? (channel === 'attachment_doc_type' ? 'attachments' : 'submissions') : task === 'extract' ? 'documents' : 'emails'} · ${task === 'extract' ? 'graded by an AI judge' : 'graded against human labels'}` })
        } else if (ev.type === 'iter') {
          setChart((c) => [...c, { iter: ev.iter, dev_mf1: ev.dev_mf1, best_mf1: ev.best_mf1, accepted: ev.accepted === true }])
          if (ev.per_class) setPerClass(ev.per_class)
          if (ev.confusion) setConfusion(ev.confusion)
          if (ev.rows) setRows(ev.rows)
          if (ev.metrics) setMetrics(ev.metrics)
          if (ev.solution) { setSolution(ev.solution); setSolStatus(ev.accepted === true ? 'kept — new best' : ev.accepted === false ? 'candidate (discarded)' : 'baseline') }
          setSplit(`practice set · round ${ev.iter}`); setBestF1(ev.best_mf1)
          if (ev.accepted === true && ev.candidate_prompt) setPrompts((p) => ({ ...p, best: ev.candidate_prompt }))
          addLog({ kind: 'iter', iter: ev.iter, f1: ev.dev_mf1, accepted: ev.accepted, best: ev.best_mf1, desc: ev.description, verdict: ev.verdict, p: ev.stats?.p_better, prompt: ev.candidate_prompt, inc: ev.incumbent_prompt })
        } else if (ev.type === 'review') {
          setReview({ runId: runIdRef.current, iter: ev.iter, cand: ev.cand_mf1, best: ev.best_mf1,
            prompt: ev.candidate_prompt })
          if (ev.rows) setRows(ev.rows)
          if (ev.confusion) setConfusion(ev.confusion)
          if (ev.per_class) setPerClass(ev.per_class)
          if (ev.metrics) setMetrics(ev.metrics)
          setSplit(`practice set · round ${ev.iter} · CANDIDATE under review`)
          setPrompts((p) => ({ ...p, candidate: ev.candidate_prompt }))
          addLog({ kind: 'plain', text: `⏸ awaiting underwriter review — iter ${ev.iter} scored ${pct(ev.cand_mf1)} (beats ${pct(ev.best_mf1)})` })
        } else if (ev.type === 'final') {
          if (ev.confusion) setConfusion(ev.confusion)
          if (ev.per_class) setPerClass(ev.per_class)
          if (ev.rows) setRows(ev.rows)
          if (ev.metrics) setMetrics(ev.metrics)
          if (ev.solution) { setSolution(ev.solution); setSolStatus('best · final') }
          setSplit('UNSEEN emails · final'); setBestF1(ev.best_mf1); setFinalScore(ev.test_mf1)
          setFinalInfo({ mf1: ev.test_mf1, acc: ev.test_acc, n: ev.n })
          setRunResult({ improved: ev.improved, beforeMf1: ev.before_mf1, beforeAcc: ev.before_acc,
            afterMf1: ev.test_mf1, afterAcc: ev.test_acc, n: ev.n, bestIter: ev.best_iter })
          setRunning(false); setReview(null)
          addLog({ kind: 'final', text: `FINAL — score on UNSEEN data: ${pct(ev.test_mf1)} (the honest number; best from round ${ev.best_iter})${ev.stopped_early ? ' · stopped early: hit the 100% ceiling' : ''}` })
          getBestPrompt(channel).then(setPrompts).catch(() => {})
          getNotebook(channel).then((d) => setNotebook(d.experiments || [])).catch(() => {})
        } else if (ev.type === 'note') {
          addLog({ kind: 'plain', text: ev.text })
        } else if (ev.type === 'error') {
          setError(ev.message); setRunning(false); addLog({ kind: 'err', text: ev.message })
        }
      },
      () => { setError('Stream interrupted.'); setRunning(false); addLog({ kind: 'err', text: 'stream interrupted' }) })
  }

  function decide(decision) {
    if (!review) return
    postReview(review.runId, decision)
    addLog({ kind: 'plain', text: `underwriter ${decision === 'approve' ? 'APPROVED' : 'REJECTED'} iter ${review.iter}` })
    setReview(null)
    setPrompts((p) => ({ ...p, candidate: null }))
  }

  async function handleFiles(files) {
    const txt = [...files].filter((f) => f.name.endsWith('.txt'))
    if (!txt.length) { setUploadMsg('only .txt files are accepted'); return }
    setUploadMsg(`uploading ${txt.length} file(s)…`)
    try {
      const r = await uploadDocs(channel, txt)
      if (isEmails) {
        setUploadMsg(`added ${r.saved} · ${r.total_docs} docs total · ${r.unmatched} unmatched`
          + (r.missing_real?.length ? ` · still missing real: ${r.missing_real.join(', ')}` : ' · all classes covered ✓'))
        getStatus().then(setStatus).catch(() => {})
      } else {
        setUploadMsg(`added ${r.saved} file(s) to ${channel}`)
        getChannelStatus(channel).then(setChStatus).catch(() => {})
      }
    } catch { setUploadMsg('upload failed') }
  }
  const onDrop = (e) => { e.preventDefault(); handleFiles(e.dataTransfer.files) }
  const onPick = (e) => { handleFiles(e.target.files); e.target.value = '' }

  async function onReset() {
    await resetPrompt(channel)
    setPrompts((p) => ({ ...p, best: '' }))
    addLog({ kind: 'plain', text: `reset ${channel} — next run starts from the seed prompt` })
  }

  const metricLabel = task === 'extract' ? 'LLM-judge score' : 'macro-F1'

  if (!authChecked) return null
  if (needLogin) return <Login onLogin={() => setNeedLogin(false)} />

  return (
    <>
      <div className="brandstripe" />
      <header className="topbar">
        <img className="logo" src="/zurich-mark.png" alt="Zurich" />
        <span className="vrule" />
        <span className="product">Auto-Research <em>Engine</em></span>
        <span className="spacer" />
        {keyOff && <span className="meta"><span className="down">● no API key</span></span>}
        {cognitoOn && <button className="signout" onClick={() => { cognitoLogout(); setNeedLogin(true) }}>sign out</button>}
      </header>

      <div className="page">
        {!BROKER_ONLY && (
          <div className="masthead">
            <h1>One loop, every channel</h1>
            <p>
              Karpathy's auto-research loop optimises a prompt against a <b>labelled sample</b> and keeps only what beats the
              incumbent. <b>Each channel needs only its labelled sample; the agent does the rest.</b> Life emails are scored by
              exact match, extraction channels by an <b>LLM-as-judge</b> — and <b>Commercial Submissions</b> classifies whole
              broker emails (5-layer buckets + risk flags) and indexes every attachment by document type.
            </p>
          </div>
        )}

        {/* channel tabs, grouped: Zurich Life · Commercial Submissions */}
        <div className="tabgroups">
          {groups.map((g) => (
            <div className="tabgroup" key={g}>
              <span className="tg-label">{g}</span>
              <div className="tabs">
                {shownChannels.filter((c) => (c.group || 'Channels') === g).map((c) => (
                  <button key={c.id} className={'tab' + (c.id === channel ? ' on' : '')} onClick={() => !running && setChannel(c.id)} disabled={running}>
                    {c.label}
                    <span className="tasktag">
                      {c.task === 'extract' ? 'extract · LLM-judge' : 'classify'}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        {error && <div className="note err"><b>Error:</b> {error}</div>}

        {isEmails && status?.missing_real?.length > 0 && (
          <div className="note">
            <b>Note:</b> {status.missing_real.join(', ')} have no real docs; eval covers {status.coverage.filter((c) => !c.missing_real).length}/{status.categories.length} classes.
          </div>
        )}

        {/* ribbon — hidden in demo mode: the engine cards carry these numbers */}
        {!BROKER_ONLY && <div className="ribbon">
          {isSub ? (
            <>
              <div className="stat"><div className="lab">Majority-class floor</div><div className="num">{chStatus?.baseline ? pct(chStatus.baseline.mf1) : '—'}</div></div>
              <div className="stat"><div className="lab">Best on practice set</div><div className="num">{bestF1 != null ? pct(bestF1) : '—'}</div></div>
              <div className="stat"><div className="lab">Final · unseen docs</div>
                {/* at n<=12 a percentage is fake precision — show the raw count */}
                <div className="num hl">{finalInfo == null ? '—'
                  : finalInfo.n <= 12 ? <>{Math.round(finalInfo.acc * finalInfo.n)}/{finalInfo.n}<small> correct · F1 {pct(finalInfo.mf1)}</small></>
                  : pct(finalInfo.mf1)}</div></div>
              <div className="stat"><div className="lab">Practice / unseen</div><div className="num">{chStatus ? chStatus.dev : '—'}<small> / {chStatus ? chStatus.test : '—'}</small></div></div>
              <div className="stat"><div className="lab">Buckets</div><div className="num">{chStatus?.categories?.length ?? '—'}</div></div>
            </>
          ) : isEmails ? (
            <>
              <div className="stat"><div className="lab">Simple keyword floor</div><div className="num">{baseline ? pct(baseline.mf1) : '—'}</div></div>
              <div className="stat"><div className="lab">Best on practice set</div><div className="num">{bestF1 != null ? pct(bestF1) : '—'}</div></div>
              <div className="stat"><div className="lab">Final · unseen emails</div><div className="num hl">{finalScore != null ? pct(finalScore) : '—'}</div></div>
              <div className="stat"><div className="lab">Practice / unseen docs</div><div className="num">{status ? status.splits.dev : '—'}<small> / {status ? status.splits.test : '—'}</small></div></div>
              <div className="stat"><div className="lab">Categories</div><div className="num">{status ? status.categories.length : '—'}</div></div>
            </>
          ) : (
            <>
              <div className="stat"><div className="lab">Best on practice set</div><div className="num">{bestF1 != null ? pct(bestF1) : '—'}</div></div>
              <div className="stat"><div className="lab">Final · unseen docs</div><div className="num hl">{finalScore != null ? pct(finalScore) : '—'}</div></div>
              <div className="stat"><div className="lab">Field accuracy</div><div className="num">{metrics ? pct(metrics.field_accuracy) : '—'}</div></div>
              <div className="stat"><div className="lab">Practice / unseen</div><div className="num">{chStatus ? chStatus.dev : '—'}<small> / {chStatus ? chStatus.test : '—'}</small></div></div>
              <div className="stat"><div className="lab">Graded by</div><div className="num" style={{ fontSize: 16 }}>AI judge</div></div>
            </>
          )}
        </div>}

        {!BROKER_ONLY && <div className="explainer">
          <b>How to read this:</b> the loop <b>tunes</b> its prompt on a practice set to score higher there.
          The number that counts is the <b>“Final · unseen”</b> score — measured on documents it never trained on, so it reflects
          real-world performance. The practice score is always a bit higher (it studied those examples); the unseen score is the honest one.
        </div>}

        {/* broker submission triage — the Commercial Submissions demo panel */}
        {isSub && (
          <>
            <div className="seclab"><span className="tick" /><h2>Triage a submission</h2>
              <span className="hint">drop a broker email (.eml/.msg) — attachments read locally, PII anonymised, then bucketed &amp; indexed</span></div>
            <SubmissionTriage />
            <div className="seclab"><span className="tick" /><h2>Layer scoreboard</h2>
              <span className="hint">every layer's real numbers — floor, current best, honest unseen result, improvements kept</span></div>
            <Scoreboard />
          </>
        )}

        {/* upload labelled sample */}
        {!isSub && (
          <>
            <div className="seclab"><span className="tick" /><h2>Add to the labelled sample</h2>
              <span className="hint">{isEmails ? 'drop .txt emails — auto-labelled from ground truth & re-ingested instantly' : `drop .txt ${chStatus?.unit || 'doc'}s into this channel`}</span></div>
            <div className="dropzone" onClick={() => fileRef.current?.click()}
                 onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
              <input ref={fileRef} type="file" multiple accept=".txt" onChange={onPick} style={{ display: 'none' }} />
              <div className="dz-title">Drop .txt files here, or click to choose</div>
              <div className="dz-sub">{isEmails ? 'filenames are matched to ground_truth.csv to assign labels' : 'labels come from this channel’s ground-truth file'}</div>
              {uploadMsg && <div className="dz-msg">{uploadMsg}</div>}
            </div>
          </>
        )}

        {/* controls + chart */}
        <div className="seclab"><span className="tick" /><h2>Experiment — {channels.find((c) => c.id === channel)?.label || channel}</h2></div>
        {isSub && channel !== 'attachment_doc_type' && (
          <div className="note">
            <b>Small-sample layer:</b> only 8 labelled submissions exist → {chStatus?.dev ?? 5} practice / {chStatus?.test ?? 3} unseen.
            Scores here move in giant steps (1 document ≈ {chStatus?.test ? Math.round(100 / chStatus.test) : 33}%) and most rounds
            will be <b>inconclusive</b> — the statistics refusing to bank noise, not a failure. To watch the loop
            actually learn, use <b>Attachment document type</b> (35 practice / 28 unseen).
          </div>
        )}
        <div className="grid exp">
          <div className="block">
            <div className="head"><h3>Run</h3><span className="sub">{running ? 'streaming…' : 'idle'}</span></div>
            <div className="body controls">
              <div className="row">
                <div className="field">iterations
                  <input type="number" min="1" max="40" value={iterations} disabled={running}
                    onChange={(e) => setIterations(Math.max(1, Math.min(40, +e.target.value || 1)))} />
                </div>
                {isEmails && <button className="btn btn-ghost" onClick={onBaseline} disabled={running}>baseline</button>}
              </div>
              <label className="hitl"><input type="checkbox" checked={warm} disabled={running}
                onChange={(e) => setWarm(e.target.checked)} /> continue from the saved best prompt (cumulative across runs)</label>
              <label className="hitl"><input type="checkbox" checked={hitl} disabled={running}
                onChange={(e) => setHitl(e.target.checked)} /> human-in-the-loop (underwriter approves each improvement)</label>
              <button className="btn btn-primary" onClick={onRun} disabled={running || keyOff}>
                {running ? 'Optimizing…' : 'Run optimization loop'}
              </button>
              {prompts.best && !running && (
                <button className="resetlink" onClick={onReset}>↺ reset to seed prompt</button>
              )}
              {review && (
                <div className="review">
                  <div className="review-h">⏸ Underwriter review — iteration {review.iter}</div>
                  <div className="review-b">Candidate scored <b>{pct(review.cand)}</b>, beating the kept <b>{pct(review.best)}</b>. Read the proposed prompt below, then decide.</div>
                  <pre className="review-prompt">{review.prompt || '(no prompt text received)'}</pre>
                  <div className="review-b" style={{ marginTop: 10 }}>Its predictions on the dev set are shown in “The answers” below.</div>
                  <div className="row">
                    <button className="btn btn-primary" onClick={() => decide('approve')}>Approve &amp; adopt</button>
                    <button className="btn btn-ghost" onClick={() => decide('reject')}>Reject</button>
                  </div>
                </div>
              )}
              <div className="hl-line">
                The loop tries a new prompt each round on a <b>practice set</b>, keeping only what scores higher.
                The headline number is the <b>final score on unseen documents</b> the loop never trained on — the honest result.
              </div>
            </div>
          </div>
          <ScoreChart data={chart} baseline={isEmails ? baseline?.mf1 : null}
            metric={task === 'extract' ? 'LLM-judge score' : 'macro-F1'} />
        </div>

        {/* the run's verdict on UNSEEN docs — three honest states, counts first at tiny n */}
        {runResult && (() => {
          const cnt = (a) => `${Math.round(a * runResult.n)}/${runResult.n} correct`
          const gain = runResult.afterMf1 - runResult.beforeMf1
          const same = Math.abs(gain) < 0.005
          if (!runResult.improved) return (
            <div className="result-banner">
              <span className="rb-label">RESULT</span>
              <span className="rb-nums">no change kept</span>
              <span className="rb-sub">no candidate beat the current prompt with statistical confidence — unseen stays at {cnt(runResult.afterAcc)} (macro-F1 {pct(runResult.afterMf1)}). Nothing is banked on noise.</span>
            </div>)
          if (same) return (
            <div className="result-banner">
              <span className="rb-label">RESULT</span>
              <span className="rb-nums">kept on practice · unseen unchanged</span>
              <span className="rb-sub">round {runResult.bestIter}'s change won on the practice set and was adopted — but the unseen score did not move: {cnt(runResult.afterAcc)} (macro-F1 {pct(runResult.afterMf1)}). The unseen set is the honest check on practice-set wins.</span>
            </div>)
          if (gain > 0) return (
            <div className="result-banner improved">
              <span className="rb-label">RESULT — score on unseen documents</span>
              <span className="rb-nums">{pct(runResult.beforeMf1)} <span className="rb-arrow">→</span> <b>{pct(runResult.afterMf1)}</b></span>
              <span className="rb-sub">improvement from round {runResult.bestIter} adopted &amp; saved · {cnt(runResult.afterAcc)} on n={runResult.n}</span>
            </div>)
          return (
            <div className="result-banner warn">
              <span className="rb-label">RESULT — caution</span>
              <span className="rb-nums">{pct(runResult.beforeMf1)} <span className="rb-arrow">→</span> {pct(runResult.afterMf1)}</span>
              <span className="rb-sub">round {runResult.bestIter} won on the tiny practice set but scored WORSE on unseen ({cnt(runResult.afterAcc)}) — small-sample overfitting, caught because the unseen set is honest.</span>
            </div>)
        })()}

        {/* the loop made tangible: this round's documents -> buckets */}
        {isSub && <BucketFlow rows={rows} channel={channel} split={split} running={running} />}

        <div style={{ marginTop: 18 }}><LiveLog lines={log} running={running} /></div>

        {/* engine internals — on the broker tab these fold into one closed drawer:
            the run story above (chart + result banner + activity) IS the demo */}
        {(() => {
          const internals = (
            <>
              <div className="seclab"><span className="tick" /><h2>Research notebook</h2>
                <span className="hint">every experiment ever tried — kept &amp; discarded — so it never repeats a dead end</span></div>
              <ResearchLog experiments={notebook} />

              <div className="seclab"><span className="tick" /><h2>Solution</h2>
                <span className="hint">the editable artifact the agent mutates each experiment — Karpathy's train.py</span></div>
              <SolutionPanel solution={solution} task={task} status={solStatus} />

              {!isEmails && chStatus?.schema && (
                <>
                  <div className="seclab"><span className="tick" /><h2>Target schema</h2><span className="hint">the JSON the agent must produce, judged field-by-field</span></div>
                  <div className="block"><div className="body">
                    <table className="preds"><tbody>
                      {Object.entries(chStatus.schema).map(([k, v]) => (
                        <tr key={k}><td className="code" style={{ width: 180 }}>{k}</td><td className="snip">{v}</td></tr>
                      ))}
                    </tbody></table>
                  </div></div>
                </>
              )}

              <div className="seclab"><span className="tick" /><h2>The answers</h2><span className="hint">every scored document — ground truth vs what the model produced</span></div>
              <PredictionsTable rows={rows} split={split} task={task} />

              {(isEmails || isSub) && (
                <>
                  <div className="seclab"><span className="tick" /><h2>Scorecard</h2></div>
                  <div className={confusion ? 'grid cols-2' : 'grid'}>
                    {confusion && <ConfusionMatrix confusion={confusion} title={split} />}
                    <PerClassF1 perClass={perClass} title={split} />
                  </div>
                </>
              )}

              <div className="seclab"><span className="tick" /><h2>{isEmails ? 'Coverage & prompt' : 'Prompt'}</h2></div>
              <div className={isEmails ? 'grid cols-2' : 'grid'}>
                {isEmails && <CoveragePanel coverage={status?.coverage} />}
                <PromptViewer seed={prompts.seed} best={prompts.best} candidate={review ? prompts.candidate : null} />
              </div>
            </>
          )
          return internals
        })()}

        <div className="foot">
          <span>karpathy auto-research · temp=0 scoring · LLM-as-judge ≠ generator · human-in-the-loop</span>
          <img src="/zurich-logo.png" alt="Zurich" />
        </div>
      </div>
    </>
  )
}

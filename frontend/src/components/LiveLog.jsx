import { useEffect, useRef } from 'react'

// Refined activity timeline (not a terminal): one elegant row per event.
export default function LiveLog({ lines, running }) {
  const ref = useRef(null)
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight }, [lines, running])

  const pct = (v) => `${(v * 100).toFixed(1)}%`

  function Row({ l }) {
    if (l.kind === 'iter') {
      // four honest verdicts, not two: only a real p_worse>=0.95 loss is "Discarded";
      // "Inconclusive" = indistinguishable from noise, rolled back but retryable.
      const v = l.accepted === null ? 'seed'
        : l.verdict === 'keep' || l.accepted === true ? 'keep'
        : l.verdict === 'discard' ? 'discard'
        : l.verdict === 'duplicate' ? 'duplicate' : 'inconclusive'
      const cls = { seed: 'seed', keep: 'ok', discard: 'no', duplicate: 'mid', inconclusive: 'mid' }[v]
      const chip = { seed: 'Seed', keep: 'Kept', discard: 'Discarded', duplicate: 'Duplicate', inconclusive: 'Inconclusive' }[v]
      return (
        <div className="frow">
          <span className={'fmark ' + cls} />
          <div className="fmain fmain-exp">
            <div className="exp-head">
              <span className="lab">{l.accepted === null ? 'Seed baseline' : `Experiment ${l.iter}`}</span>
              <span className="score">{pct(l.f1)}</span>
              {l.accepted !== null && <span className="muted">best {pct(l.best)}</span>}
              {l.p != null && <span className="muted">p(better) {Math.round(l.p * 100)}%</span>}
            </div>
            {l.desc && l.accepted !== null && <div className="exp-desc">{l.desc}</div>}
          </div>
          <span className={'fchip ' + cls}>{chip}</span>
          <span className="ftime">{l.t}</span>
        </div>
      )
    }
    if (l.kind === 'final') {
      return (
        <div className="frow">
          <span className="fmark final" />
          <div className="fmain"><span className="lab">{l.text}</span></div>
          <span className="fchip final">Final</span>
          <span className="ftime">{l.t}</span>
        </div>
      )
    }
    if (l.kind === 'err') {
      return (
        <div className="frow"><span className="fmark err" />
          <div className="fmain"><span className="lab" style={{ color: 'var(--bad)' }}>{l.text}</span></div>
          <span className="ftime">{l.t}</span></div>
      )
    }
    return (
      <div className="frow plain"><span className="fmark seed" />
        <div className="fmain"><span className="fplain">{l.text.replace(/^\$ /, '')}</span></div>
        <span className="ftime">{l.t}</span></div>
    )
  }

  return (
    <div className="block">
      <div className="head"><h3>Activity</h3><span className="sub">{running ? 'live' : 'idle'}</span></div>
      <div className="body feed" ref={ref}>
        {lines.length === 0 && !running && <div className="empty">Run a loop to see the optimisation unfold.</div>}
        {lines.map((l, i) => <Row key={i} l={l} />)}
        {running && <div className="feed-live"><span className="pulse" /> optimising…</div>}
      </div>
    </div>
  )
}

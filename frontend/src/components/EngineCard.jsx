import { Fragment, useEffect, useState } from 'react'
import { getEngineSummary } from '../api'

// THE SELF-IMPROVING ENGINE — two measured, held-out stories for the exec view:
// product quality on broker attachments, and the loop's banked learning curve
// on the Life email channel (its longest-running proof).
const pct = (x) => `${(x * 100).toFixed(1)}%`

export default function EngineCard() {
  const [d, setD] = useState(null)
  useEffect(() => { getEngineSummary().then(setD).catch(() => {}) }, [])
  if (!d || !d.attachment) return null
  const a = d.attachment, e = d.emails

  return (
    <div className="grid cols-2">
      <div className="block">
        <div className="head"><h3>Attachment indexing · quality</h3><span className="sub">held-out documents it never trained on</span></div>
        <div className="body engine-body">
          <div className="engine-steps">
            <div className="estep"><div className="e-num">{pct(a.floor_mf1)}</div><div className="e-lab">keyword floor</div></div>
            <div className="e-arrow">→</div>
            <div className="estep big"><div className="e-num hl">{a.correct}/{a.n_test}</div><div className="e-lab">correct on unseen · macro-F1 {pct(a.best_mf1)}</div></div>
          </div>
          <div className="e-note">content-only (no filename hints) · scored against the human answer key</div>
        </div>
      </div>
      <div className="block">
        <div className="head"><h3>Proof the loop learns · Life email triage</h3><span className="sub">3 compounding runs, held-out score after each</span></div>
        <div className="body engine-body">
          <div className="engine-steps">
            <div className="estep"><div className="e-num">{pct(e.floor_mf1)}</div><div className="e-lab">keyword floor</div></div>
            {e.finals.map((f, i) => (
              <Fragment key={i}>
                <div className="e-arrow">→</div>
                <div className={'estep' + (i === e.finals.length - 1 ? ' big' : '')}>
                  <div className={'e-num' + (i === e.finals.length - 1 ? ' hl' : '')}>{pct(f)}</div>
                  <div className="e-lab">run {i + 1}</div>
                </div>
              </Fragment>
            ))}
          </div>
          <div className="e-note">every improvement banked only after a paired statistical test — noise is never kept</div>
        </div>
      </div>
    </div>
  )
}

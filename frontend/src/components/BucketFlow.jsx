import { useEffect, useState } from 'react'
import { listSubmissions } from '../api'

// THE MISSING PICTURE: during/after a loop run, show every document the round
// just classified — the submission email (with its attachment count) or the
// individual attachment — and which bucket the candidate prompt put it in,
// against the human answer. Updates every round, so the loop is visibly
// re-bucketing real emails, not just moving a number.
export default function BucketFlow({ rows, channel, split, running }) {
  const [subs, setSubs] = useState({})
  useEffect(() => {
    listSubmissions()
      .then((d) => setSubs(Object.fromEntries(d.submissions.map((s) => [s.id, s]))))
      .catch(() => {})
  }, [])
  const isAtt = channel === 'attachment_doc_type'
  const chips = (s) => (s || '').split(' | ').filter(Boolean)

  return (
    <div className="block" style={{ marginTop: 18 }}>
      <div className="head">
        <h3>{isAtt ? 'Every attachment → its index label' : 'Every submission (email + attachments) → its bucket'}</h3>
        <span className="sub">{split || ''}{running ? ' · re-classified every round' : ''}</span>
      </div>
      <div className="body">
        {!rows || rows.length === 0 ? (
          <div className="empty">
            Run the loop — each round, every {isAtt ? 'attachment' : 'submission email (with its attachments)'} is
            re-classified by the candidate prompt and compared to the human answer here.
          </div>
        ) : (
          <div className="preds-wrap">
            <table className="preds">
              <thead><tr>
                <th style={{ width: 28 }}></th>
                <th>{isAtt ? 'attachment · from submission' : 'submission'}</th>
                <th>{isAtt ? 'indexed as' : 'bucketed as'}</th>
                <th>human answer</th>
              </tr></thead>
              <tbody>
                {rows.map((r) => {
                  const slash = r.file.indexOf('/')
                  const sid = slash > 0 ? r.file.slice(0, slash) : r.file
                  const fname = slash > 0 ? r.file.slice(slash + 1) : null
                  const meta = subs[sid]
                  return (
                    <tr key={r.file} className={r.correct ? '' : 'wrong'}>
                      <td className={'mark ' + (r.correct ? 'good' : 'bad')}>{r.correct ? '✓' : '✗'}</td>
                      <td>
                        <div className="code" style={{ fontWeight: 700 }}>{fname || sid}</div>
                        <div className="snip" style={{ fontSize: 11 }}>
                          {fname ? `attachment of ${sid}`
                            : meta ? `email + ${meta.attachments} attachments` : 'email + attachments'}
                        </div>
                      </td>
                      <td>{chips(r.pred).map((p) => <span className="tri-chip" key={p} style={{ marginRight: 4 }}>{p}</span>)}</td>
                      <td className="code">{r.true}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

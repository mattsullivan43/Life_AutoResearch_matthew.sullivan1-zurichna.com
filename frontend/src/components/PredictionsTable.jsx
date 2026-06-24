import { useState } from 'react'

// THE ANSWERS — adapts to the channel task:
//  classify -> true label vs predicted label (+ email snippet)
//  extract  -> ground-truth JSON vs model JSON, scored 0-1 by the LLM-as-judge
export default function PredictionsTable({ rows, split, task = 'classify' }) {
  const [filter, setFilter] = useState('all')
  if (!rows || rows.length === 0) {
    return (
      <div className="block">
        <div className="head"><h3>Predictions vs ground truth</h3></div>
        <div className="body"><div className="empty">Run the loop to see every document scored.</div></div>
      </div>
    )
  }
  const wrong = rows.filter((r) => !r.correct).length
  const shown = filter === 'wrong' ? rows.filter((r) => !r.correct) : rows
  const fmt = (s) => { try { return JSON.stringify(JSON.parse(s)) } catch { return s } }

  return (
    <div className="block">
      <div className="head">
        <h3>Predictions vs ground truth</h3>
        <span className="sub">{split || 'eval'} · {task === 'extract' ? 'scored by LLM-judge' : `${rows.length - wrong}/${rows.length} correct`}</span>
      </div>
      <div className="body">
        <div className="preds-toolbar">
          <div className="seg">
            <button className={filter === 'all' ? 'on' : ''} onClick={() => setFilter('all')}>all {rows.length}</button>
            <button className={filter === 'wrong' ? 'on' : ''} onClick={() => setFilter('wrong')}>
              {task === 'extract' ? `low <0.8 ${wrong}` : `mistakes ${wrong}`}
            </button>
          </div>
          <span>ground truth is the human answer</span>
        </div>
        <div className="preds-wrap">
          <table className="preds">
            {task === 'extract' ? (
              <>
                <thead>
                  <tr><th style={{ width: 50 }}>judge</th><th>document</th><th>ground truth</th><th>model output</th><th>notes</th></tr>
                </thead>
                <tbody>
                  {shown.map((r) => (
                    <tr key={r.file} className={r.correct ? '' : 'wrong'}>
                      <td className={'code ' + (r.correct ? 'good' : 'bad')} style={{ fontWeight: 700 }}>{Math.min(100, Math.max(0, r.score * 100)).toFixed(0)}</td>
                      <td className="code">{r.file}</td>
                      <td className="snip" style={{ fontFamily: 'var(--mono)', fontSize: 11 }}>{fmt(r.true)}</td>
                      <td className="snip" style={{ fontFamily: 'var(--mono)', fontSize: 11 }}>{fmt(r.pred)}</td>
                      <td className="snip">{r.notes}</td>
                    </tr>
                  ))}
                </tbody>
              </>
            ) : (
              <>
                <thead>
                  <tr><th style={{ width: 28 }}></th><th>document</th><th>true</th><th>predicted</th><th>email snippet</th></tr>
                </thead>
                <tbody>
                  {shown.map((r) => (
                    <tr key={r.file} className={r.correct ? '' : 'wrong'}>
                      <td className={'mark ' + (r.correct ? 'good' : 'bad')}>{r.correct ? '✓' : '✗'}</td>
                      <td className="code">{r.file}</td>
                      <td className="code">{r.true}</td>
                      <td className={'code pred ' + (r.correct ? 'good' : 'bad')}>{r.pred}</td>
                      <td className="snip">{r.snippet}…</td>
                    </tr>
                  ))}
                </tbody>
              </>
            )}
          </table>
        </div>
      </div>
    </div>
  )
}

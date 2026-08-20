import { useEffect, useState } from 'react'
import { getScoreboard } from '../api'

// THE SCOREBOARD — no story cards, just every layer's real numbers:
// data size, the no-model floor, current best on practice, the honest unseen
// result (counts when n is tiny — a % on 3 docs is fake precision), and how
// many improvements the loop has ever banked on that layer.
const pct = (x) => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)

export default function Scoreboard({ refreshKey = 0 }) {
  const [rows, setRows] = useState(null)
  // refetch on mount AND whenever a run finishes (App bumps refreshKey on `final`)
  useEffect(() => {
    getScoreboard().then((d) => setRows(d.rows)).catch(() => {})
  }, [refreshKey])
  if (!rows) return null
  const unseen = (r) => {
    if (r.unseen_mf1 == null) return '—'
    if (r.unseen_acc != null && r.n_test != null && r.n_test <= 12)
      return `${Math.round(r.unseen_acc * r.n_test)}/${r.n_test} · F1 ${pct(r.unseen_mf1)}`
    if (r.unseen_acc != null && r.n_test != null)
      return `${Math.round(r.unseen_acc * r.n_test)}/${r.n_test} · F1 ${pct(r.unseen_mf1)}`
    return pct(r.unseen_mf1)
  }
  return (
    <div className="block">
      <div className="head"><h3>Layer scoreboard</h3>
        <span className="sub">floor = predict the majority class · unseen = documents the loop never trained on</span></div>
      <div className="body preds-wrap">
        <table className="preds">
          <thead><tr>
            <th>layer</th><th>practice / unseen docs</th><th>majority floor</th>
            <th>best on practice</th><th>result on unseen</th><th>kept / tried</th>
          </tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="code" style={{ fontWeight: 700 }}>{r.label}{r.multi ? ' (multi)' : ''}</td>
                <td className="code">{r.dev} / {r.test}</td>
                <td className="code">{pct(r.floor)}</td>
                <td className="code">{pct(r.best_dev)}</td>
                <td className="code" style={{ fontWeight: 700 }}>{unseen(r)}</td>
                <td className="code">{r.keeps} / {r.experiments}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

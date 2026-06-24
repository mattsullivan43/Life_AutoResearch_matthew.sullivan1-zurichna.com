// The persistent research notebook (results_<channel>.tsv) — every experiment ever
// tried for this channel, with its keep/discard verdict. This is the memory that
// makes the loop compound: it never repeats a banked failure.
export default function ResearchLog({ experiments }) {
  const exps = experiments || []
  const kept = exps.filter((e) => e.status === 'keep').length
  return (
    <div className="block">
      <div className="head">
        <h3>Research notebook</h3>
        <span className="sub">{exps.length} experiments · {kept} kept · persists across runs</span>
      </div>
      <div className="body">
        {exps.length === 0 ? (
          <div className="empty">No experiments yet — run the loop. Every attempt is logged here forever, so it never repeats a dead end.</div>
        ) : (
          <div className="preds-wrap">
            <table className="preds">
              <thead>
                <tr><th style={{ width: 40 }}>#</th><th style={{ width: 64 }}>dev</th><th style={{ width: 72 }}>unseen</th><th style={{ width: 84 }}>verdict</th><th>what it tried</th></tr>
              </thead>
              <tbody>
                {[...exps].reverse().map((e, i) => {
                  const dev = parseFloat(e.dev), test = parseFloat(e.test)
                  const cls = e.status === 'keep' ? 'ok' : e.status === 'final' ? 'final' : 'no'
                  return (
                    <tr key={i}>
                      <td className="code">{e.exp_id}</td>
                      <td className="code">{isNaN(dev) ? '—' : `${(dev * 100).toFixed(1)}%`}</td>
                      <td className="code">{test > 0 ? `${(test * 100).toFixed(1)}%` : '—'}</td>
                      <td><span className={'fchip ' + cls}>{e.status}</span></td>
                      <td className="snip">{e.description}</td>
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

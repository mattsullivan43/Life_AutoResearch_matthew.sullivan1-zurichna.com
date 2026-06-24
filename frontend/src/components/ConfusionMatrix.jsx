// Confusion matrix (true rows × predicted cols). Diagonal = correct.
export default function ConfusionMatrix({ confusion, title }) {
  if (!confusion || !confusion.labels) {
    return (
      <div className="block">
        <div className="head"><h3>Confusion matrix</h3></div>
        <div className="body"><div className="empty">No scores yet.</div></div>
      </div>
    )
  }
  const { labels, matrix } = confusion
  const max = Math.max(1, ...matrix.flat())
  const short = (l) => ({ CTRTCANCELPLAN: 'CANCEL', UWADDINFOCUST: 'UW-CUST', 'UWAI GP': 'UW-GP', 'SERV GEN': 'SERV', 'n/a': 'n/a' }[l] || l)
  const style = (n, diag) => {
    if (n === 0) return { background: '#fafbfe', color: '#cfd4e0' }
    const t = n / max
    const rgb = diag ? '10,125,77' : '1,39,150'
    return { background: `rgba(${rgb},${0.12 + 0.88 * t})`, color: t > 0.45 ? '#fff' : '#14161c' }
  }
  return (
    <div className="block">
      <div className="head"><h3>Confusion matrix</h3><span className="sub">{title || 'eval'}</span></div>
      <div className="body">
        <div className="cm-cap">rows = true · cols = predicted · diagonal = correct</div>
        <table className="cm">
          <thead>
            <tr><th></th>{labels.map((l) => <th key={l}>{short(l)}</th>)}</tr>
          </thead>
          <tbody>
            {matrix.map((row, i) => (
              <tr key={labels[i]}>
                <th className="rowlab">{short(labels[i])}</th>
                {row.map((n, j) => <td key={j} className="cell" style={style(n, i === j)}>{n}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="cm-note">Empty rows/cols = classes with no real test docs yet (CANCEL, UW-GP, n/a).</div>
      </div>
    </div>
  )
}

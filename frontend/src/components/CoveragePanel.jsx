export default function CoveragePanel({ coverage }) {
  if (!coverage) return null
  const max = Math.max(1, ...coverage.map((c) => c.real + c.synthetic))
  return (
    <div className="block coverage-block">
      <div className="head"><h3>Data coverage</h3><span className="sub">real = scored · synthetic = few-shot only</span></div>
      <div className="body cov-body">
        <div className="cov-list">
          {coverage.map((c) => (
            <div className="cov" key={c.category}>
              <div className={'name' + (c.missing_real ? ' miss' : '')}>{c.category}</div>
              <div className="bar">
                <div className="real" style={{ width: `${(c.real / max) * 100}%` }} />
                <div className="syn" style={{ width: `${(c.synthetic / max) * 100}%` }} />
              </div>
              <div className="cnt">{c.missing_real ? 'no real docs' : `${c.real} real`}{c.synthetic ? ` +${c.synthetic} syn` : ''}</div>
            </div>
          ))}
        </div>
        <div className="cov-legend">
          <span><i style={{ background: 'var(--blue)' }} />real</span>
          <span><i style={{ background: 'var(--gold)', opacity: .6 }} />synthetic</span>
        </div>
      </div>
    </div>
  )
}

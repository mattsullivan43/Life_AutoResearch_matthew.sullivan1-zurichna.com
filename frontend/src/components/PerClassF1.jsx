// Per-class F1 — bars fill the card height, colour-coded by score so weak
// classes are obvious (green = strong, blue = ok, amber = weak).
export default function PerClassF1({ perClass, title }) {
  const entries = perClass ? Object.entries(perClass) : []
  const colour = (f1) => (f1 >= 0.7 ? 'var(--good)' : f1 >= 0.5 ? 'var(--blue)' : 'var(--amber)')
  return (
    <div className="block perclass-block">
      <div className="head"><h3>Per-class F1</h3><span className="sub">{title || ''}</span></div>
      <div className="body pc-body">
        {entries.length === 0 ? (
          <div className="empty">No scores yet.</div>
        ) : (
          <div className="pc-list">
            {entries.map(([name, f1]) => (
              <div className="pc-row" key={name}>
                <div className="pc-name">{name}</div>
                <div className="pc-track"><div className="pc-fill" style={{ width: `${Math.round(f1 * 100)}%`, background: colour(f1) }} /></div>
                <div className="pc-val" style={{ color: colour(f1) }}>{(f1 * 100).toFixed(0)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

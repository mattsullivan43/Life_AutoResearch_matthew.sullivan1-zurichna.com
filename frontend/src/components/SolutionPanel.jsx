// The editable artifact (Karpathy's train.py). It is a small SOLUTION dict of KNOBS,
// never free-form code: classify channels tune instructions / shots_per_class /
// fewshot_seed; extract channels tune the extraction prompt. Each experiment changes ONE.
export default function SolutionPanel({ solution, task, status }) {
  const isClassify = task === 'classify' || (solution &&
    (solution.shots_per_class !== undefined || solution.fewshot_seed !== undefined))
  return (
    <div className="block">
      <div className="head">
        <h3>Solution · the editable artifact</h3>
        <span className="sub">{status || 'the knobs each experiment tunes (≙ train.py)'}</span>
      </div>
      <div className="body">
        {!solution ? (
          <div className="empty">Run the loop — the knobs the agent tunes will show here.</div>
        ) : isClassify ? (
          <>
            <div className="sol-knobs">
              <span className="solknob">shots_per_class = <b>{solution.shots_per_class ?? '—'}</b></span>
              <span className="solknob">fewshot_seed = <b>{solution.fewshot_seed ?? '—'}</b></span>
            </div>
            <div className="sol-label">instructions</div>
            <pre className="prompt">{solution.instructions}</pre>
          </>
        ) : (
          <>
            <div className="sol-label">instructions (extraction prompt)</div>
            <pre className="prompt">{solution.instructions}</pre>
          </>
        )}
      </div>
    </div>
  )
}

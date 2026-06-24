import {
  ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, Dot,
} from 'recharts'

function AcceptDot({ cx, cy, payload }) {
  if (!payload || cx == null || cy == null) return null
  if (payload.accepted) return <Dot cx={cx} cy={cy} r={5} fill="#0a7d4d" stroke="#fff" strokeWidth={1.5} />
  return <Dot cx={cx} cy={cy} r={3} fill="#012796" stroke="#fff" strokeWidth={1} />
}

const asPct = (v) => `${Math.round(v * 100)}%`

export default function ScoreChart({ data, baseline, metric = 'macro-F1' }) {
  const has = data && data.length > 0
  return (
    <div className="block">
      <div className="head">
        <h3>Score on the practice set · per round</h3>
        <span className="sub">solid = this round · dashed = best kept · ● adopted · {metric}</span>
      </div>
      <div className="body" style={{ height: 300 }}>
        {!has ? (
          <div className="empty">Run the loop — each point is a candidate prompt scored on the dev set.</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 16, right: 24, left: 8, bottom: 24 }}>
              <defs>
                <linearGradient id="fillBlue" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#012796" stopOpacity={0.10} />
                  <stop offset="100%" stopColor="#012796" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#efece4" vertical={false} />
              <XAxis
                dataKey="iter" type="number"
                domain={[0, 'dataMax']} allowDecimals={false}
                tick={{ fontSize: 11, fill: '#8a8678', fontFamily: 'var(--mono)' }}
                tickLine={false} axisLine={{ stroke: '#e8e4da' }} tickMargin={8}
                label={{ value: 'iteration', position: 'insideBottom', offset: -14, fontSize: 10.5, fill: '#a6a39a', letterSpacing: 1 }}
              />
              <YAxis
                domain={[0, 1.04]} ticks={[0, 0.25, 0.5, 0.75, 1]} width={44} allowDataOverflow
                tick={{ fontSize: 11, fill: '#8a8678', fontFamily: 'var(--mono)' }}
                tickLine={false} axisLine={false} tickFormatter={asPct} tickMargin={6}
              />
              <Tooltip
                formatter={(v, n) => [asPct(v), n === 'dev_mf1' ? 'candidate' : 'best kept']}
                labelFormatter={(l) => `iteration ${l}`}
                contentStyle={{ borderRadius: 8, border: '1px solid #e8e4da', fontSize: 12, boxShadow: '0 8px 24px -12px rgba(8,20,48,.25)' }}
              />
              {baseline != null && (
                <ReferenceLine y={baseline} stroke="#b89455" strokeDasharray="4 4"
                  label={{ value: `floor ${asPct(baseline)}`, position: 'insideBottomRight', fontSize: 10, fill: '#8a6d34' }} />
              )}
              <Area type="monotone" dataKey="dev_mf1" stroke="none" fill="url(#fillBlue)" isAnimationActive={false} />
              <Line type="monotone" dataKey="best_mf1" name="best kept" stroke="#bdb9ad"
                strokeWidth={1.5} strokeDasharray="5 3" dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="dev_mf1" name="dev_mf1" stroke="#012796"
                strokeWidth={2.5} dot={<AcceptDot />} activeDot={{ r: 5 }} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}

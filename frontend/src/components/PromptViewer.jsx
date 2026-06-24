import { useState, useEffect } from 'react'

function render(text) {
  if (!text) return null
  const parts = text.split('{FEWSHOT}')
  return parts.map((p, i) => (
    <span key={i}>{p}{i < parts.length - 1 && <span className="fewshot">{'{FEWSHOT}'}</span>}</span>
  ))
}

export default function PromptViewer({ seed, best, candidate }) {
  const [tab, setTab] = useState('best')
  // jump to the candidate tab whenever one is under review
  useEffect(() => { if (candidate) setTab('candidate') }, [candidate])
  const text = tab === 'best' ? best : tab === 'seed' ? seed : candidate
  return (
    <div className="block">
      <div className="head">
        <h3>Classifier prompt</h3>
        <div className="ptabs">
          {candidate && <button className={tab === 'candidate' ? 'on' : ''} style={{ color: tab === 'candidate' ? undefined : '#8a6d34' }} onClick={() => setTab('candidate')}>under review</button>}
          <button className={tab === 'best' ? 'on' : ''} onClick={() => setTab('best')}>optimized</button>
          <button className={tab === 'seed' ? 'on' : ''} onClick={() => setTab('seed')}>seed</button>
        </div>
      </div>
      <div className="body">
        {text ? <pre className="prompt">{render(text)}</pre>
              : <div className="empty">{tab === 'best' ? 'No optimized prompt yet — run the loop.' : tab === 'candidate' ? 'No candidate under review.' : 'Seed prompt not loaded.'}</div>}
      </div>
    </div>
  )
}

import { useState } from 'react'
import { login } from '../auth'

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setErr(''); setBusy(true)
    try { await login(email.trim(), password); onLogin() }
    catch (e) { setErr(e.message || 'Sign-in failed'); setBusy(false) }
  }

  return (
    <div className="login-wrap">
      <div className="brandstripe" />
      <form className="login-card" onSubmit={submit}>
        <img className="login-logo" src="/zurich-mark.png" alt="Zurich" />
        <h1>Auto-Research <em>Engine</em></h1>
        <p className="login-sub">Sign in to continue</p>
        <label>Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus required />
        </label>
        <label>Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {err && <div className="login-err">{err}</div>}
        <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  )
}

// Cognito auth for the SPA. Config is fetched at runtime from /api/auth_config
// so the same build works in any environment.
import { CognitoUserPool, CognitoUser, AuthenticationDetails } from 'amazon-cognito-identity-js'

let _cfg = null
export async function authConfig() {
  if (_cfg) return _cfg
  try { _cfg = await (await fetch('/api/auth_config')).json() }
  catch { _cfg = { enabled: false } }
  return _cfg
}

function pool(c) { return new CognitoUserPool({ UserPoolId: c.userPoolId, ClientId: c.clientId }) }

export function getToken() { return localStorage.getItem('access_token') || '' }
export function logout() { localStorage.removeItem('access_token') }

export async function login(email, password) {
  const c = await authConfig()
  const user = new CognitoUser({ Username: email, Pool: pool(c) })
  user.setAuthenticationFlowType('USER_PASSWORD_AUTH')
  const details = new AuthenticationDetails({ Username: email, Password: password })
  return new Promise((resolve, reject) => {
    user.authenticateUser(details, {
      onSuccess: (s) => { localStorage.setItem('access_token', s.getAccessToken().getJwtToken()); resolve(true) },
      onFailure: (e) => reject(e),
      newPasswordRequired: () => reject(new Error('Password reset required — contact the admin.')),
    })
  })
}

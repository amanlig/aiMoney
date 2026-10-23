import {html, useState, useEffect} from './ui.js';
import {api} from './api.js';

function SignIn() {
  const [email, setEmail] = useState(''), [challenge, setChallenge] = useState(null);
  const [code, setCode] = useState(''), [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  async function submit(event) {
    event.preventDefault(); setBusy(true); setMessage('');
    try {
      if (!challenge) {
        const data = await api('/api/auth/request-code', {body: {email}});
        setChallenge(data.challenge_id); setMessage(data.message);
      } else {
        await api('/api/auth/verify', {body: {challenge_id: challenge, code, remember}});
        location.replace('/covered-call-optimizer');
      }
    } catch (error) {setMessage(error.message);}
    finally {setBusy(false);}
  }
  return html`<main className="signin-page"><section className="signin-card" aria-labelledby="signin-title">
    <p className="signin-brand">aiMoney</p><h1 id="signin-title">Sign in</h1>
    <p>${challenge ? `Enter the 8-digit code sent to ${email}.` : 'Use your authorized email to access your portfolio.'}</p>
    <form onSubmit=${submit}>
      ${!challenge ? html`<label>Email address<input type="email" name="email" autoComplete="email" required maxLength="254" value=${email} onInput=${e => setEmail(e.target.value)} disabled=${busy}/></label>`
        : html`<label>Sign-in code<input key=${challenge} type="text" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{8}" minLength="8" maxLength="8" required autoFocus value=${code} onInput=${e => setCode(e.target.value.replace(/[^0-9]/g, ''))} disabled=${busy}/></label>
          <label className="remember-device"><input type="checkbox" checked=${remember} onChange=${e => setRemember(e.target.checked)} disabled=${busy}/>Remember this device for 30 days</label>
          <p className="muted">Use this option only on a personal device.</p>`}
      <button className="primary" type="submit" disabled=${busy}>${busy ? 'Please wait…' : challenge ? 'Verify & sign in' : 'Send sign-in code'}</button>
    </form>
    <p role="status" aria-live="polite">${message}</p>
    ${challenge && html`<button type="button" className="signin-back" disabled=${busy} onClick=${() => {setChallenge(null); setCode(''); setMessage('');}}>Change email or request a new code</button>`}
    <p className="muted">Access is by invitation. There is no public registration.</p>
  </section></main>`;
}

export function AuthGate({children}) {
  const [session, setSession] = useState(null), [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    api('/api/auth/session', {signal: controller.signal}).then(data => {
      if (data.enabled && location.pathname === '/signin') location.replace('/covered-call-optimizer');
      else setSession(data);
    }).catch(e => {
      if (e.name === 'AbortError') return;
      if (e.status === 401) {
        if (location.pathname !== '/signin') location.replace('/signin');
        else setSession({enabled: true, signedOut: true});
      } else setError('Sign-in is temporarily unavailable. Please reload and try again.');
    });
    return () => controller.abort();
  }, []);
  async function logout() {
    try {await api('/api/auth/logout', {body: {}}); location.replace('/signin');}
    catch (e) {setError(e.message);}
  }
  if (error) return html`<main className="signin-page"><p role="alert">${error}</p><a href="/signin">Try again</a></main>`;
  if (!session) return html`<main className="signin-page"><p role="status">Checking sign-in…</p></main>`;
  if (session.signedOut) return html`<${SignIn}/>`;
  if (!session.enabled) return children;
  return html`<div className="authenticated-app"><div className="account-bar"><span>${session.email}</span><button type="button" onClick=${logout}>Sign out</button></div>${children}</div>`;
}

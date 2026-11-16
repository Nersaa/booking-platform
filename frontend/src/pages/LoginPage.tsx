import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { useAuth } from '../auth'

export default function LoginPage() {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()

  const [isNewUser, setIsNewUser] = useState(false)
  const [firstName, setFirstName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isSending, setIsSending] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setIsSending(true)
    try {
      if (isNewUser) await register(firstName, email, password)
      else await login(email, password)
      navigate(params.get('next') ?? '/')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Something went wrong.')
    } finally {
      setIsSending(false)
    }
  }

  return (
    <main className="page narrow">
      <h1>{isNewUser ? 'Create an account' : 'Log in'}</h1>
      <form className="form" onSubmit={submit}>
        {isNewUser && (
          <label>
            First name
            <input value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
          </label>
        )}
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={isNewUser ? 'new-password' : 'current-password'}
            minLength={isNewUser ? 8 : undefined}
            required
          />
        </label>
        {error && <p className="notice notice-error">{error}</p>}
        <button className="primary" disabled={isSending}>
          {isNewUser ? 'Create account' : 'Log in'}
        </button>
      </form>
      <button className="link-button" onClick={() => setIsNewUser(!isNewUser)}>
        {isNewUser ? 'I already have an account' : 'I am new here: create an account'}
      </button>
    </main>
  )
}

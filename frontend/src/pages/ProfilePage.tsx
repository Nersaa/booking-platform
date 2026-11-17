import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'

import { api, setTokens, type Tokens } from '../api/client'
import type { User } from '../api/types'
import { useAuth } from '../auth'

export default function ProfilePage() {
  const { user, isLoggedIn, logout } = useAuth()

  if (!isLoggedIn) return <Navigate to="/login?next=/profile" replace />
  if (!user) return <p className="page notice">Loading…</p>

  return (
    <main className="page narrow">
      <h1>Profile</h1>
      <p className="muted">{user.email}</p>
      {/* A new key gives the form fresh values once the profile is saved. */}
      <NameForm key={`${user.first_name}|${user.last_name}`} user={user} />
      <PasswordForm />
      <HostSection user={user} />
      <h2>Session</h2>
      <button onClick={logout}>Log out</button>
    </main>
  )
}

function NameForm({ user }: { user: User }) {
  const queryClient = useQueryClient()
  const [firstName, setFirstName] = useState(user.first_name)
  const [lastName, setLastName] = useState(user.last_name)

  const save = useMutation({
    mutationFn: () =>
      api<User>('/api/v1/users/me', {
        method: 'PATCH',
        body: { first_name: firstName, last_name: lastName },
      }),
    onSuccess: (updated) => queryClient.setQueryData(['me'], updated),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    save.mutate()
  }

  return (
    <form className="form" onSubmit={submit}>
      <h2>Your name</h2>
      <label>
        First name
        <input value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
      </label>
      <label>
        Last name
        <input value={lastName} onChange={(e) => setLastName(e.target.value)} />
      </label>
      {save.error && <p className="notice notice-error">{save.error.message}</p>}
      {save.isSuccess && <p className="notice">Saved.</p>}
      <button className="primary" disabled={save.isPending}>
        Save name
      </button>
    </form>
  )
}

function PasswordForm() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')

  const change = useMutation({
    mutationFn: () =>
      api('/api/v1/users/me/password', {
        method: 'POST',
        body: { current_password: current, new_password: next },
      }),
    onSuccess: () => {
      setCurrent('')
      setNext('')
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    change.mutate()
  }

  return (
    <form className="form" onSubmit={submit}>
      <h2>Password</h2>
      <label>
        Current password
        <input
          type="password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          autoComplete="current-password"
          required
        />
      </label>
      <label>
        New password
        <input
          type="password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          autoComplete="new-password"
          minLength={8}
          required
        />
      </label>
      {change.error && <p className="notice notice-error">{change.error.message}</p>}
      {change.isSuccess && <p className="notice">Password changed.</p>}
      <button className="primary" disabled={change.isPending}>
        Change password
      </button>
    </form>
  )
}

function HostSection({ user }: { user: User }) {
  const queryClient = useQueryClient()

  const becomeHost = useMutation({
    // The answer carries new tokens that already include the host role.
    mutationFn: () => api<Tokens & { user: User }>('/api/v1/users/me/host', { method: 'POST' }),
    onSuccess: ({ access, refresh, user: updated }) => {
      setTokens({ access, refresh })
      queryClient.setQueryData(['me'], updated)
    },
  })

  return (
    <section>
      <h2>Hosting</h2>
      {user.is_host ? (
        <p>You are a host. Guests' bookings of your places are under Hosting.</p>
      ) : (
        <>
          <p className="muted">Have a place to rent out? Become a host to publish listings.</p>
          {becomeHost.error && <p className="notice notice-error">{becomeHost.error.message}</p>}
          <button disabled={becomeHost.isPending} onClick={() => becomeHost.mutate()}>
            Become a host
          </button>
        </>
      )}
    </section>
  )
}

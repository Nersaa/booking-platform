import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { TicketDetail, TicketStatus } from '../api/types'
import { useAuth } from '../auth'
import { shortDate, time } from '../format'

export const STATUS_LABELS: Record<TicketStatus, string> = {
  open: 'Waiting for support',
  answered: 'Answered',
  closed: 'Closed',
}

export default function TicketPage() {
  const { id = '' } = useParams()
  const { isLoggedIn } = useAuth()
  const queryClient = useQueryClient()
  const [text, setText] = useState('')

  const ticket = useQuery({
    queryKey: ['ticket', id],
    queryFn: () => api<TicketDetail>(`/api/v1/support/tickets/${id}`),
    enabled: isLoggedIn,
    // Support answers from the admin; while it's their turn, look for a reply now and then.
    refetchInterval: (query) => (query.state.data?.status === 'open' ? 15_000 : false),
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['ticket', id] })
    queryClient.invalidateQueries({ queryKey: ['tickets'] })
  }

  const reply = useMutation({
    mutationFn: () =>
      api(`/api/v1/support/tickets/${id}/messages`, { method: 'POST', body: { text } }),
    onSuccess: () => {
      setText('')
      refresh()
    },
  })

  const close = useMutation({
    mutationFn: () => api(`/api/v1/support/tickets/${id}/close`, { method: 'POST' }),
    onSuccess: refresh,
  })

  if (!isLoggedIn) return <Navigate to={`/login?next=/support/${id}`} replace />
  if (ticket.isPending) return <p className="page notice">Loading…</p>
  if (ticket.error) return <p className="page notice notice-error">{ticket.error.message}</p>

  const { subject, status, messages, booking_id: bookingId } = ticket.data
  const isClosed = status === 'closed'

  function submit(event: FormEvent) {
    event.preventDefault()
    reply.mutate()
  }

  return (
    <main className="page narrow-wide">
      <p>
        <Link to="/support">All requests</Link>
      </p>
      <h1>{subject}</h1>
      <p className={`status status-${status}`}>{STATUS_LABELS[status]}</p>
      {bookingId && (
        <p className="muted small">
          About booking <Link to="/bookings">{bookingId.slice(0, 8)}</Link>
        </p>
      )}

      <ol className="messages">
        {messages.map((message) => (
          <li key={message.id} className={message.from_support ? 'message from-other' : 'message'}>
            <p className="message-meta">
              <strong>{message.from_support ? `Support, ${message.author_name}` : 'You'}</strong>{' '}
              <span className="muted">
                {shortDate(message.created_at)}, {time(message.created_at)}
              </span>
            </p>
            <p className="message-text">{message.text}</p>
          </li>
        ))}
      </ol>

      {isClosed ? (
        <p className="notice">
          This request is closed. <Link to="/support">Open a new one</Link> if you need more help.
        </p>
      ) : (
        <form className="form" onSubmit={submit}>
          <label>
            Your message
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} required />
          </label>
          {(reply.error ?? close.error) && (
            <p className="notice notice-error">{(reply.error ?? close.error)?.message}</p>
          )}
          <div className="form-actions">
            <button className="primary" disabled={reply.isPending}>
              Send
            </button>
            <button type="button" disabled={close.isPending} onClick={() => close.mutate()}>
              My problem is solved, close the request
            </button>
          </div>
        </form>
      )}
    </main>
  )
}

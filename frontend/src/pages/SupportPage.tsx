import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import type { Booking, DrfPage, Page, Ticket, TicketDetail } from '../api/types'
import { useAuth } from '../auth'
import { shortDate } from '../format'
import { STATUS_LABELS } from './TicketPage'

const TOPICS: Record<string, string> = {
  booking: 'A booking',
  payment: 'Payment or refund',
  listing: 'My listing (for hosts)',
  account: 'My account',
  other: 'Something else',
}

export default function SupportPage() {
  const { isLoggedIn } = useAuth()
  const tickets = useQuery({
    queryKey: ['tickets'],
    queryFn: () => api<DrfPage<Ticket>>('/api/v1/support/tickets'),
    enabled: isLoggedIn,
  })

  if (!isLoggedIn) return <Navigate to="/login?next=/support" replace />

  return (
    <main className="page narrow-wide">
      <h1>Help</h1>
      <p className="muted">
        Write to us about a booking, a payment or your account. We answer here and by email.
      </p>

      <NewTicketForm />

      <h2>Your requests</h2>
      {tickets.isPending && <p className="notice">Loading…</p>}
      {tickets.error && <p className="notice notice-error">{tickets.error.message}</p>}
      {tickets.data?.count === 0 && <p className="muted">No requests yet.</p>}
      <ul className="tickets">
        {tickets.data?.results.map((ticket) => (
          <li key={ticket.id}>
            <Link to={`/support/${ticket.id}`} className="ticket-row">
              <span className="ticket-subject">{ticket.subject}</span>
              <span className={`status status-${ticket.status}`}>
                {STATUS_LABELS[ticket.status]}
              </span>
              <span className="muted small">{shortDate(ticket.updated_at)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  )
}

function NewTicketForm() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [topic, setTopic] = useState('booking')
  const [bookingId, setBookingId] = useState('')
  const [subject, setSubject] = useState('')
  const [text, setText] = useState('')

  // So the user can say which booking the question is about.
  const bookings = useQuery({
    queryKey: ['bookings'],
    queryFn: () => api<Page<Booking>>('/api/v1/bookings', { params: { limit: 50 } }),
  })

  const send = useMutation({
    mutationFn: () =>
      api<TicketDetail>('/api/v1/support/tickets', {
        method: 'POST',
        body: { topic, subject, text, booking_id: bookingId || null },
      }),
    onSuccess: (ticket) => {
      queryClient.invalidateQueries({ queryKey: ['tickets'] })
      navigate(`/support/${ticket.id}`)
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    send.mutate()
  }

  return (
    <form className="form support-form" onSubmit={submit}>
      <div className="form-row">
        <label>
          Topic
          <select value={topic} onChange={(e) => setTopic(e.target.value)}>
            {Object.entries(TOPICS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Booking
          <select value={bookingId} onChange={(e) => setBookingId(e.target.value)}>
            <option value="">Not about a booking</option>
            {bookings.data?.items.map((booking) => (
              <option key={booking.id} value={booking.id}>
                {shortDate(booking.check_in)} to {shortDate(booking.check_out)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Subject
        <input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={150} required />
      </label>
      <label>
        Message
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} required />
      </label>
      {send.error && <p className="notice notice-error">{send.error.message}</p>}
      <button className="primary" disabled={send.isPending}>
        Send request
      </button>
    </form>
  )
}

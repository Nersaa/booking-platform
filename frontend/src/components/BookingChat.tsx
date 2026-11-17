import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { api } from '../api/client'
import type { BookingMessage } from '../api/types'
import { shortDate, time } from '../format'

type Props = { bookingId: string; asHost: boolean }

// Messages between the guest and the host about one booking.
export default function BookingChat({ bookingId, asHost }: Props) {
  const queryClient = useQueryClient()
  const [text, setText] = useState('')
  const url = asHost
    ? `/api/v1/host/bookings/${bookingId}/messages`
    : `/api/v1/bookings/${bookingId}/messages`

  const messages = useQuery({
    queryKey: ['booking-messages', bookingId],
    queryFn: () => api<BookingMessage[]>(url),
    refetchInterval: 10_000, // simple polling: the other side may answer any time
  })

  const send = useMutation({
    mutationFn: () => api<BookingMessage>(url, { method: 'POST', body: { text } }),
    onSuccess: () => {
      setText('')
      queryClient.invalidateQueries({ queryKey: ['booking-messages', bookingId] })
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    send.mutate()
  }

  const other = asHost ? 'the guest' : 'the host'
  return (
    <section className="chat">
      <h2>Messages with {other}</h2>
      {messages.data?.length === 0 && (
        <p className="muted">
          {asHost
            ? 'No messages yet.'
            : 'Questions about check-in, parking or anything else? Ask the host here.'}
        </p>
      )}
      <ol className="messages">
        {messages.data?.map((message) => {
          const mine = message.from_host === asHost
          return (
            <li key={message.id} className={mine ? 'message' : 'message from-other'}>
              <p className="message-meta">
                <strong>{mine ? 'You' : asHost ? 'Guest' : 'Host'}</strong>{' '}
                <span className="muted">
                  {shortDate(message.created_at)}, {time(message.created_at)}
                </span>
              </p>
              <p className="message-text">{message.text}</p>
            </li>
          )
        })}
      </ol>
      <form className="form" onSubmit={submit}>
        <label>
          Write to {other}
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} required />
        </label>
        {send.error && <p className="notice notice-error">{send.error.message}</p>}
        <div className="form-actions">
          <button className="primary" disabled={send.isPending}>
            Send
          </button>
        </div>
      </form>
    </section>
  )
}

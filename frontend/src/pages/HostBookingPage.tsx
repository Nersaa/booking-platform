import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Booking, Listing } from '../api/types'
import { useAuth } from '../auth'
import BookingChat from '../components/BookingChat'
import { dateTime, money, plural, shortDate } from '../format'
import { STATUS_LABELS } from './BookingsPage'

// One booking of the host's place: the stay, the money and the conversation with the guest.
export default function HostBookingPage() {
  const { id = '' } = useParams()
  const { isLoggedIn } = useAuth()
  const queryClient = useQueryClient()

  const booking = useQuery({
    queryKey: ['host-booking', id],
    queryFn: () => api<Booking>(`/api/v1/host/bookings/${id}`),
    enabled: isLoggedIn,
  })
  const listingId = booking.data?.listing_id
  const listing = useQuery({
    queryKey: ['listing', listingId],
    queryFn: () => api<Listing>(`/api/v1/listings/${listingId}`),
    enabled: listingId !== undefined,
  })

  const updated = (data: Booking) => {
    queryClient.setQueryData(['host-booking', id], data)
    queryClient.invalidateQueries({ queryKey: ['host-bookings'] })
  }
  const answer = useMutation({
    mutationFn: ({ action, reason }: { action: 'accept' | 'decline'; reason?: string }) =>
      api<Booking>(`/api/v1/host/bookings/${id}/${action}`, {
        method: 'POST',
        body: action === 'decline' ? { reason } : undefined,
      }),
    onSuccess: updated,
  })

  const cancel = useMutation({
    mutationFn: () =>
      api<Booking>(`/api/v1/host/bookings/${id}/cancel`, { method: 'POST', body: {} }),
    onSuccess: updated,
  })

  function decline() {
    const reason = window.prompt('Decline this request? You can tell the guest why (optional).')
    if (reason !== null) answer.mutate({ action: 'decline', reason })
  }

  if (!isLoggedIn) return <Navigate to={`/login?next=/hosting/${id}`} replace />
  if (booking.isPending) return <p className="page notice">Loading…</p>
  if (booking.error) return <p className="page notice notice-error">{booking.error.message}</p>

  const b = booking.data
  const nights = Math.round(
    (new Date(b.check_out).getTime() - new Date(b.check_in).getTime()) / 86_400_000,
  )
  const canCancel = b.status === 'pending_payment' || b.status === 'confirmed'

  return (
    <main className="page narrow-wide">
      <p>
        <Link to="/hosting">All bookings</Link>
      </p>
      <h1>{listing.data?.title ?? 'Booking'}</h1>
      <p className={`status status-${b.status}`}>{STATUS_LABELS[b.status]}</p>
      <p>
        {shortDate(b.check_in)} to {shortDate(b.check_out)}, {plural(nights, 'night')},{' '}
        {plural(b.guests, 'guest')}. Total {money(b.total, b.currency)}.
      </p>
      {b.status === 'awaiting_host' && (
        <section className="status-panel">
          <div>
            <h2>The guest asks to book</h2>
            <p>
              Answer by{' '}
              {b.hold_expires_at && <strong>{dateTime(b.hold_expires_at)}</strong>}, or the
              request expires and the dates are free again. After you accept, the guest has a
              day to pay.
            </p>
          </div>
          <div className="form-actions">
            <button
              className="primary"
              disabled={answer.isPending}
              onClick={() => answer.mutate({ action: 'accept' })}
            >
              Accept
            </button>
            <button disabled={answer.isPending} onClick={decline}>
              Decline
            </button>
          </div>
        </section>
      )}
      {answer.error && <p className="notice notice-error">{answer.error.message}</p>}
      {canCancel && (
        <p>
          <button
            disabled={cancel.isPending}
            onClick={() =>
              window.confirm('Cancel this booking? The guest gets a full refund.') && cancel.mutate()
            }
          >
            Cancel booking
          </button>
        </p>
      )}
      {cancel.error && <p className="notice notice-error">{cancel.error.message}</p>}
      <BookingChat bookingId={b.id} asHost />
    </main>
  )
}

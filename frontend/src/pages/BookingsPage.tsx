import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate } from 'react-router-dom'

import { api } from '../api/client'
import type { Booking, BookingStatus, Listing, Page, Payment } from '../api/types'
import { useAuth } from '../auth'
import { money, plural, shortDate, time } from '../format'

const STATUS_LABELS: Record<BookingStatus, string> = {
  pending_payment: 'Waiting for payment',
  confirmed: 'Confirmed',
  cancelled: 'Cancelled',
  expired: 'Expired: not paid in time',
  completed: 'Completed',
}

export default function BookingsPage() {
  const { isLoggedIn } = useAuth()

  const bookings = useQuery({
    queryKey: ['bookings'],
    queryFn: () => api<Page<Booking>>('/api/v1/bookings', { params: { limit: 50 } }),
    enabled: isLoggedIn,
    // The payment result arrives at the backend as a webhook, so while something is
    // unpaid the list is re-read every 3 seconds to show the confirmation.
    refetchInterval: (query) =>
      query.state.data?.items.some((b) => b.status === 'pending_payment') ? 3000 : false,
  })

  if (!isLoggedIn) return <Navigate to="/login?next=/bookings" replace />

  return (
    <main className="page narrow-wide">
      <h1>My bookings</h1>
      {bookings.isPending && <p className="notice">Loading…</p>}
      {bookings.error && <p className="notice notice-error">{bookings.error.message}</p>}
      {bookings.data?.total === 0 && (
        <p className="notice">
          Nothing booked yet. <Link to="/">Find a place to stay.</Link>
        </p>
      )}
      {bookings.data?.items.map((booking) => (
        <BookingCard key={booking.id} booking={booking} />
      ))}
    </main>
  )
}

function BookingCard({ booking }: { booking: Booking }) {
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['bookings'] })

  // A booking only stores the listing id; the title comes from the Catalog service.
  const listing = useQuery({
    queryKey: ['listing', booking.listing_id],
    queryFn: () => api<Listing>(`/api/v1/listings/${booking.listing_id}`),
  })

  const pay = useMutation({
    mutationFn: async () => {
      // Opened right on the click, before the request: browsers block tabs opened later.
      const tab = window.open('', '_blank')
      try {
        const payment = await api<Payment>(`/api/v1/bookings/${booking.id}/payments`, {
          method: 'POST',
        })
        if (tab) tab.location.href = payment.checkout_url
        else window.location.href = payment.checkout_url
      } catch (error) {
        tab?.close()
        throw error
      }
    },
    onSettled: refresh,
  })

  const cancel = useMutation({
    mutationFn: () =>
      api<Booking>(`/api/v1/bookings/${booking.id}/cancel`, { method: 'POST', body: {} }),
    onSettled: refresh,
  })

  const nights = Math.round(
    (new Date(booking.check_out).getTime() - new Date(booking.check_in).getTime()) / 86_400_000,
  )
  const isPending = booking.status === 'pending_payment'
  const canCancel = isPending || booking.status === 'confirmed'
  const error = pay.error ?? cancel.error

  return (
    <article className="booking">
      <div>
        <h2>
          <Link to={`/listings/${booking.listing_id}`}>{listing.data?.title ?? 'Listing'}</Link>
        </h2>
        <p>
          {shortDate(booking.check_in)} to {shortDate(booking.check_out)}, {plural(nights, 'night')},{' '}
          {plural(booking.guests, 'guest')}
        </p>
        <p className={`status status-${booking.status}`}>{STATUS_LABELS[booking.status]}</p>
        {isPending && booking.hold_expires_at && (
          <p className="muted small">The dates are held until {time(booking.hold_expires_at)}.</p>
        )}
        {booking.refund_amount > 0 && (
          <p className="muted small">Refunded {money(booking.refund_amount, booking.currency)}.</p>
        )}
        {error && <p className="notice notice-error">{error.message}</p>}
      </div>
      <div className="booking-actions">
        <strong>{money(booking.total, booking.currency)}</strong>
        {isPending && (
          <button className="primary" disabled={pay.isPending} onClick={() => pay.mutate()}>
            Pay
          </button>
        )}
        {canCancel && (
          <button
            disabled={cancel.isPending}
            onClick={() => window.confirm('Cancel this booking?') && cancel.mutate()}
          >
            Cancel booking
          </button>
        )}
      </div>
    </article>
  )
}

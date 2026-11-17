import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Booking, Listing, Payment } from '../api/types'
import { useAuth } from '../auth'
import BookingChat from '../components/BookingChat'
import Cover from '../components/Cover'
import ReviewForm from '../components/ReviewForm'
import { money, plural } from '../format'

// One booking: what was booked, what it costs, and the next step (pay, wait, or nothing).
export default function BookingPage() {
  const { id = '' } = useParams()
  const { isLoggedIn } = useAuth()
  const queryClient = useQueryClient()

  const booking = useQuery({
    queryKey: ['booking', id],
    queryFn: () => api<Booking>(`/api/v1/bookings/${id}`),
    enabled: isLoggedIn,
    // The payment result reaches the backend as a webhook, not through this page, so
    // while the booking waits for payment the page checks back every 2 seconds.
    refetchInterval: (query) => (query.state.data?.status === 'pending_payment' ? 2000 : false),
  })
  const listingId = booking.data?.listing_id
  const listing = useQuery({
    queryKey: ['listing', listingId],
    queryFn: () => api<Listing>(`/api/v1/listings/${listingId}`),
    enabled: listingId !== undefined,
  })

  const pay = useMutation({
    mutationFn: () => api<Payment>(`/api/v1/bookings/${id}/payments`, { method: 'POST' }),
    // The provider's page sends the guest back here when the payment is done.
    onSuccess: (payment) => window.location.assign(payment.checkout_url),
  })

  const cancel = useMutation({
    mutationFn: () => api<Booking>(`/api/v1/bookings/${id}/cancel`, { method: 'POST', body: {} }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['booking', id], updated)
      queryClient.invalidateQueries({ queryKey: ['bookings'] })
    },
  })

  if (!isLoggedIn) return <Navigate to={`/login?next=/bookings/${id}`} replace />
  if (booking.isPending) return <p className="page notice">Loading…</p>
  if (booking.error) return <p className="page notice notice-error">{booking.error.message}</p>

  const b = booking.data
  const nights = daysBetween(b.check_in, b.check_out)
  const canCancel = b.status === 'pending_payment' || b.status === 'confirmed'
  const error = pay.error ?? cancel.error

  return (
    <main className="page booking-page">
      <p>
        <Link to="/bookings">My bookings</Link>
      </p>

      <StatusPanel
        booking={b}
        listingId={b.listing_id}
        isPaying={pay.isPending}
        onPay={() => pay.mutate()}
      />
      {error && <p className="notice notice-error">{error.message}</p>}
      {b.status === 'completed' && <ReviewForm bookingId={b.id} listingId={b.listing_id} />}

      <div className="booking-layout">
        <section className="trip">
          <Cover
            url={listing.data?.photos[0]?.large_url}
            propertyType={listing.data?.property_type ?? 'apartment'}
            className="trip-cover"
          />
          <h1>
            <Link to={`/listings/${b.listing_id}`}>{listing.data?.title ?? 'Your stay'}</Link>
          </h1>
          {listing.data && (
            <p className="muted">
              {listing.data.city}, {listing.data.country}. Hosted by {listing.data.host.first_name}.
            </p>
          )}
          <dl className="trip-dates">
            <div>
              <dt>Check-in</dt>
              <dd>{longDate(b.check_in)}</dd>
            </div>
            <div>
              <dt>Check-out</dt>
              <dd>{longDate(b.check_out)}</dd>
            </div>
            <div>
              <dt>Guests</dt>
              <dd>{b.guests}</dd>
            </div>
          </dl>
          <BookingChat bookingId={b.id} asHost={false} />
        </section>

        <aside className="booking-box">
          <h2>Price</h2>
          <dl className="quote">
            <dt>{plural(nights, 'night')}</dt>
            <dd>{money(b.subtotal, b.currency)}</dd>
            {b.discount > 0 && (
              <>
                <dt>Long stay discount</dt>
                <dd>−{money(b.discount, b.currency)}</dd>
              </>
            )}
            <dt>Cleaning</dt>
            <dd>{money(b.cleaning_fee, b.currency)}</dd>
            <dt className="quote-total">Total</dt>
            <dd className="quote-total">{money(b.total, b.currency)}</dd>
            {b.refund_amount > 0 && (
              <>
                <dt>Refunded</dt>
                <dd>{money(b.refund_amount, b.currency)}</dd>
              </>
            )}
          </dl>
          {canCancel && (
            <>
              <p className="muted small">
                Free cancellation up to 7 days before check-in, half refund until the day
                before, no refund on the day.
              </p>
              <button
                disabled={cancel.isPending}
                onClick={() => window.confirm('Cancel this booking?') && cancel.mutate()}
              >
                Cancel booking
              </button>
            </>
          )}
        </aside>
      </div>
    </main>
  )
}

type StatusProps = {
  booking: Booking
  listingId: string
  isPaying: boolean
  onPay: () => void
}

function StatusPanel({ booking, listingId, isPaying, onPay }: StatusProps) {
  const total = money(booking.total, booking.currency)

  switch (booking.status) {
    case 'pending_payment':
      return (
        <section className="status-panel status-panel-pay">
          <div>
            <h2>Pay to confirm your stay</h2>
            <p>
              The dates are held for you for{' '}
              {booking.hold_expires_at && <Countdown until={booking.hold_expires_at} />}. After
              that they are released.
            </p>
          </div>
          <button className="primary pay-button" disabled={isPaying} onClick={onPay}>
            {isPaying ? 'Opening payment…' : `Pay ${total}`}
          </button>
        </section>
      )
    case 'confirmed':
      return (
        <section className="status-panel status-panel-ok">
          <h2>Your stay is confirmed</h2>
          <p>We received {total}. The details are in your email.</p>
        </section>
      )
    case 'completed':
      return (
        <section className="status-panel">
          <h2>Hope you enjoyed your stay</h2>
          <p>This trip is over.</p>
        </section>
      )
    case 'expired':
      return (
        <section className="status-panel">
          <h2>The hold ran out</h2>
          <p>
            The booking was not paid in time, so the dates were released.{' '}
            <Link to={`/listings/${listingId}`}>Book again</Link> if they are still free.
          </p>
        </section>
      )
    case 'cancelled':
      return (
        <section className="status-panel">
          <h2>Cancelled{booking.cancelled_by === 'host' ? ' by the host' : ''}</h2>
          <p>
            {booking.refund_amount > 0
              ? `${money(booking.refund_amount, booking.currency)} is on its way back to your card.`
              : 'No payment was taken or no refund was due.'}
          </p>
        </section>
      )
  }
}

// "12:34", counting down every second.
function Countdown({ until }: { until: string }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const seconds = Math.max(0, Math.floor((new Date(until).getTime() - now) / 1000))
  const text = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
  return <strong className="countdown">{text}</strong>
}

function daysBetween(from: string, to: string): number {
  return Math.round((new Date(to).getTime() - new Date(from).getTime()) / 86_400_000)
}

function longDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString('en', {
    weekday: 'short',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

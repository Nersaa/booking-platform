import { useQuery } from '@tanstack/react-query'
import { Link, Navigate } from 'react-router-dom'

import { api } from '../api/client'
import type { Booking, BookingStatus, Listing, Page } from '../api/types'
import { useAuth } from '../auth'
import { money, plural, shortDate } from '../format'

export const STATUS_LABELS: Record<BookingStatus, string> = {
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
        <BookingRow key={booking.id} booking={booking} />
      ))}
    </main>
  )
}

function BookingRow({ booking }: { booking: Booking }) {
  // A booking only stores the listing id; the title comes from the Catalog service.
  const listing = useQuery({
    queryKey: ['listing', booking.listing_id],
    queryFn: () => api<Listing>(`/api/v1/listings/${booking.listing_id}`),
  })
  const nights = Math.round(
    (new Date(booking.check_out).getTime() - new Date(booking.check_in).getTime()) / 86_400_000,
  )

  return (
    <Link to={`/bookings/${booking.id}`} className="booking">
      <div>
        <h2>{listing.data?.title ?? 'Your stay'}</h2>
        <p>
          {shortDate(booking.check_in)} to {shortDate(booking.check_out)}, {plural(nights, 'night')},{' '}
          {plural(booking.guests, 'guest')}
        </p>
        <p className={`status status-${booking.status}`}>{STATUS_LABELS[booking.status]}</p>
      </div>
      <strong className="booking-total">{money(booking.total, booking.currency)}</strong>
    </Link>
  )
}

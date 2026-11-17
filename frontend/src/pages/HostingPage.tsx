import { useQuery } from '@tanstack/react-query'
import { Link, Navigate } from 'react-router-dom'

import { api } from '../api/client'
import type { Booking, Listing, Page } from '../api/types'
import { useAuth } from '../auth'
import { money, plural, shortDate } from '../format'
import { STATUS_LABELS } from './BookingsPage'

// For hosts: guests' bookings of their places, by check-in date.
export default function HostingPage() {
  const { user, isLoggedIn } = useAuth()

  const bookings = useQuery({
    queryKey: ['host-bookings'],
    queryFn: () => api<Page<Booking>>('/api/v1/host/bookings', { params: { limit: 50 } }),
    enabled: user?.is_host === true,
  })

  if (!isLoggedIn) return <Navigate to="/login?next=/hosting" replace />
  if (user && !user.is_host) return <Navigate to="/profile" replace />

  return (
    <main className="page narrow-wide">
      <h1>Hosting</h1>
      <p className="muted">Bookings of your places. Open one to message the guest.</p>
      {bookings.isPending && <p className="notice">Loading…</p>}
      {bookings.error && <p className="notice notice-error">{bookings.error.message}</p>}
      {bookings.data?.total === 0 && <p className="notice">No bookings of your places yet.</p>}
      {bookings.data?.items.map((booking) => (
        <HostBookingRow key={booking.id} booking={booking} />
      ))}
    </main>
  )
}

function HostBookingRow({ booking }: { booking: Booking }) {
  const listing = useQuery({
    queryKey: ['listing', booking.listing_id],
    queryFn: () => api<Listing>(`/api/v1/listings/${booking.listing_id}`),
  })
  const nights = Math.round(
    (new Date(booking.check_out).getTime() - new Date(booking.check_in).getTime()) / 86_400_000,
  )

  return (
    <Link to={`/hosting/${booking.id}`} className="booking">
      <div>
        <h2>{listing.data?.title ?? 'Your place'}</h2>
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

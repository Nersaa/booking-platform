import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'

import { api } from '../api/client'
import type { Booking, HostListing, HostListingPage, Listing, Page } from '../api/types'
import { useAuth } from '../auth'
import { money, plural, shortDate } from '../format'
import { STATUS_LABELS } from './BookingsPage'
import { LISTING_STATUS } from './HostListingPage'

// For hosts: their places and guests' bookings of them, by check-in date.
const PLACES_SHOWN = 5 // the rest behind "Show all"

export default function HostingPage() {
  const { user, isLoggedIn } = useAuth()
  const [showAll, setShowAll] = useState(false)

  const places = useQuery({
    queryKey: ['host-listings'],
    queryFn: () => api<HostListingPage>('/api/v1/host/listings', { params: { page_size: 100 } }),
    enabled: user?.is_host === true,
  })
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

      <div className="section-head">
        <h2>Your places</h2>
        <Link to="/hosting/listings/new" className="primary">
          Add a place
        </Link>
      </div>
      {places.error && <p className="notice notice-error">{places.error.message}</p>}
      {places.data?.count === 0 && <p className="notice">You have no places yet.</p>}
      <ul className="host-places">
        {places.data?.results.slice(0, showAll ? undefined : PLACES_SHOWN).map((place) => (
          <HostPlaceRow key={place.id} place={place} />
        ))}
      </ul>
      {!showAll && places.data && places.data.results.length > PLACES_SHOWN && (
        <button className="link-button" onClick={() => setShowAll(true)}>
          Show {places.data.results.length} of {places.data.count} places
        </button>
      )}

      <h2>Bookings</h2>
      <p className="muted">Open a booking to message the guest.</p>
      {bookings.isPending && <p className="notice">Loading…</p>}
      {bookings.error && <p className="notice notice-error">{bookings.error.message}</p>}
      {bookings.data?.total === 0 && <p className="notice">No bookings of your places yet.</p>}
      {bookings.data?.items.map((booking) => (
        <HostBookingRow key={booking.id} booking={booking} />
      ))}
    </main>
  )
}

function HostPlaceRow({ place }: { place: HostListing }) {
  const cover = place.photos.find((photo) => photo.thumb_url)
  return (
    <li>
      <Link to={`/hosting/listings/${place.id}`} className="host-place">
        {cover?.thumb_url ? <img src={cover.thumb_url} alt="" /> : <span className="host-place-empty" />}
        <span>
          <strong>{place.title}</strong>
          <span className="muted small">{place.city}, {place.country}</span>
        </span>
        <span className={`listing-status listing-status-${place.status}`}>
          {LISTING_STATUS[place.status].label}
        </span>
      </Link>
    </li>
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

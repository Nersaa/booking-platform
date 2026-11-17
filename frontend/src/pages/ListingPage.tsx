import { useQuery } from '@tanstack/react-query'
import { useParams, useSearchParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Calendar, Listing, ReviewPage } from '../api/types'
import BookingBox from '../components/BookingBox'
import Cover from '../components/Cover'
import DateRangePicker, { toIso } from '../components/DateRangePicker'
import SaveButton from '../components/SaveButton'
import { plural, shortDate } from '../format'

const CALENDAR_DAYS = 180 // how far ahead the calendar shows free nights and prices

export default function ListingPage() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()

  // The page itself comes from the Catalog service, prices and dates from Booking.
  const listing = useQuery({
    queryKey: ['listing', id],
    queryFn: () => api<Listing>(`/api/v1/listings/${id}`),
  })
  const reviews = useQuery({
    queryKey: ['reviews', id],
    queryFn: () => api<ReviewPage>(`/api/v1/listings/${id}/reviews`),
  })
  const calendar = useQuery({
    queryKey: ['calendar', id],
    queryFn: () => {
      const today = new Date()
      const end = new Date(today.getFullYear(), today.getMonth(), today.getDate() + CALENDAR_DAYS)
      return api<Calendar>(`/api/v1/listings/${id}/calendar`, {
        params: { start_date: toIso(today), end_date: toIso(end) },
      })
    },
  })

  function chooseDates(checkIn: string, checkOut: string) {
    const next = new URLSearchParams(params)
    for (const [key, value] of [['check_in', checkIn], ['check_out', checkOut]]) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setParams(next, { replace: true })
  }

  if (listing.isPending) return <p className="page notice">Loading…</p>
  if (listing.error) return <p className="page notice notice-error">{listing.error.message}</p>

  const place = listing.data
  const photo = place.photos[0]?.large_url
  return (
    <main className="page listing">
      <div className="listing-main">
        <Cover url={photo} propertyType={place.property_type} className="listing-cover" />
        <div className="listing-title">
          <h1>{place.title}</h1>
          <SaveButton listingId={place.id} />
        </div>
        <p className="muted">
          {place.city}, {place.country}. Hosted by {place.host.first_name}.{' '}
          {place.bedrooms === 0 ? 'Studio' : plural(place.bedrooms, 'bedroom')},{' '}
          {plural(place.beds, 'bed')},{' '}
          {plural(place.bathrooms, 'bathroom')}, up to {plural(place.max_guests, 'guest')}.
        </p>
        <p className="listing-description">{place.description}</p>

        {place.amenities.length > 0 && (
          <>
            <h2>What this place offers</h2>
            <ul className="amenities">
              {place.amenities.map((amenity) => (
                <li key={amenity.code}>{amenity.name}</li>
              ))}
            </ul>
          </>
        )}

        {calendar.data && (
          <>
            <h2>Choose your dates</h2>
            <p className="muted small">
              Grey days are taken. Prices are per night; weekends and seasons may cost more.
            </p>
            <DateRangePicker
              checkIn={params.get('check_in') ?? ''}
              checkOut={params.get('check_out') ?? ''}
              onChange={chooseDates}
              calendar={calendar.data}
            />
          </>
        )}

        <h2>
          {place.rating ? (
            <>
              <span className="star">★</span> {place.rating}, {plural(place.review_count, 'review')}
            </>
          ) : (
            'No reviews yet'
          )}
        </h2>
        {reviews.data?.results.map((review) => (
          <article key={review.id} className="review">
            <p>
              <strong>{review.author.first_name}</strong>{' '}
              <span className="star">{'★'.repeat(review.rating)}</span>{' '}
              <span className="muted">{shortDate(review.created_at)}</span>
            </p>
            <p>{review.text}</p>
            {review.host_reply && (
              <p className="review-reply">
                <strong>{place.host.first_name} replied:</strong> {review.host_reply}
              </p>
            )}
          </article>
        ))}
      </div>

      {calendar.isPending ? (
        <aside className="booking-box">Loading prices…</aside>
      ) : (
        <BookingBox listingId={place.id} maxGuests={place.max_guests} calendar={calendar.data} />
      )}
    </main>
  )
}

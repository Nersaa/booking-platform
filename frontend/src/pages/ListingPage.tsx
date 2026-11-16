import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Listing, ReviewPage } from '../api/types'
import BookingBox from '../components/BookingBox'
import Cover from '../components/Cover'
import { plural, shortDate } from '../format'

export default function ListingPage() {
  const { id = '' } = useParams()

  // The page itself comes from the Catalog service, prices and dates from Booking.
  const listing = useQuery({
    queryKey: ['listing', id],
    queryFn: () => api<Listing>(`/api/v1/listings/${id}`),
  })
  const reviews = useQuery({
    queryKey: ['reviews', id],
    queryFn: () => api<ReviewPage>(`/api/v1/listings/${id}/reviews`),
  })

  if (listing.isPending) return <p className="page notice">Loading…</p>
  if (listing.error) return <p className="page notice notice-error">{listing.error.message}</p>

  const place = listing.data
  const photo = place.photos[0]?.large_url
  return (
    <main className="page listing">
      <div className="listing-main">
        <Cover url={photo} propertyType={place.property_type} className="listing-cover" />
        <h1>{place.title}</h1>
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

      <BookingBox listingId={place.id} maxGuests={place.max_guests} />
    </main>
  )
}

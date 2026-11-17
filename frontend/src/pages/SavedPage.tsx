import { Link, Navigate } from 'react-router-dom'

import { useAuth } from '../auth'
import Cover from '../components/Cover'
import SaveButton from '../components/SaveButton'
import { useFavorites } from '../favorites'
import { plural } from '../format'

export default function SavedPage() {
  const { isLoggedIn } = useAuth()
  const { saved, isLoading } = useFavorites()

  if (!isLoggedIn) return <Navigate to="/login?next=/saved" replace />

  return (
    <main className="search">
      <h1>Saved</h1>
      {isLoading && <p className="notice">Loading…</p>}
      {!isLoading && saved.length === 0 && (
        <p className="notice">
          Nothing saved yet. Tap the heart on a place to keep it here.{' '}
          <Link to="/">Find a place</Link>
        </p>
      )}
      <div className="cards">
        {saved.map((listing) => (
          <Link key={listing.id} to={`/listings/${listing.id}`} className="card">
            <div className="card-media">
              <Cover url={listing.cover_url} propertyType={listing.property_type} className="card-cover" />
              <SaveButton listingId={listing.id} className="on-cover" />
            </div>
            <div className="card-head">
              <h2 className="card-title">{listing.title}</h2>
              {listing.rating && (
                <span className="card-rating">
                  <span className="star">★</span> {listing.rating}
                </span>
              )}
            </div>
            <p className="muted">
              {listing.city}, {listing.country}
              {listing.review_count > 0 && `, ${plural(listing.review_count, 'review')}`}
            </p>
          </Link>
        ))}
      </div>
    </main>
  )
}

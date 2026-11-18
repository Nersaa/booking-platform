import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'

import { ApiError, api } from '../api/client'
import type { Block, HostListing, ListingStatus, Pricing } from '../api/types'
import { useAuth } from '../auth'
import ClosedDates from '../components/host/ClosedDates'
import ListingForm, { type ListingFields } from '../components/host/ListingForm'
import PhotoManager from '../components/host/PhotoManager'
import PricingForm from '../components/host/PricingForm'

export const LISTING_STATUS: Record<ListingStatus, { label: string; hint: string }> = {
  draft: {
    label: 'Draft',
    hint: 'Only you see it. Add photos and send it for review when it is ready.',
  },
  pending_review: {
    label: 'In review',
    hint: 'A moderator checks it, usually within a day. It cannot be changed meanwhile.',
  },
  published: { label: 'Published', hint: 'Guests can find and book it.' },
  rejected: { label: 'Rejected', hint: 'Fix what the moderator asked and send it again.' },
  archived: { label: 'Archived', hint: 'Hidden from guests for good. Past bookings stay.' },
}

const EDITABLE: ListingStatus[] = ['draft', 'rejected', 'published']

// Everything about one of the host's places: status, photos, details, prices, closed dates.
export default function HostListingPage() {
  const { id = '' } = useParams()
  const { user, isLoggedIn } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const listing = useQuery({
    queryKey: ['host-listing', id],
    queryFn: () => api<HostListing>(`/api/v1/host/listings/${id}`),
    enabled: user?.is_host === true,
    // Check again every 2 s while a worker is still resizing an uploaded photo.
    refetchInterval: (query) =>
      query.state.data?.photos.some((p) => p.status === 'processing') ? 2000 : false,
  })

  const saved = (data: HostListing) => {
    queryClient.setQueryData(['host-listing', id], data)
    queryClient.invalidateQueries({ queryKey: ['host-listings'] })
  }
  const update = useMutation({
    mutationFn: (fields: ListingFields) =>
      api<HostListing>(`/api/v1/host/listings/${id}`, { method: 'PATCH', body: fields }),
    onSuccess: saved,
  })
  const action = useMutation({
    mutationFn: (name: 'submit' | 'archive') =>
      api<HostListing>(`/api/v1/host/listings/${id}/${name}`, { method: 'POST' }),
    onSuccess: saved,
  })
  const remove = useMutation({
    mutationFn: () => api(`/api/v1/host/listings/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['host-listings'] })
      navigate('/hosting', { replace: true })
    },
  })

  if (!isLoggedIn) return <Navigate to={`/login?next=/hosting/listings/${id}`} replace />
  if (user && !user.is_host) return <Navigate to="/profile" replace />
  if (listing.isPending) return <p className="page notice">Loading…</p>
  if (listing.error) return <p className="page notice notice-error">{listing.error.message}</p>

  const place = listing.data
  const status = LISTING_STATUS[place.status]
  const canEdit = EDITABLE.includes(place.status)
  const hasReadyPhoto = place.photos.some((p) => p.status === 'ready')

  function archive() {
    if (window.confirm('Archive this place? Guests will no longer find it. This cannot be undone.')) {
      action.mutate('archive')
    }
  }

  function deleteDraft() {
    if (window.confirm('Delete this draft with its photos?')) remove.mutate()
  }

  return (
    <main className="page narrow-wide">
      <p>
        <Link to="/hosting">← Hosting</Link>
        {place.status === 'published' && (
          <>
            {' · '}
            <Link to={`/listings/${place.id}`}>Open as a guest</Link>
          </>
        )}
      </p>
      <h1>{place.title}</h1>

      <section className="host-section">
        <p>
          <span className={`listing-status listing-status-${place.status}`}>{status.label}</span>{' '}
          <span className="muted">{status.hint}</span>
        </p>
        {place.status === 'rejected' && place.rejection_reason && (
          <p className="notice notice-error">Moderator: {place.rejection_reason}</p>
        )}
        {action.error && <p className="notice notice-error">{action.error.message}</p>}
        {remove.error && <p className="notice notice-error">{remove.error.message}</p>}
        <div className="form-actions">
          {(place.status === 'draft' || place.status === 'rejected') && (
            <button
              className="primary"
              onClick={() => action.mutate('submit')}
              disabled={!hasReadyPhoto || action.isPending}
              title={hasReadyPhoto ? undefined : 'Add at least one photo first'}
            >
              Send for review
            </button>
          )}
          {place.status === 'draft' && (
            <button onClick={deleteDraft} disabled={remove.isPending}>
              Delete draft
            </button>
          )}
          {place.status === 'published' && (
            <button onClick={archive} disabled={action.isPending}>
              Archive
            </button>
          )}
        </div>
      </section>

      <PhotoManager listing={place} canEdit={canEdit} />

      {place.status === 'published' && <PricesAndDates listingId={place.id} />}

      <section className="host-section">
        <h2>Details</h2>
        {canEdit ? (
          <ListingForm
            key={place.id}
            listing={place}
            submitLabel="Save details"
            isSaving={update.isPending}
            error={update.error}
            onSubmit={(fields) => update.mutate(fields)}
          />
        ) : (
          <p className="muted">A place {status.label.toLowerCase()} cannot be edited.</p>
        )}
        {update.isSuccess && <p className="notice">Details saved.</p>}
      </section>
    </main>
  )
}

// Prices and the calendar live in the Booking service. It learns about a newly published
// place from an event, so for a few seconds after publishing it may not know it yet.
function PricesAndDates({ listingId }: { listingId: string }) {
  const pricing = useQuery({
    queryKey: ['host-pricing', listingId],
    queryFn: async () => {
      try {
        return await api<Pricing>(`/api/v1/host/listings/${listingId}/pricing`)
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null // no prices yet
        throw error
      }
    },
  })
  const blocks = useQuery({
    queryKey: ['host-blocks', listingId],
    queryFn: () => api<Block[]>(`/api/v1/host/listings/${listingId}/blocks`),
    retry: 5, // see above: the place may reach Booking a moment later
  })

  if (blocks.error) {
    return (
      <section className="host-section">
        <p className="notice notice-error">{blocks.error.message}</p>
      </section>
    )
  }
  if (pricing.isPending || blocks.isPending) {
    return <p className="notice">Loading prices…</p>
  }

  return (
    <>
      <section className="host-section">
        <h2>Prices</h2>
        {pricing.data === null && (
          <p className="notice">Set a price per night: until then guests cannot book this place.</p>
        )}
        {pricing.error ? (
          <p className="notice notice-error">{pricing.error.message}</p>
        ) : (
          <PricingForm listingId={listingId} pricing={pricing.data ?? null} />
        )}
      </section>
      <section className="host-section">
        <h2>Closed dates</h2>
        <ClosedDates listingId={listingId} blocks={blocks.data} />
      </section>
    </>
  )
}

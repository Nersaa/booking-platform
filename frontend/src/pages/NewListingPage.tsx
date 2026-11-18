import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import type { HostListing } from '../api/types'
import { useAuth } from '../auth'
import ListingForm, { type ListingFields } from '../components/host/ListingForm'

// Step one for a new place: the details. Photos and sending for review come next.
export default function NewListingPage() {
  const { user, isLoggedIn } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const create = useMutation({
    mutationFn: (fields: ListingFields) =>
      api<HostListing>('/api/v1/host/listings', { method: 'POST', body: fields }),
    onSuccess: (listing) => {
      queryClient.invalidateQueries({ queryKey: ['host-listings'] })
      navigate(`/hosting/listings/${listing.id}`, { replace: true })
    },
  })

  if (!isLoggedIn) return <Navigate to="/login?next=/hosting/listings/new" replace />
  if (user && !user.is_host) return <Navigate to="/profile" replace />

  return (
    <main className="page narrow-wide">
      <p>
        <Link to="/hosting">← Hosting</Link>
      </p>
      <h1>Add a place</h1>
      <p className="muted">
        It is saved as a draft. Next you add photos and send it for review; guests see it
        once a moderator publishes it.
      </p>
      <ListingForm
        submitLabel="Save and add photos"
        isSaving={create.isPending}
        error={create.error}
        onSubmit={(fields) => create.mutate(fields)}
      />
    </main>
  )
}

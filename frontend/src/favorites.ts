import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './api/client'
import type { SavedListing } from './api/types'
import { useAuth } from './auth'

// Saved listings of the logged-in user, shared by every heart button on the page.
export function useFavorites() {
  const { isLoggedIn } = useAuth()
  const queryClient = useQueryClient()

  const saved = useQuery({
    queryKey: ['favorites'],
    queryFn: () => api<SavedListing[]>('/api/v1/favorites'),
    enabled: isLoggedIn,
  })
  const savedIds = new Set(saved.data?.map((listing) => listing.id))

  const toggle = useMutation({
    mutationFn: (listingId: string) =>
      api(`/api/v1/favorites/${listingId}`, { method: savedIds.has(listingId) ? 'DELETE' : 'PUT' }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['favorites'] }),
  })

  return {
    saved: saved.data ?? [],
    isLoading: saved.isPending && isLoggedIn,
    isSaved: (listingId: string) => savedIds.has(listingId),
    toggle: (listingId: string) => toggle.mutate(listingId),
  }
}

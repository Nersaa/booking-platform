import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type ChangeEvent } from 'react'

import { api } from '../../api/client'
import type { HostListing, PhotoUpload } from '../../api/types'

const MAX_PHOTOS = 20
const MAX_SIZE = 10 * 1024 * 1024 // the storage refuses bigger files anyway
const TYPES = ['image/jpeg', 'image/png', 'image/webp']

const STATUS_TEXT = {
  pending_upload: 'Uploading…',
  processing: 'Processing…',
  ready: '',
  failed: 'Not a photo, or smaller than 400 px. Remove it and try another.',
}

// A photo goes straight from the browser to object storage, not through our API:
// 1. the API returns a presigned form (where to send the file and a signed policy),
// 2. the browser posts the file there,
// 3. the API is told the upload is done and a worker makes the resized versions.
async function uploadPhoto(listingId: string, file: File) {
  const base = `/api/v1/host/listings/${listingId}/photos`
  const { photo, upload } = await api<PhotoUpload>(base, {
    method: 'POST',
    body: { content_type: file.type },
  })

  const form = new FormData()
  for (const [name, value] of Object.entries(upload.fields)) form.append(name, value)
  form.append('file', file) // the storage wants the file as the last field
  // Only the path: the page and the storage share the gateway, also behind the dev server.
  const response = await fetch(new URL(upload.url).pathname, { method: 'POST', body: form })
  if (!response.ok) throw new Error(`${file.name} could not be uploaded.`)

  await api(`${base}/${photo.id}/complete`, { method: 'POST' })
}

export default function PhotoManager({ listing, canEdit }: { listing: HostListing; canEdit: boolean }) {
  const queryClient = useQueryClient()
  const [problem, setProblem] = useState('')
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['host-listing', listing.id] })

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) await uploadPhoto(listing.id, file)
    },
    onSettled: refresh,
  })
  const remove = useMutation({
    mutationFn: (photoId: string) =>
      api(`/api/v1/host/listings/${listing.id}/photos/${photoId}`, { method: 'DELETE' }),
    onSettled: refresh,
  })

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const files = [...(event.target.files ?? [])]
    event.target.value = '' // lets the same file be chosen again
    const room = MAX_PHOTOS - listing.photos.length
    const bad = files.find((f) => !TYPES.includes(f.type) || f.size > MAX_SIZE)
    if (bad) {
      setProblem(`${bad.name}: use a JPEG, PNG or WebP file up to 10 MB.`)
    } else if (files.length > room) {
      setProblem(`A place can have up to ${MAX_PHOTOS} photos; you can add ${room} more.`)
    } else {
      setProblem('')
      upload.mutate(files)
    }
  }

  const error = problem || upload.error?.message || remove.error?.message
  return (
    <section className="host-section">
      <h2>Photos</h2>
      <p className="muted small">
        The first photo is the cover in search. Guests see the rest on the place's page.
      </p>
      {listing.photos.length === 0 && <p className="notice">No photos yet. Add at least one.</p>}
      <ul className="host-photos">
        {listing.photos.map((photo) => (
          <li key={photo.id} className="host-photo">
            {photo.thumb_url ? (
              <img src={photo.thumb_url} alt="" />
            ) : (
              <span className="host-photo-status">{STATUS_TEXT[photo.status]}</span>
            )}
            {canEdit && (
              <button
                type="button"
                className="host-photo-remove"
                onClick={() => remove.mutate(photo.id)}
                disabled={remove.isPending}
                aria-label="Remove photo"
              >
                ×
              </button>
            )}
          </li>
        ))}
      </ul>
      {error && <p className="notice notice-error">{error}</p>}
      {canEdit && listing.photos.length < MAX_PHOTOS && (
        <label className="upload-button">
          {upload.isPending ? 'Uploading…' : 'Add photos'}
          <input
            type="file"
            accept={TYPES.join(',')}
            multiple
            onChange={choose}
            disabled={upload.isPending}
          />
        </label>
      )}
    </section>
  )
}

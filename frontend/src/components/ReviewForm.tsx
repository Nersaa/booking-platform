import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { api } from '../api/client'
import type { PendingReview } from '../api/types'
import { shortDate } from '../format'

// After a finished stay: rate it and write a few words, while the review window is open.
export default function ReviewForm({ bookingId, listingId }: { bookingId: string; listingId: string }) {
  const queryClient = useQueryClient()
  const [rating, setRating] = useState(0)
  const [text, setText] = useState('')

  // Catalog knows which stays can still be reviewed (once, within 14 days).
  const pending = useQuery({
    queryKey: ['reviews-pending'],
    queryFn: () => api<PendingReview[]>('/api/v1/reviews/pending'),
  })

  const send = useMutation({
    mutationFn: () =>
      api('/api/v1/reviews', { method: 'POST', body: { booking_id: bookingId, rating, text } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reviews-pending'] })
      queryClient.invalidateQueries({ queryKey: ['reviews', listingId] })
      queryClient.invalidateQueries({ queryKey: ['listing', listingId] })
    },
  })

  if (send.isSuccess) {
    return <p className="notice">Thank you! Your review is on the listing page.</p>
  }
  const open = pending.data?.find((stay) => stay.booking_id === bookingId)
  if (!open) return null

  function submit(event: FormEvent) {
    event.preventDefault()
    send.mutate()
  }

  return (
    <form className="form review-form" onSubmit={submit}>
      <h2>How was your stay?</h2>
      <p className="muted small">You can leave a review until {shortDate(open.review_deadline)}.</p>
      <div className="stars" role="radiogroup" aria-label="Rating">
        {[1, 2, 3, 4, 5].map((value) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={rating === value}
            aria-label={`${value} of 5`}
            className={value <= rating ? 'star-button is-on' : 'star-button'}
            onClick={() => setRating(value)}
          >
            ★
          </button>
        ))}
      </div>
      <label>
        Your review
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} required />
      </label>
      {send.error && <p className="notice notice-error">{send.error.message}</p>}
      <div className="form-actions">
        <button className="primary" disabled={rating === 0 || send.isPending}>
          Publish review
        </button>
      </div>
    </form>
  )
}

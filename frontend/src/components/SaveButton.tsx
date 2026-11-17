import type { MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../auth'
import { useFavorites } from '../favorites'

// The heart on a listing. Logged-out visitors are sent to log in first.
export default function SaveButton({ listingId, className = '' }: { listingId: string; className?: string }) {
  const { isLoggedIn } = useAuth()
  const { isSaved, toggle } = useFavorites()
  const navigate = useNavigate()
  const saved = isSaved(listingId)

  function click(event: MouseEvent) {
    event.preventDefault() // the button sits inside a card that is a link
    event.stopPropagation()
    if (isLoggedIn) toggle(listingId)
    else navigate(`/login?next=${encodeURIComponent(window.location.pathname)}`)
  }

  return (
    <button
      className={`save-button ${saved ? 'is-saved' : ''} ${className}`}
      onClick={click}
      aria-pressed={saved}
      aria-label={saved ? 'Remove from saved' : 'Save'}
      title={saved ? 'Remove from saved' : 'Save'}
    >
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
        <path d="M12 20.5s-7.5-4.6-9.3-9.2C1.4 8 3.6 4.5 7.1 4.5c2 0 3.6 1.1 4.9 2.8 1.3-1.7 2.9-2.8 4.9-2.8 3.5 0 5.7 3.5 4.4 6.8-1.8 4.6-9.3 9.2-9.3 9.2Z" />
      </svg>
    </button>
  )
}

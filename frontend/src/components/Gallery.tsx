import { useState, type KeyboardEvent } from 'react'

import type { Listing } from '../api/types'
import Cover from './Cover'

type Props = { photos: Listing['photos']; propertyType: string; title: string }

// The listing's photos: one large, arrows and thumbnails to flip through the rest.
export default function Gallery({ photos, propertyType, title }: Props) {
  const ready = photos.filter((photo) => photo.large_url)
  const [index, setIndex] = useState(0)

  if (ready.length === 0) {
    return <Cover url={null} propertyType={propertyType} className="listing-cover" />
  }

  const current = ready[Math.min(index, ready.length - 1)]
  const go = (step: number) => setIndex((index + step + ready.length) % ready.length)

  function onKey(event: KeyboardEvent) {
    if (event.key === 'ArrowLeft') go(-1)
    if (event.key === 'ArrowRight') go(1)
  }

  return (
    <div className="gallery" onKeyDown={onKey}>
      <div className="gallery-main">
        <img src={current.large_url ?? ''} alt={`${title}, photo ${index + 1} of ${ready.length}`} />
        {ready.length > 1 && (
          <>
            <button className="gallery-arrow prev" onClick={() => go(-1)} aria-label="Previous photo">
              ‹
            </button>
            <button className="gallery-arrow next" onClick={() => go(1)} aria-label="Next photo">
              ›
            </button>
            <span className="gallery-count">
              {index + 1} / {ready.length}
            </span>
          </>
        )}
      </div>
      {ready.length > 1 && (
        <div className="gallery-thumbs">
          {ready.map((photo, i) => (
            <button
              key={photo.id}
              className={i === index ? 'gallery-thumb is-current' : 'gallery-thumb'}
              onClick={() => setIndex(i)}
              aria-label={`Show photo ${i + 1}`}
              aria-current={i === index}
            >
              <img src={photo.thumb_url ?? ''} alt="" loading="lazy" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

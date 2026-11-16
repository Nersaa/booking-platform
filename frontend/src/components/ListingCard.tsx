import { Link } from 'react-router-dom'

import type { SearchItem } from '../api/types'
import { money, plural } from '../format'
import Cover from './Cover'

type Props = {
  item: SearchItem
  to: string
  onHover: (id: string | null) => void
}

export default function ListingCard({ item, to, onHover }: Props) {
  return (
    <Link
      to={to}
      className="card"
      onMouseEnter={() => onHover(item.id)}
      onMouseLeave={() => onHover(null)}
    >
      <Cover url={item.cover_photo_url} propertyType={item.property_type} className="card-cover" />
      <div className="card-body">
        <h2 className="card-title">{item.title}</h2>
        <p className="muted">
          {capitalize(item.property_type)} in {item.city},{' '}
          {item.bedrooms === 0 ? 'studio' : plural(item.bedrooms, 'bedroom')}, up to{' '}
          {plural(item.max_guests, 'guest')}
        </p>
        <p className="card-rating">
          {item.rating ? (
            <>
              <span className="star">★</span> {item.rating} ({plural(item.review_count, 'review')})
            </>
          ) : (
            <span className="muted">No reviews yet</span>
          )}
        </p>
      </div>
      <div className="card-price">
        {item.stay_total !== null ? (
          <>
            <strong>{money(item.stay_total, item.currency)}</strong>
            <span className="muted">for the stay</span>
          </>
        ) : (
          <>
            <strong>{money(item.nightly_price, item.currency)}</strong>
            <span className="muted">per night</span>
          </>
        )}
      </div>
    </Link>
  )
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

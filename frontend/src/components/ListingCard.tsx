import { Link } from 'react-router-dom'

import type { SearchItem } from '../api/types'
import { money, plural } from '../format'
import Cover from './Cover'

export default function ListingCard({ item, to }: { item: SearchItem; to: string }) {
  return (
    <Link to={to} className="card">
      <Cover url={item.cover_photo_url} propertyType={item.property_type} className="card-cover" />
      <div className="card-head">
        <h2 className="card-title">{item.title}</h2>
        {item.rating && (
          <span className="card-rating">
            <span className="star">★</span> {item.rating}
          </span>
        )}
      </div>
      <p className="muted">
        {capitalize(item.property_type)},{' '}
        {item.bedrooms === 0 ? 'studio' : plural(item.bedrooms, 'bedroom')}, up to{' '}
        {plural(item.max_guests, 'guest')}
      </p>
      <p className="card-price">
        {item.stay_total !== null ? (
          <>
            <strong>{money(item.stay_total, item.currency)}</strong> for the stay
          </>
        ) : (
          <>
            <strong>{money(item.nightly_price, item.currency)}</strong> per night
          </>
        )}
      </p>
    </Link>
  )
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

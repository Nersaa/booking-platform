import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import type { Amenity } from '../api/types'

const PLACE_TYPES = ['apartment', 'house', 'cottage', 'room']

export type FilterValues = {
  minPrice: string // euros per night, as typed
  maxPrice: string
  types: string[]
  amenities: string[]
  bedrooms: string
  rating: string
}

type Props = {
  values: FilterValues
  onChange: (changes: Record<string, string | string[] | null>) => void
}

// Everything the search API can filter by besides place, dates and guests.
export default function MoreFilters({ values, onChange }: Props) {
  const amenities = useQuery({
    queryKey: ['amenities'],
    queryFn: () => api<Amenity[]>('/api/v1/amenities'),
    staleTime: Infinity, // a dictionary: it does not change while the page is open
  })

  function toggle(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((item) => item !== value) : [...list, value]
  }

  return (
    <div className="more-filters">
      <fieldset>
        <legend>Price per night, €</legend>
        <div className="price-range">
          <input
            type="number"
            min={0}
            placeholder="From"
            aria-label="Lowest price per night"
            value={values.minPrice}
            onChange={(e) => onChange({ min_price: e.target.value })}
          />
          <input
            type="number"
            min={0}
            placeholder="To"
            aria-label="Highest price per night"
            value={values.maxPrice}
            onChange={(e) => onChange({ max_price: e.target.value })}
          />
        </div>
      </fieldset>

      <fieldset>
        <legend>Type of place</legend>
        {PLACE_TYPES.map((type) => (
          <label key={type} className="check">
            <input
              type="checkbox"
              checked={values.types.includes(type)}
              onChange={() => onChange({ type: toggle(values.types, type) })}
            />
            {type.charAt(0).toUpperCase() + type.slice(1)}
          </label>
        ))}
      </fieldset>

      <fieldset>
        <legend>Rooms and rating</legend>
        <label>
          Bedrooms
          <select value={values.bedrooms} onChange={(e) => onChange({ bedrooms: e.target.value })}>
            <option value="">Any</option>
            {[1, 2, 3, 4].map((n) => (
              <option key={n} value={n}>
                {n}+
              </option>
            ))}
          </select>
        </label>
        <label>
          Guest rating
          <select value={values.rating} onChange={(e) => onChange({ rating: e.target.value })}>
            <option value="">Any</option>
            <option value="4">4+</option>
            <option value="4.5">4.5+</option>
          </select>
        </label>
      </fieldset>

      <fieldset className="amenity-list">
        <legend>Amenities</legend>
        {amenities.data?.map((amenity) => (
          <label key={amenity.code} className="check">
            <input
              type="checkbox"
              checked={values.amenities.includes(amenity.code)}
              onChange={() => onChange({ amenity: toggle(values.amenities, amenity.code) })}
            />
            {amenity.name}
          </label>
        ))}
      </fieldset>
    </div>
  )
}

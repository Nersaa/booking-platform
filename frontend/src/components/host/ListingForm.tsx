import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { api } from '../../api/client'
import type { Amenity, HostListing } from '../../api/types'
import LocationPicker from './LocationPicker'

// What the Catalog API takes to create or edit a listing.
export type ListingFields = {
  title: string
  description: string
  property_type: string
  country: string
  city: string
  address: string
  latitude: string
  longitude: string
  max_guests: number
  bedrooms: number
  beds: number
  bathrooms: number
  amenities: string[]
}

const EMPTY: ListingFields = {
  title: '',
  description: '',
  property_type: 'apartment',
  country: '',
  city: '',
  address: '',
  latitude: '',
  longitude: '',
  max_guests: 2,
  bedrooms: 1,
  beds: 1,
  bathrooms: 1,
  amenities: [],
}

// Only the fields the form edits: the API ignores the rest, but there is no point sending it.
function fromListing(listing: HostListing): ListingFields {
  const fields = { ...EMPTY }
  for (const key of Object.keys(EMPTY) as (keyof ListingFields)[]) {
    if (key !== 'amenities') Object.assign(fields, { [key]: listing[key] })
  }
  return { ...fields, amenities: listing.amenities.map((a) => a.code) }
}

type Props = {
  listing?: HostListing
  submitLabel: string
  isSaving: boolean
  error: Error | null
  onSubmit: (fields: ListingFields) => void
}

export default function ListingForm({ listing, submitLabel, isSaving, error, onSubmit }: Props) {
  const [fields, setFields] = useState<ListingFields>(() => (listing ? fromListing(listing) : EMPTY))
  const amenities = useQuery({
    queryKey: ['amenities'],
    queryFn: () => api<Amenity[]>('/api/v1/amenities'),
    staleTime: Infinity,
  })

  function set<K extends keyof ListingFields>(key: K, value: ListingFields[K]) {
    setFields((current) => ({ ...current, [key]: value }))
  }

  function toggleAmenity(code: string) {
    const list = fields.amenities
    set('amenities', list.includes(code) ? list.filter((c) => c !== code) : [...list, code])
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    onSubmit(fields)
  }

  const number = (key: 'max_guests' | 'bedrooms' | 'beds' | 'bathrooms', label: string, min: number) => (
    <label>
      {label}
      <input
        type="number"
        min={min}
        max={50}
        value={fields[key]}
        onChange={(e) => set(key, Number(e.target.value))}
        required
      />
    </label>
  )

  return (
    <form className="form host-form" onSubmit={submit}>
      <label>
        Title
        <input
          value={fields.title}
          onChange={(e) => set('title', e.target.value)}
          maxLength={120}
          placeholder="Bright flat near the old town"
          required
        />
      </label>
      <label>
        Description
        <textarea
          value={fields.description}
          onChange={(e) => set('description', e.target.value)}
          rows={5}
          maxLength={5000}
          required
        />
      </label>
      <label>
        Type of place
        <select value={fields.property_type} onChange={(e) => set('property_type', e.target.value)}>
          <option value="apartment">Apartment</option>
          <option value="house">House</option>
          <option value="cottage">Cottage</option>
          <option value="room">Room</option>
        </select>
      </label>

      <div className="form-row">
        {number('max_guests', 'Guests', 1)}
        {number('bedrooms', 'Bedrooms', 0)}
        {number('beds', 'Beds', 1)}
        {number('bathrooms', 'Bathrooms', 0)}
      </div>

      <fieldset className="amenity-list">
        <legend>Amenities</legend>
        {amenities.data?.map((amenity) => (
          <label key={amenity.code} className="check">
            <input
              type="checkbox"
              checked={fields.amenities.includes(amenity.code)}
              onChange={() => toggleAmenity(amenity.code)}
            />
            {amenity.name}
          </label>
        ))}
      </fieldset>

      <div className="form-row">
        <label>
          Country code
          <input
            value={fields.country}
            onChange={(e) => set('country', e.target.value.toUpperCase())}
            maxLength={2}
            placeholder="PT"
            required
          />
        </label>
        <label>
          City
          <input value={fields.city} onChange={(e) => set('city', e.target.value)} required />
        </label>
      </div>
      <label>
        Address
        <input value={fields.address} onChange={(e) => set('address', e.target.value)} required />
      </label>
      <div>
        <p className="field-label">Location on the map</p>
        <p className="muted small">
          {fields.latitude
            ? `${fields.latitude}, ${fields.longitude}. Click elsewhere to move it.`
            : 'Click the map where the place is. Guests find it by this point.'}
        </p>
        <LocationPicker
          latitude={fields.latitude}
          longitude={fields.longitude}
          onChange={(latitude, longitude) => setFields((f) => ({ ...f, latitude, longitude }))}
        />
      </div>

      {error && <p className="notice notice-error">{error.message}</p>}
      <div className="form-actions">
        <button className="primary" disabled={isSaving || fields.latitude === ''}>
          {isSaving ? 'Saving…' : submitLabel}
        </button>
      </div>
    </form>
  )
}

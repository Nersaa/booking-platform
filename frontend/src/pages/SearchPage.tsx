import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Page, SearchItem } from '../api/types'
import ListingCard from '../components/ListingCard'
import ResultsMap from '../components/ResultsMap'

// The cities of the demo data (`python loadtest/seed.py`).
const CITIES: Record<string, [number, number]> = {
  Lisbon: [38.7223, -9.1393],
  Porto: [41.1579, -8.6291],
  Barcelona: [41.3874, 2.1686],
  Madrid: [40.4168, -3.7038],
  Paris: [48.8566, 2.3522],
  Berlin: [52.52, 13.405],
  Rome: [41.9028, 12.4964],
  Amsterdam: [52.3676, 4.9041],
}
const PAGE_SIZE = 24
const MAP_SIZE = 50 // the map shows more places at once; the API allows up to 50

export default function SearchPage() {
  // Filters live in the URL, so a search can be shared and survives the Back button.
  const [params, setParams] = useSearchParams()
  const [selected, setSelected] = useState<SearchItem | null>(null)

  const city = params.get('city') ?? 'Lisbon'
  const bbox = params.get('bbox')
  const checkIn = params.get('check_in') ?? ''
  const checkOut = params.get('check_out') ?? ''
  const guests = Number(params.get('guests') ?? 2)
  const sort = params.get('sort') ?? 'rating'
  const offset = Number(params.get('offset') ?? 0)
  const showMap = params.get('view') === 'map'
  const center = bbox ? null : (CITIES[city] ?? CITIES.Lisbon)
  const hasDates = checkIn !== '' && checkOut !== ''

  const query = {
    ...(center ? { lat: center[0], lon: center[1], radius_km: 15 } : { bbox }),
    ...(hasDates ? { check_in: checkIn, check_out: checkOut } : {}),
    guests,
    sort,
    currency: sort === 'price' ? 'EUR' : undefined, // prices are compared within one currency
    limit: showMap ? MAP_SIZE : PAGE_SIZE,
    offset: showMap ? 0 : offset,
  }
  const { data, error, isPending } = useQuery({
    queryKey: ['search', query],
    queryFn: () => api<Page<SearchItem>>('/api/v1/listings', { params: query }),
    placeholderData: keepPreviousData, // keep the old results on screen while new ones load
  })

  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params)
    if (!('offset' in changes)) next.delete('offset') // a new search starts from page one
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setParams(next)
    setSelected(null)
  }

  const stay = hasDates ? `?check_in=${checkIn}&check_out=${checkOut}&guests=${guests}` : ''
  const items = data?.items ?? []
  const where = bbox ? 'in this map area' : `in ${city}`

  return (
    <main className={showMap ? 'search search-map' : 'search'}>
      <form className="filters" onSubmit={(event) => event.preventDefault()}>
        <label>
          Where
          <select
            value={bbox ? '' : city}
            onChange={(event) => update({ city: event.target.value, bbox: null })}
          >
            {bbox && <option value="">Map area</option>}
            {Object.keys(CITIES).map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <label>
          Check-in
          <input
            type="date"
            value={checkIn}
            min={today()}
            onChange={(event) => update({ check_in: event.target.value })}
          />
        </label>
        <label>
          Check-out
          <input
            type="date"
            value={checkOut}
            min={checkIn || today()}
            onChange={(event) => update({ check_out: event.target.value })}
          />
        </label>
        <label>
          Guests
          <input
            type="number"
            min={1}
            max={16}
            value={guests}
            onChange={(event) => update({ guests: event.target.value })}
          />
        </label>
        <label>
          Sort by
          <select value={sort} onChange={(event) => update({ sort: event.target.value })}>
            <option value="rating">Top rated</option>
            <option value="price">Lowest price</option>
          </select>
        </label>
      </form>

      <div className="results-bar">
        {data && (
          <p className="results-count">
            {data.total === 0
              ? 'No places match. Try other dates or another city.'
              : `${data.total} ${data.total === 1 ? 'place' : 'places'} ${where}${hasDates ? ', free on your dates' : ''}`}
          </p>
        )}
        <button onClick={() => update({ view: showMap ? null : 'map' })}>
          {showMap ? 'Show list' : 'Show map'}
        </button>
      </div>

      {error && <p className="notice notice-error">{error.message}</p>}
      {isPending && <p className="notice">Searching…</p>}

      {showMap ? (
        <div className="map-view">
          <ResultsMap
            items={items}
            center={center}
            bbox={bbox}
            selectedId={selected?.id ?? null}
            onSelect={setSelected}
            onSearchArea={(area) => update({ bbox: area, city: null })}
          />
          {selected && (
            <div className="map-preview">
              <button className="map-preview-close" onClick={() => setSelected(null)}>
                Close
              </button>
              <ListingCard item={selected} to={`/listings/${selected.id}${stay}`} />
            </div>
          )}
          {data && data.total > items.length && (
            <p className="map-hint">
              Showing {items.length} of {data.total}. Zoom in and search this area to see the
              rest.
            </p>
          )}
        </div>
      ) : (
        <>
          <div className="cards">
            {items.map((item) => (
              <ListingCard key={item.id} item={item} to={`/listings/${item.id}${stay}`} />
            ))}
          </div>

          {data && data.total > PAGE_SIZE && (
            <div className="pager">
              <button
                disabled={offset === 0}
                onClick={() => update({ offset: String(offset - PAGE_SIZE) })}
              >
                Previous
              </button>
              <span className="muted">
                {offset + 1}–{offset + items.length} of {data.total}
              </span>
              <button
                disabled={offset + PAGE_SIZE >= data.total}
                onClick={() => update({ offset: String(offset + PAGE_SIZE) })}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </main>
  )
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

import L from 'leaflet'
import { useEffect } from 'react'
import { MapContainer, Marker, TileLayer, useMap } from 'react-leaflet'

import type { SearchItem } from '../api/types'
import { money } from '../format'

type Props = {
  items: SearchItem[]
  center: [number, number] | null // null while the user searches a map area of their own
  bbox: string | null // that map area: "min_lon,min_lat,max_lon,max_lat"
  highlightedId: string | null
  onOpen: (item: SearchItem) => void
  onSearchArea: (bbox: string) => void
}

export default function ResultsMap(props: Props) {
  const { items, center, bbox, highlightedId, onOpen, onSearchArea } = props
  // Where the map opens: the city, or the area from a shared link.
  const [west, south, east, north] = (bbox ?? '').split(',').map(Number)
  const start = center
    ? { center, zoom: 12 }
    : { bounds: L.latLngBounds([south, west], [north, east]) }

  return (
    <MapContainer className="map" {...start}>
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      />
      {center && <Recenter center={center} />}
      <SearchAreaButton onSearchArea={onSearchArea} />
      {items.map((item) => (
        <Marker
          key={item.id}
          position={[Number(item.latitude), Number(item.longitude)]}
          icon={priceTag(item, item.id === highlightedId)}
          zIndexOffset={item.id === highlightedId ? 1000 : 0}
          eventHandlers={{ click: () => onOpen(item) }}
        />
      ))}
    </MapContainer>
  )
}

// A marker that shows the nightly price instead of a pin.
function priceTag(item: SearchItem, highlighted: boolean) {
  const price = money(item.nightly_price, item.currency)
  return L.divIcon({
    className: '',
    iconSize: [0, 0],
    html: `<span class="price-tag${highlighted ? ' is-highlighted' : ''}">${price}</span>`,
  })
}

function Recenter({ center }: { center: [number, number] }) {
  const map = useMap()
  const [lat, lon] = center
  useEffect(() => {
    map.setView([lat, lon], 12)
  }, [map, lat, lon])
  return null
}

function SearchAreaButton({ onSearchArea }: { onSearchArea: (bbox: string) => void }) {
  const map = useMap()

  function search() {
    const bounds = map.getBounds()
    // The API takes min_lon,min_lat,max_lon,max_lat within the valid coordinate range.
    const bbox = [
      Math.max(bounds.getWest(), -180),
      Math.max(bounds.getSouth(), -90),
      Math.min(bounds.getEast(), 180),
      Math.min(bounds.getNorth(), 90),
    ]
    onSearchArea(bbox.map((value) => value.toFixed(4)).join(','))
  }

  return (
    <button className="map-button" onClick={search}>
      Search this area
    </button>
  )
}

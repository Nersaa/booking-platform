import { CircleMarker, MapContainer, TileLayer, useMapEvents } from 'react-leaflet'

type Props = {
  latitude: string
  longitude: string
  onChange: (latitude: string, longitude: string) => void
}

// Click the map to put the place on it; search uses these coordinates.
export default function LocationPicker({ latitude, longitude, onChange }: Props) {
  const hasPoint = latitude !== '' && longitude !== ''
  const point: [number, number] = hasPoint ? [Number(latitude), Number(longitude)] : [48, 8]

  return (
    // No wheel zoom: scrolling down the form would zoom the map instead. The +/- buttons work.
    <MapContainer
      className="location-map"
      center={point}
      zoom={hasPoint ? 13 : 4}
      scrollWheelZoom={false}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      />
      <ClickToPlace onChange={onChange} />
      {hasPoint && <CircleMarker center={point} radius={9} pathOptions={{ color: '#0f6e6a' }} />}
    </MapContainer>
  )
}

function ClickToPlace({ onChange }: Pick<Props, 'onChange'>) {
  useMapEvents({
    click(event) {
      // The API stores 6 decimal places: about 10 cm, more than enough.
      onChange(event.latlng.lat.toFixed(6), event.latlng.lng.toFixed(6))
    },
  })
  return null
}

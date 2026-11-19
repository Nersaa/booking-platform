import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'

import { api } from '../api/client'
import type { HostStats, MonthStats } from '../api/types'
import { useAuth } from '../auth'
import { money, plural } from '../format'

const THIS_YEAR = new Date().getFullYear()
const YEARS = [THIS_YEAR + 1, THIS_YEAR, THIS_YEAR - 1, THIS_YEAR - 2]

// The host's year in numbers. Booking counts them in SQL; this page only draws them.
export default function HostStatsPage() {
  const { user, isLoggedIn } = useAuth()
  const [year, setYear] = useState(THIS_YEAR)
  const [currency, setCurrency] = useState('')

  const stats = useQuery({
    queryKey: ['host-stats', year, currency],
    queryFn: () => api<HostStats>('/api/v1/host/stats', { params: { year, currency } }),
    enabled: user?.is_host === true,
  })

  if (!isLoggedIn) return <Navigate to="/login?next=/hosting/stats" replace />
  if (user && !user.is_host) return <Navigate to="/profile" replace />

  const data = stats.data
  return (
    <main className="page">
      <p>
        <Link to="/hosting">← Hosting</Link>
      </p>
      <div className="section-head">
        <h1>Statistics</h1>
        <div className="stats-filters">
          <select value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Year">
            {YEARS.map((y) => (
              <option key={y}>{y}</option>
            ))}
          </select>
          {data && data.currencies.length > 1 && (
            <select value={data.currency} onChange={(e) => setCurrency(e.target.value)} aria-label="Currency">
              {data.currencies.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          )}
        </div>
      </div>
      <p className="muted">
        Paid stays only. Money and bookings count in the month of check-in; nights in the
        month they fall in.
      </p>

      {stats.isPending && <p className="notice">Loading…</p>}
      {stats.error && <p className="notice notice-error">{stats.error.message}</p>}
      {data && (
        <>
          <div className="stat-tiles">
            <Tile label="Revenue" value={money(data.revenue, data.currency)} />
            <Tile label="Bookings" value={data.bookings.toLocaleString('en')} />
            <Tile label="Average booking" value={money(data.average_booking, data.currency)} />
            <Tile
              label="Occupancy"
              value={`${data.occupancy_percent}%`}
              note={`${data.nights.toLocaleString('en')} nights booked, ${plural(data.listed_places, 'place')}`}
            />
          </div>

          <h2>Revenue by month</h2>
          <RevenueChart months={data.months} currency={data.currency} />

          <details className="stats-table">
            <summary>Show as a table</summary>
            <table>
              <thead>
                <tr>
                  <th>Month</th>
                  <th>Revenue</th>
                  <th>Bookings</th>
                  <th>Nights</th>
                  <th>Occupancy</th>
                </tr>
              </thead>
              <tbody>
                {data.months.map((m) => (
                  <tr key={m.month}>
                    <td>{monthName(m.month, 'long')}</td>
                    <td>{money(m.revenue, data.currency)}</td>
                    <td>{m.bookings}</td>
                    <td>{m.nights}</td>
                    <td>{m.occupancy_percent}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>

          <h2>Best places</h2>
          {data.top_listings.length === 0 ? (
            <p className="muted">No paid stays in {year} yet.</p>
          ) : (
            <ol className="top-places">
              {data.top_listings.map((place) => (
                <li key={place.listing_id}>
                  <Link to={`/hosting/listings/${place.listing_id}`}>{place.title}</Link>
                  <span className="muted">{plural(place.bookings, 'booking')}</span>
                  <strong>{money(place.revenue, data.currency)}</strong>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </main>
  )
}

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="stat-tile">
      <p className="muted small">{label}</p>
      <p className="stat-value">{value}</p>
      {note && <p className="muted small">{note}</p>}
    </div>
  )
}

// One bar per month, its height relative to the best month. Hovering (or focusing) a bar
// shows that month's numbers.
function RevenueChart({ months, currency }: { months: MonthStats[]; currency: string }) {
  const max = Math.max(...months.map((m) => m.revenue))
  const best = months.find((m) => m.revenue === max && max > 0)

  return (
    <div className="bar-chart" role="img" aria-label="Revenue by month">
      {months.map((m) => (
        <div key={m.month} className="bar-column" tabIndex={0}>
          <div className="bar-track">
            {/* Only the best month carries its value; the rest is in the tooltip and table. */}
            {m === best && <span className="bar-label">{money(m.revenue, currency)}</span>}
            <div className="bar" style={{ height: max ? `${(m.revenue / max) * 100}%` : 0 }} />
          </div>
          <span className="bar-month">
            <span className="month-wide">{monthName(m.month, 'short')}</span>
            <span className="month-narrow">{monthName(m.month, 'narrow')}</span>
          </span>
          <div className="bar-tooltip" role="tooltip">
            <strong>{monthName(m.month, 'long')}</strong>
            <span>{money(m.revenue, currency)}</span>
            <span>
              {plural(m.bookings, 'booking')}, {m.occupancy_percent}% occupied
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

function monthName(isoDate: string, width: 'narrow' | 'short' | 'long'): string {
  return new Date(isoDate).toLocaleDateString('en', { month: width })
}

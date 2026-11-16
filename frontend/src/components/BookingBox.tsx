import { useMutation, useQuery } from '@tanstack/react-query'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Booking, Calendar, Quote } from '../api/types'
import { useAuth } from '../auth'
import { money, plural, shortDate } from '../format'

// Dates, the price for them, and the "Book" button.
export default function BookingBox({ listingId, maxGuests }: { listingId: string; maxGuests: number }) {
  const { isLoggedIn } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [params, setParams] = useSearchParams()

  const checkIn = params.get('check_in') ?? ''
  const checkOut = params.get('check_out') ?? ''
  const guests = Number(params.get('guests') ?? 2)
  const hasDates = checkIn !== '' && checkOut !== '' && checkOut > checkIn

  function update(key: string, value: string) {
    const next = new URLSearchParams(params)
    next.set(key, value)
    setParams(next, { replace: true })
  }

  const calendar = useQuery({
    queryKey: ['calendar', listingId],
    queryFn: () => api<Calendar>(`/api/v1/listings/${listingId}/calendar`),
  })

  const stay = { check_in: checkIn, check_out: checkOut, guests }
  const quote = useQuery({
    queryKey: ['quote', listingId, stay],
    queryFn: () => api<Quote>(`/api/v1/listings/${listingId}/quote`, { params: stay }),
    enabled: hasDates,
  })

  const book = useMutation({
    mutationFn: () =>
      api<Booking>('/api/v1/bookings', { method: 'POST', body: { listing_id: listingId, ...stay } }),
    onSuccess: () => navigate('/bookings'),
  })

  if (calendar.error) {
    return <aside className="booking-box">This place is not open for booking yet.</aside>
  }

  const firstDay = calendar.data?.days[0]
  return (
    <aside className="booking-box">
      {calendar.data && firstDay && (
        <p className="booking-price">
          <strong>{money(firstDay.nightly_price, calendar.data.currency)}</strong> per night
          <span className="muted">, {plural(calendar.data.min_nights, 'night')} minimum</span>
        </p>
      )}

      <div className="booking-dates">
        <label>
          Check-in
          <input
            type="date"
            value={checkIn}
            min={firstDay?.date}
            onChange={(event) => update('check_in', event.target.value)}
          />
        </label>
        <label>
          Check-out
          <input
            type="date"
            value={checkOut}
            min={checkIn || firstDay?.date}
            onChange={(event) => update('check_out', event.target.value)}
          />
        </label>
        <label>
          Guests
          <input
            type="number"
            min={1}
            max={maxGuests}
            value={guests}
            onChange={(event) => update('guests', event.target.value)}
          />
        </label>
      </div>

      {calendar.data && <Availability calendar={calendar.data} />}

      {!hasDates && <p className="muted">Choose dates to see the price.</p>}
      {quote.error && <p className="notice notice-error">{quote.error.message}</p>}
      {quote.data && (
        <dl className="quote">
          <dt>{plural(quote.data.nights.length, 'night')}</dt>
          <dd>{money(quote.data.subtotal, quote.data.currency)}</dd>
          {quote.data.discount > 0 && (
            <>
              <dt>Long stay discount</dt>
              <dd>−{money(quote.data.discount, quote.data.currency)}</dd>
            </>
          )}
          <dt>Cleaning</dt>
          <dd>{money(quote.data.cleaning_fee, quote.data.currency)}</dd>
          <dt className="quote-total">Total</dt>
          <dd className="quote-total">{money(quote.data.total, quote.data.currency)}</dd>
        </dl>
      )}

      {book.error && <p className="notice notice-error">{book.error.message}</p>}
      {isLoggedIn ? (
        <button
          className="primary"
          disabled={!quote.data || book.isPending}
          onClick={() => book.mutate()}
        >
          {book.isPending ? 'Booking…' : 'Book'}
        </button>
      ) : (
        <Link
          className="primary"
          to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`}
        >
          Log in to book
        </Link>
      )}
      <p className="muted small">
        Booking holds the dates for 15 minutes. You pay on the next step.
      </p>
    </aside>
  )
}

// The next six weeks at a glance: which nights are still free.
function Availability({ calendar }: { calendar: Calendar }) {
  return (
    <div className="availability">
      <p className="small">
        Next six weeks, <span className="day day-free" /> free <span className="day" /> taken
      </p>
      <div className="days">
        {calendar.days.slice(0, 42).map((day) => (
          <span
            key={day.date}
            className={day.available ? 'day day-free' : 'day'}
            title={`${shortDate(day.date)}: ${day.available ? money(day.nightly_price, calendar.currency) : 'taken'}`}
          />
        ))}
      </div>
    </div>
  )
}

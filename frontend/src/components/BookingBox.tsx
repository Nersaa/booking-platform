import { useMutation, useQuery } from '@tanstack/react-query'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '../api/client'
import type { Booking, Calendar, Quote } from '../api/types'
import { useAuth } from '../auth'
import { money, plural, shortDate } from '../format'

type Props = { listingId: string; maxGuests: number; calendar: Calendar | undefined }

// The chosen dates, the price for them, and the "Book" button. Dates are picked in the
// calendar on the listing page; both read them from the URL.
export default function BookingBox({ listingId, maxGuests, calendar }: Props) {
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

  const stay = { check_in: checkIn, check_out: checkOut, guests }
  const quote = useQuery({
    queryKey: ['quote', listingId, stay],
    queryFn: () => api<Quote>(`/api/v1/listings/${listingId}/quote`, { params: stay }),
    enabled: hasDates,
  })

  const book = useMutation({
    mutationFn: () =>
      api<Booking>('/api/v1/bookings', { method: 'POST', body: { listing_id: listingId, ...stay } }),
    onSuccess: (booking) => navigate(`/bookings/${booking.id}`),
  })

  if (!calendar) {
    return <aside className="booking-box">This place is not open for booking yet.</aside>
  }

  const firstDay = calendar.days[0]
  return (
    <aside className="booking-box">
      {firstDay && (
        <p className="booking-price">
          <strong>{money(firstDay.nightly_price, calendar.currency)}</strong> per night
          <span className="muted">, {plural(calendar.min_nights, 'night')} minimum</span>
        </p>
      )}

      <div className="booking-dates">
        <div className="chosen-date">
          <span>Check-in</span>
          <strong>{checkIn ? shortDate(checkIn) : 'Add date'}</strong>
        </div>
        <div className="chosen-date">
          <span>Check-out</span>
          <strong>{checkOut ? shortDate(checkOut) : 'Add date'}</strong>
        </div>
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

      {!hasDates && <p className="muted">Pick your dates in the calendar to see the price.</p>}
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
          {book.isPending ? 'Sending…' : calendar.instant_book ? 'Book' : 'Request to book'}
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
        {calendar.instant_book
          ? 'Booking holds the dates for 15 minutes. You pay on the next step.'
          : 'The host answers within 24 hours and the dates are held meanwhile. You pay only after they accept.'}
      </p>
    </aside>
  )
}


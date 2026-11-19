import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { api } from '../../api/client'
import type { Pricing } from '../../api/types'

// The API keeps money in cents; the form shows whole units (120.50).
const toUnits = (cents: number | null) => (cents === null ? '' : String(cents / 100))
const toCents = (units: string) => Math.round(Number(units) * 100)

type Props = { listingId: string; pricing: Pricing | null }

export default function PricingForm({ listingId, pricing }: Props) {
  const queryClient = useQueryClient()
  const [currency, setCurrency] = useState(pricing?.currency ?? 'EUR')
  const [nightly, setNightly] = useState(toUnits(pricing?.nightly_price ?? null))
  const [weekend, setWeekend] = useState(toUnits(pricing?.weekend_price ?? null))
  const [cleaning, setCleaning] = useState(toUnits(pricing?.cleaning_fee ?? 0))
  const [minNights, setMinNights] = useState(pricing?.min_nights ?? 1)
  const [maxNights, setMaxNights] = useState(pricing?.max_nights ?? 30)
  const [weekly, setWeekly] = useState(pricing?.weekly_discount_percent ?? 0)
  const [monthly, setMonthly] = useState(pricing?.monthly_discount_percent ?? 0)
  const [instantBook, setInstantBook] = useState(pricing?.instant_book ?? true)

  const save = useMutation({
    mutationFn: () =>
      api<Pricing>(`/api/v1/host/listings/${listingId}/pricing`, {
        method: 'PUT',
        body: {
          currency,
          nightly_price: toCents(nightly),
          weekend_price: weekend === '' ? null : toCents(weekend),
          cleaning_fee: toCents(cleaning || '0'),
          min_nights: minNights,
          max_nights: maxNights,
          weekly_discount_percent: weekly,
          monthly_discount_percent: monthly,
          instant_book: instantBook,
        },
      }),
    onSuccess: (saved) => queryClient.setQueryData(['host-pricing', listingId], saved),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    save.mutate()
  }

  return (
    <form className="form" onSubmit={submit}>
      <div className="form-row">
        <label>
          Price per night
          <input type="number" min="1" step="0.01" value={nightly} onChange={(e) => setNightly(e.target.value)} required />
        </label>
        <label>
          Currency
          <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
            <option>EUR</option>
            <option>USD</option>
            <option>GBP</option>
          </select>
        </label>
      </div>
      <div className="form-row">
        <label>
          Friday and Saturday (optional)
          <input type="number" min="1" step="0.01" value={weekend} onChange={(e) => setWeekend(e.target.value)} />
        </label>
        <label>
          Cleaning fee
          <input type="number" min="0" step="0.01" value={cleaning} onChange={(e) => setCleaning(e.target.value)} />
        </label>
      </div>
      <div className="form-row">
        <label>
          Shortest stay, nights
          <input type="number" min={1} max={365} value={minNights} onChange={(e) => setMinNights(Number(e.target.value))} required />
        </label>
        <label>
          Longest stay, nights
          <input type="number" min={1} max={365} value={maxNights} onChange={(e) => setMaxNights(Number(e.target.value))} required />
        </label>
      </div>
      <div className="form-row">
        <label>
          Discount for a week or more, %
          <input type="number" min={0} max={90} value={weekly} onChange={(e) => setWeekly(Number(e.target.value))} />
        </label>
        <label>
          Discount for 4 weeks or more, %
          <input type="number" min={0} max={90} value={monthly} onChange={(e) => setMonthly(Number(e.target.value))} />
        </label>
      </div>
      <label className="check">
        <input type="checkbox" checked={instantBook} onChange={(e) => setInstantBook(e.target.checked)} />
        Instant booking: guests book without waiting for you
      </label>
      <p className="muted small">
        Turned off, every booking is a request: you accept or decline it within 24 hours
        under Hosting, and the guest pays after you accept.
      </p>
      {save.error && <p className="notice notice-error">{save.error.message}</p>}
      {save.isSuccess && <p className="notice">Prices saved. Search and the calendar use them now.</p>}
      <div className="form-actions">
        <button className="primary" disabled={save.isPending}>
          {save.isPending ? 'Saving…' : 'Save prices'}
        </button>
      </div>
    </form>
  )
}

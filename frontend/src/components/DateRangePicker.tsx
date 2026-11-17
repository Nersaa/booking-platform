import 'react-day-picker/style.css'

import { useState } from 'react'
import { DayButton, DayPicker, type DateRange, type DayButtonProps } from 'react-day-picker'

import type { Calendar } from '../api/types'
import { money } from '../format'

type Props = {
  checkIn: string // yyyy-mm-dd, or '' when not chosen
  checkOut: string
  onChange: (checkIn: string, checkOut: string) => void
  // With a listing's calendar, taken nights are greyed out and each day shows its price.
  calendar?: Calendar
}

export default function DateRangePicker({ checkIn, checkOut, onChange, calendar }: Props) {
  const [months] = useState(() => (window.matchMedia('(max-width: 54rem)').matches ? 1 : 2))
  const selected: DateRange | undefined = checkIn
    ? { from: fromIso(checkIn), to: checkOut ? fromIso(checkOut) : undefined }
    : undefined

  const prices = new Map(calendar?.days.map((day) => [day.date, day]))
  const today = startOfToday()

  function isNightTaken(date: Date): boolean {
    if (!calendar) return false
    const day = prices.get(toIso(date))
    return day === undefined || !day.available // past the calendar's end counts as taken
  }

  function isDisabled(date: Date): boolean {
    if (date < today) return true
    // Choosing the check-out: every night from check-in up to the day before must be free.
    // The check-out day itself may be taken by the next guest.
    if (selected?.from && !selected.to && date > selected.from) {
      for (let night = selected.from; night < date; night = addDays(night, 1)) {
        if (isNightTaken(night)) return true
      }
      return false
    }
    return isNightTaken(date)
  }

  function select(range: DateRange | undefined) {
    if (!range?.from) {
      onChange('', '')
    } else if (!range.to || range.to.getTime() === range.from.getTime()) {
      onChange(toIso(range.from), '') // first click: check-in only
    } else {
      onChange(toIso(range.from), toIso(range.to))
    }
  }

  function PriceDayButton({ day, modifiers, ...buttonProps }: DayButtonProps) {
    const price = prices.get(toIso(day.date))
    return (
      <DayButton day={day} modifiers={modifiers} {...buttonProps}>
        {buttonProps.children}
        {calendar && price?.available && !modifiers.disabled && !modifiers.outside && (
          <span className="day-price">{money(price.nightly_price, calendar.currency)}</span>
        )}
      </DayButton>
    )
  }

  return (
    <DayPicker
      className={calendar ? 'date-picker with-prices' : 'date-picker'}
      mode="range"
      numberOfMonths={months}
      startMonth={today}
      selected={selected}
      onSelect={select}
      disabled={isDisabled}
      components={calendar ? { DayButton: PriceDayButton } : undefined}
    />
  )
}

// Dates go to the API as yyyy-mm-dd in local time; toISOString() would shift them by
// the timezone and could move the stay by a day.
export function toIso(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

function fromIso(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function addDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days)
}

function startOfToday(): Date {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), now.getDate())
}

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'

import { api } from '../../api/client'
import type { Block } from '../../api/types'
import { shortDate } from '../../format'
import DateRangePicker from '../DateRangePicker'

type Props = { listingId: string; blocks: Block[] }

// Dates the host closes themself (repairs, own stay). Guests cannot book them.
export default function ClosedDates({ listingId, blocks }: Props) {
  const queryClient = useQueryClient()
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [note, setNote] = useState('')
  const path = `/api/v1/host/listings/${listingId}/blocks`
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['host-blocks', listingId] })

  const add = useMutation({
    mutationFn: () => api<Block>(path, { method: 'POST', body: { start_date: start, end_date: end, note } }),
    onSuccess: () => {
      setStart('')
      setEnd('')
      setNote('')
      return refresh()
    },
  })
  const remove = useMutation({
    mutationFn: (blockId: string) => api(`${path}/${blockId}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    add.mutate()
  }

  return (
    <>
      {blocks.length === 0 ? (
        <p className="muted">No closed dates. Every free night can be booked.</p>
      ) : (
        <ul className="blocks">
          {blocks.map((block) => (
            <li key={block.id}>
              <span>
                {shortDate(block.start_date)} to {shortDate(block.end_date)}
                {block.note && <span className="muted">, {block.note}</span>}
              </span>
              <button
                type="button"
                className="link-button"
                onClick={() => remove.mutate(block.id)}
                disabled={remove.isPending}
              >
                Open again
              </button>
            </li>
          ))}
        </ul>
      )}

      <form className="form" onSubmit={submit}>
        <p className="field-label">Close more dates</p>
        <p className="muted small">Pick the first closed night and the day after the last one.</p>
        <DateRangePicker
          checkIn={start}
          checkOut={end}
          onChange={(checkIn, checkOut) => {
            setStart(checkIn)
            setEnd(checkOut)
          }}
        />
        <label>
          Note for yourself (optional)
          <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} placeholder="Repairs" />
        </label>
        {(add.error ?? remove.error) && (
          <p className="notice notice-error">{(add.error ?? remove.error)?.message}</p>
        )}
        <div className="form-actions">
          <button className="primary" disabled={!start || !end || add.isPending}>
            Close these dates
          </button>
        </div>
      </form>
    </>
  )
}

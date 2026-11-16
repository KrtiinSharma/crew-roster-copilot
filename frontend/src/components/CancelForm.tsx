import { useState, type FormEvent } from 'react'
import type { Disruption, FlightView } from '../api'
import DaySelect from './DaySelect'
import FlightSelect from './FlightSelect'
import { submitClass } from './formStyles'

interface Props {
  flights: FlightView[]
  disabled: boolean
  onApply: (d: Disruption) => void
}

export default function CancelForm({ flights, disabled, onApply }: Props) {
  const [day, setDay] = useState(0)
  const [flightId, setFlightId] = useState('')
  const options = flights.filter((f) => f.day === day)
  const selected = options.some((f) => f.id === flightId) ? flightId : (options[0]?.id ?? '')

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!selected) return
    setFlightId(selected)
    onApply({ kind: 'cancel', flight_id: selected })
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <h3 className="text-sm font-semibold">Cancel flight</h3>
      <div className="flex gap-2">
        <DaySelect label="Day" value={day} onChange={setDay} />
        <FlightSelect flights={options} value={selected} onChange={setFlightId} />
      </div>
      <button type="submit" className={submitClass} disabled={disabled || !selected}>
        Cancel flight
      </button>
    </form>
  )
}

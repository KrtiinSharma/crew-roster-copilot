import { useState, type FormEvent } from 'react'
import type { Disruption, FlightView } from '../api'
import DaySelect from './DaySelect'
import FlightSelect from './FlightSelect'
import { fieldClass, labelClass, submitClass } from './formStyles'

interface Props {
  flights: FlightView[]
  disabled: boolean
  onApply: (d: Disruption) => void
}

export default function DelayForm({ flights, disabled, onApply }: Props) {
  const [day, setDay] = useState(0)
  const [flightId, setFlightId] = useState('')
  const [minutes, setMinutes] = useState(60)
  const options = flights.filter((f) => f.day === day)
  const selected = options.some((f) => f.id === flightId) ? flightId : (options[0]?.id ?? '')
  const valid = minutes >= 30 && minutes <= 600 && minutes % 15 === 0

  function submit(e: FormEvent) {
    e.preventDefault()
    if (selected && valid) onApply({ kind: 'delay', flight_id: selected, minutes })
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <h3 className="text-sm font-semibold">Delay flight</h3>
      <div className="flex gap-2">
        <DaySelect label="Day" value={day} onChange={setDay} />
        <FlightSelect flights={options} value={selected} onChange={setFlightId} />
      </div>
      <label className="block">
        <span className={labelClass}>Delay in minutes (30–600, steps of 15)</span>
        <input
          type="number"
          className={fieldClass}
          min={30}
          max={600}
          step={15}
          value={minutes}
          aria-invalid={!valid}
          onChange={(e) => setMinutes(Number(e.target.value))}
        />
      </label>
      <button type="submit" className={submitClass} disabled={disabled || !selected || !valid}>
        Delay flight
      </button>
    </form>
  )
}

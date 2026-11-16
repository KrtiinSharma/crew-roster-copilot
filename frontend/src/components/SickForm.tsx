import { useState, type FormEvent } from 'react'
import type { Disruption, PilotView } from '../api'
import DaySelect from './DaySelect'
import { fieldClass, labelClass, submitClass } from './formStyles'

interface Props {
  pilots: PilotView[]
  disabled: boolean
  onApply: (d: Disruption) => void
}

export default function SickForm({ pilots, disabled, onApply }: Props) {
  const [pilotId, setPilotId] = useState(pilots[0]?.id ?? '')
  const [fromDay, setFromDay] = useState(0)
  const [toDay, setToDay] = useState(0)
  const bases = [...new Set(pilots.map((p) => p.base))].sort()
  const until = Math.max(fromDay, toDay)

  function submit(e: FormEvent) {
    e.preventDefault()
    if (pilotId) onApply({ kind: 'sick', pilot_id: pilotId, from_day: fromDay, to_day: until })
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <h3 className="text-sm font-semibold">Pilot sick</h3>
      <label className="block">
        <span className={labelClass}>Pilot</span>
        <select className={fieldClass} value={pilotId} onChange={(e) => setPilotId(e.target.value)}>
          {bases.map((b) => (
            <optgroup key={b} label={`${b} base`}>
              {pilots
                .filter((p) => p.base === b)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.id})
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </label>
      <div className="flex gap-2">
        <DaySelect label="From" value={fromDay} onChange={setFromDay} />
        <DaySelect label="To" value={until} onChange={setToDay} min={fromDay} />
      </div>
      <button type="submit" className={submitClass} disabled={disabled || !pilotId}>
        Mark sick
      </button>
    </form>
  )
}

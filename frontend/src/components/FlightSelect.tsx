import type { FlightView } from '../api'
import { flightOption } from '../lib/format'
import { fieldClass, labelClass } from './formStyles'

interface Props {
  flights: FlightView[]
  value: string
  onChange: (id: string) => void
}

export default function FlightSelect({ flights, value, onChange }: Props) {
  return (
    <label className="block min-w-0 flex-[2]">
      <span className={labelClass}>Flight</span>
      <select className={fieldClass} value={value} onChange={(e) => onChange(e.target.value)}>
        {flights.map((f) => (
          <option key={f.id} value={f.id}>
            {flightOption(f)}
          </option>
        ))}
      </select>
    </label>
  )
}

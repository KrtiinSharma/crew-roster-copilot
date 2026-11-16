import { DAYS, dayLabel } from '../lib/format'
import { fieldClass, labelClass } from './formStyles'

interface Props {
  label: string
  value: number
  onChange: (day: number) => void
  min?: number
}

export default function DaySelect({ label, value, onChange, min = 0 }: Props) {
  return (
    <label className="block min-w-0 flex-1">
      <span className={labelClass}>{label}</span>
      <select className={fieldClass} value={value} onChange={(e) => onChange(Number(e.target.value))}>
        {DAYS.filter((d) => d >= min).map((d) => (
          <option key={d} value={d}>
            {dayLabel(d)}
          </option>
        ))}
      </select>
    </label>
  )
}

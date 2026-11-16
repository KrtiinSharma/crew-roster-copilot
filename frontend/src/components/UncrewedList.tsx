import type { DutyView } from '../api'
import { dayLabel } from '../lib/format'

interface Props {
  duties: DutyView[]
  onSelect: (dutyId: string) => void
}

export default function UncrewedList({ duties, onSelect }: Props) {
  if (duties.length === 0) return null
  return (
    <section aria-labelledby="uncrewed-heading" className="rounded-lg border border-red-200 bg-red-50 p-3">
      <h3 id="uncrewed-heading" className="text-sm font-semibold text-red-800">
        Uncrewed duties ({duties.length})
      </h3>
      <ul className="mt-2 flex flex-wrap gap-2">
        {duties.map((d) => {
          const seats = [!d.cpt && 'captain', !d.fo && 'first officer'].filter(Boolean).join(' + ')
          return (
            <li key={d.id}>
              <button
                type="button"
                onClick={() => onSelect(d.id)}
                className="rounded-md border border-red-300 bg-white px-2 py-1 text-xs text-red-800 hover:bg-red-100 focus-visible:outline-2 focus-visible:outline-red-700"
              >
                <span className="font-semibold">{d.id}</span> · {dayLabel(d.day)} · {d.route} · no {seats}
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

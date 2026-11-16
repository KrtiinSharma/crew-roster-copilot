import type { DutyView } from '../api'
import { clockOn, hours, shortRoute } from '../lib/format'

export interface CellState {
  duty: DutyView | null
  sick: boolean
  unavailable: boolean
  changed: boolean
}

interface Props extends CellState {
  pilotName: string
  dayText: string
  selected: boolean
  onSelect: (dutyId: string) => void
}

export default function RosterCell({ duty, sick, unavailable, changed, pilotName, dayText, selected, onSelect }: Props) {
  const shade = sick ? 'sick-stripes' : unavailable ? 'bg-slate-200' : ''
  if (!duty) {
    return (
      <td className={`h-14 border-b border-l border-slate-100 p-1 text-center align-middle ${shade}`}>
        {sick && <span className="text-[11px] font-medium text-red-800">Sick</span>}
        {!sick && unavailable && <span className="text-[11px] text-slate-600">Off</span>}
      </td>
    )
  }
  const border = !duty.legal
    ? 'border-red-500 ring-1 ring-red-500'
    : changed
      ? 'border-amber-500 ring-2 ring-amber-400'
      : 'border-sky-200'
  const label = `${pilotName}, ${dayText}: duty ${duty.id}, ${duty.route}${duty.night ? ', night' : ''}${changed ? ', changed' : ''}${duty.legal ? '' : ', breaks a rule'}`
  return (
    <td className={`h-14 border-b border-l border-slate-100 p-1 align-middle ${shade}`}>
      <button
        type="button"
        onClick={() => onSelect(duty.id)}
        aria-label={label}
        aria-pressed={selected}
        className={`block w-full rounded-md border bg-sky-50 px-1.5 py-1 text-left leading-tight hover:bg-sky-100 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-sky-700 ${border} ${selected ? 'bg-sky-100' : ''}`}
      >
        <span className="flex items-center justify-between gap-1 text-xs font-semibold text-slate-900">
          <span className="truncate">{shortRoute(duty.route, duty.base)}</span>
          {duty.night && <span aria-hidden="true">🌙</span>}
          {!duty.legal && <span aria-hidden="true" className="text-red-700">!</span>}
        </span>
        <span className="block font-mono text-[10px] text-slate-700">
          {clockOn(duty.report, duty.day)}–{clockOn(duty.release, duty.day)}
        </span>
        <span className="block text-[10px] text-slate-600">FT {hours(duty.flight_time_h)}</span>
      </button>
    </td>
  )
}

import { MAX_DISRUPTIONS, type Disruption, type FlightView, type PilotView } from '../api'
import { describeDisruption } from '../lib/format'
import CancelForm from './CancelForm'
import DelayForm from './DelayForm'
import SickForm from './SickForm'

interface Props {
  pilots: PilotView[]
  flights: FlightView[]
  disruptions: Disruption[]
  busy: boolean
  onApply: (d: Disruption) => void
  onRemove: (index: number) => void
}

export default function DisruptionPanel({ pilots, flights, disruptions, busy, onApply, onRemove }: Props) {
  const pilotMap = new Map(pilots.map((p) => [p.id, p]))
  const flightMap = new Map(flights.map((f) => [f.id, f]))
  const full = disruptions.length >= MAX_DISRUPTIONS
  const disabled = busy || full

  return (
    <section aria-labelledby="disruptions-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="disruptions-heading" className="text-base font-semibold">
        Disruptions
      </h2>
      <p className="mt-0.5 text-xs text-slate-600">
        Each change re-plans the week, keeping as much of the original roster as the rules allow.
      </p>

      <div className="mt-3 grid gap-4 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
        <SickForm pilots={pilots} disabled={disabled} onApply={onApply} />
        <DelayForm flights={flights} disabled={disabled} onApply={onApply} />
        <CancelForm flights={flights} disabled={disabled} onApply={onApply} />
      </div>
      {full && (
        <p className="mt-2 text-xs text-amber-800">
          Limit of {MAX_DISRUPTIONS} disruptions reached; remove one to add another.
        </p>
      )}

      <h3 className="mt-4 text-sm font-semibold">Applied ({disruptions.length})</h3>
      {disruptions.length === 0 ? (
        <p className="mt-1 text-xs text-slate-500">None yet: the roster below is the original plan.</p>
      ) : (
        <ul className="mt-2 flex flex-wrap gap-2">
          {disruptions.map((d, i) => {
            const text = describeDisruption(d, pilotMap, flightMap)
            return (
              <li
                key={`${i}-${text}`}
                className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-slate-100 py-0.5 pr-1 pl-3 text-xs text-slate-800"
              >
                {text}
                <button
                  type="button"
                  onClick={() => onRemove(i)}
                  disabled={busy}
                  aria-label={`Remove: ${text}`}
                  className="rounded-full px-1.5 text-sm leading-none text-slate-500 hover:bg-slate-200 hover:text-slate-900 focus-visible:outline-2 focus-visible:outline-sky-700 disabled:opacity-50"
                >
                  ×
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

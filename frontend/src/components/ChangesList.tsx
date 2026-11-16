import type { ChangeView, PilotView } from '../api'
import { pilotName, seatLabel } from '../lib/format'

interface Props {
  changes: ChangeView[]
  pilots: Map<string, PilotView>
  onSelect: (dutyId: string) => void
}

export default function ChangesList({ changes, pilots, onSelect }: Props) {
  return (
    <section aria-labelledby="changes-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="changes-heading" className="text-base font-semibold">
        What changed ({changes.length})
      </h2>
      {changes.length === 0 ? (
        <p className="mt-1 text-sm text-slate-500">No assignments changed.</p>
      ) : (
        <ul className="mt-2 divide-y divide-slate-100">
          {changes.map((c) => {
            const rules = [...new Set(c.reasons.map((r) => r.rule))]
            return (
              <li key={c.id} className="py-2.5 text-sm">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <button
                    type="button"
                    onClick={() => onSelect(c.duty_id)}
                    className="font-mono text-xs font-semibold text-sky-800 underline decoration-sky-300 underline-offset-2 hover:decoration-sky-700 focus-visible:outline-2 focus-visible:outline-sky-700"
                  >
                    {c.duty_id}
                  </button>
                  <span className="text-xs text-slate-500">{seatLabel(c.role)}</span>
                  <span className="text-xs text-slate-800">
                    {pilotName(pilots, c.old_pilot)} → <strong className="font-semibold">{pilotName(pilots, c.new_pilot)}</strong>
                  </span>
                </div>
                <p className="mt-1 text-slate-700">{c.explanation}</p>
                {rules.length > 0 && (
                  <ul aria-label="Reasons" className="mt-1.5 flex flex-wrap gap-1">
                    {rules.map((r) => (
                      <li key={r} className="rounded bg-amber-50 px-1.5 py-0.5 font-mono text-[11px] text-amber-900 ring-1 ring-amber-200">
                        {r}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

import { useEffect, useRef, type ReactNode } from 'react'
import type { ChangeView, DutyView, FlightView, PilotView } from '../api'
import { clock, clockOn, dayLabel, hours, pilotName, seatLabel } from '../lib/format'

interface Props {
  duty: DutyView
  flights: Map<string, FlightView>
  pilots: Map<string, PilotView>
  changes: ChangeView[]
  onClose: () => void
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-3 py-1">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-900">{children}</dd>
    </div>
  )
}

export default function DutyCard({ duty, flights, pilots, changes, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [duty.id, onClose])

  return (
    <aside
      role="dialog"
      aria-labelledby="duty-card-heading"
      className="fixed inset-x-0 bottom-0 z-40 max-h-[80vh] overflow-y-auto rounded-t-xl border border-slate-200 bg-white p-4 shadow-2xl sm:inset-x-auto sm:top-4 sm:right-4 sm:bottom-auto sm:w-96 sm:rounded-xl"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 id="duty-card-heading" className="font-mono text-base font-semibold">{duty.id}</h2>
          <p className="text-sm text-slate-600">
            {dayLabel(duty.day)} · {duty.route}
          </p>
        </div>
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          aria-label="Close duty details"
          className="rounded-md px-2 py-1 text-lg leading-none text-slate-500 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-sky-700"
        >
          ×
        </button>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
        {duty.night && <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-indigo-800">🌙 Night duty</span>}
        {duty.legal ? (
          <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-800">Within the rules ✓</span>
        ) : (
          <span className="rounded bg-red-50 px-1.5 py-0.5 text-red-800">Breaks a rule</span>
        )}
      </div>

      <dl className="mt-3 divide-y divide-slate-100 text-sm">
        <Row label="Captain">{pilotName(pilots, duty.cpt)}</Row>
        <Row label="First officer">{pilotName(pilots, duty.fo)}</Row>
        <Row label="Report – release">
          {clock(duty.report)} – {clockOn(duty.release, duty.day)}
        </Row>
        <Row label="Duty time">{hours(duty.duty_h)} h</Row>
        <Row label="Flight time">{hours(duty.flight_time_h)} h</Row>
        <Row label="Landings">{duty.landings}</Row>
      </dl>

      <h3 className="mt-4 text-sm font-semibold">Flights</h3>
      <ul className="mt-1 space-y-1 text-sm">
        {duty.flight_ids.map((id) => {
          const f = flights.get(id)
          return (
            <li key={id} className="flex justify-between gap-2 font-mono text-xs">
              <span>{id}</span>
              {f && (
                <span className="text-slate-600">
                  {f.origin}→{f.dest} {clock(f.dep)}–{clockOn(f.arr, f.day)}
                </span>
              )}
            </li>
          )
        })}
      </ul>

      {changes.length > 0 && (
        <>
          <h3 className="mt-4 text-sm font-semibold">What changed</h3>
          <ul className="mt-1 space-y-2">
            {changes.map((c) => (
              <li key={c.id} className="rounded-md border border-amber-300 bg-amber-50 p-2 text-sm">
                <p className="text-xs font-medium text-amber-900">
                  {seatLabel(c.role)}: {pilotName(pilots, c.old_pilot)} → {pilotName(pilots, c.new_pilot)}
                </p>
                <p className="mt-1 text-slate-800">{c.explanation}</p>
              </li>
            ))}
          </ul>
        </>
      )}
    </aside>
  )
}

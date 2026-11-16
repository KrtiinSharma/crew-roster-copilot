import { useMemo, useState } from 'react'
import type { DutyView, ScenarioView } from '../api'
import { DAYS, dayLabel } from '../lib/format'
import RosterCell, { type CellState } from './RosterCell'
import RosterLegend from './RosterLegend'
import UncrewedList from './UncrewedList'

interface Props {
  view: ScenarioView
  selectedDutyId: string | null
  onSelect: (dutyId: string) => void
}

type RankFilter = 'all' | 'CPT' | 'FO'

const selectClass =
  'rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus-visible:outline-2 focus-visible:outline-sky-700'

export default function RosterGrid({ view, selectedDutyId, onSelect }: Props) {
  const bases = useMemo(() => [...new Set(view.pilots.map((p) => p.base))].sort(), [view.pilots])
  const [base, setBase] = useState(bases[0] ?? 'DEL')
  const [rank, setRank] = useState<RankFilter>('all')
  const [changedOnly, setChangedOnly] = useState(false)

  // pilot id -> day -> duty they fly that day
  const dutyByPilotDay = useMemo(() => {
    const map = new Map<string, Map<number, DutyView>>()
    for (const d of view.duties) {
      for (const pid of [d.cpt, d.fo]) {
        if (!pid) continue
        if (!map.has(pid)) map.set(pid, new Map())
        map.get(pid)!.set(d.day, d)
      }
    }
    return map
  }, [view.duties])

  // "dutyId|pilotId" for every seat a pilot newly holds, plus every pilot touched by a change
  const { changedSeats, changedPilots } = useMemo(() => {
    const seats = new Set<string>()
    const pilots = new Set<string>()
    for (const c of view.changes) {
      if (c.new_pilot) {
        seats.add(`${c.duty_id}|${c.new_pilot}`)
        pilots.add(c.new_pilot)
      }
      if (c.old_pilot) pilots.add(c.old_pilot)
    }
    return { changedSeats: seats, changedPilots: pilots }
  }, [view.changes])

  const rows = view.pilots.filter(
    (p) =>
      p.base === base &&
      (rank === 'all' || p.rank === rank) &&
      (!changedOnly || changedPilots.has(p.id)),
  )
  const uncrewed = view.duties.filter((d) => !d.cpt || !d.fo)

  return (
    <section aria-labelledby="roster-heading" className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 id="roster-heading" className="text-base font-semibold">
          7-day roster
        </h2>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-1.5">
            <span className="text-slate-600">Base</span>
            <select className={selectClass} value={base} onChange={(e) => setBase(e.target.value)}>
              {bases.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1.5">
            <span className="text-slate-600">Rank</span>
            <select className={selectClass} value={rank} onChange={(e) => setRank(e.target.value as RankFilter)}>
              <option value="all">All</option>
              <option value="CPT">Captains</option>
              <option value="FO">First officers</option>
            </select>
          </label>
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={changedOnly}
              onChange={(e) => setChangedOnly(e.target.checked)}
              className="size-4 accent-sky-700"
            />
            <span>Changed only</span>
          </label>
        </div>
      </div>

      <RosterLegend />

      <div className="max-h-[70vh] overflow-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full min-w-[760px] border-separate border-spacing-0 text-sm">
          <caption className="sr-only">
            {base} pilots by day. Select a duty to see its details.
          </caption>
          <thead>
            <tr>
              <th scope="col" className="sticky top-0 left-0 z-20 w-40 border-b border-slate-200 bg-slate-100 px-2 py-2 text-left text-xs font-semibold text-slate-700">
                Pilot
              </th>
              {DAYS.map((d) => (
                <th key={d} scope="col" className="sticky top-0 z-10 border-b border-l border-slate-200 bg-slate-100 px-1 py-2 text-xs font-semibold text-slate-700">
                  {dayLabel(d)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} className="hover:bg-slate-50">
                <th scope="row" className="sticky left-0 z-10 w-40 border-b border-slate-100 bg-white px-2 py-1 text-left align-middle font-normal">
                  <span className="block truncate text-xs font-medium text-slate-900">{p.name}</span>
                  <span className="block font-mono text-[10px] text-slate-500">
                    {p.id} · {p.rank}
                  </span>
                </th>
                {DAYS.map((day) => {
                  const duty = dutyByPilotDay.get(p.id)?.get(day) ?? null
                  const state: CellState = {
                    duty,
                    sick: p.sick_days.includes(day),
                    unavailable: p.unavailable_days.includes(day),
                    changed: duty !== null && changedSeats.has(`${duty.id}|${p.id}`),
                  }
                  return (
                    <RosterCell
                      key={day}
                      {...state}
                      pilotName={p.name}
                      dayText={dayLabel(day)}
                      selected={duty !== null && duty.id === selectedDutyId}
                      onSelect={onSelect}
                    />
                  )
                })}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-sm text-slate-500">
                  No pilots match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <UncrewedList duties={uncrewed} onSelect={onSelect} />
    </section>
  )
}

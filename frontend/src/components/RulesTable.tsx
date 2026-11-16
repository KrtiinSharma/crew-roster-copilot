import type { RuleSet, Ruleset } from '../api'

type Kind = 'hours' | 'count' | 'window' | 'fdp'

// Rule keys from GET /rules. Time values arrive in minutes; counts as plain numbers.
const ROWS: { key: string; label: string; kind: Kind; source?: string }[] = [
  { key: 'max_ft_per_duty', label: 'Flight time per duty', kind: 'hours' },
  { key: 'max_fdp_by_landings', label: 'Flight duty period by landings', kind: 'fdp' },
  { key: 'night_start', label: 'Night window', kind: 'window', source: 'night_window' },
  { key: 'night_max_fdp', label: 'Flight duty period touching night', kind: 'hours' },
  { key: 'night_max_landings', label: 'Landings in a night duty', kind: 'count' },
  { key: 'max_consecutive_nights', label: 'Consecutive night duties', kind: 'count' },
  { key: 'min_rest', label: 'Minimum rest between duties', kind: 'hours' },
  { key: 'weekly_rest', label: 'Weekly continuous rest', kind: 'hours' },
  { key: 'ft_7d', label: 'Flight time, 7 days', kind: 'hours' },
  { key: 'ft_28d', label: 'Flight time, 28 days', kind: 'hours' },
  { key: 'duty_7d', label: 'Duty time, 7 days', kind: 'hours' },
  { key: 'duty_28d', label: 'Duty time, 28 days', kind: 'hours' },
]

const h = (minutes: number) => `${+(minutes / 60).toFixed(2)} h`
const hhmm = (minutes: number) =>
  `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`

function format(rules: RuleSet, key: string, kind: Kind): string {
  const v = rules[key]
  switch (kind) {
    case 'hours':
      return h(Number(v))
    case 'count':
      return String(v)
    case 'window':
      return `${hhmm(Number(rules.night_start))}–${hhmm(Number(rules.night_end))}`
    case 'fdp':
      return fdpByLandings(v as Record<string, number>)
  }
}

/** {"1": 780, "2": 780, "3": 750} → "13 h (1–2 landings) · 12.5 h (3)". */
function fdpByLandings(limits: Record<string, number>): string {
  const groups: { from: string; to: string; m: number }[] = []
  for (const [landings, m] of Object.entries(limits)) {
    const last = groups[groups.length - 1]
    if (last && last.m === m) last.to = landings
    else groups.push({ from: landings, to: landings, m })
  }
  return groups
    .map((g, i) => `${h(g.m)} (${g.from === g.to ? g.from : `${g.from}–${g.to}`}${i === 0 ? ' landings' : ''})`)
    .join(' · ')
}

interface Props {
  rules: Record<Ruleset, RuleSet>
}

export default function RulesTable({ rules }: Props) {
  const current = rules.dgca_current
  const exemption = rules.dgca_dec2025_exemption
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-left text-xs">
        <thead className="bg-slate-100 text-slate-700">
          <tr>
            <th scope="col" className="px-2 py-1.5">Rule (limit)</th>
            <th scope="col" className="px-2 py-1.5">Current rules</th>
            <th scope="col" className="px-2 py-1.5">Dec-2025 exemption</th>
            <th scope="col" className="px-2 py-1.5">Source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {ROWS.map((r) => {
            const a = format(current, r.key, r.kind)
            const b = format(exemption, r.key, r.kind)
            const src = r.source ?? r.key
            const srcA = current.sources[src]
            const srcB = exemption.sources[src]
            return (
              <tr key={r.key} className="align-top">
                <th scope="row" className="px-2 py-1.5 font-medium text-slate-800">{r.label}</th>
                <td className="px-2 py-1.5 tabular-nums">{a}</td>
                <td className={`px-2 py-1.5 tabular-nums ${a !== b ? 'font-semibold text-amber-800' : ''}`}>{b}</td>
                <td className="px-2 py-1.5 text-slate-600">
                  {srcA}
                  {srcB && srcB !== srcA && <span className="mt-1 block">Exemption: {srcB}</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

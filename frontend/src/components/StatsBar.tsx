import type { Stats } from '../api'
import Spinner from './Spinner'

interface Props {
  stats: Stats
  busy: boolean
}

function Tile({ label, value, tone = 'plain' }: { label: string; value: string; tone?: 'plain' | 'bad' | 'good' }) {
  const colour = { plain: 'text-slate-900', bad: 'text-red-700', good: 'text-emerald-700' }[tone]
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className={`mt-0.5 text-lg font-semibold tabular-nums ${colour}`}>{value}</dd>
    </div>
  )
}

export default function StatsBar({ stats, busy }: Props) {
  return (
    <section aria-label="Roster numbers" aria-busy={busy}>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Tile label="Duties" value={String(stats.duties)} />
        <Tile label="Crewed seats" value={`${stats.crewed}/${stats.slots}`} />
        <Tile label="Uncrewed" value={String(stats.uncovered)} tone={stats.uncovered > 0 ? 'bad' : 'plain'} />
        <Tile label="Assignments changed" value={String(stats.changes)} />
        <Tile
          label="Rule breaches"
          value={stats.violations === 0 ? '0 breaches ✓' : `${stats.violations} breaches`}
          tone={stats.violations === 0 ? 'good' : 'bad'}
        />
        <Tile label="Solve time" value={stats.solve_seconds < 0.1 ? '< 0.1 s' : `${stats.solve_seconds.toFixed(1)} s`} />
      </dl>
      <div className="mt-2 h-5">{busy && <Spinner label="Re-planning…" />}</div>
    </section>
  )
}

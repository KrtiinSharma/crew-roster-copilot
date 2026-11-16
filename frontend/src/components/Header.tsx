import type { Ruleset } from '../api'

const RULESETS: { id: Ruleset; label: string }[] = [
  { id: 'dgca_current', label: 'Current rules' },
  { id: 'dgca_dec2025_exemption', label: 'Dec-2025 exemption' },
]

interface Props {
  ruleset: Ruleset
  label: string | null
  busy: boolean
  onRuleset: (r: Ruleset) => void
  onReset: () => void
  onAbout: () => void
}

const ghostButton =
  'rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-700 disabled:opacity-50'

export default function Header({ ruleset, label, busy, onRuleset, onReset, onAbout }: Props) {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-[110rem] flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold text-slate-900">
            Crew Roster Copilot <span className="font-normal text-slate-500">· Skyline Air</span>
          </h1>
          {label && <p className="truncate text-xs text-slate-600">{label}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div role="group" aria-label="Ruleset" className="inline-flex rounded-md border border-slate-300 bg-slate-100 p-0.5">
            {RULESETS.map((r) => (
              <button
                key={r.id}
                type="button"
                aria-pressed={ruleset === r.id}
                disabled={busy}
                onClick={() => ruleset !== r.id && onRuleset(r.id)}
                className={`rounded px-2.5 py-1 text-sm font-medium focus-visible:outline-2 focus-visible:outline-sky-700 disabled:cursor-wait ${
                  ruleset === r.id ? 'bg-white text-sky-800 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
          <button type="button" onClick={onReset} disabled={busy} className={ghostButton}>
            Reset
          </button>
          <button type="button" onClick={onAbout} className={ghostButton}>
            About
          </button>
        </div>
      </div>
    </header>
  )
}

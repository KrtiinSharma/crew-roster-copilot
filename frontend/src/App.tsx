import { useEffect, useState } from 'react'
import { replan, type Ruleset, type ScenarioView } from './api'

export default function App() {
  const [ruleset] = useState<Ruleset>('dgca_current')
  const [view, setView] = useState<ScenarioView | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    replan(ruleset, [])
      .then((v) => !cancelled && setView(v))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [ruleset])

  return (
    <main className="mx-auto max-w-6xl p-4">
      <h1 className="text-xl font-semibold">Crew Roster Copilot · Skyline Air</h1>
      {error && <p role="alert" className="mt-4 text-red-700">{error}</p>}
      {!view && !error && <p className="mt-4 text-slate-600">Loading roster…</p>}
      {view && (
        <p className="mt-4 text-slate-700">
          {view.label}: {view.stats.duties} duties, {view.pilots.length} pilots,{' '}
          {view.stats.crewed}/{view.stats.slots} slots crewed.
        </p>
      )}
    </main>
  )
}

import { useCallback, useEffect, useMemo, useState } from 'react'
import { replan, type Ruleset, type ScenarioView } from './api'
import DutyCard from './components/DutyCard'
import RosterGrid from './components/RosterGrid'
import Spinner from './components/Spinner'
import StatsBar from './components/StatsBar'

export default function App() {
  const [ruleset] = useState<Ruleset>('dgca_current')
  const [view, setView] = useState<ScenarioView | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedDutyId, setSelectedDutyId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setBusy(true)
    replan(ruleset, [])
      .then((v) => !cancelled && setView(v))
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setBusy(false))
    return () => {
      cancelled = true
    }
  }, [ruleset])

  const pilots = useMemo(() => new Map(view?.pilots.map((p) => [p.id, p])), [view])
  const flights = useMemo(() => new Map(view?.flights.map((f) => [f.id, f])), [view])
  const selectedDuty = view?.duties.find((d) => d.id === selectedDutyId) ?? null
  const closeCard = useCallback(() => setSelectedDutyId(null), [])

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-4">
      <h1 className="text-xl font-semibold">Crew Roster Copilot · Skyline Air</h1>
      {error && <p role="alert" className="text-red-700">{error}</p>}
      {!view && !error && <Spinner label="Loading roster…" />}
      {view && (
        <>
          <StatsBar stats={view.stats} busy={busy} />
          <RosterGrid view={view} selectedDutyId={selectedDutyId} onSelect={setSelectedDutyId} />
        </>
      )}
      {view && selectedDuty && (
        <DutyCard
          duty={selectedDuty}
          flights={flights}
          pilots={pilots}
          changes={view.changes.filter((c) => c.duty_id === selectedDuty.id)}
          onClose={closeCard}
        />
      )}
    </main>
  )
}

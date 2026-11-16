import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { replan, type Disruption, type Ruleset, type ScenarioView } from './api'
import ChangesList from './components/ChangesList'
import DisruptionPanel from './components/DisruptionPanel'
import DutyCard from './components/DutyCard'
import RosterGrid from './components/RosterGrid'
import Spinner from './components/Spinner'
import StatsBar from './components/StatsBar'

export default function App() {
  const [ruleset, setRuleset] = useState<Ruleset>('dgca_current')
  const [disruptions, setDisruptions] = useState<Disruption[]>([])
  const [view, setView] = useState<ScenarioView | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedDutyId, setSelectedDutyId] = useState<string | null>(null)
  const latest = useRef(0)

  // Re-plan a whole scenario. The scenario is only committed once the server accepts it,
  // so a rejected disruption (e.g. 422) is dropped and the previous view stays on screen.
  const plan = useCallback(async (nextRuleset: Ruleset, next: Disruption[]) => {
    const id = ++latest.current
    setBusy(true)
    setError(null)
    try {
      const v = await replan(nextRuleset, next)
      if (id !== latest.current) return
      setView(v)
      setRuleset(nextRuleset)
      setDisruptions(next)
    } catch (e) {
      if (id === latest.current) setError((e as Error).message)
    } finally {
      if (id === latest.current) setBusy(false)
    }
  }, [])

  useEffect(() => {
    void plan('dgca_current', [])
  }, [plan])

  const pilots = useMemo(() => new Map(view?.pilots.map((p) => [p.id, p])), [view])
  const flights = useMemo(() => new Map(view?.flights.map((f) => [f.id, f])), [view])
  const selectedDuty = view?.duties.find((d) => d.id === selectedDutyId) ?? null
  const closeCard = useCallback(() => setSelectedDutyId(null), [])

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-4">
      <h1 className="text-xl font-semibold">Crew Roster Copilot · Skyline Air</h1>
      {error && (
        <p role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      )}
      {!view && !error && <Spinner label="Loading roster…" />}
      {view && (
        <>
          <DisruptionPanel
            pilots={view.pilots}
            flights={view.flights}
            disruptions={disruptions}
            busy={busy}
            onApply={(d) => plan(ruleset, [...disruptions, d])}
            onRemove={(i) => plan(ruleset, disruptions.filter((_, j) => j !== i))}
          />
          <StatsBar stats={view.stats} busy={busy} />
          <ChangesList changes={view.changes} pilots={pilots} onSelect={setSelectedDutyId} />
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

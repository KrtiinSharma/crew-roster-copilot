import { useEffect, useRef, useState } from 'react'
import { fetchRules, type RuleSet, type Ruleset } from '../api'
import RulesTable from './RulesTable'
import Spinner from './Spinner'

const REPO_URL = 'https://github.com/KrtiinSharma/crew-roster-copilot'

interface Props {
  onClose: () => void
}

export default function AboutView({ onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const [rules, setRules] = useState<Record<Ruleset, RuleSet> | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (ref.current && !ref.current.open) ref.current.showModal()
    fetchRules()
      .then(setRules)
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby="about-heading"
      className="m-auto w-[min(56rem,calc(100%-2rem))] rounded-xl p-0 text-slate-800 shadow-2xl backdrop:bg-slate-900/50"
    >
      <div className="max-h-[85vh] overflow-y-auto p-5">
        <div className="flex items-start justify-between gap-4">
          <h2 id="about-heading" className="text-lg font-semibold text-slate-900">
            About Crew Roster Copilot
          </h2>
          <button
            type="button"
            onClick={() => ref.current?.close()}
            aria-label="Close about"
            className="rounded-md px-2 py-1 text-lg leading-none text-slate-500 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-sky-700"
          >
            ×
          </button>
        </div>

        <div className="mt-3 space-y-3 text-sm leading-relaxed">
          <p>
            A 7-day pilot roster for Skyline Air's Delhi and Mumbai bases, built under India's DGCA
            flight duty time limits. Add a sick pilot, a delay or a cancellation and the roster is
            re-planned in a few seconds, keeping as many of the original assignments as the rules allow.
            Each change comes with a plain-language reason.
          </p>
          <h3 className="font-semibold text-slate-900">How the optimiser works</h3>
          <ol className="list-decimal space-y-1 pl-5">
            <li>
              <strong>Duties.</strong> Flights are chained into out-and-back duties from each base; a
              CP-SAT set-partitioning model covers every flight with the fewest duties.
            </li>
            <li>
              <strong>Pilots.</strong> A second CP-SAT model gives each duty a captain and a first officer
              while respecting rest, cumulative flight and duty limits, night rules and leave. A re-plan
              ranks its goals: crew every duty, then change as few assignments as possible, then keep
              flying hours fair.
            </li>
          </ol>
          <h3 className="font-semibold text-slate-900">The number check</h3>
          <p>
            The copilot answers by calling the optimiser's tools. Every number in its answer must appear
            in those tool outputs or in your question; if one does not, it gets one retry and is otherwise
            shown with an "unverified numbers" warning. Change explanations get the same check.
          </p>
          <h3 className="font-semibold text-slate-900">DGCA rules modelled</h3>
          {error && <p role="alert" className="text-red-800">Could not load the rules: {error}</p>}
          {!rules && !error && <Spinner label="Loading rules…" />}
          {rules && <RulesTable rules={rules} />}
          <p className="rounded-md bg-slate-100 px-3 py-2 text-slate-700">
            Fictional airline. Inspired by the December 2025 crew-rostering disruption in Indian aviation;
            not affiliated with any airline.
          </p>
          <p>
            Source code:{' '}
            <a href={REPO_URL} className="text-sky-800 underline underline-offset-2 hover:text-sky-950" target="_blank" rel="noreferrer">
              github.com/KrtiinSharma/crew-roster-copilot
            </a>
          </p>
        </div>
      </div>
    </dialog>
  )
}

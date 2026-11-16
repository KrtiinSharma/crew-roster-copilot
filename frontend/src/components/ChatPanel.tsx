import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  ApiError,
  chat,
  MAX_CHAT_MESSAGES,
  MAX_MESSAGE_CHARS,
  type ChatTurn,
  type Disruption,
  type Ruleset,
} from '../api'
import ChatMessage, { type ChatEntry } from './ChatMessage'
import Spinner from './Spinner'
import { submitClass } from './formStyles'

const EXAMPLES = [
  'Who could replace the captain of BOM-D3-05 if they fell sick?',
  'How many hours can DEL-C01 still fly by day 4?',
  'How many pilots would BOM need under the Dec-2025 exemption?',
]

interface Props {
  ruleset: Ruleset
  disruptions: Disruption[]
  busy: boolean
  entries: ChatEntry[]
  onEntries: (entries: ChatEntry[]) => void
}

function errorText(e: unknown): string {
  if (e instanceof ApiError && e.status === 503) return "The assistant isn't configured yet (no LLM API key)."
  return e instanceof Error ? e.message : 'Something went wrong.'
}

export default function ChatPanel({ ruleset, disruptions, busy, entries, onEntries }: Props) {
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scenarioKey = JSON.stringify([ruleset, disruptions])
  const scenarioRef = useRef(scenarioKey)
  scenarioRef.current = scenarioKey
  const listRef = useRef<HTMLOListElement>(null)

  useEffect(() => {
    listRef.current?.lastElementChild?.scrollIntoView({ block: 'nearest' })
  }, [entries, pending])

  async function ask(question: string) {
    const text = question.trim().slice(0, MAX_MESSAGE_CHARS)
    if (!text || pending) return
    const withQuestion: ChatEntry[] = [...entries, { role: 'user', content: text }]
    onEntries(withQuestion)
    setDraft('')
    setError(null)
    setPending(true)
    const askedFor = scenarioKey
    // The API accepts a bounded history; send the most recent turns only.
    // At most MAX_CHAT_MESSAGES - 1 previous turns plus the new question, starting on a user turn.
    let recent = withQuestion.slice(-MAX_CHAT_MESSAGES)
    while (recent.length > 1 && recent[0].role !== 'user') recent = recent.slice(1)
    const turns: ChatTurn[] = recent.map(({ role, content }) => ({ role, content: content.slice(0, MAX_MESSAGE_CHARS) }))
    try {
      const answer = await chat(ruleset, disruptions, turns)
      onEntries([...withQuestion, { role: 'assistant', content: answer.answer, answer, stale: askedFor !== scenarioRef.current }])
    } catch (e) {
      // Drop the unanswered question from the history and give it back for editing.
      onEntries(entries)
      setDraft(text)
      setError(errorText(e))
    } finally {
      setPending(false)
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    void ask(draft)
  }

  return (
    <section aria-labelledby="chat-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="chat-heading" className="text-base font-semibold">
        Ask the copilot
      </h2>
      <p className="mt-0.5 text-xs text-slate-600">
        Answers come from the optimiser's tools on the current scenario; every number is checked against
        the tool outputs.
      </p>

      {entries.length === 0 && (
        <ul aria-label="Example questions" className="mt-3 space-y-1.5">
          {EXAMPLES.map((q) => (
            <li key={q}>
              <button
                type="button"
                onClick={() => void ask(q)}
                disabled={pending}
                className="w-full rounded-md border border-slate-200 px-3 py-1.5 text-left text-sm text-slate-700 hover:border-sky-300 hover:bg-sky-50 focus-visible:outline-2 focus-visible:outline-sky-700 disabled:opacity-60"
              >
                {q}
              </button>
            </li>
          ))}
        </ul>
      )}

      {entries.length > 0 && (
        <ol ref={listRef} aria-live="polite" className="mt-3 max-h-[28rem] space-y-3 overflow-y-auto">
          {entries.map((m, i) => (
            <ChatMessage key={i} entry={m} />
          ))}
        </ol>
      )}

      <div className="mt-2 min-h-5">
        {pending && <Spinner label="Thinking…" />}
        {error && (
          <p role="alert" className="text-sm text-red-800">
            {error}
          </p>
        )}
      </div>

      <form onSubmit={submit} className="mt-2 flex gap-2">
        <label htmlFor="chat-input" className="sr-only">
          Your question
        </label>
        <input
          id="chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={MAX_MESSAGE_CHARS}
          placeholder="Ask about the roster…"
          className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus-visible:outline-2 focus-visible:outline-sky-700"
        />
        <button type="submit" className={submitClass} disabled={pending || busy || !draft.trim()}>
          Ask
        </button>
      </form>
    </section>
  )
}

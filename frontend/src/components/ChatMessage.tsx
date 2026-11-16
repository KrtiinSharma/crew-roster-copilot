import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { AgentAnswer } from '../api'

export interface ChatEntry {
  role: 'user' | 'assistant'
  content: string
  answer?: AgentAnswer
  /** The scenario changed while this answer was being produced. */
  stale?: boolean
}

function VerifiedBadge({ answer, stale }: { answer: AgentAnswer; stale?: boolean }) {
  if (stale) {
    return (
      <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-900 ring-1 ring-amber-300">
        answered for an earlier scenario
      </span>
    )
  }
  if (answer.verified) {
    return (
      <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-800 ring-1 ring-emerald-200">
        verified ✓
      </span>
    )
  }
  return (
    <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-900 ring-1 ring-amber-300">
      unverified numbers{answer.ungrounded.length > 0 && `: ${answer.ungrounded.join(', ')}`}
    </span>
  )
}

function ToolsUsed({ answer }: { answer: AgentAnswer }) {
  if (answer.tool_calls.length === 0) return null
  return (
    <details className="text-xs text-slate-600">
      <summary className="cursor-pointer rounded select-none hover:text-slate-900 focus-visible:outline-2 focus-visible:outline-sky-700">
        Tools used ({answer.tool_calls.length})
      </summary>
      <ul className="mt-1 space-y-0.5 pl-4">
        {answer.tool_calls.map((t, i) => (
          <li key={i} className="flex gap-2 font-mono">
            <span className={t.ok ? 'text-emerald-700' : 'text-red-700'} aria-label={t.ok ? 'succeeded' : 'failed'}>
              {t.ok ? '✓' : '✗'}
            </span>
            <span className="text-slate-800">{t.name}</span>
            <span>{t.seconds.toFixed(1)} s</span>
          </li>
        ))}
      </ul>
    </details>
  )
}

export default function ChatMessage({ entry }: { entry: ChatEntry }) {
  if (entry.role === 'user') {
    return (
      <li className="ml-8 rounded-lg bg-sky-700 px-3 py-2 text-sm whitespace-pre-wrap text-white">
        <span className="sr-only">You: </span>
        {entry.content}
      </li>
    )
  }
  return (
    <li className="mr-4 space-y-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
      <span className="sr-only">Copilot: </span>
      <div className="prose-answer text-slate-800">
        <Markdown remarkPlugins={[remarkGfm]}>{entry.content}</Markdown>
      </div>
      {entry.answer && (
        <div className="flex flex-wrap items-start gap-3">
          <VerifiedBadge answer={entry.answer} stale={entry.stale} />
          <ToolsUsed answer={entry.answer} />
        </div>
      )}
    </li>
  )
}

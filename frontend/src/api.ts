// Backend base URL: "/api" in dev (Vite proxies and strips it), the Cloud Run URL in production.
export const API_URL = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/$/, '')

export type Ruleset = 'dgca_current' | 'dgca_dec2025_exemption'

export type Disruption =
  | { kind: 'sick'; pilot_id: string; from_day: number; to_day: number }
  | { kind: 'delay'; flight_id: string; minutes: number }
  | { kind: 'cancel'; flight_id: string }

export interface Violation {
  rule: string
  pilot_id: string | null
  duty_id: string | null
  day: number | null
  value: number
  limit: number
  message: string
}

export interface PilotView {
  id: string
  name: string
  rank: 'CPT' | 'FO'
  base: string
  unavailable_days: number[]
  sick_days: number[]
}

export interface FlightView {
  id: string
  day: number
  origin: string
  dest: string
  dep: string
  arr: string
  dep_min: number
  arr_min: number
}

export interface DutyView {
  id: string
  base: string
  day: number
  route: string
  flight_ids: string[]
  report: string
  release: string
  report_min: number
  release_min: number
  flight_time_h: number
  duty_h: number
  landings: number
  night: boolean
  legal: boolean
  cpt: string | null
  fo: string | null
}

export interface ChangeView {
  id: string
  duty_id: string
  role: 'CPT' | 'FO'
  old_pilot: string | null
  new_pilot: string | null
  reasons: Violation[]
  explanation: string
}

export interface Stats {
  duties: number
  slots: number
  crewed: number
  uncovered: number
  changes: number
  violations: number
  solve_seconds: number
  status: string
}

export interface ScenarioView {
  ruleset: Ruleset
  label: string
  disruptions: Disruption[]
  stats: Stats
  pilots: PilotView[]
  flights: FlightView[]
  duties: DutyView[]
  changes: ChangeView[]
  illegal_duties: string[]
}

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface ToolCallTrace {
  name: string
  args: Record<string, unknown>
  seconds: number
  ok: boolean
}

export interface AgentAnswer {
  answer: string
  verified: boolean
  ungrounded: string[]
  tool_calls: ToolCallTrace[]
}

/** Rule values as served by GET /rules: times in minutes, counts as plain numbers. */
export interface RuleSet {
  name: string
  label: string
  sources: Record<string, string>
  [key: string]: unknown
}

/** An API failure that keeps the HTTP status, so the UI can word 429/503 specially. */
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function detailOf(res: Response): Promise<string> {
  try {
    const body = await res.json()
    const detail = body?.detail
    if (typeof detail === 'string') return detail
    // FastAPI request-validation errors: a list of {loc, msg}.
    if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join('; ')
  } catch {
    // not JSON: fall through to the status text
  }
  return res.statusText || `Request failed (${res.status})`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) throw new ApiError(res.status, await detailOf(res))
  return res.json() as Promise<T>
}

export function replan(ruleset: Ruleset, disruptions: Disruption[]): Promise<ScenarioView> {
  return request('/replan', { method: 'POST', body: JSON.stringify({ ruleset, disruptions }) })
}

export function chat(
  ruleset: Ruleset,
  disruptions: Disruption[],
  messages: ChatTurn[],
): Promise<AgentAnswer> {
  return request('/chat', {
    method: 'POST',
    body: JSON.stringify({ ruleset, disruptions, messages }),
  })
}

export function fetchRules(): Promise<Record<Ruleset, RuleSet>> {
  return request('/rules')
}

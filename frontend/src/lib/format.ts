import type { PilotView } from '../api'

export const DAYS = [0, 1, 2, 3, 4, 5, 6] as const

export function dayLabel(day: number): string {
  return `Day ${day}`
}

/** "BOM-DEL-BOM-PNQ-BOM" → "DEL·PNQ": the outstations visited, without the home base. */
export function shortRoute(route: string, base: string): string {
  const stops = route.split('-').filter((a) => a !== base)
  return [...new Set(stops)].join('·') || route
}

/** "D6 18:00" → "18:00"; the API prefixes clock times with their day. */
export function clock(stamp: string): string {
  return stamp.replace(/^D\d+\s*/, '')
}

/** Clock time, with "+1" when it falls on a later day than `day` (overnight duties). */
export function clockOn(stamp: string, day: number): string {
  const d = Number(stamp.match(/^D(\d+)/)?.[1] ?? day)
  return d > day ? `${clock(stamp)}+${d - day}` : clock(stamp)
}

/** 2.33 → "2:20" (hours as h:mm). */
export function hours(h: number): string {
  const total = Math.round(h * 60)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

export function pilotName(pilots: Map<string, PilotView>, id: string | null): string {
  if (!id) return 'Uncrewed'
  return pilots.get(id)?.name ?? id
}

export function seatLabel(role: 'CPT' | 'FO'): string {
  return role === 'CPT' ? 'Captain' : 'First officer'
}

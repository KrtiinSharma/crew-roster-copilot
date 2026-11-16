import type { ReactNode } from 'react'

function Swatch({ className, children }: { className: string; children?: ReactNode }) {
  return (
    <span aria-hidden="true" className={`inline-flex size-4 items-center justify-center rounded text-[10px] ${className}`}>
      {children}
    </span>
  )
}

export default function RosterLegend() {
  return (
    <ul aria-label="Legend" className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
      <li className="flex items-center gap-1.5"><Swatch className="border border-sky-200 bg-sky-50" />Duty (outstations, report–release, flight time)</li>
      <li className="flex items-center gap-1.5"><Swatch className="">🌙</Swatch>Night duty (touches 00:00–06:00)</li>
      <li className="flex items-center gap-1.5"><Swatch className="border border-amber-500 bg-sky-50 ring-2 ring-amber-400" />Assignment changed</li>
      <li className="flex items-center gap-1.5"><Swatch className="border border-red-500 bg-sky-50 font-bold text-red-700">!</Swatch>Breaks a rule</li>
      <li className="flex items-center gap-1.5"><Swatch className="sick-stripes" />Sick</li>
      <li className="flex items-center gap-1.5"><Swatch className="bg-slate-200" />Unavailable (leave / training)</li>
      <li>+1 = next day</li>
    </ul>
  )
}

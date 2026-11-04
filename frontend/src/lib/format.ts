const WD = ['일', '월', '화', '수', '목', '금', '토']
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}.${p(d.getMonth() + 1)}.${p(d.getDate())} (${WD[d.getDay()]}) ${p(d.getHours())}:${p(d.getMinutes())}`
}
export function fmtRange(start: string, end: string | null): string {
  if (!end) return fmtDateTime(start)
  const e = new Date(end)
  return `${fmtDateTime(start)} ~ ${String(e.getHours()).padStart(2, '0')}:${String(e.getMinutes()).padStart(2, '0')}`
}
export function relDays(iso: string): string {
  const diff = Math.round((new Date(iso).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000)
  if (diff === 0) return '오늘'
  if (diff === 1) return '내일'
  if (diff > 0) return `D-${diff}`
  return `${-diff}일 전`
}
export function fmtSize(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}
/** datetime-local 입력값(로컬) ↔ ISO(UTC) */
export function localInputToIso(v: string): string { return new Date(v).toISOString() }
export function isoToLocalInput(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

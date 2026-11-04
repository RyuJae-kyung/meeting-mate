import type { Basis, BriefingItem } from '../api/types'

export default function ItemsEditor({ items, onChange }: { items: BriefingItem[]; onChange: (v: BriefingItem[]) => void }) {
  const upd = (i: number, patch: Partial<BriefingItem>) => onChange(items.map((x, j) => (j === i ? { ...x, ...patch } : x)))
  return (
    <div className="space-y-2">
      {items.map((it, i) => (
        <div key={i} className="flex flex-col gap-2 rounded-md border border-gray-200 p-2 sm:flex-row sm:items-start">
          <select className="input sm:w-28" value={it.basis} onChange={(e) => upd(i, { basis: e.target.value as Basis })} aria-label="근거 구분">
            <option value="fact">자료 근거</option><option value="inference">AI 추론</option><option value="uncertain">확인 필요</option>
          </select>
          <textarea className="input flex-1" rows={2} value={it.text} onChange={(e) => upd(i, { text: e.target.value })} aria-label="내용" />
          <input className="input sm:w-40" placeholder="출처 (선택)" value={it.source ?? ''} onChange={(e) => upd(i, { source: e.target.value || null })} aria-label="출처" />
          <button type="button" className="btn-ghost text-red-600" onClick={() => onChange(items.filter((_, j) => j !== i))}>삭제</button>
        </div>
      ))}
      <button type="button" className="btn-ghost text-indigo-600" onClick={() => onChange([...items, { text: '', basis: 'inference', source: null }])}>+ 항목 추가</button>
    </div>
  )
}

/** 빈 텍스트 항목 제거 (서버 검증: text 최소 1자) */
export function cleanItems(items: BriefingItem[]): BriefingItem[] {
  return items.filter((i) => i.text.trim()).map((i) => ({ ...i, text: i.text.trim() }))
}

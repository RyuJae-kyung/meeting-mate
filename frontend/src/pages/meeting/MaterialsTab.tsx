import { useRef, useState } from 'react'
import { api, errorMessage } from '../../api/client'
import type { Material, MaterialDetail, MeetingDetail } from '../../api/types'
import { Alert, EmptyState, Modal, SourceBadge, Spinner } from '../../components/ui'
import { fmtDateTime, fmtSize } from '../../lib/format'

export default function MaterialsTab({ m, reload }: { m: MeetingDetail; reload: () => Promise<unknown> }) {
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [view, setView] = useState<MaterialDetail | null>(null)
  const ref = useRef<HTMLInputElement>(null)

  async function upload(list: FileList | null) {
    if (!list?.length) return
    setBusy('upload'); setErr('')
    const fd = new FormData()
    Array.from(list).forEach((f) => fd.append('files', f))
    try {
      const r = await api.post<Material[]>(`/meetings/${m.id}/materials`, fd)
      const failed = r.data.filter((x) => x.status === 'failed')
      if (failed.length) setErr(failed.map((f) => `${f.original_filename}: ${f.error}`).join(' / '))
      await reload()
    } catch (e) { setErr(errorMessage(e)) } finally { setBusy(''); if (ref.current) ref.current.value = '' }
  }
  async function open(id: number) {
    try { setView((await api.get<MaterialDetail>(`/materials/${id}`)).data) } catch (e) { setErr(errorMessage(e)) }
  }
  async function reanalyze(id: number) {
    setBusy(`re-${id}`); setErr('')
    try { await api.post(`/materials/${id}/reanalyze`); await reload() } catch (e) { setErr(errorMessage(e)) } finally { setBusy('') }
  }
  async function remove(x: Material) {
    if (!confirm(`'${x.original_filename}' 자료를 삭제할까요?`)) return
    try { await api.delete(`/materials/${x.id}`); await reload() } catch (e) { setErr(errorMessage(e)) }
  }

  return (
    <div className="space-y-4">
      {m.can_edit && (
        <div className="flex flex-wrap items-center gap-3">
          <button className="btn-primary" onClick={() => ref.current?.click()} disabled={busy === 'upload'}>{busy === 'upload' && <Spinner />}{busy === 'upload' ? '업로드 및 분석 중...' : '+ 자료 업로드'}</button>
          <input ref={ref} type="file" multiple accept=".pdf,.docx,.pptx,.txt" className="hidden" onChange={(e) => upload(e.target.files)} />
          <span className="text-xs text-gray-500">PDF, DOCX, PPTX, TXT · 파일당 최대 20MB. 새 자료는 'AI 브리핑 다시 생성' 시 반영됩니다.</span>
        </div>
      )}
      {err && <Alert onClose={() => setErr('')}>{err}</Alert>}
      {!m.materials.length ? <EmptyState title="업로드된 자료가 없습니다" desc="자료가 있으면 브리핑이 자료 근거를 바탕으로 더 정확해집니다." /> : (
        <div className="space-y-3">
          {m.materials.map((x) => (
            <div key={x.id} className="card p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] font-semibold uppercase text-gray-600">{x.file_type}</span>
                    <p className="truncate text-sm font-medium">{x.original_filename}</p>
                    {x.status === 'failed' && <span className="rounded bg-red-50 px-1.5 py-0.5 text-[11px] font-medium text-red-600">분석 실패</span>}
                  </div>
                  <p className="mt-0.5 text-xs text-gray-500">{fmtSize(x.size_bytes)} · {fmtDateTime(x.uploaded_at)}</p>
                </div>
                <div className="flex gap-1">
                  {x.status === 'processed' && <button className="btn-ghost text-xs" onClick={() => open(x.id)}>추출 텍스트 보기</button>}
                  {m.can_edit && <button className="btn-ghost text-xs" onClick={() => reanalyze(x.id)} disabled={!!busy}>{busy === `re-${x.id}` && <Spinner className="h-3 w-3" />}재분석</button>}
                  {m.can_edit && <button className="btn-ghost text-xs text-red-600" onClick={() => remove(x)}>삭제</button>}
                </div>
              </div>
              {x.error && <p className="mt-2 text-xs text-red-600">{x.error}</p>}
              {x.status === 'processed' && (
                <div className="mt-3 space-y-2 text-sm">
                  {x.title && <p><span className="text-gray-500">제목 </span>{x.title}</p>}
                  {x.summary && <p className="text-gray-700"><span className="mr-1 text-gray-500">주요 내용</span><SourceBadge source={x.summary_source} /> {x.summary}</p>}
                  {x.keywords.length > 0 && <div className="flex flex-wrap items-center gap-1"><span className="mr-1 text-gray-500">핵심 키워드</span>{x.keywords.map((k) => <span key={k} className="rounded bg-indigo-50 px-1.5 py-0.5 text-xs text-indigo-700">{k}</span>)}</div>}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <Modal open={!!view} title={view?.original_filename ?? ''} onClose={() => setView(null)} wide>
        {view && <div className="space-y-4">{view.segments.map((s, i) => (
          <div key={i}><p className="mb-1 text-xs font-semibold text-gray-500">{s.loc}</p><p className="whitespace-pre-wrap text-sm text-gray-800">{s.text}</p></div>
        ))}</div>}
      </Modal>
    </div>
  )
}

import { useEffect, useState } from 'react'

type Candidate = {
  report_id: string
  title: string
  source: string
  provider?: string | null
  published_at?: string | null
  page_count?: number | null
}

type LinkRow = Candidate & {
  axis_index: number
  axis_label: string
  relation: 'corroboration' | 'dissent' | 'supplement'
  select_reason?: string | null
}

type Props = {
  runId: string
  axisIndex: number
  axisLabel: string
}

const RELATIONS = [
  ['corroboration', 'ì§€ì§€'],
  ['dissent', 'ìƒë°˜'],
  ['supplement', 'ë³´ì™„'],
] as const

export function ExternalDocsPanel({ runId, axisIndex, axisLabel }: Props) {
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [links, setLinks] = useState<LinkRow[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [relation, setRelation] = useState<LinkRow['relation']>('supplement')
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const [candidateResponse, linkResponse] = await Promise.all([
        fetch(
          `/api/consensus/runs/${runId}/external-docs/candidates?axis_index=${axisIndex}`,
        ),
        fetch(
          `/api/consensus/runs/${runId}/external-docs?axis_index=${axisIndex}`,
        ),
      ])
      const candidateData = await candidateResponse.json()
      const linkData = await linkResponse.json()
      if (!candidateResponse.ok || !candidateData.ok) {
        throw new Error(candidateData.message || `í›„ë³´ ì¡°íšŒ ì‹¤íŒ¨ (${candidateResponse.status})`)
      }
      if (!linkResponse.ok || !linkData.ok) {
        throw new Error(linkData.message || `ì—°ê²° ì¡°íšŒ ì‹¤íŒ¨ (${linkResponse.status})`)
      }
      setCandidates(candidateData.items ?? [])
      setLinks(linkData.items ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [runId, axisIndex])

  async function addLink() {
    if (!selectedId) return
    setError(null)
    const response = await fetch(`/api/consensus/runs/${runId}/external-docs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        axis_index: axisIndex,
        axis_label: axisLabel,
        report_id: selectedId,
        relation,
        select_reason: reason.trim() || null,
      }),
    })
    const data = await response.json()
    if (!response.ok || !data.ok) {
      setError(data.message || `ì €ìž¥ ì‹¤íŒ¨ (${response.status})`)
      return
    }
    setSelectedId('')
    setReason('')
    await load()
  }

  async function reviewWithAi() {
    setReviewing(true)
    setError(null)
    try {
      const response = await fetch(
        `/api/consensus/runs/${runId}/external-docs/review?axis_index=${axisIndex}&axis_label=${encodeURIComponent(axisLabel)}`,
      )
      const data = await response.json()
      if (!response.ok || !data.ok) {
        throw new Error(data.message || `AI 분석 실패 (${response.status})`)
      }
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setReviewing(false)
    }
  }

  async function removeLink(reportId: string) {
    const response = await fetch(`/api/consensus/runs/${runId}/external-docs`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ axis_index: axisIndex, report_id: reportId }),
    })
    const data = await response.json()
    if (!response.ok || !data.ok) {
      setError(data.message || `ì‚­ì œ ì‹¤íŒ¨ (${response.status})`)
      return
    }
    await load()
  }

  return (
    <section className="panel">
      <div className="section-head">
        <h2>ì™¸ë¶€ ìžë£Œ ë³´ì™„ Â· {axisLabel}</h2>
      </div>
      <p className="section-note">
        FnGuideë¥¼ ê¸°ì¤€ìœ¼ë¡œ ì™¸ë¶€ ë³´ê³ ì„œë¥¼ ì§€ì§€Â·ìƒë°˜Â·ë³´ì™„ ìžë£Œë¡œ ì—°ê²°í•©ë‹ˆë‹¤.
      </p>
      {error ? <p className="error-line">{error}</p> : null}
      <div className="chip-row" style={{ gap: '0.5rem', flexWrap: 'wrap' }}>
        <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)}>
          <option value="">ì™¸ë¶€ ë³´ê³ ì„œ ì„ íƒ</option>
          {candidates.map((item) => (
            <option key={item.report_id} value={item.report_id}>
              [{item.source}] {item.title}
            </option>
          ))}
        </select>
        <select
          value={relation}
          onChange={(e) => setRelation(e.target.value as LinkRow['relation'])}
        >
          {RELATIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="ì—°ê²° ì´ìœ (ì„ íƒ)"
        />
        <button type="button" className="btn" disabled={!selectedId} onClick={() => void addLink()}>
          ì—°ê²° ì €ìž¥
        </button>
        <button type="button" className="btn" disabled={reviewing || loading} onClick={() => void reviewWithAi()}>
          {reviewing ? 'AI 분석 중…' : 'AI 외부자료 분석'}
        </button>
        <button type="button" className="text-link" onClick={() => void load()} disabled={loading}>
          {loading ? 'ë¶ˆëŸ¬ì˜¤ëŠ” ì¤‘â€¦' : 'ìƒˆë¡œê³ ì¹¨'}
        </button>
      </div>
      {candidates.length === 0 ? (
        <p className="section-note">í˜„ìž¬ ì—°ê²° ê°€ëŠ¥í•œ ì™¸ë¶€ ë³´ê³ ì„œê°€ ì—†ìŠµë‹ˆë‹¤.</p>
      ) : null}
      {links.length > 0 ? (
        <ul className="select-review-list">
          {links.map((item) => (
            <li key={item.report_id}>
              <strong>{item.title}</strong> Â· {item.relation} Â· {item.source}
              <button
                type="button"
                className="text-link"
                onClick={() => void removeLink(item.report_id)}
              >
                ì—°ê²° í•´ì œ
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="section-note">ì´ ì¶•ì— ì—°ê²°ëœ ì™¸ë¶€ ë³´ê³ ì„œê°€ ì—†ìŠµë‹ˆë‹¤.</p>
      )}
    </section>
  )
}
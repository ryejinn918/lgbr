import { useEffect, useState } from 'react'

type Candidate = {
  report_id: string
  title: string
  source: string
  provider?: string | null
}

type LinkRow = Candidate & {
  relation: 'corroboration' | 'dissent' | 'supplement'
  ai_confidence?: number | null
  ai_reason?: string | null
  review_state?: string | null
}

type Props = { runId: string; axisIndex: number; axisLabel: string }

const labels: Record<string, string> = {
  corroboration: '\uC9C0\uC9C0',
  dissent: '\uC0C1\uBC18',
  supplement: '\uBCF4\uC644',
}

export function ExternalDocsPanelUtf8({ runId, axisIndex, axisLabel }: Props) {
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
    try {
      const [a, b] = await Promise.all([
        fetch(`/api/consensus/runs/${runId}/external-docs/candidates?axis_index=${axisIndex}`),
        fetch(`/api/consensus/runs/${runId}/external-docs?axis_index=${axisIndex}`),
      ])
      const candidatesData = await a.json()
      const linksData = await b.json()
      if (!a.ok || !candidatesData.ok) throw new Error(candidatesData.message || `HTTP ${a.status}`)
      if (!b.ok || !linksData.ok) throw new Error(linksData.message || `HTTP ${b.status}`)
      setCandidates(candidatesData.items ?? [])
      setLinks(linksData.items ?? [])
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [runId, axisIndex])

  async function reviewWithAi() {
    setReviewing(true)
    setError(null)
    try {
      const url = `/api/consensus/runs/${runId}/external-docs/review?axis_index=${axisIndex}&axis_label=${encodeURIComponent(axisLabel)}`
      const response = await fetch(url)
      const data = await response.json()
      if (!response.ok || !data.ok) throw new Error(data.message || `AI ${response.status}`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setReviewing(false)
    }
  }

  async function saveLink() {
    if (!selectedId) return
    const response = await fetch(`/api/consensus/runs/${runId}/external-docs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ axis_index: axisIndex, axis_label: axisLabel, report_id: selectedId, relation, select_reason: reason || null }),
    })
    const data = await response.json()
    if (!response.ok || !data.ok) { setError(data.message || `HTTP ${response.status}`); return }
    setSelectedId(''); setReason(''); await load()
  }

  return (
    <section className="panel">
      <div className="section-head"><h2>{'\uC678\uBD80 \uC790\uB8CC \uBCF4\uC644 · '}{axisLabel}</h2></div>
      <p className="section-note">{'FnGuide\uB97C \uAE30\uC900\uC73C\uB85C \uC678\uBD80 \uBCF4\uACE0\uC11C\uB97C \uBD84\uC11D\uD569\uB2C8\uB2E4.'}</p>
      {error ? <p className="error-line">{error}</p> : null}
      <div className="chip-row" style={{ gap: '0.5rem', flexWrap: 'wrap' }}>
        <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)}>
          <option value="">{'\uC678\uBD80 \uBCF4\uACE0\uC11C \uC120\uD0DD'}</option>
          {candidates.map((item) => <option key={item.report_id} value={item.report_id}>[{item.source}] {item.title}</option>)}
        </select>
        <select value={relation} onChange={(e) => setRelation(e.target.value as LinkRow['relation'])}>
          <option value="corroboration">{'\uC9C0\uC9C0'}</option>
          <option value="dissent">{'\uC0C1\uBC18'}</option>
          <option value="supplement">{'\uBCF4\uC644'}</option>
        </select>
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={'\uC5F0\uACB0 \uC774\uC720 (\uC120\uD0DD)'} />
        <button type="button" className="btn" disabled={reviewing || loading} onClick={() => void reviewWithAi()}>{reviewing ? '\uC785\uB825 \uBD84\uC11D \uC911…' : 'AI \uC678\uBD80\uC790\uB8CC \uBD84\uC11D'}</button>
        <button type="button" className="btn" disabled={!selectedId} onClick={() => void saveLink()}>{'\uC5F0\uACB0 \uC800\uC7A5'}</button>
      </div>
      {links.length === 0 ? <p className="section-note">{'\uC5F0\uACB0\uB41C \uC678\uBD80 \uBCF4\uACE0\uC11C\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.'}</p> : (
        <ul className="select-review-list">
          {links.map((item) => <li key={item.report_id}><strong>{item.title}</strong> · {labels[item.relation] || item.relation} · {item.source}{item.review_state === 'ai_suggested' ? ` · AI ${'\uCD94\uCC9C'}` : ''}{item.ai_confidence != null ? ` · ${Math.round(item.ai_confidence * 100)}%` : ''}{item.ai_reason ? <span className="section-note"> · {item.ai_reason}</span> : null}</li>)}
        </ul>
      )}
    </section>
  )
}

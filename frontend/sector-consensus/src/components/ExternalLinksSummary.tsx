import { useEffect, useState } from 'react'

type LinkRow = {
  report_id: string
  axis_index: number
  axis_label: string
  relation: string
  source?: string | null
  title: string
  provider?: string | null
  select_reason?: string | null
  ai_reason?: string | null
  ai_confidence?: number | null
  review_state?: string | null
}

type Props = {
  runId: string
  axes: string[]
}

const relationLabels: Record<string, string> = {
  corroboration: '\uC9C0\uC9C0',
  dissent: '\uC0C1\uBC18',
  supplement: '\uBCF4\uC644',
}

export function ExternalLinksSummary({ runId, axes }: Props) {
  const [items, setItems] = useState<LinkRow[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void Promise.all(
      axes.map((_, index) =>
        fetch(`/api/consensus/runs/${runId}/external-docs?axis_index=${index}`).then(
          async (response) => {
            const data = await response.json()
            if (!response.ok || !data.ok) {
              throw new Error(data.message || `HTTP ${response.status}`)
            }
            return (data.items ?? []) as LinkRow[]
          },
        ),
      ),
    )
      .then((groups) => {
        if (!cancelled) {
          setItems(groups.flat())
          setError(null)
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [runId, axes])

  if (error) return <p className="error-line">{error}</p>
  if (items.length === 0) {
    return (
      <p className="section-note">
        {'\uC544\uC9C1 AI\uAC00 \uCD94\uCC9C\uD55C \uC678\uBD80 \uC790\uB8CC\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.'}
      </p>
    )
  }

  return (
    <div className="select-review">
      <h3>{'\uC678\uBD80 \uC790\uB8CC \u00B7 AI \uCD94\uCC9C'}</h3>
      <table className="data-table">
        <thead>
          <tr>
            <th>{'\uBD84\uC11D \uCD95'}</th>
            <th>{'\uBCF4\uACE0\uC11C'}</th>
            <th>{'\uCD9C\uCC98'}</th>
            <th>{'\uAD00\uACC4'}</th>
            <th>{'AI \uC774\uC720'}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={`${item.axis_index}-${item.report_id}`}>
              <td>{item.axis_label}</td>
              <td>{item.title}</td>
              <td>{item.provider || item.source || '\u2014'}</td>
              <td>
                {relationLabels[item.relation] || item.relation}
                {item.review_state === 'ai_suggested' ? ` · AI ${'\uCD94\uCC9C'}` : ''}
                {item.ai_confidence != null
                  ? ` · ${Math.round(item.ai_confidence * 100)}%`
                  : ''}
              </td>
              <td>{item.ai_reason || item.select_reason || '\u2014'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

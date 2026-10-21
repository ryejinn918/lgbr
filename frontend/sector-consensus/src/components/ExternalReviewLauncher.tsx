import { useState } from 'react'

type Props = { runId: string; axes: string[]; onComplete?: () => void }

export function ExternalReviewLauncher({ runId, axes, onComplete }: Props) {
  const [running, setRunning] = useState(false)
  const [message, setMessage] = useState('')

  async function runReview() {
    if (running || axes.length === 0) return
    setRunning(true)
    setMessage('\uC678\uBD80 \uC790\uB8CC\uB97C AI\uAC00 \uBD84\uC11D\uD558\uB294 \uC911...')
    try {
      for (const [index, axis] of axes.entries()) {
        const response = await fetch(
          `/api/consensus/runs/${runId}/external-docs/review?axis_index=${index}&axis_label=${encodeURIComponent(axis)}`,
        )
        const data = await response.json()
        if (!response.ok || !data.ok) throw new Error(data.message || `HTTP ${response.status}`)
      }
      setMessage('\uC678\uBD80 \uC790\uB8CC AI \uBD84\uB958\uAC00 \uC644\uB8CC\uB418\uC5C8\uC2B5\uB2C8\uB2E4. \uC544\uB798 \uACB0\uACFC\uB97C \uD655\uC778\uD574\uC8FC\uC138\uC694.')
      onComplete?.()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="select-review">
      <h3>{'\uC678\uBD80 \uC790\uB8CC AI \uBD84\uB958'}</h3>
      <p className="section-note">
        {'FnGuide \uBD84\uC11D \uCD95\uC744 \uAE30\uC900\uC73C\uB85C \uC678\uBD80 \uBCF4\uACE0\uC11C\uB97C AI\uAC00 \uC9C0\uC9C0\u00B7\uC0C1\uBC18\u00B7\uBCF4\uC644\uC73C\uB85C \uBD84\uB958\uD569\uB2C8\uB2E4. \uC0AC\uB78C\uC774 \uBCF4\uACE0\uC11C\uB97C \uD558\uB098\uC529 \uC120\uD0DD\uD560 \uD544\uC694\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.'}
      </p>
      <button type="button" className="btn" disabled={running} onClick={() => void runReview()}>
        {running ? 'AI \uBD84\uC11D \uC9C4\uD589 \uC911...' : 'AI \uC678\uBD80 \uC790\uB8CC \uC804\uCCB4 \uBD84\uC11D'}
      </button>
      {message ? <p className="section-note">{message}</p> : null}
    </div>
  )
}

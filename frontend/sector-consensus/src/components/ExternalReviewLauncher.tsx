import { useState } from 'react'

type Props = {
  runId: string
  axes: string[]
  onComplete?: () => void
}

export function ExternalReviewLauncher({
  runId,
  axes,
  onComplete,
}: Props) {
  const [running, setRunning] = useState(false)
  const [message, setMessage] = useState('')

  async function runReview() {
    if (running) return

    if (axes.length === 0) {
      setMessage('분석 축이 없어 외부 자료를 분석할 수 없습니다.')
      return
    }

    setRunning(true)
    setMessage('외부 자료 분석을 시작했습니다.')

    try {
      for (const [index, axis] of axes.entries()) {
        setMessage(
          `외부 자료를 분석 중입니다. (${index + 1}/${axes.length})`,
        )

        const response = await fetch(
          `/api/consensus/runs/${runId}/external-docs/review?axis_index=${index}&axis_label=${encodeURIComponent(axis)}`,
        )

        const responseText = await response.text()

        let data: { ok?: boolean; message?: string } = {}

        if (responseText.trim()) {
          try {
            data = JSON.parse(responseText)
          } catch {
            throw new Error(
              '외부 자료 분석 결과를 읽지 못했습니다. 잠시 후 다시 시도해 주세요.',
            )
          }
        }

        if (!response.ok || !data.ok) {
          throw new Error(
            data.message ||
              `외부 자료 분석에 실패했습니다. (HTTP ${response.status})`,
          )
        }
      }

      setMessage(
        '외부 자료 분석 요청이 완료되었습니다. 추천 자료가 바로 보이지 않으면 잠시 후 새로고침해 주세요.',
      )

      onComplete?.()
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : '외부 자료 분석에 실패했습니다. 잠시 후 다시 눌러 주세요.',
      )
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="select-review">
      <h3>외부 자료 AI 분류</h3>

      <p className="section-note">
        FnGuide 분석 축을 기준으로 외부 보고서를 AI가 지지·상반·보완으로
        분류합니다. 분석이 완료되면 추천 자료를 확인할 수 있습니다.
      </p>

      <button
        type="button"
        className="btn"
        disabled={running}
        onClick={() => void runReview()}
      >
        {running ? 'AI 분석 진행 중...' : 'AI 외부 자료 전체 분석'}
      </button>

      {message ? (
        <p className="section-note" aria-live="polite">
          {message}
        </p>
      ) : null}
    </div>
  )
}
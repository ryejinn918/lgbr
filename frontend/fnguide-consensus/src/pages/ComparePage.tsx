import { useEffect, useRef, useState } from 'react'
import { toPng } from 'html-to-image'
import { Link, useParams } from 'react-router-dom'
import { useCompareStore } from '../compare/CompareStore'
import { prepareSend, type ColumnState, type Mode } from '../compare/compareState'
import { Markdown } from '../components/Markdown'
import { readChatSse } from '../lib/chatStream'
import { formatTime } from '../lib/format'
import {
  APP_BRAND,
  CHAT_MODE,
  CHAT_ROLE,
  FRAME_TAB,
  NAV,
  labelChatPhase,
  labelRole,
} from '../lib/labels'
import { parseTheme, themePath } from '../lib/theme'
import { THEME_LABEL } from '../types'

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

function exportStamp(): string {
  const d = new Date()
  return `${d.getFullYear()}${pad2(d.getMonth() + 1)}${pad2(d.getDate())}-${pad2(d.getHours())}${pad2(d.getMinutes())}`
}

export function ComparePage() {
  const { theme: raw } = useParams()
  const theme = parseTheme(raw)
  const { state, dispatch } = useCompareStore(theme)
  const { plain, grounded, sharedDraft, frameTab, latest } = state
  const { run, filled, consensus, error: frameError } = latest
  const exportRef = useRef<HTMLDivElement>(null)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    let cancelled = false
    dispatch({ type: 'latest_loading' })
    void fetch(`/api/consensus/latest?theme=${theme}`)
      .then(async (r) => {
        const d = await r.json()
        if (!r.ok || !d.ok) throw new Error(d.message || `HTTP ${r.status}`)
        if (cancelled) return
        dispatch({
          type: 'latest_ok',
          run: d.run ?? null,
          filled: d.filled_frame ?? null,
          consensus: d.consensus_frame ?? null,
        })
      })
      .catch((e) => {
        if (!cancelled) {
          dispatch({
            type: 'latest_err',
            message: e instanceof Error ? e.message : String(e),
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [theme, dispatch])

  async function runStream(
    mode: Mode,
    apiMessages: { role: string; content: string }[],
    turnId: string,
  ) {
    try {
      const res = await fetch('/api/consensus/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, theme, messages: apiMessages }),
      })
      let errored = false
      await readChatSse(res, {
        onStatus: (phase) => {
          dispatch({ type: 'stream_status', mode, turnId, phase })
        },
        onTool: (tool) => {
          dispatch({ type: 'stream_tool', mode, turnId, tool })
        },
        onDelta: (chunk) => {
          dispatch({ type: 'stream_delta', mode, turnId, text: chunk })
        },
        onDone: () => {
          dispatch({ type: 'stream_done', mode, turnId })
        },
        onError: (message) => {
          errored = true
          dispatch({ type: 'stream_error', mode, turnId, message })
        },
      })
      if (!errored) {
        dispatch({ type: 'stream_done', mode, turnId })
      }
    } catch (e) {
      dispatch({
        type: 'stream_error',
        mode,
        turnId,
        message: e instanceof Error ? e.message : String(e),
      })
    }
  }

  async function streamColumn(mode: Mode, userText: string) {
    if (mode === 'grounded' && !state.latest.run) {
      window.alert(
        `이 섹터에 완료된 실행이 없습니다. ${NAV.ops}에서 먼저 시작하세요.`,
      )
      return
    }
    const prepared = prepareSend(state, mode, userText)
    if (!prepared) return
    dispatch({
      type: 'send_start',
      mode,
      text: prepared.text,
      turnId: prepared.turnId,
    })
    await runStream(mode, prepared.apiMessages, prepared.turnId)
  }

  async function sendColumn(mode: Mode) {
    const column = mode === 'plain' ? plain : grounded
    await streamColumn(mode, column.input)
  }

  async function sendBothSame() {
    const text =
      sharedDraft.trim() || plain.input.trim() || grounded.input.trim()
    if (!text) return
    if (plain.loading || grounded.loading) return

    const plainPrep = prepareSend(state, 'plain', text)
    const groundedPrep = prepareSend(state, 'grounded', text)
    if (!plainPrep && !groundedPrep) {
      if (!state.latest.run) {
        window.alert(
          `이 섹터에 완료된 실행이 없습니다. ${NAV.ops}에서 먼저 시작하세요.`,
        )
      }
      return
    }

    dispatch({ type: 'set_shared_draft', value: '' })

    const jobs: Promise<void>[] = []
    if (plainPrep) {
      dispatch({
        type: 'send_start',
        mode: 'plain',
        text: plainPrep.text,
        turnId: plainPrep.turnId,
      })
      jobs.push(runStream('plain', plainPrep.apiMessages, plainPrep.turnId))
    }
    if (groundedPrep) {
      dispatch({
        type: 'send_start',
        mode: 'grounded',
        text: groundedPrep.text,
        turnId: groundedPrep.turnId,
      })
      jobs.push(
        runStream('grounded', groundedPrep.apiMessages, groundedPrep.turnId),
      )
    } else if (!state.latest.run) {
      window.alert(
        `이 섹터에 완료된 실행이 없습니다. ${CHAT_MODE.grounded}은 건너뜁니다.`,
      )
    }
    await Promise.all(jobs)
  }

  async function exportPng() {
    const node = exportRef.current
    if (!node) return
    setExporting(true)
    try {
      // Wait for React paint so .is-exporting expands chat logs.
      await new Promise<void>((r) => {
        requestAnimationFrame(() => requestAnimationFrame(() => r()))
      })
      const dataUrl = await toPng(node, {
        pixelRatio: 2,
        cacheBust: true,
        backgroundColor: '#f7f9fb',
      })
      const a = document.createElement('a')
      a.href = dataUrl
      a.download = `compare-${theme}-${exportStamp()}.png`
      a.click()
    } catch (e) {
      window.alert(
        e instanceof Error ? e.message : '이미지 내보내기에 실패했습니다.',
      )
    } finally {
      setExporting(false)
    }
  }

  const frameBody = frameTab === 'filled' ? filled : consensus
  const hasAnyMessages =
    plain.messages.length > 0 || grounded.messages.length > 0

  return (
    <>
      <header className="monitor-header">
        <h1>
          {THEME_LABEL[theme]} · {NAV.compare}
        </h1>
        <p className="lede">
          섹터 논지를 근거로 질문하고 답합니다. 오른쪽에 일반 답변을 두고
          나란히 볼 수 있습니다.
        </p>
      </header>

      <section className="panel">
        {run ? (
          <p className="section-note">
            최근 실행 · {formatTime(run.ended_at)} · {run.question}
          </p>
        ) : (
          <p className="section-note">
            {CHAT_MODE.grounded}에 쓸 완료된 실행이 없습니다.{' '}
            <Link to={themePath(theme, 'ops')}>{NAV.ops}에서 시작</Link>
          </p>
        )}
        {frameError && <p className="error-line">{frameError}</p>}
        <div className="compare-toolbar">
          <label className="shared-draft">
            동일 질문 (양쪽)
            <input
              value={sharedDraft}
              placeholder="공통 질문…"
              onChange={(e) =>
                dispatch({ type: 'set_shared_draft', value: e.target.value })
              }
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  void sendBothSame()
                }
              }}
            />
          </label>
          <button
            type="button"
            className="btn"
            disabled={
              plain.loading ||
              grounded.loading ||
              !(sharedDraft.trim() || plain.input.trim() || grounded.input.trim())
            }
            onClick={() => void sendBothSame()}
          >
            양쪽 동일 전송
          </button>
          <button
            type="button"
            className="btn ghost"
            disabled={!hasAnyMessages || exporting}
            onClick={() => void exportPng()}
          >
            {exporting ? '내보내는 중…' : '이미지로 내보내기'}
          </button>
          <button
            type="button"
            className="btn ghost"
            onClick={() => dispatch({ type: 'clear_chats' })}
          >
            대화 초기화
          </button>
        </div>
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>참고할 논지</h2>
          <div className="chip-row">
            {(
              [
                ['filled', FRAME_TAB.filled],
                ['consensus', FRAME_TAB.consensus],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                className={`chip ${frameTab === k ? 'active' : ''}`}
                onClick={() => dispatch({ type: 'set_frame_tab', tab: k })}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {frameBody ? (
          <div className="frame-scroll">
            <Markdown>{frameBody}</Markdown>
          </div>
        ) : (
          <p className="section-note">표시할 논지가 없습니다.</p>
        )}
      </section>

      <div
        ref={exportRef}
        className={`compare-export-root${exporting ? ' is-exporting' : ''}`}
      >
        <div className="compare-export-meta">
          <p className="compare-export-brand">
            {APP_BRAND} · {THEME_LABEL[theme]}
          </p>
          <p className="section-note">
            {run
              ? `최근 실행 · ${formatTime(run.ended_at)} · ${run.question}`
              : '완료된 실행 없음'}
          </p>
        </div>
        <section className="compare-grid">
          <ChatColumn
            variant="ours"
            eyebrow={CHAT_ROLE.ours}
            title={CHAT_MODE.grounded}
            hint="최근 살 붙인 논지를 참고합니다."
            column={grounded}
            onInput={(v) =>
              dispatch({ type: 'set_input', mode: 'grounded', value: v })
            }
            onSend={() => void sendColumn('grounded')}
            sendDisabled={grounded.loading || !grounded.input.trim() || !run}
          />
          <ChatColumn
            variant="control"
            eyebrow={CHAT_ROLE.control}
            title={CHAT_MODE.plain}
            hint="웹 검색만 사용합니다. 이 섹터 논지는 보지 않습니다."
            column={plain}
            onInput={(v) =>
              dispatch({ type: 'set_input', mode: 'plain', value: v })
            }
            onSend={() => void sendColumn('plain')}
            sendDisabled={plain.loading || !plain.input.trim()}
          />
        </section>
      </div>
    </>
  )
}

function ChatColumn({
  variant,
  eyebrow,
  title,
  hint,
  column,
  onInput,
  onSend,
  sendDisabled,
}: {
  variant: 'ours' | 'control'
  eyebrow: string
  title: string
  hint: string
  column: ColumnState
  onInput: (v: string) => void
  onSend: () => void
  sendDisabled: boolean
}) {
  return (
    <div className={`panel chat-col ${variant}`}>
      <p className="chat-eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <p className="section-note chat-hint">{hint}</p>
      <div className="chat-log">
        {column.messages.length === 0 && (
          <p className="section-note">아직 메시지 없음</p>
        )}
        {column.messages.map((m, i) => (
          <div key={m.turnId ?? `m-${i}`} className={`bubble role-${m.role}`}>
            <div className="bubble-head">
              <p className="bubble-role">{labelRole(m.role)}</p>
              {m.role === 'assistant' &&
                !m.streaming &&
                m.content.trim() && (
                  <CopyAnswerButton text={m.content} />
                )}
            </div>
            {m.tools && m.tools.length > 0 && (
              <ul className="tool-list">
                {m.tools.map((t, j) => (
                  <li key={j}>
                    <span className="tool-query">웹검색: {t.query}</span>
                    <ul className="tool-links">
                      {t.results.slice(0, 3).map((r, k) => (
                        <li key={k}>
                          <a href={r.link} target="_blank" rel="noreferrer">
                            {r.title || r.link}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
            {m.role === 'assistant' ? (
              <>
                <Markdown>{m.content || (m.streaming ? '…' : '')}</Markdown>
                {m.streaming && <span className="stream-cursor" aria-hidden />}
              </>
            ) : (
              <p className="bubble-text">{m.content}</p>
            )}
          </div>
        ))}
        {column.loading && column.phase && (
          <p className="section-note">{labelChatPhase(column.phase)}</p>
        )}
        {column.error && <p className="error-line">{column.error}</p>}
      </div>
      <div className="col-compose">
        <textarea
          rows={3}
          value={column.input}
          placeholder={`${title}에 질문… (Ctrl/⌘+Enter)`}
          onChange={(e) => onInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault()
              onSend()
            }
          }}
        />
        <button
          type="button"
          className="btn"
          disabled={sendDisabled}
          onClick={onSend}
        >
          {column.loading ? '응답 중…' : '전송'}
        </button>
      </div>
    </div>
  )
}

function CopyAnswerButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      window.alert('클립보드에 복사하지 못했습니다.')
    }
  }

  return (
    <button type="button" className="btn-copy" onClick={() => void onCopy()}>
      {copied ? '복사됨' : '복사'}
    </button>
  )
}

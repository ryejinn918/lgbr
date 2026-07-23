import { useEffect, useReducer } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  compareReducer,
  initialCompareState,
  prepareSend,
  type ColumnState,
  type Mode,
} from '../compare/compareState'
import { Markdown } from '../components/Markdown'
import { readChatSse } from '../lib/chatStream'
import { formatTime } from '../lib/format'
import {
  CHAT_MODE,
  CHAT_ROLE,
  FRAME_TAB,
  NAV,
  labelChatPhase,
  labelRole,
} from '../lib/labels'
import type { ConsensusTheme } from '../types'
import { THEME_LABEL } from '../types'

const THEMES: ConsensusTheme[] = ['datacenter', 'ai', 'physical_ai']

function parseTheme(raw: string | null): ConsensusTheme {
  if (raw && THEMES.includes(raw as ConsensusTheme)) return raw as ConsensusTheme
  return 'datacenter'
}

export function ComparePage() {
  const [params, setParams] = useSearchParams()
  const theme = parseTheme(params.get('theme'))
  const [state, dispatch] = useReducer(compareReducer, undefined, initialCompareState)
  const { plain, grounded, sharedDraft, frameTab, latest } = state
  const { run, filled, consensus, error: frameError } = latest

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
  }, [theme])

  function setTheme(next: ConsensusTheme) {
    setParams({ theme: next }, { replace: true })
    dispatch({ type: 'theme_reset' })
  }

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
        `이 섹터에 완료된 실행이 없습니다. ${NAV.ops}에서 먼저 생성하세요.`,
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
          `이 섹터에 완료된 실행이 없습니다. ${NAV.ops}에서 먼저 생성하세요.`,
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

  const frameBody = frameTab === 'filled' ? filled : consensus

  return (
    <>
      <header className="monitor-header">
        <h1>{NAV.compare}</h1>
        <p className="lede">
          왼쪽이 {CHAT_MODE.grounded}({CHAT_ROLE.ours}), 오른쪽이{' '}
          {CHAT_MODE.plain}({CHAT_ROLE.control})입니다. 열마다 다른 질문·이어
          묻기도 가능합니다.
        </p>
      </header>

      <section className="panel">
        <div className="chip-row">
          {THEMES.map((t) => (
            <button
              key={t}
              type="button"
              className={`chip ${theme === t ? 'active' : ''}`}
              onClick={() => setTheme(t)}
            >
              {THEME_LABEL[t]}
            </button>
          ))}
        </div>
        {run ? (
          <p className="section-note">
            {run.asset_id} · {formatTime(run.ended_at)} · {run.question}
          </p>
        ) : (
          <p className="section-note">
            {CHAT_MODE.grounded}에 쓸 완료된 실행이 없습니다.{' '}
            <Link to={`/ops?theme=${theme}`}>{NAV.ops}에서 생성</Link>
          </p>
        )}
        {frameError && <p className="error-line">{frameError}</p>}
        <div className="compare-toolbar">
          <label className="shared-draft">
            동일 질문 (양쪽)
            <input
              value={sharedDraft}
              placeholder="비교용 공통 질문…"
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
            onClick={() => dispatch({ type: 'clear_chats' })}
          >
            대화 초기화
          </button>
        </div>
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>참고 논지</h2>
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

      <section className="compare-grid">
        <ChatColumn
          variant="ours"
          eyebrow={CHAT_ROLE.ours}
          title={CHAT_MODE.grounded}
          hint="최신 상세 논지를 참고합니다."
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
          hint="웹검색만 사용. 섹터 논지는 보지 않습니다."
          column={plain}
          onInput={(v) => dispatch({ type: 'set_input', mode: 'plain', value: v })}
          onSend={() => void sendColumn('plain')}
          sendDisabled={plain.loading || !plain.input.trim()}
        />
      </section>
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
      <p className="section-note">{hint}</p>
      <div className="chat-log">
        {column.messages.length === 0 && (
          <p className="section-note">아직 메시지 없음</p>
        )}
        {column.messages.map((m, i) => (
          <div key={m.turnId ?? `m-${i}`} className={`bubble role-${m.role}`}>
            <p className="bubble-role">{labelRole(m.role)}</p>
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

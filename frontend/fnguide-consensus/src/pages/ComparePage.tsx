import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Markdown } from '../components/Markdown'
import { formatTime } from '../lib/format'
import type { ChatMessage, ConsensusRun, ConsensusTheme } from '../types'
import { THEME_LABEL } from '../types'

type Column = {
  messages: ChatMessage[]
  loading: boolean
  error: string | null
}

type FrameTab = 'filled' | 'consensus'

const THEMES: ConsensusTheme[] = ['datacenter', 'ai', 'physical_ai']
const emptyCol = (): Column => ({ messages: [], loading: false, error: null })

function parseTheme(raw: string | null): ConsensusTheme {
  if (raw && THEMES.includes(raw as ConsensusTheme)) return raw as ConsensusTheme
  return 'datacenter'
}

export function ComparePage() {
  const [params, setParams] = useSearchParams()
  const theme = parseTheme(params.get('theme'))
  const [run, setRun] = useState<ConsensusRun | null>(null)
  const [filled, setFilled] = useState<string | null>(null)
  const [consensus, setConsensus] = useState<string | null>(null)
  const [frameTab, setFrameTab] = useState<FrameTab>('filled')
  const [frameError, setFrameError] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [plain, setPlain] = useState<Column>(emptyCol)
  const [grounded, setGrounded] = useState<Column>(emptyCol)

  useEffect(() => {
    let cancelled = false
    setFrameError(null)
    void fetch(`/api/consensus/latest?theme=${theme}`)
      .then(async (r) => {
        const d = await r.json()
        if (!r.ok || !d.ok) throw new Error(d.message || `HTTP ${r.status}`)
        if (cancelled) return
        setRun(d.run ?? null)
        setFilled(d.filled_frame ?? null)
        setConsensus(d.consensus_frame ?? null)
      })
      .catch((e) => {
        if (!cancelled) {
          setRun(null)
          setFilled(null)
          setConsensus(null)
          setFrameError(e instanceof Error ? e.message : String(e))
        }
      })
    return () => {
      cancelled = true
    }
  }, [theme])

  function setTheme(next: ConsensusTheme) {
    setParams({ theme: next }, { replace: true })
    setPlain(emptyCol())
    setGrounded(emptyCol())
    setFrameTab('filled')
  }

  async function sendBoth() {
    const text = input.trim()
    if (!text) return
    if (!run) {
      window.alert('이 섹터에 ended run이 없습니다. 운영에서 먼저 실행하세요.')
      return
    }
    setInput('')
    const userMsg: ChatMessage = { role: 'user', content: text }
    const plainMsgs = [...plain.messages, userMsg]
    const groundedMsgs = [...grounded.messages, userMsg]
    setPlain({ messages: plainMsgs, loading: true, error: null })
    setGrounded({ messages: groundedMsgs, loading: true, error: null })

    const call = async (mode: 'plain' | 'grounded', messages: ChatMessage[]) => {
      const res = await fetch('/api/consensus/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, theme, messages }),
      })
      const data = await res.json()
      if (!res.ok || !data.ok) {
        throw new Error(data.message || `HTTP ${res.status}`)
      }
      return String(data.content || '')
    }

    const [p, g] = await Promise.allSettled([
      call('plain', plainMsgs),
      call('grounded', groundedMsgs),
    ])

    if (p.status === 'fulfilled') {
      setPlain({
        messages: [...plainMsgs, { role: 'assistant', content: p.value }],
        loading: false,
        error: null,
      })
    } else {
      setPlain({
        messages: plainMsgs,
        loading: false,
        error: p.reason instanceof Error ? p.reason.message : String(p.reason),
      })
    }
    if (g.status === 'fulfilled') {
      setGrounded({
        messages: [...groundedMsgs, { role: 'assistant', content: g.value }],
        loading: false,
        error: null,
      })
    } else {
      setGrounded({
        messages: groundedMsgs,
        loading: false,
        error: g.reason instanceof Error ? g.reason.message : String(g.reason),
      })
    }
  }

  const frameBody =
    frameTab === 'filled' ? filled : consensus

  return (
    <>
      <header className="monitor-header">
        <h1>비교</h1>
        <p className="lede">
          섹터 최신 프레임을 읽고, Plain / Grounded 응답을 나란히 비교합니다.
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
            이 섹터에 ended run이 없습니다.{' '}
            <Link to={`/ops?theme=${theme}`}>운영에서 실행</Link>
          </p>
        )}
        {frameError && <p className="error-line">{frameError}</p>}
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>프레임 논지</h2>
          <div className="chip-row">
            {(
              [
                ['filled', 'Filled'],
                ['consensus', 'Consensus'],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                className={`chip ${frameTab === k ? 'active' : ''}`}
                onClick={() => setFrameTab(k)}
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
          <p className="section-note">표시할 프레임이 없습니다.</p>
        )}
      </section>

      <section className="compare-grid">
        <ChatColumn title="Plain" column={plain} />
        <ChatColumn title="Grounded" column={grounded} />
      </section>

      <section className="panel compare-compose">
        <textarea
          rows={3}
          value={input}
          placeholder="비교할 질문을 입력… (Ctrl/⌘+Enter)"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault()
              void sendBoth()
            }
          }}
        />
        <div className="compare-toolbar">
          <button
            type="button"
            className="btn"
            disabled={plain.loading || grounded.loading || !input.trim() || !run}
            onClick={() => void sendBoth()}
          >
            양쪽 전송
          </button>
          <button
            type="button"
            className="btn ghost"
            onClick={() => {
              setPlain(emptyCol())
              setGrounded(emptyCol())
            }}
          >
            대화 초기화
          </button>
        </div>
      </section>
    </>
  )
}

function ChatColumn({ title, column }: { title: string; column: Column }) {
  return (
    <div className="panel chat-col">
      <h2>{title}</h2>
      <div className="chat-log">
        {column.messages.length === 0 && (
          <p className="section-note">아직 메시지 없음</p>
        )}
        {column.messages.map((m, i) => (
          <div key={i} className={`bubble role-${m.role}`}>
            <p className="bubble-role">{m.role}</p>
            {m.role === 'assistant' ? (
              <Markdown>{m.content}</Markdown>
            ) : (
              <p className="bubble-text">{m.content}</p>
            )}
          </div>
        ))}
        {column.loading && <p className="section-note">응답 대기…</p>}
        {column.error && <p className="error-line">{column.error}</p>}
      </div>
    </div>
  )
}

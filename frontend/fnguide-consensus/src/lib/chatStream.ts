export type StreamToolEvent = {
  name: string
  query: string
  results: { title: string; link: string; snippet: string }[]
}

export type StreamHandlers = {
  onStatus?: (phase: string, data: Record<string, unknown>) => void
  onTool?: (tool: StreamToolEvent) => void
  onDelta?: (text: string) => void
  onDone?: (data: Record<string, unknown>) => void
  onError?: (message: string) => void
}

/** Parse SSE from fetch body; supports `event:` + `data:` blocks. */
export async function readChatSse(
  res: Response,
  handlers: StreamHandlers,
): Promise<void> {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const j = await res.json()
      msg = j.message || msg
    } catch {
      /* ignore */
    }
    handlers.onError?.(msg)
    return
  }
  const reader = res.body?.getReader()
  if (!reader) {
    handlers.onError?.('empty response body')
    return
  }
  const decoder = new TextDecoder()
  let buf = ''
  let event = 'message'

  const flushBlock = (block: string) => {
    const lines = block.split('\n')
    let ev = event
    const dataLines: string[] = []
    for (const line of lines) {
      if (line.startsWith('event:')) {
        ev = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim())
      }
    }
    if (!dataLines.length) return
    const raw = dataLines.join('\n')
    let data: Record<string, unknown> = {}
    try {
      data = JSON.parse(raw) as Record<string, unknown>
    } catch {
      handlers.onError?.(`bad SSE json: ${raw.slice(0, 120)}`)
      return
    }
    if (ev === 'status') {
      handlers.onStatus?.(String(data.phase || ''), data)
    } else if (ev === 'tool') {
      handlers.onTool?.(data as unknown as StreamToolEvent)
    } else if (ev === 'delta') {
      handlers.onDelta?.(String(data.text || ''))
    } else if (ev === 'done') {
      handlers.onDone?.(data)
    } else if (ev === 'error') {
      handlers.onError?.(String(data.message || 'stream error'))
    }
    event = 'message'
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let sep: number
    while ((sep = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, sep)
      buf = buf.slice(sep + 2)
      if (block.trim()) flushBlock(block)
    }
  }
  if (buf.trim()) flushBlock(buf)
}

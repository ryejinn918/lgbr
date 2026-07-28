import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = {
  children: ReactNode
  title?: string
}

type State = { error: string | null }

/** Keeps the eval route alive if the perspective graph throws. */
export class GraphErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(err: Error): State {
    return { error: err?.message || 'graph render failed' }
  }

  componentDidCatch(err: Error, info: ErrorInfo) {
    console.warn('PerspectiveGraph failed', err, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="eval-graph-panel">
          {this.props.title ? <h3>{this.props.title}</h3> : null}
          <p className="section-note">그래프를 그릴 수 없음</p>
          <p className="error-line">{this.state.error}</p>
        </div>
      )
    }
    return this.props.children
  }
}

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function Markdown({ children }: { children: string }) {
  return (
    <div className="md-prose">
      <ReactMarkdown remarkPlugins={[[remarkGfm, { singleTilde: false }]]}>
        {children}
      </ReactMarkdown>
    </div>
  )
}

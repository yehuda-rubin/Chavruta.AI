import type { Citation } from '../types'

interface Props {
  citation: Citation
  index: number
}

export function CitationCard({ citation, index }: Props) {
  const hasHe = citation.text_he?.trim()
  const hasEn = citation.text_en?.trim()

  return (
    <div className="border border-slate-700 rounded-lg overflow-hidden bg-slate-900/50 text-sm">
      <div className="flex items-center justify-between px-3 py-2 bg-slate-800/60 border-b border-slate-700">
        <span className="text-amber-400 font-medium text-xs">[{index + 1}]</span>
        <a
          href={citation.deep_link || `https://www.sefaria.org/${encodeURIComponent(citation.ref)}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-400 hover:text-blue-300 font-medium truncate max-w-[70%] text-right he"
        >
          {citation.ref}
        </a>
        {citation.commentator && (
          <span className="text-slate-400 text-xs ml-2 shrink-0">{citation.commentator}</span>
        )}
      </div>

      <div className="px-3 py-2 space-y-2">
        {hasHe && (
          <p className="he text-slate-200 leading-relaxed text-base">{citation.text_he}</p>
        )}
        {hasEn && (
          <p className="en text-slate-400 text-xs leading-relaxed">{citation.text_en}</p>
        )}
      </div>
    </div>
  )
}

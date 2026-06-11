// 解析透视 · 结构化块流（Office/无版面坐标文档的画布降级视图）
// DOCX/PPTX/Excel 无 origin.pdf 且 bbox 全 0，改为按阅读顺序铺块卡，
// 仍保留「点块联动」与类型层位色，结构感知依旧可见。

import { Fragment, useEffect } from "react"
import { ImageOff } from "lucide-react"
import type { IRBlock } from "@/api/types"
import { getAssetUrl } from "@/api/client"
import { cn } from "@/lib/utils"
import { isImageType, typeMeta } from "./helpers"
import { BlockTypeBadge } from "./badges"

export function BlockStream({
  blocks, kbId, docId, selectedBlockId, hoveredBlockId, activeSectionId,
  onSelectBlock, onHoverBlock,
}: {
  blocks: IRBlock[]
  kbId: string
  docId: string
  selectedBlockId: string | null
  hoveredBlockId: string | null
  activeSectionId: string | null
  onSelectBlock: (id: string) => void
  onHoverBlock: (id: string | null) => void
}) {
  const ordered = [...blocks].sort((a, b) => a.order_in_doc - b.order_in_doc)
  const crumbOf = (b: IRBlock) => (b.header_path || []).filter(Boolean).join(" › ")

  useEffect(() => {
    if (selectedBlockId) {
      const el = document.getElementById(`block-box-${selectedBlockId}`)
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" })
      }
    }
  }, [selectedBlockId])

  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-surface-2/40 px-4 py-4">
      <div className="mx-auto max-w-2xl space-y-1.5">
        {ordered.map((b, i) => {
          const crumb = crumbOf(b)
          const prevCrumb = i > 0 ? crumbOf(ordered[i - 1]) : ""
          const showCrumb = crumb && crumb !== prevCrumb
          const meta = typeMeta(b.type)
          const isSel = b.block_id === selectedBlockId
          const isHover = b.block_id === hoveredBlockId
          const inActive = !isSel && b.section_id === activeSectionId
          return (
            <Fragment key={b.block_id}>
              {showCrumb && (
                <p className="truncate px-1 pt-3 text-[11px] font-medium text-ink-faint" title={crumb}>
                  {crumb}
                </p>
              )}
              <button
                id={`block-box-${b.block_id}`}
                onClick={() => onSelectBlock(b.block_id)}
                onMouseEnter={() => onHoverBlock(b.block_id)}
                onMouseLeave={() => onHoverBlock(null)}
                className={cn(
                  "block w-full rounded-lg border bg-surface px-3 py-2 text-left transition-colors",
                  isSel
                    ? "border-accent/50 shadow-raised"
                    : isHover || inActive
                      ? "border-border-strong"
                      : "border-border hover:border-border-strong",
                )}
                style={{ borderLeft: `3px solid ${meta.color}` }}
              >
                <div className="mb-1 flex items-center gap-2">
                  <BlockTypeBadge type={b.type} />
                  {b.title_level != null && (
                    <span className="font-mono text-[10px] text-ink-faint">level {b.title_level}</span>
                  )}
                </div>
                {isImageType(b.type) ? (
                  <ImageThumb kbId={kbId} docId={docId} assetId={b.assets[0]} vlm={b.vlm_description} />
                ) : (
                  <p className={cn(
                    "whitespace-pre-wrap break-words text-sm leading-relaxed text-ink-soft",
                    !isSel && "line-clamp-3",
                  )}>
                    {b.text || <span className="italic text-ink-faint">（空文本块）</span>}
                  </p>
                )}
              </button>
            </Fragment>
          )
        })}
      </div>
    </div>
  )
}

function ImageThumb({ kbId, docId, assetId, vlm }: {
  kbId: string; docId: string; assetId?: string; vlm: string
}) {
  return (
    <div className="flex gap-3">
      {assetId ? (
        <img
          src={getAssetUrl(kbId, docId, assetId)}
          alt="图片块"
          className="h-20 w-28 shrink-0 rounded-md border border-border object-cover"
          loading="lazy"
        />
      ) : (
        <div className="flex h-20 w-28 shrink-0 items-center justify-center rounded-md border border-border bg-surface-2 text-ink-faint">
          <ImageOff className="h-5 w-5" />
        </div>
      )}
      {vlm && <p className="line-clamp-4 text-xs leading-relaxed text-ink-soft">{vlm}</p>}
    </div>
  )
}

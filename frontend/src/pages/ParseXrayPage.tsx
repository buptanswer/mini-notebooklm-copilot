// 解析透视 Parse X-Ray（v1.4.0 Phase 3）
// 把 MinerU 解析 → 结构感知 → LLM 文档树重建 → 坐标锚定 → 父子切片 → 图片 VLM
// 这条隐藏流水线揭开成可视化：左=文档树，中=版面 bbox 画布（PDF）/块流（Office），右=解析检视。

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useParams, useSearchParams } from "react-router-dom"
import {
  AlertCircle, Boxes, FileScan, FileText, Image as ImageIcon, Layers,
  ListTree, Loader2, PanelLeftOpen, PanelRightOpen, ScanLine, Sparkles,
} from "lucide-react"
import {
  getDocumentChunks, getDocumentIR, getOriginPdfUrl, listDocIndexes, listDocuments,
} from "@/api/client"
import type { ChunksResponse, DocInfo, ExtraIndex, IRResponse } from "@/api/types"
import { cn } from "@/lib/utils"
import {
  buildMaps, buildSectionTree, hasGeometry,
} from "@/components/dissect/helpers"
import { MetaPill } from "@/components/dissect/badges"
import { DocTree } from "@/components/dissect/DocTree"
import { DocCanvas, type CanvasLayers } from "@/components/dissect/DocCanvas"
import { BlockStream } from "@/components/dissect/BlockStream"
import { Inspector } from "@/components/dissect/Inspector"
import { GranularityControl } from "@/components/dissect/GranularityControl"

const ELIGIBLE_STATUS = new Set(["indexed", "needs_review"])
const isEligible = (d: DocInfo) =>
  ELIGIBLE_STATUS.has(d.status) && d.source_format !== "txt" && d.source_format !== "md"

export default function ParseXrayPage() {
  const { kbId } = useParams<{ kbId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  // 深链参数只在首渲读一次（来自对话页「解析透视」：?doc=&child=/&block=）
  const deepLinkRef = useRef<{ doc: string | null; child: string | null; block: string | null } | null>(null)
  if (deepLinkRef.current === null) {
    deepLinkRef.current = {
      doc: searchParams.get("doc"),
      child: searchParams.get("child"),
      block: searchParams.get("block"),
    }
  }
  const [docs, setDocs] = useState<DocInfo[]>([])
  const [docId, setDocId] = useState<string>("")
  const [ir, setIr] = useState<IRResponse | null>(null)
  const [chunks, setChunks] = useState<ChunksResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null)
  const [selectedSectionId, setSelectedSectionId] = useState<string | null>(null)
  const [selectedParentId, setSelectedParentId] = useState<string | null>(null)
  const [hoveredBlockId, setHoveredBlockId] = useState<string | null>(null)
  const [pageIdx, setPageIdx] = useState(0)
  const [layers, setLayers] = useState<CanvasLayers>({ blocks: true, parents: true, color: true })
  const [treeOpen, setTreeOpen] = useState(true)
  const [inspectorOpen, setInspectorOpen] = useState(true)
  // 父块自定义索引：parent_chunk_id → 该父块索引列表
  const [indexesByParent, setIndexesByParent] = useState<Record<string, ExtraIndex[]>>({})
  // 重切片后自增，触发 IR / chunks / indexes 全量重载
  const [reloadKey, setReloadKey] = useState(0)
  const reqRef = useRef(0)

  // 文档列表
  useEffect(() => {
    if (!kbId) return
    listDocuments(kbId)
      .then((all) => {
        const elig = all.filter(isEligible)
        setDocs(elig)
        const wantDoc = deepLinkRef.current?.doc
        const preferred = wantDoc && elig.some((d) => d.doc_id === wantDoc) ? wantDoc : ""
        setDocId((cur) => cur || preferred || (elig[0]?.doc_id ?? ""))
      })
      .catch((e) => setError((e as Error).message))
  }, [kbId])

  // 加载选中文档的 IR + chunks
  useEffect(() => {
    if (!kbId || !docId) return
    const seq = ++reqRef.current
    setLoading(true)
    setError(null)
    setIr(null)
    setChunks(null)
    setSelectedBlockId(null)
    setSelectedSectionId(null)
    setSelectedParentId(null)
    setPageIdx(0)
    Promise.all([
      getDocumentIR(kbId, docId),
      getDocumentChunks(kbId, docId).catch(() => null), // chunks 缺失不阻断
    ])
      .then(([irRes, chRes]) => {
        if (seq !== reqRef.current) return
        setIr(irRes)
        setChunks(chRes)
      })
      .catch((e) => {
        if (seq !== reqRef.current) return
        setError((e as Error).message || "加载失败")
      })
      .finally(() => {
        if (seq === reqRef.current) setLoading(false)
      })
  }, [kbId, docId, reloadKey])

  // Load extra indexes when docId changes（重切片后随 reloadKey 重载）
  useEffect(() => {
    if (!kbId || !docId) return
    listDocIndexes(kbId, docId)
      .then((r) => setIndexesByParent(r.by_parent))
      .catch(() => setIndexesByParent({}))
  }, [kbId, docId, reloadKey])

  const refreshIndexes = useCallback(() => {
    if (!kbId || !docId) return
    listDocIndexes(kbId, docId)
      .then((r) => setIndexesByParent(r.by_parent))
      .catch(() => {})
  }, [kbId, docId])

  const selectedDoc = useMemo(() => docs.find((d) => d.doc_id === docId) ?? null, [docs, docId])
  const maps = useMemo(() => (ir ? buildMaps(ir, chunks) : null), [ir, chunks])
  const tree = useMemo(() => (ir ? buildSectionTree(ir.sections) : []), [ir])
  const canRenderPdf = useMemo(
    () => !!ir && !!ir.document.origin_pdf_path && hasGeometry(ir.blocks),
    [ir],
  )

  const selectedBlock = (maps && selectedBlockId && maps.blockById.get(selectedBlockId)) || null
  const selectedSection = (maps && selectedSectionId && maps.sectionById.get(selectedSectionId)) || null
  const activeSectionId = selectedBlock?.section_id ?? selectedSectionId

  const selectBlock = (id: string) => {
    setSelectedBlockId(id)
    setSelectedSectionId(null)
    const b = maps?.blockById.get(id)
    if (b && canRenderPdf) setPageIdx(b.page_idx)
    const p = maps?.parentByBlock.get(id)
    setSelectedParentId(p?.parent_chunk_id ?? null)
  }
  const selectSection = (id: string) => {
    setSelectedSectionId(id)
    setSelectedBlockId(null)
    const p = maps ? [...maps.parentById.values()].find((pp) => pp.section_id === id) : null
    setSelectedParentId(p?.parent_chunk_id ?? null)
    const s = maps?.sectionById.get(id)
    if (s && canRenderPdf && s.page_span?.length) setPageIdx(s.page_span[0])
  }
  const selectParent = useCallback((pid: string) => {
    setSelectedParentId(pid)
    setSelectedBlockId(null)
    setSelectedSectionId(null)
    if (!maps || !canRenderPdf) return
    const entries = maps.parentBoxes.get(pid)
    if (entries?.length) setPageIdx(entries[0].page_idx)
  }, [maps, canRenderPdf])

  // 深链：目标文档 maps 就绪后，定位到来源块（block 直选 / child→首个 source_block），仅一次
  useEffect(() => {
    if (!maps) return
    const dl = deepLinkRef.current
    if (!dl || (!dl.child && !dl.block)) return
    let target: string | null = null
    if (dl.block && maps.blockById.has(dl.block)) {
      target = dl.block
    } else if (dl.child) {
      const c = chunks?.children.find((x) => x.child_chunk_id === dl.child)
      target = c?.source_block_ids?.find((id) => maps.blockById.has(id)) ?? null
    }
    deepLinkRef.current = { doc: dl.doc, child: null, block: null } // 用过即清
    if (target) selectBlock(target)
    setSearchParams({}, { replace: true }) // 清 URL，刷新不重复定位
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [maps])

  const pageBlocks = (maps?.blocksByPage.get(pageIdx) ?? [])

  return (
    <div className="flex h-full flex-col bg-bg">
      {/* 头：标题 + 文档选择 + 元数据 */}
      <header className="shrink-0 border-b border-border px-5 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent-soft text-accent">
              <FileScan className="h-5 w-5" />
            </span>
            <div>
              <h1 className="font-display text-lg font-semibold leading-tight text-ink">解析透视</h1>
              <p className="text-[11px] text-ink-faint">看清 PDF 如何被拆解、锚定坐标、重建层级、切成父子块</p>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-2">
            <FileText className="h-4 w-4 text-ink-faint" />
            <div className="relative">
              <select
                value={docId}
                onChange={(e) => setDocId(e.target.value)}
                disabled={!docs.length}
                className="max-w-[280px] truncate rounded-xl border border-border bg-surface py-2 pl-3 pr-8 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50"
              >
                {docs.length === 0 ? (
                  <option value="">无可透视文档</option>
                ) : (
                  docs.map((d) => (
                    <option key={d.doc_id} value={d.doc_id}>
                      {d.filename}
                    </option>
                  ))
                )}
              </select>
            </div>
          </div>
        </div>

        {/* 元数据条 */}
        {ir && maps && (
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <MetaPill icon={FileText} label="格式" value={ir.document.source_format?.toUpperCase() || "—"} />
            <MetaPill icon={FileText} label="页" value={ir.document.page_count} />
            <MetaPill icon={Boxes} label="块" value={ir.blocks.length} />
            <MetaPill icon={Layers} label="小节" value={ir.sections.length} />
            <MetaPill icon={Layers} label="父块" value={chunks?.counts.parents ?? 0} tone="accent" />
            <MetaPill icon={Boxes} label="子块" value={chunks?.counts.children ?? 0} tone="accent" />
            {ir.blocks.some((b) => b.type === "image") && (
              <MetaPill icon={ImageIcon} label="图片" value={ir.blocks.filter((b) => b.type === "image").length} />
            )}
            {ir.enriched && (
              <span className="inline-flex items-center gap-1 rounded-lg border border-accent/30 bg-accent-soft px-2.5 py-1 text-xs text-accent-strong">
                <Sparkles className="h-3.5 w-3.5" /> VLM 富化
              </span>
            )}

            <div className="ml-auto">
              <GranularityControl
                key={docId}
                kbId={kbId!}
                docId={docId}
                currentLevel={selectedDoc?.parent_heading_level ?? 0}
                onReindexed={() => setReloadKey((k) => k + 1)}
              />
            </div>
          </div>
        )}
      </header>

      {/* 主体 */}
      {loading ? (
        <CenterState icon={<Loader2 className="h-7 w-7 animate-spin text-accent" />} text="正在读取解析产物（IR / 父子切片）…" />
      ) : error ? (
        <CenterState icon={<AlertCircle className="h-7 w-7 text-accent" />} text={error} />
      ) : !ir || !maps ? (
        <CenterState
          icon={<FileScan className="h-8 w-8 text-ink-faint" />}
          text={docs.length ? "选择一个文档开始透视" : "该知识库暂无已解析的文档（先在「文件」里解析 PDF / Office / 图片）"}
        />
      ) : (
        <div className="flex min-h-0 flex-1">
          {/* 左：文档树（可收起） */}
          {treeOpen ? (
            <aside className="hidden w-60 shrink-0 border-r border-border bg-surface/40 md:block">
              <DocTree
                tree={tree}
                selectedSectionId={selectedSectionId}
                activeSectionId={activeSectionId}
                blockCount={(sid) => (maps.blocksBySection.get(sid) ?? []).length}
                onSelectSection={selectSection}
                onCollapse={() => setTreeOpen(false)}
              />
            </aside>
          ) : (
            <RailReopen side="left" icon={ListTree} label="文档树" onClick={() => setTreeOpen(true)} />
          )}

          {/* 中：画布 / 块流 */}
          <main className="min-w-0 flex-1">
            {canRenderPdf ? (
              <DocCanvas
                pdfUrl={getOriginPdfUrl(kbId!, docId)}
                pageIdx={pageIdx}
                pageCount={Math.max(1, ir.document.page_count || ir.pages.length || 1)}
                blocks={pageBlocks}
                parentBoxes={maps.parentBoxes}
                selectedBlockId={selectedBlockId}
                hoveredBlockId={hoveredBlockId}
                activeSectionId={activeSectionId}
                selectedParentId={selectedParentId}
                layers={layers}
                onLayers={setLayers}
                onSelectBlock={selectBlock}
                onSelectParent={selectParent}
                onHoverBlock={setHoveredBlockId}
                onPageChange={setPageIdx}
              />
            ) : (
              <BlockStream
                blocks={ir.blocks}
                kbId={kbId!}
                docId={docId}
                selectedBlockId={selectedBlockId}
                hoveredBlockId={hoveredBlockId}
                activeSectionId={activeSectionId}
                onSelectBlock={selectBlock}
                onHoverBlock={setHoveredBlockId}
              />
            )}
          </main>

          {/* 右：解析检视（可收起） */}
          {inspectorOpen ? (
            <aside className="hidden w-[360px] shrink-0 border-l border-border bg-surface/40 lg:block">
              <Inspector
                ir={ir}
                maps={maps}
                kbId={kbId!}
                docId={docId}
                parentCount={chunks?.counts.parents ?? 0}
                childCount={chunks?.counts.children ?? 0}
                selectedBlock={selectedBlock}
                selectedSection={selectedSection}
                selectedParentId={selectedParentId}
                indexesByParent={indexesByParent}
                onSelectBlock={selectBlock}
                onSelectSection={selectSection}
                onSelectParent={selectParent}
                onRefreshIndexes={refreshIndexes}
                onCollapse={() => setInspectorOpen(false)}
              />
            </aside>
          ) : (
            <RailReopen side="right" icon={ScanLine} label="解析检视" onClick={() => setInspectorOpen(true)} />
          )}
        </div>
      )}
    </div>
  )
}

function CenterState({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center text-ink-soft">
      {icon}
      <p className="max-w-sm text-sm">{text}</p>
    </div>
  )
}

/** 收起后的细条，点击重新展开侧栏。 */
function RailReopen({ side, icon: Icon, label, onClick }: {
  side: "left" | "right"
  icon: React.ComponentType<{ className?: string }>
  label: string
  onClick: () => void
}) {
  const ReopenIcon = side === "left" ? PanelLeftOpen : PanelRightOpen
  return (
    <button
      onClick={onClick}
      title={`展开${label}`}
      className={cn(
        "hidden w-9 shrink-0 flex-col items-center gap-3 bg-surface/40 py-3 text-ink-faint transition-colors hover:text-accent md:flex",
        side === "left" ? "border-r border-border" : "border-l border-border",
      )}
    >
      <ReopenIcon className="h-4 w-4" />
      <span className="flex items-center gap-1.5 text-xs [writing-mode:vertical-rl]">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </span>
    </button>
  )
}

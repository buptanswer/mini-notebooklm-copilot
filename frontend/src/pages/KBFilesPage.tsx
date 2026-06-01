import { useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import {
  AlertTriangle, CheckSquare, ChevronDown, ChevronRight, Database, FileText,
  FolderClosed, FolderOpen, FolderPlus, FolderSync, MessagesSquare, PlayCircle,
  RefreshCw, Square, Trash2, Upload,
} from "lucide-react"
import {
  deleteDocument, getKB, indexTextDoc, listDocuments, syncFolder, triggerParse, uploadDocument,
} from "@/api/client"
import type { DocInfo, DocStatus, KBInfo } from "@/api/types"
import { Btn, Modal } from "@/components/Modal"
import { cn } from "@/lib/utils"

const STATUS_LABEL: Record<DocStatus, string> = {
  uploaded: "待解析", parsing: "解析中", needs_review: "需检视", indexed: "已索引",
  failed: "失败", text_only: "纯文本", missing: "已消失",
}
const STATUS_STYLE: Record<DocStatus, string> = {
  uploaded: "bg-surface-2 text-ink-soft",
  parsing: "bg-accent-soft text-accent",
  needs_review: "bg-accent-soft text-accent",
  indexed: "bg-[color:var(--c-success)]/15 text-[color:var(--c-success)]",
  failed: "bg-accent-soft text-accent",
  text_only: "bg-surface-2 text-ink-soft",
  missing: "bg-surface-2 text-ink-faint",
}

const StatusBadge = ({ status }: { status: DocStatus }) => (
  <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium", STATUS_STYLE[status])}>
    {status === "parsing" && <span className="breathe-dot h-1.5 w-1.5 rounded-full bg-accent" />}
    {status === "needs_review" && <AlertTriangle className="h-3 w-3" />}
    {STATUS_LABEL[status]}
  </span>
)

const formatBytes = (n: number) =>
  n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`

// ── Tree ─────────────────────────────────────────────────────
interface FolderNode { type: "folder"; name: string; fullPath: string; children: TreeItem[] }
interface FileNode { type: "file"; name: string; fullPath: string; doc: DocInfo }
type TreeItem = FolderNode | FileNode

function buildTree(docs: DocInfo[]): TreeItem[] {
  const rootItems: TreeItem[] = []
  const folderMap = new Map<string, FolderNode>()
  function getFolder(path: string): FolderNode {
    const existing = folderMap.get(path)
    if (existing) return existing
    const parts = path.split("/")
    const node: FolderNode = { type: "folder", name: parts[parts.length - 1], fullPath: path, children: [] }
    folderMap.set(path, node)
    if (parts.length === 1) rootItems.push(node)
    else getFolder(parts.slice(0, -1).join("/")).children.push(node)
    return node
  }
  for (const doc of docs) {
    const rp = doc.relative_path || doc.filename
    const parts = rp.split("/")
    if (parts.length === 1) rootItems.push({ type: "file", name: doc.filename, fullPath: rp, doc })
    else getFolder(parts.slice(0, -1).join("/")).children.push({ type: "file", name: parts[parts.length - 1], fullPath: rp, doc })
  }
  const sortItems = (items: TreeItem[]): TreeItem[] =>
    [...items].sort((a, b) => (a.type !== b.type ? (a.type === "folder" ? -1 : 1) : a.name.localeCompare(b.name)))
      .map((it) => (it.type === "folder" ? { ...it, children: sortItems(it.children) } : it))
  return sortItems(rootItems)
}
function flattenVisible(nodes: TreeItem[], collapsed: Set<string>): DocInfo[] {
  const out: DocInfo[] = []
  for (const n of nodes) {
    if (n.type === "file") out.push(n.doc)
    else if (!collapsed.has(n.fullPath)) out.push(...flattenVisible(n.children, collapsed))
  }
  return out
}
function countFiles(node: TreeItem): number {
  return node.type === "file" ? 1 : node.children.reduce((s, c) => s + countFiles(c), 0)
}

export default function KBFilesPage() {
  const { kbId } = useParams<{ kbId: string }>()
  const navigate = useNavigate()
  const [kbInfo, setKbInfo] = useState<KBInfo | null>(null)
  const [docs, setDocs] = useState<DocInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [uploading, setUploading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState("")
  const [dragOver, setDragOver] = useState(false)
  const [delTarget, setDelTarget] = useState<DocInfo | null>(null)
  const [actioningId, setActioningId] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const lastClickedRef = useRef<string | null>(null)

  const load = async () => {
    if (!kbId) return
    try {
      const [data, kb] = await Promise.all([listDocuments(kbId), kbInfo ? Promise.resolve(kbInfo) : getKB(kbId)])
      setDocs(data); if (!kbInfo) setKbInfo(kb); setError("")
    } catch (e) { setError((e as Error).message) } finally { setLoading(false) }
  }
  useEffect(() => { load(); return () => { if (pollingRef.current) clearInterval(pollingRef.current) } /* eslint-disable-next-line */ }, [kbId])
  useEffect(() => {
    const busy = docs.some((d) => d.status === "parsing")
    if (busy && !pollingRef.current) pollingRef.current = setInterval(load, 3000)
    else if (!busy && pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
  }, [docs]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const fi = folderInputRef.current
    if (fi) { fi.setAttribute("webkitdirectory", ""); fi.setAttribute("directory", "") }
  }, [])

  const canParse = (d: DocInfo) =>
    ["uploaded", "failed", "needs_review"].includes(d.status) && d.source_format !== "txt" && d.source_format !== "md"
  const canIndexText = (d: DocInfo) =>
    (d.source_format === "md" || d.source_format === "txt") &&
    !(d.folder_category === "recording" && d.source_format === "txt") &&
    d.status !== "missing"

  const handleFiles = async (files: FileList | File[], fromFolder = false) => {
    if (!kbId) return
    const arr = Array.from(files)
    if (!arr.length) return
    setUploading(true)
    let fail = 0, lastErr = ""
    for (const file of arr) {
      try {
        const relPath = fromFolder && file.webkitRelativePath ? file.webkitRelativePath : file.name
        const doc = await uploadDocument(kbId, file, relPath)
        if (doc.source_format !== "txt" && doc.source_format !== "md") await triggerParse(kbId, doc.doc_id)
      } catch (e) { fail++; lastErr = (e as Error).message }
    }
    setUploading(false)
    setError(fail > 0 ? `上传完成，但 ${fail} 个失败：${lastErr}` : "")
    await load()
  }

  const handleReParse = async (doc: DocInfo) => {
    if (!kbId) return
    setActioningId(doc.doc_id)
    try { await triggerParse(kbId, doc.doc_id); await load() }
    catch (e) { setError((e as Error).message) } finally { setActioningId(null) }
  }
  const handleIndexText = async (doc: DocInfo) => {
    if (!kbId) return
    setActioningId(doc.doc_id)
    try { await indexTextDoc(kbId, doc.doc_id); await load() }
    catch (e) { setError((e as Error).message) } finally { setActioningId(null) }
  }
  const handleDelete = async () => {
    if (!kbId || !delTarget) return
    try {
      await deleteDocument(kbId, delTarget.doc_id)
      setSelected((p) => { const n = new Set(p); n.delete(delTarget.doc_id); return n })
      setDelTarget(null); await load()
    } catch (e) { setError((e as Error).message) }
  }
  const handleSync = async () => {
    if (!kbId) return
    setSyncing(true); setSyncResult("")
    try {
      const diff = await syncFolder(kbId)
      setSyncResult(`同步完成：新增 ${diff.added.length}，消失 ${diff.removed.length}，未变 ${diff.unchanged}`)
      await load()
    } catch (e) { setError((e as Error).message) } finally { setSyncing(false) }
  }

  const tree = buildTree(docs)
  const allSelected = docs.length > 0 && selected.size === docs.length
  const toggleSelectAll = () => setSelected(allSelected ? new Set() : new Set(docs.map((d) => d.doc_id)))
  const toggleFolder = (p: string) => setCollapsed((prev) => { const n = new Set(prev); if (n.has(p)) n.delete(p); else n.add(p); return n })
  const selectDoc = (docId: string, e: React.MouseEvent) => {
    if (e.shiftKey && lastClickedRef.current) {
      const flat = flattenVisible(tree, collapsed)
      const i1 = flat.findIndex((d) => d.doc_id === lastClickedRef.current)
      const i2 = flat.findIndex((d) => d.doc_id === docId)
      if (i1 !== -1 && i2 !== -1) {
        const [lo, hi] = [Math.min(i1, i2), Math.max(i1, i2)]
        setSelected((p) => { const n = new Set(p); flat.slice(lo, hi + 1).forEach((d) => n.add(d.doc_id)); return n }); return
      }
    }
    lastClickedRef.current = docId
    setSelected((p) => { const n = new Set(p); if (n.has(docId)) n.delete(docId); else n.add(docId); return n })
  }
  const batchDelete = async () => {
    if (!kbId || !selected.size || !window.confirm(`确认批量删除 ${selected.size} 个文件？不可恢复。`)) return
    for (const id of selected) { try { await deleteDocument(kbId, id) } catch { /* ignore */ } }
    setSelected(new Set()); await load()
  }
  const batchReParse = async () => {
    if (!kbId || !selected.size) return
    const cands = docs.filter((d) => selected.has(d.doc_id) && canParse(d))
    if (!cands.length) { setError("所选文件均不可重新解析"); return }
    for (const d of cands) { try { await triggerParse(kbId, d.doc_id) } catch { /* ignore */ } }
    await load()
  }

  const renderNodes = (nodes: TreeItem[], depth: number): React.ReactNode =>
    nodes.map((node) => {
      if (node.type === "file") {
        const doc = node.doc
        return (
          <div key={doc.doc_id} style={{ marginLeft: depth * 18 }}>
            <div className="mb-1.5 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-surface px-4 py-2.5">
              <button onClick={(e) => selectDoc(doc.doc_id, e)} className="text-ink-faint hover:text-accent">
                {selected.has(doc.doc_id) ? <CheckSquare className="h-4 w-4 text-accent" /> : <Square className="h-4 w-4" />}
              </button>
              <FileText className="h-4 w-4 shrink-0 text-ink-faint" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink" title={doc.filename}>{doc.filename}</p>
                <p className="mt-0.5 text-xs text-ink-faint">
                  {doc.source_format?.toUpperCase() || "—"} · {formatBytes(doc.file_size)}{doc.page_count ? ` · ${doc.page_count} 页` : ""}
                </p>
              </div>
              <StatusBadge status={doc.status} />
              <div className="flex shrink-0 gap-1">
                {canIndexText(doc) && (
                  <button onClick={() => handleIndexText(doc)} disabled={actioningId === doc.doc_id}
                    className="rounded-lg p-1.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-accent disabled:opacity-40" title="索引到检索库">
                    <Database className="h-4 w-4" />
                  </button>
                )}
                {canParse(doc) && (
                  <button onClick={() => handleReParse(doc)} disabled={actioningId === doc.doc_id}
                    className="rounded-lg p-1.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-accent disabled:opacity-40" title="解析">
                    <PlayCircle className="h-4 w-4" />
                  </button>
                )}
                <button onClick={() => setDelTarget(doc)} className="rounded-lg p-1.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-accent" title="删除">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
            {doc.status === "needs_review" && doc.warnings && (
              <div className="mb-1.5 rounded-xl border border-border bg-accent-soft px-4 py-2 text-xs text-accent" style={{ marginLeft: depth * 18 }}>
                <span className="font-medium">MinerU 解析警告：</span><span className="whitespace-pre-line">{doc.warnings}</span>
              </div>
            )}
          </div>
        )
      }
      const isCollapsed = collapsed.has(node.fullPath)
      return (
        <div key={node.fullPath}>
          <button onClick={() => toggleFolder(node.fullPath)} style={{ marginLeft: depth * 18 }}
            className="mb-1 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-sm text-ink-soft transition-colors hover:bg-surface-2">
            {isCollapsed ? <ChevronRight className="h-4 w-4 text-ink-faint" /> : <ChevronDown className="h-4 w-4 text-ink-faint" />}
            {isCollapsed ? <FolderClosed className="h-4 w-4 text-accent" /> : <FolderOpen className="h-4 w-4 text-accent" />}
            <span className="flex-1 text-left font-medium">{node.name}</span>
            <span className="text-xs text-ink-faint">{countFiles(node)} 个文件</span>
          </button>
          {!isCollapsed && renderNodes(node.children, depth + 1)}
        </div>
      )
    })

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-6 py-6">
        <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="font-display text-2xl font-semibold text-ink">{kbInfo?.name ?? "文件"}</h1>
            <p className="mt-0.5 text-xs text-ink-faint">{kbInfo?.description || "管理文档：上传、解析、索引"}</p>
          </div>
          <div className="flex gap-2">
            {kbInfo?.bound_folder_path && (
              <Btn variant="ghost" onClick={handleSync} disabled={syncing}>
                <FolderSync className={cn("h-4 w-4", syncing && "animate-spin")} />同步文件夹
              </Btn>
            )}
            <Btn variant="ghost" onClick={() => { setLoading(true); load() }}><RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />刷新</Btn>
            <Btn onClick={() => navigate(`/kb/${kbId}/chat`)}><MessagesSquare className="h-4 w-4" />对话</Btn>
          </div>
        </header>

        {error && <div className="mb-4 rounded-xl border border-border bg-accent-soft px-4 py-2.5 text-sm text-accent">⚠ {error}</div>}
        {syncResult && <div className="mb-4 rounded-xl border border-border bg-[color:var(--c-success)]/12 px-4 py-2.5 text-sm text-[color:var(--c-success)]">✓ {syncResult}</div>}

        {/* 上传区 */}
        <div
          className={cn("mb-6 rounded-2xl border-2 border-dashed p-8 text-center transition-colors", dragOver ? "border-accent bg-accent-soft" : "border-border bg-surface/40")}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files) }}
        >
          <input ref={fileInputRef} type="file" multiple accept=".pdf,.docx,.doc,.pptx,.ppt,.png,.jpg,.jpeg,.txt,.md" className="hidden" onChange={(e) => e.target.files && handleFiles(e.target.files)} />
          <input ref={folderInputRef} type="file" multiple className="hidden" onChange={(e) => e.target.files && handleFiles(e.target.files, true)} />
          {uploading ? (
            <div className="flex flex-col items-center gap-2 text-accent"><Upload className="breathe-dot h-7 w-7" /><p className="text-sm font-medium">上传并解析中…</p></div>
          ) : (
            <div className="flex flex-col items-center gap-2 text-ink-faint">
              <Upload className="h-7 w-7 opacity-60" />
              <p className="text-sm text-ink-soft">拖放文件到此，或</p>
              <div className="flex gap-2">
                <Btn variant="ghost" onClick={() => fileInputRef.current?.click()}>选择文件</Btn>
                <Btn variant="ghost" onClick={() => folderInputRef.current?.click()}><FolderPlus className="h-4 w-4" />上传文件夹</Btn>
              </div>
              <p className="mt-1 text-xs">支持 PDF / Word / PPT / 图片 / TXT / MD</p>
            </div>
          )}
        </div>

        {loading ? (
          <div className="py-12 text-center text-ink-faint">加载中…</div>
        ) : docs.length === 0 ? (
          <div className="card flex flex-col items-center border-dashed py-12 text-center text-ink-faint">
            <FileText className="mb-2 h-8 w-8 opacity-50" /><p className="text-sm">暂无文件，请先上传或同步文件夹</p>
          </div>
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-surface px-3 py-2">
              <button onClick={toggleSelectAll} className="inline-flex items-center gap-2 text-sm text-ink-soft hover:text-ink">
                {allSelected ? <CheckSquare className="h-4 w-4 text-accent" /> : <Square className="h-4 w-4" />}
                全选 ({selected.size}/{docs.length})
              </button>
              <span className="text-xs text-ink-faint">Shift+点击 范围选择</span>
              <div className="flex gap-2">
                <Btn variant="ghost" onClick={batchReParse} disabled={!selected.size}><PlayCircle className="h-4 w-4" />批量解析</Btn>
                <Btn variant="danger" onClick={batchDelete} disabled={!selected.size}><Trash2 className="h-4 w-4" />批量删除</Btn>
              </div>
            </div>
            {renderNodes(tree, 0)}
          </>
        )}
      </div>

      <Modal
        open={!!delTarget}
        onClose={() => setDelTarget(null)}
        title="删除文件"
        description={`确认删除「${delTarget?.filename}」？相关向量索引与任务记录将一并删除，不可恢复。`}
        footer={<><Btn variant="ghost" onClick={() => setDelTarget(null)}>取消</Btn><Btn variant="danger" onClick={handleDelete}>确认删除</Btn></>}
      />
    </div>
  )
}

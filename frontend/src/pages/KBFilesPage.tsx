import { useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import {
  Upload, Trash2, RefreshCw, MessageSquare, ArrowLeft,
  PlayCircle, FileText, AlertTriangle, FolderPlus, CheckSquare, Square,
  FolderSync, Folder, FolderOpen, ChevronRight, ChevronDown,
} from "lucide-react"
import {
  listDocuments, uploadDocument, triggerParse, deleteDocument, getKB, syncFolder,
} from "@/api/client"
import type { DocInfo, DocStatus, KBInfo } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Spinner } from "@/components/ui/spinner"
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert"
import { Dialog, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogClose } from "@/components/ui/dialog"
import { Progress } from "@/components/ui/progress"

const STATUS_LABEL: Record<DocStatus, string> = {
  uploaded: "已上传",
  parsing: "解析中",
  needs_review: "需检视",
  indexed: "已索引",
  failed: "失败",
  text_only: "可用",
  missing: "已消失",
}

const StatusBadge = ({ status }: { status: DocStatus }) => {
  const variants: Record<DocStatus, "secondary" | "default" | "warning" | "success" | "destructive"> = {
    uploaded: "secondary",
    parsing: "default",
    needs_review: "warning",
    indexed: "success",
    failed: "destructive",
    text_only: "success",
    missing: "secondary",
  }
  return (
    <span className="flex items-center gap-1">
      {status === "parsing" && <Spinner size="sm" />}
      {status === "needs_review" && <AlertTriangle className="h-3 w-3 text-yellow-600" />}
      <Badge variant={variants[status]}>{STATUS_LABEL[status]}</Badge>
    </span>
  )
}

const formatBytes = (n: number) => {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

// ── Tree 数据结构 ────────────────────────────────────────────

interface FolderNode {
  type: "folder"
  name: string
  fullPath: string
  children: TreeItem[]
}
interface FileNode {
  type: "file"
  name: string
  fullPath: string
  doc: DocInfo
}
type TreeItem = FolderNode | FileNode

function buildTree(docs: DocInfo[]): TreeItem[] {
  const sorted = [...docs].sort((a, b) => {
    const pa = (a.relative_path || a.filename).toLowerCase()
    const pb = (b.relative_path || b.filename).toLowerCase()
    return pa.localeCompare(pb)
  })

  const rootItems: TreeItem[] = []
  const folderMap = new Map<string, FolderNode>()

  function getOrCreateFolder(path: string): FolderNode {
    if (folderMap.has(path)) return folderMap.get(path)!
    const parts = path.split("/")
    const name = parts[parts.length - 1]
    const node: FolderNode = { type: "folder", name, fullPath: path, children: [] }
    folderMap.set(path, node)
    if (parts.length === 1) {
      rootItems.push(node)
    } else {
      const parentPath = parts.slice(0, -1).join("/")
      getOrCreateFolder(parentPath).children.push(node)
    }
    return node
  }

  for (const doc of sorted) {
    const rp = doc.relative_path || doc.filename
    const parts = rp.split("/")
    if (parts.length === 1) {
      rootItems.push({ type: "file", name: doc.filename, fullPath: rp, doc })
    } else {
      const dirPath = parts.slice(0, -1).join("/")
      getOrCreateFolder(dirPath).children.push({
        type: "file", name: parts[parts.length - 1], fullPath: rp, doc,
      })
    }
  }

  function sortItems(items: TreeItem[]): TreeItem[] {
    return [...items]
      .sort((a, b) => {
        if (a.type !== b.type) return a.type === "folder" ? -1 : 1
        return a.name.localeCompare(b.name)
      })
      .map(item =>
        item.type === "folder"
          ? { ...item, children: sortItems(item.children) }
          : item
      )
  }

  return sortItems(rootItems)
}

function flattenVisible(nodes: TreeItem[], collapsed: Set<string>): DocInfo[] {
  const result: DocInfo[] = []
  for (const node of nodes) {
    if (node.type === "file") {
      result.push(node.doc)
    } else if (!collapsed.has(node.fullPath)) {
      result.push(...flattenVisible(node.children, collapsed))
    }
  }
  return result
}

// ── 单文件行组件 ─────────────────────────────────────────────

const FileRow = ({
  doc, depth, selected, actioningId, canParse,
  onSelect, onReParse, onDelete,
}: {
  doc: DocInfo
  depth: number
  selected: boolean
  actioningId: string | null
  canParse: boolean
  onSelect: (e: React.MouseEvent) => void
  onReParse: () => void
  onDelete: () => void
}) => (
  <div>
    <div
      className="flex items-center gap-3 flex-wrap rounded-lg border border-gray-200 bg-white px-4 py-3 shadow-sm mb-1"
      style={{ marginLeft: depth * 20 }}
    >
      <button type="button" className="text-gray-400 hover:text-blue-600" onClick={onSelect}>
        {selected
          ? <CheckSquare className="h-4 w-4 text-blue-600" />
          : <Square className="h-4 w-4" />}
      </button>
      <FileText className="h-5 w-5 text-gray-400 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-800 truncate" title={doc.filename}>
          {doc.filename}
        </p>
        <p className="text-xs text-gray-400 mt-0.5">
          {doc.source_format?.toUpperCase() || "—"} · {formatBytes(doc.file_size)}
          {doc.page_count ? ` · ${doc.page_count} 页` : ""}
        </p>
      </div>
      <StatusBadge status={doc.status} />
      <div className="flex gap-2 shrink-0">
        {canParse && (
          <button
            className="p-1.5 rounded hover:bg-blue-50 text-blue-400 hover:text-blue-600 transition-colors disabled:opacity-40"
            title="重新解析"
            disabled={actioningId === doc.doc_id}
            onClick={onReParse}
          >
            {actioningId === doc.doc_id ? <Spinner size="sm" /> : <PlayCircle className="h-4 w-4" />}
          </button>
        )}
        <button
          className="p-1.5 rounded hover:bg-red-50 text-gray-300 hover:text-red-500 transition-colors"
          title="删除文件"
          onClick={onDelete}
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
    {doc.status === "parsing" && (
      <Progress value={undefined} className="mt-[-4px] mb-1 h-1" style={{ marginLeft: depth * 20 }} />
    )}
    {doc.status === "needs_review" && doc.warnings && (
      <Alert variant="warning" className="mb-1 rounded-t-none border-t-0" style={{ marginLeft: depth * 20 }}>
        <AlertTitle className="flex items-center gap-1">
          <AlertTriangle className="h-4 w-4" /> MinerU 解析警告
        </AlertTitle>
        <AlertDescription className="text-xs mt-1 whitespace-pre-line">{doc.warnings}</AlertDescription>
      </Alert>
    )}
  </div>
)

// ── 文件夹行组件 ─────────────────────────────────────────────

const FolderRow = ({
  node, depth, collapsed, fileCount,
  onToggle,
}: {
  node: FolderNode
  depth: number
  collapsed: boolean
  fileCount: number
  onToggle: () => void
}) => (
  <button
    type="button"
    className="w-full flex items-center gap-2 rounded-lg px-3 py-2 mb-1 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
    style={{ marginLeft: depth * 20 }}
    onClick={onToggle}
  >
    {collapsed
      ? <ChevronRight className="h-4 w-4 text-gray-400 shrink-0" />
      : <ChevronDown className="h-4 w-4 text-gray-400 shrink-0" />}
    {collapsed
      ? <Folder className="h-4 w-4 text-amber-500 shrink-0" />
      : <FolderOpen className="h-4 w-4 text-amber-500 shrink-0" />}
    <span className="font-medium flex-1 text-left">{node.name}</span>
    <span className="text-xs text-gray-400">{fileCount} 个文件</span>
  </button>
)

// ── 递归树渲染 ────────────────────────────────────────────────

function countFiles(node: TreeItem): number {
  if (node.type === "file") return 1
  return node.children.reduce((s, c) => s + countFiles(c), 0)
}

function TreeNodes({
  nodes, depth, collapsed, selected, actioningId, canParseFn,
  onToggleFolder, onSelectDoc, onReParse, onDelete,
}: {
  nodes: TreeItem[]
  depth: number
  collapsed: Set<string>
  selected: Set<string>
  actioningId: string | null
  canParseFn: (doc: DocInfo) => boolean
  onToggleFolder: (path: string) => void
  onSelectDoc: (docId: string, e: React.MouseEvent) => void
  onReParse: (doc: DocInfo) => void
  onDelete: (doc: DocInfo) => void
}) {
  return (
    <>
      {nodes.map(node => {
        if (node.type === "file") {
          return (
            <FileRow
              key={node.doc.doc_id}
              doc={node.doc}
              depth={depth}
              selected={selected.has(node.doc.doc_id)}
              actioningId={actioningId}
              canParse={canParseFn(node.doc)}
              onSelect={e => onSelectDoc(node.doc.doc_id, e)}
              onReParse={() => onReParse(node.doc)}
              onDelete={() => onDelete(node.doc)}
            />
          )
        }
        const isCollapsed = collapsed.has(node.fullPath)
        return (
          <div key={node.fullPath}>
            <FolderRow
              node={node}
              depth={depth}
              collapsed={isCollapsed}
              fileCount={countFiles(node)}
              onToggle={() => onToggleFolder(node.fullPath)}
            />
            {!isCollapsed && (
              <TreeNodes
                nodes={node.children}
                depth={depth + 1}
                collapsed={collapsed}
                selected={selected}
                actioningId={actioningId}
                canParseFn={canParseFn}
                onToggleFolder={onToggleFolder}
                onSelectDoc={onSelectDoc}
                onReParse={onReParse}
                onDelete={onDelete}
              />
            )}
          </div>
        )
      })}
    </>
  )
}

// ── 主页面 ────────────────────────────────────────────────────

export default function KBFilesPage() {
  const { kbId } = useParams<{ kbId: string }>()
  const navigate = useNavigate()
  const [kbInfo, setKbInfo] = useState<KBInfo | null>(null)
  const [docs, setDocs] = useState<DocInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [uploading, setUploading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState<string>("")
  const [dragOver, setDragOver] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<DocInfo | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [actioningId, setActioningId] = useState<string | null>(null)
  const [batchDeleting, setBatchDeleting] = useState(false)
  const [batchParsing, setBatchParsing] = useState(false)
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set())
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(new Set())
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const lastClickedIdRef = useRef<string | null>(null)

  const load = async () => {
    if (!kbId) return
    try {
      const [data, kb] = await Promise.all([
        listDocuments(kbId),
        kbInfo ? Promise.resolve(kbInfo) : getKB(kbId),
      ])
      setDocs(data)
      if (!kbInfo) setKbInfo(kb)
      setError("")
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    return () => { if (pollingRef.current) clearInterval(pollingRef.current) }
  }, [kbId])

  useEffect(() => {
    const anyParsing = docs.some(d => d.status === "parsing")
    if (anyParsing) {
      if (!pollingRef.current) pollingRef.current = setInterval(load, 3000)
    } else {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
    }
  }, [docs])

  useEffect(() => {
    const folderInput = folderInputRef.current
    if (folderInput) {
      folderInput.setAttribute("webkitdirectory", "")
      folderInput.setAttribute("directory", "")
    }
  }, [])

  const handleFiles = async (files: FileList | File[], fromFolder = false) => {
    if (!kbId) return
    const arr = Array.from(files)
    if (arr.length === 0) return
    setUploading(true)
    let failCount = 0
    let lastErr = ""
    for (const file of arr) {
      try {
        const relPath = fromFolder && file.webkitRelativePath ? file.webkitRelativePath : file.name
        const doc = await uploadDocument(kbId, file, relPath)
        if (doc.source_format !== "txt" && doc.source_format !== "md") {
          await triggerParse(kbId, doc.doc_id)
        }
      } catch (e) {
        failCount += 1
        lastErr = (e as Error).message
      }
    }
    setUploading(false)
    if (failCount > 0) setError(`上传完成，但有 ${failCount} 个文件失败：${lastErr}`)
    else setError("")
    await load()
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    handleFiles(e.dataTransfer.files, false)
  }

  const handleReParse = async (doc: DocInfo) => {
    if (!kbId) return
    setActioningId(doc.doc_id)
    try {
      await triggerParse(kbId, doc.doc_id)
      await load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setActioningId(null)
    }
  }

  const handleDelete = async () => {
    if (!kbId || !deleteTarget) return
    setDeleting(true)
    try {
      await deleteDocument(kbId, deleteTarget.doc_id)
      setDeleteTarget(null)
      setSelectedDocIds(prev => { const next = new Set(prev); next.delete(deleteTarget.doc_id); return next })
      await load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setDeleting(false)
    }
  }

  const canParse = (doc: DocInfo) =>
    (doc.status === "uploaded" || doc.status === "failed" || doc.status === "needs_review")
    && doc.source_format !== "txt" && doc.source_format !== "md"

  const handleSyncFolder = async () => {
    if (!kbId) return
    setSyncing(true)
    setSyncResult("")
    try {
      const diff = await syncFolder(kbId)
      setSyncResult(`同步完成：新增 ${diff.added.length} 个，消失 ${diff.removed.length} 个，未变化 ${diff.unchanged} 个`)
      await load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSyncing(false)
    }
  }

  const allSelected = docs.length > 0 && selectedDocIds.size === docs.length
  const tree = buildTree(docs)

  const toggleSelectAll = () => {
    if (allSelected) setSelectedDocIds(new Set())
    else setSelectedDocIds(new Set(docs.map(d => d.doc_id)))
  }

  const handleToggleFolder = (path: string) => {
    setCollapsedFolders(prev => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const handleSelectDoc = (docId: string, e: React.MouseEvent) => {
    if (e.shiftKey && lastClickedIdRef.current) {
      const flat = flattenVisible(tree, collapsedFolders)
      const i1 = flat.findIndex(d => d.doc_id === lastClickedIdRef.current)
      const i2 = flat.findIndex(d => d.doc_id === docId)
      if (i1 !== -1 && i2 !== -1) {
        const lo = Math.min(i1, i2)
        const hi = Math.max(i1, i2)
        setSelectedDocIds(prev => {
          const next = new Set(prev)
          flat.slice(lo, hi + 1).forEach(d => next.add(d.doc_id))
          return next
        })
        return
      }
    }
    lastClickedIdRef.current = docId
    setSelectedDocIds(prev => {
      const next = new Set(prev)
      if (next.has(docId)) next.delete(docId)
      else next.add(docId)
      return next
    })
  }

  const handleBatchDelete = async () => {
    if (!kbId || selectedDocIds.size === 0) return
    if (!window.confirm(`确认批量删除 ${selectedDocIds.size} 个文件？此操作不可恢复。`)) return
    setBatchDeleting(true)
    let failed = 0
    let lastErr = ""
    for (const docId of selectedDocIds) {
      try { await deleteDocument(kbId, docId) } catch (e) { failed++; lastErr = (e as Error).message }
    }
    setBatchDeleting(false)
    if (failed > 0) setError(`批量删除完成，但有 ${failed} 个失败：${lastErr}`)
    setSelectedDocIds(new Set())
    await load()
  }

  const handleBatchReParse = async () => {
    if (!kbId || selectedDocIds.size === 0) return
    const candidates = docs.filter(d => selectedDocIds.has(d.doc_id) && canParse(d))
    if (candidates.length === 0) {
      setError("所选文件均不可重新解析（仅 uploaded/failed/needs_review 可触发）")
      return
    }
    setBatchParsing(true)
    let failed = 0
    let lastErr = ""
    for (const doc of candidates) {
      try { await triggerParse(kbId, doc.doc_id) } catch (e) { failed++; lastErr = (e as Error).message }
    }
    setBatchParsing(false)
    if (failed > 0) setError(`批量重解析完成，但有 ${failed} 个失败：${lastErr}`)
    await load()
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-5 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <button onClick={() => navigate("/")} className="text-gray-400 hover:text-gray-600">
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-gray-900">{kbInfo ? kbInfo.name : "文件管理"}</h1>
            <p className="text-xs text-gray-400">{kbInfo?.description || `知识库 ID: ${kbId}`}</p>
          </div>
        </div>
        <div className="flex gap-2">
          {kbInfo?.bound_folder_path && (
            <Button variant="outline" onClick={handleSyncFolder} disabled={syncing}>
              <FolderSync className={`h-4 w-4 mr-1 ${syncing ? "animate-spin" : ""}`} />
              同步文件夹
            </Button>
          )}
          <Button variant="outline" onClick={() => { setLoading(true); load() }} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} />
            刷新
          </Button>
          <Button onClick={() => navigate(`/kb/${kbId}/chat`)}>
            <MessageSquare className="h-4 w-4 mr-1" />
            开始对话
          </Button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 text-red-700 p-3 text-sm">⚠ {error}</div>
      )}
      {syncResult && (
        <div className="mb-4 rounded-lg bg-green-50 border border-green-200 text-green-700 p-3 text-sm">✓ {syncResult}</div>
      )}

      {/* Upload Zone */}
      <div
        className={`mb-6 rounded-xl border-2 border-dashed p-8 text-center transition-colors
          ${dragOver ? "border-blue-400 bg-blue-50" : "border-gray-200 bg-gray-50 hover:border-gray-300"}`}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <input ref={fileInputRef} type="file" multiple accept=".pdf,.docx,.doc,.pptx,.ppt,.png,.jpg,.jpeg" className="hidden"
          onChange={e => e.target.files && handleFiles(e.target.files)} />
        <input ref={folderInputRef} type="file" multiple accept=".pdf,.docx,.doc,.pptx,.ppt,.png,.jpg,.jpeg" className="hidden"
          onChange={e => e.target.files && handleFiles(e.target.files, true)} />
        {uploading ? (
          <div className="flex flex-col items-center gap-2 text-blue-500">
            <Spinner size="lg" />
            <p className="text-sm font-medium">上传并触发解析中…</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 text-gray-400">
            <Upload className="h-8 w-8 opacity-60" />
            <p className="text-sm">将文件拖放至此区域，或</p>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={() => fileInputRef.current?.click()}>点击选择文件</Button>
              <Button size="sm" variant="outline" onClick={() => folderInputRef.current?.click()}>
                <FolderPlus className="h-4 w-4 mr-1" />上传文件夹
              </Button>
            </div>
            <p className="text-xs mt-1 text-gray-300">支持 PDF、Word、PPT、PNG、JPG、JPEG</p>
          </div>
        )}
      </div>

      {/* File List */}
      {loading ? (
        <div className="flex items-center justify-center py-12 text-gray-400">
          <Spinner className="mr-2" /> 加载中…
        </div>
      ) : docs.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-gray-100 p-10 text-center text-gray-300">
          <FileText className="mx-auto mb-2 h-8 w-8 opacity-40" />
          <p className="text-sm">暂无文件，请先上传</p>
        </div>
      ) : (
        <div>
          {/* 批量操作栏 */}
          <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 mb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <button
                className="inline-flex items-center gap-2 text-sm text-gray-600 hover:text-gray-800"
                onClick={toggleSelectAll}
                type="button"
              >
                {allSelected ? <CheckSquare className="h-4 w-4 text-blue-600" /> : <Square className="h-4 w-4" />}
                全选 ({selectedDocIds.size}/{docs.length})
              </button>
              <p className="text-xs text-gray-400">Shift+点击 可范围选择</p>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={handleBatchReParse} disabled={selectedDocIds.size === 0 || batchParsing}>
                  {batchParsing ? <Spinner size="sm" className="mr-1" /> : <PlayCircle className="h-4 w-4 mr-1" />}
                  批量重解析
                </Button>
                <Button size="sm" className="bg-red-600 hover:bg-red-700" onClick={handleBatchDelete} disabled={selectedDocIds.size === 0 || batchDeleting}>
                  {batchDeleting ? <Spinner size="sm" className="mr-1" /> : <Trash2 className="h-4 w-4 mr-1" />}
                  批量删除
                </Button>
              </div>
            </div>
          </div>

          {/* 树形文件列表 */}
          <TreeNodes
            nodes={tree}
            depth={0}
            collapsed={collapsedFolders}
            selected={selectedDocIds}
            actioningId={actioningId}
            canParseFn={canParse}
            onToggleFolder={handleToggleFolder}
            onSelectDoc={handleSelectDoc}
            onReParse={handleReParse}
            onDelete={doc => setDeleteTarget(doc)}
          />
        </div>
      )}

      {/* Delete Confirm Dialog */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogClose onClick={() => setDeleteTarget(null)} />
        <DialogHeader>
          <DialogTitle>删除文件</DialogTitle>
          <DialogDescription>
            确认删除「{deleteTarget?.filename}」？相关向量索引和任务记录也将一并删除，不可恢复。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setDeleteTarget(null)}>取消</Button>
          <Button className="bg-red-600 hover:bg-red-700" onClick={handleDelete} disabled={deleting}>
            {deleting && <Spinner size="sm" className="mr-1.5" />}
            确认删除
          </Button>
        </DialogFooter>
      </Dialog>
    </div>
  )
}

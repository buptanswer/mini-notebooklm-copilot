import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { Plus, BookOpen, GraduationCap, Trash2, MessageSquare, FolderOpen, RefreshCw } from "lucide-react"
import { listKBs, createKB, deleteKB } from "@/api/client"
import type { KBInfo, KBType } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card"
import { Dialog, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogClose } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Spinner } from "@/components/ui/spinner"
import { cn } from "@/lib/utils"

export default function KnowledgeBasePage() {
  const navigate = useNavigate()
  const [kbs, setKbs] = useState<KBInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState("")
  const [newDesc, setNewDesc] = useState("")
  const [newKbType, setNewKbType] = useState<KBType>("general")
  const [newFolderPath, setNewFolderPath] = useState("")
  const [creating, setCreating] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<KBInfo | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = async () => {
    setLoading(true)
    setError("")
    try {
      setKbs(await listKBs())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    try {
      await createKB(newName.trim(), newDesc.trim(), newKbType, newFolderPath.trim())
      setCreateOpen(false)
      setNewName("")
      setNewDesc("")
      setNewKbType("general")
      setNewFolderPath("")
      load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await deleteKB(deleteTarget.kb_id)
      setDeleteTarget(null)
      load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setDeleting(false)
    }
  }

  const statusSummary = (kb: KBInfo) =>
    `${kb.file_count} 个文件`

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">我的知识库</h1>
          <p className="mt-1 text-sm text-gray-500">管理你的课程知识库空间</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className={cn("h-4 w-4 mr-1", loading && "animate-spin")} />
            刷新
          </Button>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1 h-4 w-4" />
            新建知识库
          </Button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 text-red-700 p-3 text-sm">
          ⚠ {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-16 text-gray-400">
          <Spinner className="mr-2" /> 加载中…
        </div>
      )}

      {/* KB Grid */}
      {!loading && kbs.length === 0 && (
        <div className="rounded-lg border-2 border-dashed border-gray-200 p-12 text-center text-gray-400">
          <BookOpen className="mx-auto mb-3 h-10 w-10 opacity-40" />
          <p>暂无知识库，点击上方「新建知识库」创建第一个</p>
        </div>
      )}

      {!loading && kbs.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {kbs.map(kb => (
            <Card
              key={kb.kb_id}
              className="flex flex-col hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => navigate(`/kb/${kb.kb_id}`)}
            >
              <CardHeader>
                <div className="flex items-start justify-between">
                  {kb.kb_type === "course"
                    ? <GraduationCap className="h-8 w-8 text-purple-500 mb-2" />
                    : <BookOpen className="h-8 w-8 text-blue-500 mb-2" />
                  }
                  <div className="flex items-center gap-1">
                    <Badge variant="outline" className={cn(
                      "text-xs",
                      kb.kb_type === "course"
                        ? "border-purple-300 text-purple-600"
                        : "border-blue-300 text-blue-600"
                    )}>
                      {kb.kb_type === "course" ? "课程" : "通用"}
                    </Badge>
                    <button
                      className="text-gray-300 hover:text-red-500 transition-colors p-1"
                      onClick={e => { e.stopPropagation(); setDeleteTarget(kb) }}
                      title="删除知识库"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
                <CardTitle>{kb.name}</CardTitle>
                <CardDescription className="line-clamp-2">
                  {kb.description || "暂无描述"}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex-1">
                <p className="text-xs text-gray-400">{statusSummary(kb)}</p>
                <p className="text-xs text-gray-400 mt-0.5">
                  更新于 {new Date(kb.updated_at).toLocaleDateString("zh-CN")}
                </p>
              </CardContent>
              <CardFooter className="gap-2 border-t pt-3">
                <Button
                  size="sm"
                  variant="outline"
                  className="flex-1 text-xs"
                  onClick={e => { e.stopPropagation(); navigate(`/kb/${kb.kb_id}`) }}
                >
                  <FolderOpen className="h-3.5 w-3.5 mr-1" />
                  文件管理
                </Button>
                <Button
                  size="sm"
                  className="flex-1 text-xs"
                  onClick={e => { e.stopPropagation(); navigate(`/kb/${kb.kb_id}/chat`) }}
                >
                  <MessageSquare className="h-3.5 w-3.5 mr-1" />
                  开始对话
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={createOpen} onClose={() => { setCreateOpen(false); setNewName(""); setNewDesc(""); setNewKbType("general"); setNewFolderPath("") }}>
        <DialogClose onClick={() => { setCreateOpen(false); setNewName(""); setNewDesc(""); setNewKbType("general"); setNewFolderPath("") }} />
        <DialogHeader>
          <DialogTitle>新建知识库</DialogTitle>
          <DialogDescription>创建一个新的知识库空间</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label htmlFor="kb-name">名称 *</Label>
            <Input
              id="kb-name"
              className="mt-1.5"
              placeholder="例如：操作系统复习"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleCreate()}
              autoFocus
            />
          </div>
          <div>
            <Label htmlFor="kb-desc">描述（可选）</Label>
            <Input
              id="kb-desc"
              className="mt-1.5"
              placeholder="这个知识库的用途…"
              value={newDesc}
              onChange={e => setNewDesc(e.target.value)}
            />
          </div>
          <div>
            <Label>类型</Label>
            <div className="mt-1.5 flex gap-2">
              <button
                type="button"
                onClick={() => setNewKbType("general")}
                className={cn(
                  "flex-1 rounded-lg border-2 p-3 text-left transition-colors",
                  newKbType === "general"
                    ? "border-blue-500 bg-blue-50"
                    : "border-gray-200 hover:border-gray-300"
                )}
              >
                <div className="flex items-center gap-2 mb-1">
                  <BookOpen className="h-4 w-4 text-blue-500" />
                  <span className="text-sm font-medium">通用知识库</span>
                </div>
                <p className="text-xs text-gray-500">适合笔记、资料整理与问答</p>
              </button>
              <button
                type="button"
                onClick={() => setNewKbType("course")}
                className={cn(
                  "flex-1 rounded-lg border-2 p-3 text-left transition-colors",
                  newKbType === "course"
                    ? "border-purple-500 bg-purple-50"
                    : "border-gray-200 hover:border-gray-300"
                )}
              >
                <div className="flex items-center gap-2 mb-1">
                  <GraduationCap className="h-4 w-4 text-purple-500" />
                  <span className="text-sm font-medium">课程知识库</span>
                </div>
                <p className="text-xs text-gray-500">含课后复盘、AI 出卷、日程管理</p>
              </button>
            </div>
          </div>
          {newKbType === "course" && (
            <div>
              <Label htmlFor="kb-folder">绑定文件夹路径（可选）</Label>
              <Input
                id="kb-folder"
                className="mt-1.5"
                placeholder="例如：C:\Users\Alan\Desktop\数学物理方法"
                value={newFolderPath}
                onChange={e => setNewFolderPath(e.target.value)}
              />
              <p className="mt-1 text-xs text-gray-400">
                绑定后可使用"同步文件夹"自动登记录音、课件等文件
              </p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setCreateOpen(false)}>取消</Button>
          <Button onClick={handleCreate} disabled={creating || !newName.trim()}>
            {creating && <Spinner size="sm" className="mr-1.5" />}
            创建
          </Button>
        </DialogFooter>
      </Dialog>

      {/* Delete Confirm Dialog */}
      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
        <DialogClose onClick={() => setDeleteTarget(null)} />
        <DialogHeader>
          <DialogTitle>删除知识库</DialogTitle>
          <DialogDescription>
            确认要删除「{deleteTarget?.name}」？此操作将同时删除该知识库下所有文档、向量索引和任务记录，且不可恢复。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setDeleteTarget(null)}>取消</Button>
          <Button
            className="bg-red-600 hover:bg-red-700"
            onClick={handleDelete}
            disabled={deleting}
          >
            {deleting && <Spinner size="sm" className="mr-1.5" />}
            确认删除
          </Button>
        </DialogFooter>
      </Dialog>
    </div>
  )
}

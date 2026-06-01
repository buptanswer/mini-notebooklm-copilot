import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { motion } from "motion/react"
import {
  BookOpenText, ClipboardList, FolderClosed, GraduationCap, Library,
  MessagesSquare, Plus, RefreshCw, Trash2,
} from "lucide-react"
import { createKB, deleteKB, listKBs } from "@/api/client"
import type { KBInfo, KBType } from "@/api/types"
import { Btn, Field, Modal } from "@/components/Modal"
import { cn } from "@/lib/utils"

export default function KnowledgeBasePage() {
  const navigate = useNavigate()
  const [kbs, setKbs] = useState<KBInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState("")
  const [desc, setDesc] = useState("")
  const [kbType, setKbType] = useState<KBType>("general")
  const [folder, setFolder] = useState("")
  const [creating, setCreating] = useState(false)
  const [delTarget, setDelTarget] = useState<KBInfo | null>(null)

  const load = async () => {
    setLoading(true); setError("")
    try { setKbs(await listKBs()) } catch (e) { setError((e as Error).message) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const resetForm = () => { setName(""); setDesc(""); setKbType("general"); setFolder("") }

  const handleCreate = async () => {
    if (!name.trim()) return
    setCreating(true)
    try { await createKB(name.trim(), desc.trim(), kbType, folder.trim()); setCreateOpen(false); resetForm(); load() }
    catch (e) { setError((e as Error).message) } finally { setCreating(false) }
  }

  const handleDelete = async () => {
    if (!delTarget) return
    try { await deleteKB(delTarget.kb_id); setDelTarget(null); load() } catch (e) { setError((e as Error).message) }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-8 py-8">
        <header className="mb-8 flex items-end justify-between">
          <div>
            <h1 className="flex items-center gap-2.5 font-display text-3xl font-semibold text-ink">
              <Library className="h-7 w-7 text-accent" />书架
            </h1>
            <p className="mt-1.5 text-sm text-ink-soft">你的课程与资料知识库</p>
          </div>
          <div className="flex gap-2">
            <Btn variant="ghost" onClick={load} disabled={loading}>
              <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />刷新
            </Btn>
            <Btn onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" />新建知识库</Btn>
          </div>
        </header>

        {error && <div className="mb-5 rounded-xl border border-border bg-accent-soft px-4 py-2.5 text-sm text-accent">⚠ {error}</div>}

        {loading && <div className="py-20 text-center text-ink-faint">加载中…</div>}

        {!loading && kbs.length === 0 && (
          <div className="card flex flex-col items-center border-dashed py-20 text-center">
            <BookOpenText className="mb-3 h-12 w-12 text-ink-faint opacity-50" />
            <p className="text-ink-soft">书架还是空的，点击右上角「新建知识库」开始。</p>
          </div>
        )}

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {kbs.map((kb, i) => {
            const course = kb.kb_type === "course"
            return (
              <motion.div
                key={kb.kb_id}
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.04, 0.3), duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
                onClick={() => navigate(`/kb/${kb.kb_id}`)}
                className="card group flex cursor-pointer flex-col p-5 transition-all hover:-translate-y-0.5 hover:shadow-raised"
              >
                <div className="mb-3 flex items-start justify-between">
                  <div className={cn("flex h-11 w-11 items-center justify-center rounded-2xl", course ? "bg-accent-soft text-accent" : "bg-surface-2 text-ink-soft")}>
                    {course ? <GraduationCap className="h-6 w-6" /> : <BookOpenText className="h-6 w-6" />}
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); setDelTarget(kb) }}
                    className="rounded-lg p-1.5 text-ink-faint opacity-0 transition-all hover:text-accent group-hover:opacity-100"
                    title="删除"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <h3 className="font-display text-lg font-semibold text-ink">{kb.name}</h3>
                <p className="mt-1 line-clamp-2 flex-1 text-sm text-ink-soft">{kb.description || "暂无描述"}</p>
                <div className="mt-3 flex items-center gap-2 text-xs text-ink-faint">
                  <span className={cn("rounded-full px-2 py-0.5 font-medium", course ? "bg-accent-soft text-accent" : "bg-surface-2")}>
                    {course ? "课程" : "通用"}
                  </span>
                  <span>{kb.file_count} 个文件</span>
                  <span>·</span>
                  <span>{new Date(kb.updated_at).toLocaleDateString("zh-CN")}</span>
                </div>
                <div className="mt-4 flex flex-wrap gap-2 border-t border-border pt-3">
                  <QuickLink icon={FolderClosed} label="文件" onClick={(e) => { e.stopPropagation(); navigate(`/kb/${kb.kb_id}/files`) }} />
                  <QuickLink icon={MessagesSquare} label="对话" onClick={(e) => { e.stopPropagation(); navigate(`/kb/${kb.kb_id}/chat`) }} />
                  {course && <>
                    <QuickLink icon={BookOpenText} label="复习" onClick={(e) => { e.stopPropagation(); navigate(`/kb/${kb.kb_id}/review`) }} />
                    <QuickLink icon={ClipboardList} label="管家" onClick={(e) => { e.stopPropagation(); navigate(`/kb/${kb.kb_id}/info`) }} />
                  </>}
                </div>
              </motion.div>
            )
          })}
        </div>
      </div>

      {/* 新建 */}
      <Modal
        open={createOpen}
        onClose={() => { setCreateOpen(false); resetForm() }}
        title="新建知识库"
        description="创建一个新的知识库空间"
        footer={<>
          <Btn variant="ghost" onClick={() => { setCreateOpen(false); resetForm() }}>取消</Btn>
          <Btn onClick={handleCreate} disabled={creating || !name.trim()}>创建</Btn>
        </>}
      >
        <div className="space-y-4">
          <Field label="名称 *" placeholder="例如：操作系统复习" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          <Field label="描述（可选）" placeholder="这个知识库的用途…" value={desc} onChange={(e) => setDesc(e.target.value)} />
          <div>
            <span className="text-xs font-medium text-ink-soft">类型</span>
            <div className="mt-1.5 flex gap-2">
              {([["general", "通用知识库", "笔记、资料整理与问答", BookOpenText], ["course", "课程知识库", "含课后复习、课程管家", GraduationCap]] as const).map(([t, title, sub, Icon]) => (
                <button key={t} type="button" onClick={() => setKbType(t)}
                  className={cn("flex-1 rounded-xl border-2 p-3 text-left transition-colors", kbType === t ? "border-accent bg-accent-soft" : "border-border hover:border-border-strong")}>
                  <div className="mb-1 flex items-center gap-2"><Icon className="h-4 w-4 text-accent" /><span className="text-sm font-medium text-ink">{title}</span></div>
                  <p className="text-xs text-ink-faint">{sub}</p>
                </button>
              ))}
            </div>
          </div>
          {kbType === "course" && (
            <Field label="绑定文件夹路径（可选）" hint="绑定后可用「同步」自动登记录音、课件等文件"
              placeholder="例如：C:\Users\Alan\Desktop\数学物理方法" value={folder} onChange={(e) => setFolder(e.target.value)} />
          )}
        </div>
      </Modal>

      {/* 删除确认 */}
      <Modal
        open={!!delTarget}
        onClose={() => setDelTarget(null)}
        title="删除知识库"
        description={`确认删除「${delTarget?.name}」？将一并删除其所有文档、向量索引与任务记录，不可恢复。`}
        footer={<>
          <Btn variant="ghost" onClick={() => setDelTarget(null)}>取消</Btn>
          <Btn variant="danger" onClick={handleDelete}>确认删除</Btn>
        </>}
      />
    </div>
  )
}

function QuickLink({ icon: Icon, label, onClick }: { icon: typeof FolderClosed; label: string; onClick: (e: React.MouseEvent) => void }) {
  return (
    <button onClick={onClick} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-ink-soft transition-colors hover:bg-surface-2 hover:text-accent">
      <Icon className="h-3.5 w-3.5" />{label}
    </button>
  )
}

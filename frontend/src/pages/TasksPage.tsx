import { useEffect, useRef, useState } from "react"
import { RefreshCw } from "lucide-react"
import { listAllTasks } from "@/api/client"
import type { TaskInfo } from "@/api/types"
import { Btn } from "@/components/Modal"
import { cn } from "@/lib/utils"

const STATUS: Record<string, { label: string; cls: string }> = {
  created: { label: "等待中", cls: "bg-surface-2 text-ink-soft" },
  running: { label: "进行中", cls: "bg-accent-soft text-accent" },
  done: { label: "完成", cls: "bg-[color:var(--c-success)]/15 text-[color:var(--c-success)]" },
  failed: { label: "失败", cls: "bg-accent-soft text-accent" },
}
const fmt = (s: string) =>
  new Date(s).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })

export default function TasksPage() {
  const [tasks, setTasks] = useState<TaskInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = async () => {
    try { setTasks(await listAllTasks(100)); setError("") } catch (e) { setError((e as Error).message) } finally { setLoading(false) }
  }
  useEffect(() => { load(); return () => { if (pollingRef.current) clearInterval(pollingRef.current) } }, [])
  useEffect(() => {
    const busy = tasks.some((t) => t.status === "running" || t.status === "created")
    if (busy && !pollingRef.current) pollingRef.current = setInterval(load, 5000)
    else if (!busy && pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
  }, [tasks])

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-8 py-8">
        <header className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="font-display text-2xl font-semibold text-ink">任务监控</h1>
            <p className="mt-0.5 text-sm text-ink-soft">近期解析与索引任务（最多 100 条，运行中自动刷新）</p>
          </div>
          <Btn variant="ghost" onClick={() => { setLoading(true); load() }} disabled={loading}>
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />刷新
          </Btn>
        </header>

        {error && <div className="mb-4 rounded-xl border border-border bg-accent-soft px-4 py-2.5 text-sm text-accent">⚠ {error}</div>}

        {loading ? (
          <div className="py-16 text-center text-ink-faint">加载中…</div>
        ) : tasks.length === 0 ? (
          <div className="card py-16 text-center text-ink-faint">暂无任务记录</div>
        ) : (
          <div className="card overflow-hidden">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-2/50 text-xs uppercase tracking-wide text-ink-faint">
                  <th className="px-4 py-3 font-medium">文档</th>
                  <th className="px-4 py-3 font-medium">类型</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="w-40 px-4 py-3 font-medium">进度</th>
                  <th className="max-w-xs px-4 py-3 font-medium">详情</th>
                  <th className="px-4 py-3 font-medium">更新</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((t) => {
                  const st = STATUS[t.status] ?? { label: t.status, cls: "bg-surface-2 text-ink-soft" }
                  const pct = typeof t.progress === "number" ? Math.round(t.progress * 100) : null
                  return (
                    <tr key={t.task_id} className="border-b border-border last:border-0 hover:bg-surface-2/30">
                      <td className="px-4 py-3 font-mono text-xs text-ink-faint">{t.doc_id.slice(0, 8)}…</td>
                      <td className="px-4 py-3 text-ink-soft">{t.task_type}</td>
                      <td className="px-4 py-3">
                        <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium", st.cls)}>
                          {t.status === "running" && <span className="breathe-dot h-1.5 w-1.5 rounded-full bg-accent" />}{st.label}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {pct !== null ? (
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-2">
                              <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${pct}%` }} />
                            </div>
                            <span className="w-8 text-xs text-ink-faint">{pct}%</span>
                          </div>
                        ) : "—"}
                      </td>
                      <td className="max-w-xs px-4 py-3">
                        {t.error_msg ? <p className="line-clamp-3 text-xs leading-snug text-accent">{t.error_msg}</p> : <span className="text-ink-faint">—</span>}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-faint">{fmt(t.updated_at)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

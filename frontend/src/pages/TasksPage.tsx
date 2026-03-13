import { useEffect, useRef, useState } from "react"
import { RefreshCw } from "lucide-react"
import { listAllTasks } from "@/api/client"
import type { TaskInfo } from "@/api/types"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Spinner } from "@/components/ui/spinner"
import { Button } from "@/components/ui/button"

const STATUS_CONFIG: Record<string, { label: string; variant: "default" | "success" | "destructive" | "secondary" }> = {
  created: { label: "等待中", variant: "secondary" },
  running: { label: "进行中", variant: "default" },
  done: { label: "完成", variant: "success" },
  failed: { label: "失败", variant: "destructive" },
}

const formatDt = (s: string) =>
  new Date(s).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" })

export default function TasksPage() {
  const [tasks, setTasks] = useState<TaskInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = async () => {
    try {
      const data = await listAllTasks(100)
      setTasks(data)
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
  }, [])

  useEffect(() => {
    const anyRunning = tasks.some(t => t.status === "running" || t.status === "created")
    if (anyRunning) {
      if (!pollingRef.current) pollingRef.current = setInterval(load, 5000)
    } else {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
    }
  }, [tasks])

  return (
    <div className="p-6">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">任务监控</h1>
          <p className="text-sm text-gray-400 mt-0.5">近期解析与索引任务记录（最多 100 条）</p>
        </div>
        <Button variant="outline" onClick={() => { setLoading(true); load() }} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} />
          刷新
        </Button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 text-red-700 p-3 text-sm">
          ⚠ {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-gray-400">
          <Spinner className="mr-2" /> 加载中…
        </div>
      ) : tasks.length === 0 ? (
        <div className="text-center py-16 text-gray-300 text-sm">暂无任务记录</div>
      ) : (
        <div className="overflow-auto rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="border-b bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
                <th className="px-4 py-3 font-medium">任务 ID</th>
                <th className="px-4 py-3 font-medium">文档 ID</th>
                <th className="px-4 py-3 font-medium">类型</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium w-36">进度</th>
                <th className="px-4 py-3 font-medium max-w-xs">详情</th>
                <th className="px-4 py-3 font-medium">更新时间</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {tasks.map(task => {
                const cfg = STATUS_CONFIG[task.status] ?? { label: task.status, variant: "secondary" }
                const progressVal = typeof task.progress === "number" ? Math.round(task.progress * 100) : null
                const isWarning = task.error_msg?.startsWith("⚠")
                return (
                  <tr key={task.task_id} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-400">
                      {task.task_id.slice(0, 8)}…
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-500">
                      {task.doc_id.slice(0, 8)}…
                    </td>
                    <td className="px-4 py-2.5 text-gray-600">{task.task_type}</td>
                    <td className="px-4 py-2.5">
                      <span className="flex items-center gap-1">
                        {task.status === "running" && <Spinner size="sm" />}
                        <Badge variant={cfg.variant}>{cfg.label}</Badge>
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      {progressVal !== null ? (
                        <div className="flex items-center gap-2">
                          <Progress value={progressVal} className="h-1.5 w-24" />
                          <span className="text-xs text-gray-400 w-8">{progressVal}%</span>
                        </div>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-2.5 max-w-xs">
                      {task.error_msg ? (
                        <p className={`text-xs leading-snug line-clamp-3 ${isWarning ? "text-yellow-700" : "text-red-500"}`}>
                          {task.error_msg}
                        </p>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-400 whitespace-nowrap">
                      {formatDt(task.updated_at)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

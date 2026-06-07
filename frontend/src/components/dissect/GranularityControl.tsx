// 解析透视 · 父块粒度控制（文档级）
// 选「几级标题=1父块」→ 应用即重切片+重索引（不重新解析 MinerU）；另提供「重新解析」入口
// （已索引 Office 取坐标 / 格式更新）。两个动作都带二步确认 + 风险提示。

import { useState } from "react"
import { Layers, Loader2, RefreshCcw, RotateCw } from "lucide-react"
import { reindexDocument, reparseDocument } from "@/api/client"

const LEVELS = [
  { v: 1, label: "一级标题" },
  { v: 2, label: "二级标题" },
  { v: 3, label: "三级标题" },
]

export function GranularityControl({ kbId, docId, currentLevel, onReindexed }: {
  kbId: string
  docId: string
  currentLevel: number          // 0=全局默认（按 L1 显示）
  onReindexed: () => void        // 重切片成功后让页面重载 IR/chunks/indexes
}) {
  const [level, setLevel] = useState(currentLevel > 0 ? currentLevel : 1)
  const [busy, setBusy] = useState<null | "reindex" | "reparse">(null)
  const [confirm, setConfirm] = useState<null | "reindex" | "reparse">(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const doReindex = async () => {
    setBusy("reindex"); setErr(null); setMsg(null); setConfirm(null)
    try {
      const r = await reindexDocument(kbId, docId, level)
      setMsg(`已重切片：${r.parents} 父块 / ${r.children} 子块`)
      onReindexed()
    } catch (e) { setErr((e as Error).message || "重切片失败") }
    finally { setBusy(null) }
  }

  const doReparse = async () => {
    setBusy("reparse"); setErr(null); setMsg(null); setConfirm(null)
    try {
      await reparseDocument(kbId, docId)
      setMsg("已开始重新解析，完成后刷新本页查看")
    } catch (e) { setErr((e as Error).message || "重新解析失败") }
    finally { setBusy(null) }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="inline-flex items-center gap-1 text-[11px] text-ink-faint">
        <Layers className="h-3.5 w-3.5" /> 父块粒度
      </span>
      <select
        value={level}
        onChange={(e) => setLevel(Number(e.target.value))}
        disabled={!!busy}
        className="rounded-lg border border-border bg-surface px-2 py-1 text-xs text-ink focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50"
      >
        {LEVELS.map((l) => <option key={l.v} value={l.v}>{l.label}</option>)}
      </select>

      {confirm === "reindex" ? (
        <span className="inline-flex items-center gap-1.5 text-[11px]">
          <span className="text-warn">重切片会清除该文档已建的自定义索引，确认?</span>
          <button onClick={doReindex} className="font-semibold text-accent hover:underline">确认</button>
          <button onClick={() => setConfirm(null)} className="text-ink-faint hover:text-ink">取消</button>
        </span>
      ) : (
        <button
          onClick={() => { setConfirm("reindex"); setMsg(null); setErr(null) }}
          disabled={!!busy}
          className="inline-flex items-center gap-1 rounded-lg bg-accent px-2.5 py-1 text-xs font-semibold text-accent-ink transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {busy === "reindex" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCw className="h-3.5 w-3.5" />}
          应用
        </button>
      )}

      {confirm === "reparse" ? (
        <span className="inline-flex items-center gap-1.5 text-[11px]">
          <span className="text-warn">重新解析会消耗 MinerU/VLM API，确认?</span>
          <button onClick={doReparse} className="font-semibold text-accent hover:underline">确认</button>
          <button onClick={() => setConfirm(null)} className="text-ink-faint hover:text-ink">取消</button>
        </span>
      ) : (
        <button
          onClick={() => { setConfirm("reparse"); setMsg(null); setErr(null) }}
          disabled={!!busy}
          title="重置状态并重新解析（已索引 Office 取版面坐标 / 格式更新）"
          className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1 text-xs text-ink-soft transition-colors hover:text-accent disabled:opacity-50"
        >
          {busy === "reparse" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCcw className="h-3.5 w-3.5" />}
          重新解析
        </button>
      )}

      {msg && <span className="text-[11px] text-success">{msg}</span>}
      {err && <span className="text-[11px] text-warn">{err}</span>}
    </div>
  )
}

import { useEffect, useState } from "react"
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom"
import { motion } from "motion/react"
import {
  ArrowLeft, BookOpenText, ClipboardList, Clock, FolderClosed, MessagesSquare,
} from "lucide-react"
import { getKB, getUpcomingDeadlines } from "@/api/client"
import type { DeadlineItem, KBInfo } from "@/api/types"
import { cn } from "@/lib/utils"

export default function KBLayout() {
  const { kbId } = useParams<{ kbId: string }>()
  const navigate = useNavigate()
  const [kb, setKb] = useState<KBInfo | null>(null)
  const [deadlines, setDeadlines] = useState<DeadlineItem[]>([])

  useEffect(() => {
    if (!kbId) return
    getKB(kbId).then(setKb).catch(() => {})
  }, [kbId])

  useEffect(() => {
    if (kb?.kb_type === "course" && kbId) {
      getUpcomingDeadlines(kbId, 7).then(setDeadlines).catch(() => {})
    }
  }, [kb, kbId])

  const navItems = [
    { path: "files", icon: FolderClosed, label: "文件" },
    { path: "chat", icon: MessagesSquare, label: "对话" },
    ...(kb?.kb_type === "course"
      ? [
          { path: "review", icon: BookOpenText, label: "课后复习" },
          { path: "info", icon: ClipboardList, label: "课程管家" },
        ]
      : []),
  ]

  return (
    <div className="flex h-full flex-col bg-bg">
      {/* 截止日 banner */}
      {deadlines.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-wrap items-center gap-2 border-b border-border bg-accent-soft px-5 py-2.5 text-sm text-accent"
        >
          <Clock className="h-4 w-4 shrink-0" />
          <span className="font-medium">近期截止</span>
          {deadlines.slice(0, 4).map((dl, i) => (
            <span key={i} className="rounded-full bg-surface/70 px-2.5 py-0.5 text-xs font-medium text-ink-soft">
              {dl.name}
              <span className="ml-1 text-accent">
                {dl.days_left === 0 ? "今天" : dl.days_left === 1 ? "明天" : `${dl.days_left}天后`}
              </span>
            </span>
          ))}
        </motion.div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* 二级侧边栏 */}
        <aside className="flex w-52 shrink-0 flex-col border-r border-border bg-surface/60">
          <div className="border-b border-border px-4 py-4">
            <button
              onClick={() => navigate("/")}
              className="mb-3 flex items-center gap-1.5 text-xs text-ink-faint transition-colors hover:text-accent"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              知识库
            </button>
            <p className="truncate font-display text-base font-semibold text-ink" title={kb?.name}>
              {kb?.name ?? "…"}
            </p>
            <span
              className={cn(
                "mt-1.5 inline-block rounded-full px-2 py-0.5 text-[10px] font-medium",
                kb?.kb_type === "course"
                  ? "bg-accent-soft text-accent"
                  : "bg-surface-2 text-ink-faint",
              )}
            >
              {kb?.kb_type === "course" ? "课程知识库" : "通用知识库"}
            </span>
          </div>

          <nav className="flex-1 space-y-1 p-2.5">
            {navItems.map(({ path, icon: Icon, label }) => (
              <NavLink
                key={path}
                to={path}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium transition-all",
                    isActive
                      ? "bg-accent-soft text-accent"
                      : "text-ink-soft hover:bg-surface-2 hover:text-ink",
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </NavLink>
            ))}
          </nav>
        </aside>

        {/* 内容区 */}
        <main className="flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

import { useEffect, useState } from "react"
import { useParams, NavLink, Outlet, useNavigate } from "react-router-dom"
import { getKB, getUpcomingDeadlines } from "@/api/client"
import type { DeadlineItem, KBInfo } from "@/api/types"
import {
  ArrowLeft,
  Folder,
  MessageSquare,
  BookOpen,
  ClipboardList,
  AlertCircle,
} from "lucide-react"
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
    { path: "files", icon: Folder, label: "文件" },
    { path: "chat", icon: MessageSquare, label: "对话" },
    ...(kb?.kb_type === "course"
      ? [
          { path: "review", icon: BookOpen, label: "课后复习" },
          { path: "info", icon: ClipboardList, label: "课程管家" },
        ]
      : []),
  ]

  return (
    <div className="flex h-full flex-col">
      {/* Deadline banner */}
      {deadlines.length > 0 && (
        <div className="flex items-center gap-2 bg-amber-50 border-b border-amber-200 px-4 py-2 text-sm text-amber-800">
          <AlertCircle className="h-4 w-4 shrink-0 text-amber-500" />
          <span className="font-medium">近期 DDL：</span>
          {deadlines.slice(0, 3).map((dl, i) => (
            <span key={i} className="rounded bg-amber-100 px-2 py-0.5 text-xs">
              {dl.name}
              {dl.days_left === 0 ? "（今天）" : dl.days_left === 1 ? "（明天）" : `（${dl.days_left}天后）`}
            </span>
          ))}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* 二级侧边栏 */}
        <aside className="flex w-44 shrink-0 flex-col border-r bg-white">
          {/* Back + KB name */}
          <div className="border-b px-3 py-3">
            <button
              onClick={() => navigate("/")}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 mb-2"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              知识库列表
            </button>
            <p className="text-sm font-semibold text-gray-800 truncate" title={kb?.name}>
              {kb?.name ?? "…"}
            </p>
            {kb?.kb_type === "course" && (
              <span className="mt-0.5 inline-block rounded text-[10px] px-1.5 py-0.5 bg-purple-100 text-purple-600">
                课程
              </span>
            )}
          </div>

          {/* Nav */}
          <nav className="flex-1 space-y-0.5 p-2">
            {navItems.map(({ path, icon: Icon, label }) => (
              <NavLink
                key={path}
                to={path}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                    isActive
                      ? "bg-blue-50 text-blue-700 font-medium"
                      : "text-gray-600 hover:bg-gray-100"
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </NavLink>
            ))}
          </nav>
        </aside>

        {/* 页面内容区 */}
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

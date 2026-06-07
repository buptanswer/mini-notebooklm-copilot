import { useEffect, useState } from "react"
import { NavLink, Outlet, useLocation, useParams } from "react-router-dom"
import {
  ArrowLeft, BookOpenText, ClipboardList, FileScan, FolderClosed,
  Library, ListTodo, MessagesSquare, PanelLeft, PanelLeftClose,
  ScanSearch, Settings,
} from "lucide-react"
import { cn } from "@/lib/utils"
import ThemeSwitch from "./ThemeSwitch"
import { getKB } from "@/api/client"
import type { KBInfo } from "@/api/types"

const mainItems = [
  { to: "/", icon: Library, label: "知识库", end: true },
  { to: "/tasks", icon: ListTodo, label: "任务", end: false },
  { to: "/settings", icon: Settings, label: "设置", end: false },
]

const kbNavItems = [
  { path: "files", icon: FolderClosed, label: "文件" },
  { path: "chat", icon: MessagesSquare, label: "对话" },
  { path: "dissect", icon: FileScan, label: "解析透视" },
  { path: "xray", icon: ScanSearch, label: "检索透视" },
]

const courseOnlyItems = [
  { path: "review", icon: BookOpenText, label: "课后复习" },
  { path: "info", icon: ClipboardList, label: "课程管家" },
]

export default function Layout() {
  const location = useLocation()
  const { kbId } = useParams<{ kbId?: string }>()

  // 是否在知识库内部
  const inKB = !!kbId

  // kb 信息（在 KB 内时获取）
  const [kb, setKb] = useState<KBInfo | null>(null)
  useEffect(() => {
    if (kbId) {
      getKB(kbId).then(setKb).catch(() => setKb(null))
    } else {
      setKb(null)
    }
  }, [kbId])

  // 解析透视页信息密度大，自动收起主菜单；用户可手动切换
  const isDissect = location.pathname.endsWith("/dissect")
  const routeKey = isDissect ? "dissect" : "default"
  const [override, setOverride] = useState<{ key: string; value: boolean } | null>(null)
  const collapsed = override?.key === routeKey ? override.value : isDissect

  // 添加 KB 子导航项
  const navItems = inKB
    ? [
        ...kbNavItems,
        ...(kb?.kb_type === "course" ? courseOnlyItems : []),
      ]
    : []

  return (
    <div className="flex h-screen bg-bg text-ink">
      {/* ── 统一侧边栏（单列）────────────────────────── */}
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r border-border bg-surface/70 backdrop-blur-sm transition-all duration-300",
          collapsed ? "w-[68px]" : "w-60",
        )}
      >
        {/* KS 头部 */}
        {inKB ? (
          <div className="border-b border-border px-4 py-4">
            <NavLink
              to="/"
              className="mb-3 flex items-center gap-1.5 text-xs text-ink-faint transition-colors hover:text-accent"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              {!collapsed && "知识库"}
            </NavLink>
            {!collapsed ? (
              <>
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
              </>
            ) : (
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent-soft font-display text-sm font-semibold text-accent">
                {kb?.name?.charAt(0) ?? "K"}
              </div>
            )}
          </div>
        ) : (
          /* 首页品牌 */
          <div className="flex h-16 items-center gap-2.5 px-4">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent font-display text-lg font-semibold text-accent-ink shadow-card">
              研
            </div>
            {!collapsed && (
              <div className="leading-tight">
                <div className="font-display text-lg font-semibold text-ink">研读室</div>
                <div className="text-[10px] uppercase tracking-[0.18em] text-ink-faint">Mini-NotebookLM</div>
              </div>
            )}
          </div>
        )}

        {/* 导航 */}
        <nav className="flex-1 space-y-1 px-3 py-3">
          {inKB
            ? /* ── KB 内部：显示 KB 子导航 ── */
              navItems.map(({ path, icon: Icon, label }) => (
                <NavLink
                  key={path}
                  to={path}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all",
                      collapsed && "justify-center px-0",
                      isActive
                        ? "bg-accent-soft text-accent"
                        : "text-ink-soft hover:bg-surface-2 hover:text-ink",
                    )
                  }
                  title={collapsed ? label : undefined}
                >
                  <Icon className="h-[18px] w-[18px] shrink-0" />
                  {!collapsed && <span>{label}</span>}
                </NavLink>
              ))
            : /* ── 首页：显示主菜单 ── */
              mainItems.map(({ to, icon: Icon, label, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all",
                      collapsed && "justify-center px-0",
                      isActive
                        ? "bg-accent-soft text-accent"
                        : "text-ink-soft hover:bg-surface-2 hover:text-ink",
                    )
                  }
                  title={collapsed ? label : undefined}
                >
                  <Icon className="h-[18px] w-[18px] shrink-0" />
                  {!collapsed && <span>{label}</span>}
                </NavLink>
              ))}
        </nav>

        {/* 底部：主题 + 折叠 */}
        <div className="border-t border-border px-3 py-3">
          {!collapsed && (
            <div className="mb-2 flex justify-center">
              <ThemeSwitch />
            </div>
          )}
          <button
            onClick={() => setOverride({ key: routeKey, value: !collapsed })}
            className="flex h-8 w-full items-center justify-center rounded-lg text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink-soft"
            title={collapsed ? "展开" : "收起"}
          >
            {collapsed ? <PanelLeft className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        </div>
      </aside>

      {/* ── 内容区 ──────────────────────────────────── */}
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}

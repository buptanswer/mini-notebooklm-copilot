import { useState } from "react"
import { NavLink, Outlet, useLocation } from "react-router-dom"
import { Library, ListTodo, PanelLeft, PanelLeftClose, Settings } from "lucide-react"
import { cn } from "@/lib/utils"
import ThemeSwitch from "./ThemeSwitch"

const navItems = [
  { to: "/", icon: Library, label: "知识库", end: true },
  { to: "/tasks", icon: ListTodo, label: "任务", end: false },
  { to: "/settings", icon: Settings, label: "设置", end: false },
]

export default function Layout() {
  const location = useLocation()
  // 解析透视页信息密度大，自动收起主菜单让出空间（知识库二级菜单不收起）；用户仍可手动展开。
  // 从路由派生默认收起态；手动开合的意图只在当前路由上下文内有效，切走后回到该页默认（无需 effect）。
  const isDissect = location.pathname.endsWith("/dissect")
  const routeKey = isDissect ? "dissect" : "default"
  const [override, setOverride] = useState<{ key: string; value: boolean } | null>(null)
  const collapsed = override?.key === routeKey ? override.value : isDissect

  return (
    <div className="flex h-screen bg-bg text-ink">
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r border-border bg-surface/70 backdrop-blur-sm transition-all duration-300",
          collapsed ? "w-[68px]" : "w-60",
        )}
      >
        {/* 品牌 */}
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

        {/* 主导航 */}
        <nav className="flex-1 space-y-1 px-3 py-3">
          {navItems.map(({ to, icon: Icon, label, end }) => (
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
              title={label}
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

      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}

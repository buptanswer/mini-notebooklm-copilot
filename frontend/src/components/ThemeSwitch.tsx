import { BookOpen, Moon, Sun } from "lucide-react"
import { useTheme } from "@/hooks/useTheme"
import { THEMES, THEME_LABEL } from "@/lib/theme"
import { cn } from "@/lib/utils"
import type { ThemeMode } from "@/api/types"

const ICON: Record<ThemeMode, typeof Sun> = { light: Sun, sepia: BookOpen, dark: Moon }

export default function ThemeSwitch() {
  const { theme, setTheme } = useTheme()
  return (
    <div className="flex items-center gap-0.5 rounded-full border border-border bg-surface-2 p-0.5">
      {THEMES.map((t) => {
        const Icon = ICON[t]
        return (
          <button
            key={t}
            onClick={() => setTheme(t)}
            title={THEME_LABEL[t]}
            className={cn(
              "flex h-7 w-7 items-center justify-center rounded-full transition-all",
              theme === t
                ? "bg-surface text-accent shadow-card"
                : "text-ink-faint hover:text-ink-soft",
            )}
          >
            <Icon className="h-3.5 w-3.5" />
          </button>
        )
      })}
    </div>
  )
}

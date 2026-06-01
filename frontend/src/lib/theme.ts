import type { ThemeMode } from "@/api/types"

const KEY = "mnlm-theme"
export const THEMES: ThemeMode[] = ["light", "sepia", "dark"]

export const THEME_LABEL: Record<ThemeMode, string> = {
  light: "明亮",
  sepia: "护眼",
  dark: "暗色",
}

export function getStoredTheme(): ThemeMode {
  try {
    const t = localStorage.getItem(KEY) as ThemeMode | null
    if (t && THEMES.includes(t)) return t
  } catch { /* ignore */ }
  return "light"
}

export function applyTheme(t: ThemeMode): void {
  document.documentElement.setAttribute("data-theme", t)
  try { localStorage.setItem(KEY, t) } catch { /* ignore */ }
}

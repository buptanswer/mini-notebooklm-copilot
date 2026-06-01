import { useCallback, useState } from "react"
import type { ThemeMode } from "@/api/types"
import { applyTheme, getStoredTheme } from "@/lib/theme"

/** 主题状态（light / sepia / dark），持久化到 localStorage，首帧前已由 index.html 内联脚本应用。 */
export function useTheme() {
  const [theme, setThemeState] = useState<ThemeMode>(getStoredTheme)

  const setTheme = useCallback((t: ThemeMode) => {
    applyTheme(t)
    setThemeState(t)
  }, [])

  return { theme, setTheme }
}

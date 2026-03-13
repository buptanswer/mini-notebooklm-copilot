// Spinner 加载动画
import { cn } from "@/lib/utils"

interface SpinnerProps {
  className?: string
  size?: "sm" | "md" | "lg"
}

const sizes = { sm: "h-4 w-4", md: "h-6 w-6", lg: "h-8 w-8" }

export function Spinner({ className, size = "md" }: SpinnerProps) {
  return (
    <span
      className={cn(
        "inline-block animate-spin rounded-full border-2 border-current border-t-transparent",
        sizes[size],
        className,
      )}
      aria-label="加载中"
    />
  )
}

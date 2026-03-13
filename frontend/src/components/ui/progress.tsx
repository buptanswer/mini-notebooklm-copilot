// Progress 进度条
import { type HTMLAttributes } from "react"
import { cn } from "@/lib/utils"

interface ProgressProps extends HTMLAttributes<HTMLDivElement> {
  value?: number   // 0-100; omit for indeterminate animation
}

export function Progress({ className, value, ...props }: ProgressProps) {
  const indeterminate = value === undefined
  return (
    <div
      className={cn("h-2 w-full overflow-hidden rounded-full bg-gray-200", className)}
      {...props}
    >
      {indeterminate ? (
        <div className="h-full w-1/3 rounded-full bg-blue-500 animate-[progress-slide_1.2s_ease-in-out_infinite]" />
      ) : (
        <div
          className="h-full bg-blue-500 transition-all duration-300"
          style={{ width: `${Math.min(100, Math.max(0, value!))}%` }}
        />
      )}
    </div>
  )
}

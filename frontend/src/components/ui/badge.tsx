// Badge 徽标组件
import { type HTMLAttributes } from "react"
import { cn } from "@/lib/utils"

type BadgeVariant = "default" | "secondary" | "success" | "warning" | "destructive" | "outline"

const variantClasses: Record<BadgeVariant, string> = {
  default:     "bg-blue-100 text-blue-700",
  secondary:   "bg-gray-100 text-gray-700",
  success:     "bg-green-100 text-green-700",
  warning:     "bg-yellow-100 text-yellow-800 border border-yellow-300",
  destructive: "bg-red-100 text-red-700",
  outline:     "border border-gray-300 text-gray-700",
}

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className,
      )}
      {...props}
    />
  )
}

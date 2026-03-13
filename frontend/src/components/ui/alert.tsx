// Alert 提示框（支持 default / warning / destructive）
import { type HTMLAttributes } from "react"
import { cn } from "@/lib/utils"

type AlertVariant = "default" | "warning" | "destructive"

const variantClasses: Record<AlertVariant, string> = {
  default:     "bg-blue-50 border-blue-200 text-blue-800",
  warning:     "bg-yellow-50 border-yellow-300 text-yellow-900",
  destructive: "bg-red-50 border-red-200 text-red-800",
}

interface AlertProps extends HTMLAttributes<HTMLDivElement> {
  variant?: AlertVariant
}

export function Alert({ className, variant = "default", ...props }: AlertProps) {
  return (
    <div
      className={cn(
        "flex gap-3 rounded-lg border p-4 text-sm",
        variantClasses[variant],
        className,
      )}
      {...props}
    />
  )
}

export function AlertTitle({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("font-semibold leading-none mb-1", className)} {...props} />
}

export function AlertDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm leading-relaxed", className)} {...props} />
}

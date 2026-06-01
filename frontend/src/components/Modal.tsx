import { AnimatePresence, motion } from "motion/react"
import { X } from "lucide-react"

export function Modal({
  open, onClose, title, description, children, footer,
}: {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children?: React.ReactNode
  footer?: React.ReactNode
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            onClick={(e) => e.stopPropagation()}
            className="card w-full max-w-lg p-6 shadow-pop"
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <h2 className="font-display text-lg font-semibold text-ink">{title}</h2>
                {description && <p className="mt-1 text-sm text-ink-soft">{description}</p>}
              </div>
              <button onClick={onClose} className="shrink-0 text-ink-faint transition-colors hover:text-ink">
                <X className="h-4 w-4" />
              </button>
            </div>
            {children}
            {footer && <div className="mt-6 flex justify-end gap-2">{footer}</div>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/** 统一按钮（token 化）。variant: primary / ghost / danger。 */
export function Btn({
  children, onClick, variant = "primary", disabled, className, type = "button",
}: {
  children: React.ReactNode
  onClick?: () => void
  variant?: "primary" | "ghost" | "danger"
  disabled?: boolean
  className?: string
  type?: "button" | "submit"
}) {
  const base = "inline-flex items-center justify-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium transition-all disabled:opacity-40"
  const styles = {
    primary: "bg-accent text-accent-ink hover:brightness-105",
    ghost: "border border-border bg-surface text-ink-soft hover:text-ink hover:border-border-strong",
    danger: "border border-border text-accent hover:bg-accent-soft",
  }[variant]
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${base} ${styles} ${className ?? ""}`}>
      {children}
    </button>
  )
}

/** 文本输入（token 化）。 */
export function Field({
  label, hint, ...props
}: { label?: string; hint?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      {label && <span className="text-xs font-medium text-ink-soft">{label}</span>}
      <input
        {...props}
        className={`mt-1.5 w-full rounded-xl border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-accent/40 ${props.className ?? ""}`}
      />
      {hint && <span className="mt-1 block text-xs text-ink-faint">{hint}</span>}
    </label>
  )
}

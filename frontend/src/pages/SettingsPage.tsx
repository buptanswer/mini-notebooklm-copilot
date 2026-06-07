import { useEffect, useState } from "react"
import { AlertCircle, CheckCircle2, ExternalLink, RefreshCw, Save, Eye, EyeOff } from "lucide-react"
import { listPrompts, reloadPrompts } from "@/api/client"
import { Btn, Field } from "@/components/Modal"
import { cn } from "@/lib/utils"

interface AppConfig {
  qa_model: string
  qa_base_url: string
  qa_api_key: string
  qa_enable_thinking: boolean
  qa_enable_multimodal: boolean
  qa_multimodal_model: string
  vlm_model: string
  mineru_api_key: string
  dashscope_api_key: string
  embedding_model: string
  rerank_model: string
  embedding_dim: number
  parent_chunk_heading_level: number
  max_concurrent_parses: number
  mineru_model_version: string
  mineru_office_use_ocr: boolean
}

export default function SettingsPage() {
  const [health, setHealth] = useState<{ ok: boolean; checked: boolean }>({ ok: false, checked: false })
  const [prompts, setPrompts] = useState<Record<string, string>>({})
  const [reloading, setReloading] = useState(false)
  const [reloadMsg, setReloadMsg] = useState("")
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [edit, setEdit] = useState<Partial<AppConfig>>({})
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState("")
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({})

  useEffect(() => {
    fetch("/api/health").then((r) => setHealth({ ok: r.ok, checked: true })).catch(() => setHealth({ ok: false, checked: true }))
    listPrompts().then(setPrompts).catch(() => {})
    fetch("/api/settings").then((r) => r.json()).then(setConfig).catch(() => {})
  }, [])

  const toggleKey = (k: string) => setShowKeys((p) => ({ ...p, [k]: !p[k] }))

  const handleSave = async () => {
    setSaving(true)
    setSaveMsg("")
    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(edit),
      })
      if (res.ok) {
        setSaveMsg("配置已保存，重启后端生效")
        setEdit({})
        // 刷新显示
        const r2 = await fetch("/api/settings")
        setConfig(await r2.json())
      } else {
        setSaveMsg("保存失败")
      }
    } catch {
      setSaveMsg("网络错误")
    } finally {
      setSaving(false)
      setTimeout(() => setSaveMsg(""), 4000)
    }
  }

  const updateEdit = (k: keyof AppConfig, v: string | boolean | number) => {
    setEdit((p) => ({ ...p, [k]: v }))
  }

  const cfg = config
  const hasEdits = Object.keys(edit).length > 0

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-2xl px-8 py-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-display text-2xl font-semibold text-ink">设置</h1>
            <p className="mt-0.5 text-sm text-ink-soft">系统配置与服务状态</p>
          </div>
          {hasEdits && (
            <Btn variant="primary" disabled={saving} onClick={handleSave}>
              <Save className="h-4 w-4" />{saving ? "保存中…" : "保存配置"}
            </Btn>
          )}
        </div>
        {saveMsg && (
          <p className={cn("mt-2 text-sm", saveMsg.includes("失败") || saveMsg.includes("错误") ? "text-accent" : "text-[color:var(--c-success)]")}>
            {saveMsg}
          </p>
        )}

        <Section title="服务状态">
          <div className="card flex items-center justify-between p-4">
            <span className="text-sm text-ink-soft">后端服务</span>
            {!health.checked ? (
              <span className="text-sm text-ink-faint">检测中…</span>
            ) : health.ok ? (
              <span className="flex items-center gap-1 text-sm text-[color:var(--c-success)]"><CheckCircle2 className="h-4 w-4" />正常运行</span>
            ) : (
              <span className="flex items-center gap-1 text-sm text-accent"><AlertCircle className="h-4 w-4" />无法连接</span>
            )}
          </div>
        </Section>

        {/* ── QA 模型配置 ── */}
        <Section title="问答模型 (QA)">
          <div className="card divide-y divide-[color:var(--c-border)]">
            <EditableRow label="模型名称" env="QA_MODEL" value={cfg?.qa_model ?? ""} editVal={edit.qa_model} onChange={(v) => updateEdit("qa_model", v)} />
            <EditableRow label="Base URL" env="QA_BASE_URL" value={cfg?.qa_base_url ?? ""} editVal={edit.qa_base_url} onChange={(v) => updateEdit("qa_base_url", v)} placeholder="留空使用百炼" />
            <EditableRow label="API Key" env="QA_API_KEY" value={cfg?.qa_api_key ?? ""} editVal={edit.qa_api_key} onChange={(v) => updateEdit("qa_api_key", v)} masked={!showKeys["qa"]} onToggleMask={() => toggleKey("qa")} placeholder="留空使用百炼 Key" />
            <ToggleRow label="思维链" value={edit.qa_enable_thinking ?? cfg?.qa_enable_thinking ?? false} onChange={(v) => updateEdit("qa_enable_thinking", v)} />
            <ToggleRow label="多模态问答" value={edit.qa_enable_multimodal ?? cfg?.qa_enable_multimodal ?? true} onChange={(v) => updateEdit("qa_enable_multimodal", v)} />
            <EditableRow label="多模态模型" env="QA_MULTIMODAL_MODEL" value={cfg?.qa_multimodal_model ?? ""} editVal={edit.qa_multimodal_model} onChange={(v) => updateEdit("qa_multimodal_model", v)} />
          </div>
        </Section>

        {/* ── VLM 配置 ── */}
        <Section title="VLM（图片/表格描述）">
          <div className="card divide-y divide-[color:var(--c-border)]">
            <EditableRow label="VLM 模型" env="VLM_MODEL" value={cfg?.vlm_model ?? ""} editVal={edit.vlm_model} onChange={(v) => updateEdit("vlm_model", v)} />
          </div>
        </Section>

        {/* ── API Keys ── */}
        <Section title="API Key">
          <div className="card divide-y divide-[color:var(--c-border)]">
            <EditableRow label="MinerU API Key" env="MINERU_API_KEY" value={cfg?.mineru_api_key ?? ""} editVal={edit.mineru_api_key} onChange={(v) => updateEdit("mineru_api_key", v)} masked={!showKeys["mineru"]} onToggleMask={() => toggleKey("mineru")} />
            <EditableRow label="百炼 API Key" env="ALIBABA_CLOUD_ACCESS_KEY_SECRET" value={cfg?.dashscope_api_key ?? ""} editVal={edit.dashscope_api_key} onChange={(v) => updateEdit("dashscope_api_key", v)} masked={!showKeys["dashscope"]} onToggleMask={() => toggleKey("dashscope")} />
          </div>
        </Section>

        <Section title="当前模型（只读）">
          <div className="card divide-y divide-[color:var(--c-border)] text-sm">
            <Row label="文档解析" value={`MinerU (${cfg?.mineru_model_version ?? "vlm"})`} />
            <Row label="向量化" value={`${cfg?.embedding_model ?? "text-embedding-v4"}（${cfg?.embedding_dim ?? 1024}维）`} />
            <Row label="重排序" value={cfg?.rerank_model ?? "qwen3-rerank"} />
            <Row label="解析并发" value={String(cfg?.max_concurrent_parses ?? 2)} />
            <Row label="父块默认粒度" value={`${cfg?.parent_chunk_heading_level ?? 1} 级标题`} />
            <Row label="Office 取坐标" value={cfg?.mineru_office_use_ocr ? "是 (is_ocr)" : "否"} />
          </div>
        </Section>

        <Section title="文档相关链接">
          <div className="flex flex-wrap gap-2">
            <LinkBtn href="http://127.0.0.1:8000/docs" label="Swagger API" />
            <LinkBtn href="http://127.0.0.1:8000/redoc" label="ReDoc API" />
          </div>
        </Section>

        <Section
          title="提示词预览"
          action={
            <div className="flex items-center gap-2">
              {reloadMsg && <span className="text-xs text-[color:var(--c-success)]">{reloadMsg}</span>}
              <Btn variant="ghost" disabled={reloading} onClick={async () => {
                setReloading(true)
                try { const r = await reloadPrompts(); setPrompts(await listPrompts()); setReloadMsg(`已重载 ${r.count} 个`); setTimeout(() => setReloadMsg(""), 3000) }
                catch { /* ignore */ } finally { setReloading(false) }
              }}>
                <RefreshCw className={cn("h-3.5 w-3.5", reloading && "animate-spin")} />重载
              </Btn>
            </div>
          }
        >
          <div className="space-y-3">
            {Object.entries(prompts).map(([name, content]) => (
              <div key={name} className="card overflow-hidden">
                <div className="border-b border-border bg-surface-2/50 px-3 py-2 font-mono text-xs font-semibold text-ink-soft">{name}.md</div>
                <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap px-3 py-2 font-mono text-xs text-ink-soft">{content}</pre>
              </div>
            ))}
            {Object.keys(prompts).length === 0 && <p className="text-xs text-ink-faint">加载中…</p>}
          </div>
          <p className="mt-2 text-xs text-ink-faint">
            提示词位于 <code className="rounded bg-surface-2 px-1">backend/app/prompts/*.md</code>，改完点「重载」即生效，无需重启。
          </p>
        </Section>
      </div>
    </div>
  )
}

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="mt-7">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

function Row({ label, value, env }: { label: string; value: string; env?: string }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5">
      <span className="text-ink-soft">{label}</span>
      <span className="flex items-center gap-1.5"><span className="text-ink">{value}</span>{env && <code className="rounded bg-surface-2 px-1 text-[10px] text-ink-faint">{env}</code>}</span>
    </div>
  )
}

function LinkBtn({ href, label }: { href: string; label: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-xl border border-border bg-surface px-3 py-1.5 text-sm text-ink-soft transition-colors hover:text-accent">
      <ExternalLink className="h-3.5 w-3.5" />{label}
    </a>
  )
}

// ── EditableRow: 可编辑字段行 ──
function EditableRow({
  label, env, value, editVal, onChange, masked, onToggleMask, placeholder,
}: {
  label: string; env?: string; value: string; editVal?: string
  onChange: (v: string) => void; masked?: boolean; onToggleMask?: () => void
  placeholder?: string
}) {
  const isEditing = editVal !== undefined
  const display = isEditing ? editVal : value
  return (
    <div className="flex items-center gap-3 px-4 py-2.5">
      <span className="w-28 shrink-0 text-sm text-ink-soft">{label}</span>
      <div className="flex flex-1 items-center gap-1.5">
        <Field
          value={isEditing || !masked ? display : (display ? "••••••••" : "")}
          onChange={(e) => onChange((e.target as HTMLInputElement).value)}
          className="flex-1 font-mono text-xs"
          placeholder={placeholder ?? ""}
        />
        {env && <code className="shrink-0 rounded bg-surface-2 px-1 text-[10px] text-ink-faint">{env}</code>}
        {onToggleMask && (
          <button onClick={onToggleMask} className="shrink-0 p-1 text-ink-faint hover:text-ink-soft" title={masked ? "显示" : "隐藏"}>
            {masked ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>
    </div>
  )
}

// ── ToggleRow: 布尔值切换行 ──
function ToggleRow({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5">
      <span className="text-sm text-ink-soft">{label}</span>
      <button
        onClick={() => onChange(!value)}
        className={cn(
          "relative h-6 w-11 rounded-full transition-colors",
          value ? "bg-accent" : "bg-surface-2",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform",
            value ? "left-[22px]" : "left-[2px]",
          )}
        />
      </button>
    </div>
  )
}

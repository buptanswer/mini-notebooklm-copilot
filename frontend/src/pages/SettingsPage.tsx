import { useEffect, useState } from "react"
import { AlertCircle, CheckCircle2, ExternalLink, RefreshCw } from "lucide-react"
import { listPrompts, reloadPrompts } from "@/api/client"
import { Btn } from "@/components/Modal"
import { cn } from "@/lib/utils"

export default function SettingsPage() {
  const [health, setHealth] = useState<{ ok: boolean; checked: boolean }>({ ok: false, checked: false })
  const [prompts, setPrompts] = useState<Record<string, string>>({})
  const [reloading, setReloading] = useState(false)
  const [reloadMsg, setReloadMsg] = useState("")

  useEffect(() => {
    fetch("/api/health").then((r) => setHealth({ ok: r.ok, checked: true })).catch(() => setHealth({ ok: false, checked: true }))
    listPrompts().then(setPrompts).catch(() => {})
  }, [])

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-2xl px-8 py-8">
        <h1 className="font-display text-2xl font-semibold text-ink">设置</h1>
        <p className="mt-0.5 text-sm text-ink-soft">系统配置说明与服务状态</p>

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

        <Section title="API 配置">
          <div className="card divide-y divide-[color:var(--c-border)]">
            <ConfigRow name="MinerU API Key" envKey="MINERU_API_KEY" desc="文档解析（PDF / PPT / Word / 图片）" link="https://mineru.net" required />
            <ConfigRow name="阿里云百炼 API Key" envKey="ALIBABA_CLOUD_ACCESS_KEY_SECRET" desc="向量化 / 重排序 / VLM" link="https://bailian.console.aliyun.com" required />
            <ConfigRow name="QA 模型 Base URL" envKey="QA_BASE_URL" desc="可选，不填用百炼 qwen-plus" />
            <ConfigRow name="QA 模型 API Key" envKey="QA_API_KEY" desc="可选，切换 DeepSeek / OpenAI 等" />
            <ConfigRow name="解析并发上限" envKey="MAX_CONCURRENT_PARSES" desc="可选，默认 2（批量解析时限流，避免连接打爆）" />
          </div>
          <p className="mt-2 text-xs text-ink-faint">
            配置在 <code className="rounded bg-surface-2 px-1">backend/.env</code>，可参考 <code className="rounded bg-surface-2 px-1">.env.example</code>，修改后重启后端生效。
          </p>
        </Section>

        <Section title="当前模型">
          <div className="card divide-y divide-[color:var(--c-border)] text-sm">
            <Row label="文档解析" value="MinerU (vlm)" />
            <Row label="向量化" value="text-embedding-v4（1024 维）" />
            <Row label="重排序" value="qwen3-rerank" />
            <Row label="图片 / 表格描述" value="qwen-vl-plus" env="VLM_MODEL" />
            <Row label="问答生成" value="qwen-plus" env="QA_MODEL" />
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
function ConfigRow({ name, envKey, desc, link, required }: { name: string; envKey: string; desc: string; link?: string; required?: boolean }) {
  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-ink">{name}</span>
        {required && <span className="rounded-full bg-accent-soft px-1.5 py-0.5 text-[10px] font-medium text-accent">必填</span>}
      </div>
      <code className="mt-0.5 inline-block rounded bg-surface-2 px-1.5 py-0.5 text-xs text-accent">{envKey}</code>
      <p className="mt-1 text-xs text-ink-soft">{desc}</p>
      {link && <a href={link} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-0.5 text-xs text-accent hover:underline">申请地址 <ExternalLink className="h-3 w-3" /></a>}
    </div>
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

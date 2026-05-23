import { useEffect, useState } from "react"
import { ExternalLink, CheckCircle, AlertCircle, RefreshCw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { Button } from "@/components/ui/button"
import { listPrompts, reloadPrompts } from "@/api/client"

interface HealthStatus {
  ok: boolean
  checked: boolean
}

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthStatus>({ ok: false, checked: false })
  const [prompts, setPrompts] = useState<Record<string, string>>({})
  const [reloading, setReloading] = useState(false)
  const [reloadMsg, setReloadMsg] = useState("")

  useEffect(() => {
    fetch("/api/health")
      .then(r => setHealth({ ok: r.ok, checked: true }))
      .catch(() => setHealth({ ok: false, checked: true }))
    listPrompts().then(setPrompts).catch(() => {})
  }, [])

  return (
    <div className="p-6 max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900">设置</h1>
      <p className="mt-1 text-sm text-gray-500">系统配置说明与服务状态</p>

      {/* 服务状态 */}
      <section className="mt-6">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">服务状态</h2>
        <div className="mt-3 rounded-lg border border-gray-200 bg-white p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-600">后端服务</span>
            {!health.checked ? (
              <Badge variant="secondary">检测中…</Badge>
            ) : health.ok ? (
              <span className="flex items-center gap-1 text-green-600 text-sm">
                <CheckCircle className="h-4 w-4" /> 正常运行
              </span>
            ) : (
              <span className="flex items-center gap-1 text-red-500 text-sm">
                <AlertCircle className="h-4 w-4" /> 无法连接
              </span>
            )}
          </div>
        </div>
      </section>

      {/* 配置说明 */}
      <section className="mt-6">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">API 配置</h2>
        <div className="mt-3 rounded-lg border border-gray-200 bg-white divide-y">
          <ConfigRow
            name="MinerU API Key"
            envKey="MINERU_API_KEY"
            desc="文档解析（PDF / PPT / Word / 图片）"
            link="https://mineru.net"
            linkText="申请地址"
            required
          />
          <ConfigRow
            name="阿里云百炼 API Key"
            envKey="ALIBABA_CLOUD_ACCESS_KEY_SECRET"
            desc="向量化（text-embedding-v4）、重排序（qwen3-rerank）、VLM（qwen-vl-plus）"
            link="https://bailian.console.aliyun.com"
            linkText="申请地址"
            required
          />
          <ConfigRow
            name="QA 模型 Base URL"
            envKey="QA_BASE_URL"
            desc="可选。不填时自动使用阿里云百炼（qwen-plus）"
          />
          <ConfigRow
            name="QA 模型 API Key"
            envKey="QA_API_KEY"
            desc="可选。配合 QA_BASE_URL 切换到 DeepSeek / OpenAI 等"
          />
          <ConfigRow
            name="QA 模型名称"
            envKey="QA_MODEL"
            desc="可选。默认：qwen-plus"
          />
        </div>
        <p className="mt-2 text-xs text-gray-400">
          所有配置项在后端 <code className="bg-gray-100 px-1 rounded">backend/.env</code> 文件中设置，
          可参考 <code className="bg-gray-100 px-1 rounded">backend/.env.example</code> 模板。
          修改后需重启后端服务生效。
        </p>
      </section>

      <Separator className="my-6" />

      {/* 模型配置 */}
      <section>
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">当前模型配置</h2>
        <div className="mt-3 rounded-lg border border-gray-200 bg-white divide-y text-sm">
          <ModelRow label="文档解析" value="MinerU (vlm)" />
          <ModelRow label="向量化" value="text-embedding-v4（1024 维）" />
          <ModelRow label="重排序" value="qwen3-rerank" />
          <ModelRow label="图片/表格描述" value="qwen-vl-plus（默认）" envKey="VLM_MODEL" />
          <ModelRow label="问答生成" value="qwen-plus（默认）" envKey="QA_MODEL" />
        </div>
        <p className="mt-2 text-xs text-gray-400">
          可在 .env 文件中覆盖带 * 的模型名称。问答模型还支持切换到 DeepSeek / OpenAI 等 OpenAI 兼容 Provider。
        </p>
      </section>

      <Separator className="my-6" />

      {/* 数据路径 */}
      <section>
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">数据目录</h2>
        <div className="mt-3 rounded-lg border border-gray-200 bg-white divide-y text-sm">
          <DataRow label="SQLite 数据库" path="data/sqlite/mini_notebooklm.db" />
          <DataRow label="Qdrant 向量存储" path="data/qdrant_storage/" />
          <DataRow label="上传文件" path="data/uploads/" />
          <DataRow label="MinerU 解析结果" path="data/mineru_zips/" />
          <DataRow label="RAG 中间输出" path="data/rag_output/" />
        </div>
        <p className="mt-2 text-xs text-gray-400">
          以上路径均相对于项目根目录，由后端自动创建，不纳入 Git 版本控制。
        </p>
      </section>

      <Separator className="my-6" />

      {/* 链接 */}
      <section>
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">相关链接</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          <a
            href="http://127.0.0.1:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 hover:text-blue-600"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Swagger API 文档
          </a>
          <a
            href="http://127.0.0.1:8000/redoc"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 hover:text-blue-600"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            ReDoc API 文档
          </a>
        </div>
      </section>

      <Separator className="my-6" />

      {/* 提示词预览 */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">提示词预览</h2>
          <div className="flex items-center gap-2">
            {reloadMsg && <span className="text-xs text-green-600">{reloadMsg}</span>}
            <Button
              size="sm"
              variant="outline"
              disabled={reloading}
              onClick={async () => {
                setReloading(true)
                try {
                  const r = await reloadPrompts()
                  setPrompts(await listPrompts())
                  setReloadMsg(`已重载 ${r.count} 个提示词`)
                  setTimeout(() => setReloadMsg(""), 3000)
                } catch { /* ignore */ } finally { setReloading(false) }
              }}
            >
              <RefreshCw className={`h-3.5 w-3.5 mr-1 ${reloading ? "animate-spin" : ""}`} />
              重载磁盘文件
            </Button>
          </div>
        </div>
        <div className="space-y-3">
          {Object.entries(prompts).map(([name, content]) => (
            <div key={name} className="rounded-lg border border-gray-200 bg-white">
              <div className="px-3 py-2 border-b bg-gray-50 text-xs font-mono font-semibold text-gray-600">
                {name}.md
              </div>
              <pre className="px-3 py-2 text-xs text-gray-700 whitespace-pre-wrap font-mono max-h-40 overflow-y-auto">
                {content}
              </pre>
            </div>
          ))}
          {Object.keys(prompts).length === 0 && (
            <p className="text-xs text-gray-400">加载中…</p>
          )}
        </div>
        <p className="mt-2 text-xs text-gray-400">
          提示词文件位于 <code className="bg-gray-100 px-1 rounded">backend/app/prompts/*.md</code>，
          修改文件后点"重载"即可生效，无需重启服务。
        </p>
      </section>
    </div>
  )
}

function ConfigRow({
  name, envKey, desc, link, linkText, required,
}: {
  name: string
  envKey: string
  desc: string
  link?: string
  linkText?: string
  required?: boolean
}) {
  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-gray-800">{name}</span>
        {required && <Badge variant="destructive" className="text-[10px] px-1 py-0">必填</Badge>}
      </div>
      <code className="mt-0.5 text-xs text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded">{envKey}</code>
      <p className="mt-1 text-xs text-gray-500">{desc}</p>
      {link && (
        <a
          href={link}
          target="_blank"
          rel="noreferrer"
          className="mt-1 inline-flex items-center gap-0.5 text-xs text-blue-500 hover:underline"
        >
          {linkText} <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </div>
  )
}

function ModelRow({ label, value, envKey }: { label: string; value: string; envKey?: string }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5">
      <span className="text-gray-600">{label}</span>
      <div className="flex items-center gap-1.5">
        <span className="text-gray-800">{value}</span>
        {envKey && (
          <code className="text-[10px] text-gray-400 bg-gray-50 px-1 rounded">{envKey}*</code>
        )}
      </div>
    </div>
  )
}

function DataRow({ label, path }: { label: string; path: string }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5">
      <span className="text-gray-600">{label}</span>
      <code className="text-xs text-gray-500 bg-gray-50 px-1.5 py-0.5 rounded">{path}</code>
    </div>
  )
}

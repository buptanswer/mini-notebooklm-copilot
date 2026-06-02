// 检索透视 · 开发态密集数据表（供开发者评估检索算法）
// 把每一路的原始名次/分数/命中词/RRF/重排 delta 全摊开，不做动画。

import type { ReactNode } from "react"
import type { RetrievalTrace, DocMeta } from "@/api/types"
import { docName, crumb, fmtScore, isImageType } from "./helpers"

function Section({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <div className="flex items-baseline gap-2">
        <h3 className="font-display text-sm font-semibold text-ink">{title}</h3>
        {count !== undefined && <span className="font-mono text-xs text-ink-faint">n={count}</span>}
      </div>
      <div className="overflow-x-auto rounded-lg border border-border bg-surface">
        {children}
      </div>
    </section>
  )
}

function Th({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <th className={`whitespace-nowrap px-2.5 py-1.5 text-left font-semibold text-ink-soft ${className}`}>
      {children}
    </th>
  )
}

function Td({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <td className={`px-2.5 py-1.5 align-top ${className}`}>{children}</td>
}

function Num({ children }: { children: ReactNode }) {
  return <span className="font-mono tabular-nums text-ink">{children}</span>
}

export function DevTables({
  trace, docs,
}: {
  trace: RetrievalTrace
  docs: Record<string, DocMeta>
}) {
  const { plan, vector_hits, keyword_hits, fusion, reranked, counts, timings_ms } = trace

  return (
    <div className="space-y-6 text-xs">
      {/* 查询规划 + 计时 */}
      <Section title="查询规划">
        <table className="w-full border-collapse">
          <tbody className="divide-y divide-border">
            <tr><Td className="w-28 font-semibold text-ink-soft">原始问题</Td><Td>{plan.original_question}</Td></tr>
            <tr><Td className="font-semibold text-ink-soft">改写问句</Td><Td>{plan.rewritten_question || "—"}</Td></tr>
            <tr><Td className="font-semibold text-ink-soft">假设答案</Td><Td className="italic text-ink-soft">{plan.semantic_query || "—"}</Td></tr>
            <tr>
              <Td className="font-semibold text-ink-soft">关键词</Td>
              <Td>
                <span className="flex flex-wrap gap-1">
                  {plan.keywords.map((k, i) => (
                    <code key={i} className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink">{k}</code>
                  ))}
                </span>
              </Td>
            </tr>
            <tr><Td className="font-semibold text-ink-soft">规划来源</Td><Td><Num>{plan.source}</Num></Td></tr>
            <tr>
              <Td className="font-semibold text-ink-soft">耗时 (ms)</Td>
              <Td>
                <Num>
                  规划 {timings_ms.plan} · 召回 {timings_ms.recall} · 融合 {timings_ms.fuse} · 重排 {timings_ms.rerank} · 合计 {timings_ms.total}
                </Num>
              </Td>
            </tr>
          </tbody>
        </table>
      </Section>

      {/* 向量路 */}
      <Section title="向量召回（语义）" count={counts.vector}>
        <table className="w-full border-collapse">
          <thead className="bg-surface-2/50 text-[11px]">
            <tr><Th>#</Th><Th>来源</Th><Th>类型</Th><Th>标题路径</Th><Th>cosine</Th><Th>文本片段</Th></tr>
          </thead>
          <tbody className="divide-y divide-border">
            {vector_hits.map((h) => (
              <tr key={h.child_chunk_id} className="hover:bg-surface-2/30">
                <Td><Num>{h.rank + 1}</Num></Td>
                <Td className="whitespace-nowrap text-ink-soft">{docName(h.doc_id, docs)}</Td>
                <Td className="whitespace-nowrap text-ink-faint">{h.chunk_type ?? "—"}</Td>
                <Td className="max-w-[160px] truncate text-ink-faint">{crumb(h.header_path)}</Td>
                <Td><Num>{fmtScore(h.score, 4)}</Num></Td>
                <Td className="max-w-[320px] truncate text-ink-soft">{h.text}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {/* 关键词路 */}
      <Section title="关键词召回（BM25 · FTS5）" count={counts.keyword}>
        {keyword_hits.length ? (
          <table className="w-full border-collapse">
            <thead className="bg-surface-2/50 text-[11px]">
              <tr><Th>#</Th><Th>来源</Th><Th>标题路径</Th><Th>bm25</Th><Th>命中词</Th><Th>文本片段</Th></tr>
            </thead>
            <tbody className="divide-y divide-border">
              {keyword_hits.map((h) => (
                <tr key={h.child_chunk_id} className="hover:bg-surface-2/30">
                  <Td><Num>{h.rank + 1}</Num></Td>
                  <Td className="whitespace-nowrap text-ink-soft">{docName(h.doc_id, docs)}</Td>
                  <Td className="max-w-[160px] truncate text-ink-faint">{crumb(h.header_path)}</Td>
                  <Td><Num>{fmtScore(h.score, 4)}</Num></Td>
                  <Td>
                    <span className="flex flex-wrap gap-1">
                      {(h.matched_keywords ?? []).map((k, i) => (
                        <code key={i} className="rounded bg-accent-soft px-1 text-[10px] text-accent-strong">{k}</code>
                      ))}
                    </span>
                  </Td>
                  <Td className="max-w-[280px] truncate text-ink-soft">{h.text}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="px-3 py-3 text-ink-faint">关键词路无命中（FTS5 unicode61 对中文不分词，纯中文关键词召回弱）。</p>
        )}
      </Section>

      {/* RRF 融合 */}
      <Section title="RRF 融合（k=60）" count={counts.fused}>
        <table className="w-full border-collapse">
          <thead className="bg-surface-2/50 text-[11px]">
            <tr><Th>#</Th><Th>来源</Th><Th>向量名次</Th><Th>向量分</Th><Th>关键词名次</Th><Th>关键词分</Th><Th>RRF</Th><Th>文本片段</Th></tr>
          </thead>
          <tbody className="divide-y divide-border">
            {fusion.map((f) => (
              <tr key={f.child_chunk_id} className="hover:bg-surface-2/30">
                <Td><Num>{f.rank + 1}</Num></Td>
                <Td className="whitespace-nowrap text-ink-soft">{docName(f.doc_id, docs)}</Td>
                <Td><Num>{f.vec_rank !== null ? f.vec_rank + 1 : "—"}</Num></Td>
                <Td><Num>{fmtScore(f.vec_score, 4)}</Num></Td>
                <Td><Num>{f.kw_rank !== null ? f.kw_rank + 1 : "—"}</Num></Td>
                <Td><Num>{fmtScore(f.kw_score, 4)}</Num></Td>
                <Td className="text-accent"><Num>{fmtScore(f.rrf_score, 5)}</Num></Td>
                <Td className="max-w-[260px] truncate text-ink-soft">{f.text}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {/* 重排 */}
      <Section title={`重排（qwen3-rerank）${trace.rerank_degraded ? " · 降级=融合序兜底" : ""}`} count={counts.final}>
        <table className="w-full border-collapse">
          <thead className="bg-surface-2/50 text-[11px]">
            <tr><Th>重排#</Th><Th>原#</Th><Th>Δ</Th><Th>来源</Th><Th>类型</Th><Th>rerank 分</Th><Th>文本片段</Th></tr>
          </thead>
          <tbody className="divide-y divide-border">
            {reranked.map((r) => (
              <tr key={r.child_chunk_id} className="hover:bg-surface-2/30">
                <Td className="text-accent"><Num>{r.rank + 1}</Num></Td>
                <Td><Num>{r.prev_rank !== null ? r.prev_rank + 1 : "—"}</Num></Td>
                <Td>
                  <Num>{r.delta === null || r.delta === undefined ? "—" : r.delta > 0 ? `↑${r.delta}` : r.delta < 0 ? `↓${-r.delta}` : "="}</Num>
                </Td>
                <Td className="whitespace-nowrap text-ink-soft">{docName(r.doc_id, docs)}</Td>
                <Td className="whitespace-nowrap text-ink-faint">
                  {r.chunk_type}{isImageType(r.chunk_type) ? " 🖼" : ""}
                </Td>
                <Td><Num>{fmtScore(r.rerank_score, 4)}</Num></Td>
                <Td className="max-w-[280px] truncate text-ink-soft">{r.text}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </div>
  )
}

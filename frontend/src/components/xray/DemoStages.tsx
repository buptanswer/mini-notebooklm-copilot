// 检索透视 · 演示态六阶段（动画揭示隐藏检索链路）
//   ① 查询规划 ② 关键词扫描(BM25) ③ 语义空间近邻(向量) ④ RRF 融合 ⑤ 重排 ⑥ 终选
// 每个阶段 = StageShell（脊柱站点 + 内容卡）。视觉仅用设计 token，动效用 motion。

import { useMemo } from "react"
import type { ReactNode } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { motion } from "motion/react"
import {
  Sparkles, ScanLine, Radar, GitMerge, ArrowUpNarrowWide, Trophy,
  ArrowUp, ArrowDown, Minus, AlertTriangle, ImageIcon,
} from "lucide-react"
import type { RetrievalTrace, DocMeta } from "@/api/types"
import { cn } from "@/lib/utils"
import {
  StageShell, ScoreBar, KeywordChip, ChunkTypeBadge, CountBadge,
} from "./shared"
import { docName, crumb, fmtScore, highlightKeywords, isImageType } from "./helpers"

type StageState = "pending" | "active"

interface StageProps {
  trace: RetrievalTrace
  docs: Record<string, DocMeta>
  state: StageState
  current: boolean
}

// ── 局部小部件 ──────────────────────────────────────────────

function Lab({ children }: { children: ReactNode }) {
  return (
    <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
      {children}
    </span>
  )
}

function SubPanel({
  title, icon, children, glow = false,
}: {
  title: string
  icon?: ReactNode
  children: ReactNode
  glow?: boolean
}) {
  return (
    <div
      className={cn(
        "rounded-lg border p-3",
        glow ? "border-accent/30 bg-accent-soft/30" : "border-border bg-surface-2/40",
      )}
    >
      <div className="mb-2 flex items-center gap-1.5 text-ink-soft">
        {icon}
        <span className="text-[11px] font-semibold">{title}</span>
      </div>
      {children}
    </div>
  )
}

function DocTag({ docId, docs }: { docId: string; docs: Record<string, DocMeta> }) {
  return (
    <span className="truncate rounded bg-surface-2 px-1.5 py-0.5 text-[10px] font-medium text-ink-soft">
      {docName(docId, docs)}
    </span>
  )
}

// ═══════════════════════════════════════════════════════════
// ① 查询规划
// ═══════════════════════════════════════════════════════════

export function StageQuery({ trace, state, current }: StageProps) {
  const { plan, timings_ms } = trace
  const rewritten =
    plan.rewritten_question && plan.rewritten_question !== plan.original_question
      ? plan.rewritten_question
      : null
  return (
    <StageShell
      index={1}
      icon={Sparkles}
      title="查询规划"
      subtitle="不直接拿问题去检索 —— 先让 LLM 拆出关键词，并改写成一句『假设答案』陈述句"
      state={state}
      current={current}
      badge={<CountBadge>{timings_ms.plan} ms</CountBadge>}
    >
      <div className="space-y-3.5">
        <div>
          <Lab>用户问题</Lab>
          <p className="mt-1 font-serif text-[15px] leading-relaxed text-ink">
            {plan.original_question}
          </p>
        </div>

        <div className="flex items-center gap-2 text-ink-faint">
          <div className="h-px flex-1 bg-border" />
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-[10px] font-semibold",
              plan.source === "llm"
                ? "bg-accent-soft text-accent"
                : "bg-surface-2 text-warn",
            )}
          >
            {plan.source === "llm" ? "LLM 规划" : "回退 · 朴素分词"}
          </span>
          <div className="h-px flex-1 bg-border" />
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <SubPanel title="关键词 · 用于 BM25 关键词检索" icon={<ScanLine className="h-3.5 w-3.5" />}>
            <div className="flex flex-wrap gap-1.5">
              {plan.keywords.length ? (
                plan.keywords.map((k, i) => <KeywordChip key={k + i} word={k} index={i} active />)
              ) : (
                <span className="text-xs text-ink-faint">（无）</span>
              )}
            </div>
          </SubPanel>
          <SubPanel title="假设答案 HyDE · 用于语义向量检索" icon={<Radar className="h-3.5 w-3.5" />} glow>
            <p className="font-serif text-sm italic leading-relaxed text-ink">
              “{plan.semantic_query || plan.original_question}”
            </p>
          </SubPanel>
        </div>

        {rewritten && (
          <div>
            <Lab>改写后独立问句 · 用于重排打分</Lab>
            <p className="mt-1 text-sm leading-relaxed text-ink-soft">{rewritten}</p>
          </div>
        )}
      </div>
    </StageShell>
  )
}

// ═══════════════════════════════════════════════════════════
// ② 关键词扫描（BM25）
// ═══════════════════════════════════════════════════════════

export function StageKeyword({ trace, docs, state, current }: StageProps) {
  const { plan, keyword_hits, counts, timings_ms } = trace
  const navigate = useNavigate()
  const { kbId } = useParams<{ kbId: string }>()
  const matchedUnion = useMemo(() => {
    const s = new Set<string>()
    keyword_hits.forEach((h) => h.matched_keywords?.forEach((k) => s.add(k)))
    return s
  }, [keyword_hits])

  return (
    <StageShell
      index={2}
      icon={ScanLine}
      title="关键词检索 · BM25"
      subtitle="用规划出的关键词在全文倒排索引（SQLite FTS5）里扫描，按词频/逆文档频率打分"
      state={state}
      current={current}
      badge={<CountBadge>命中 {counts.keyword} · {timings_ms.recall} ms</CountBadge>}
    >
      <div className="space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {plan.keywords.map((k, i) => (
            <KeywordChip key={k + i} word={k} index={i} active={matchedUnion.has(k)} />
          ))}
        </div>

        {/* 扫描面板 */}
        <div className="relative overflow-hidden rounded-lg border border-border bg-bg/60">
          {/* 扫描光束（连续扫盘 + 高亮前沿线） */}
          {state === "active" && (
            <motion.div
              aria-hidden
              initial={{ y: "-55%" }}
              animate={{ y: "175%" }}
              transition={{ duration: 2.2, ease: "easeInOut", repeat: Infinity, repeatDelay: 0.5 }}
              className="pointer-events-none absolute inset-x-0 z-10 h-1/3 bg-gradient-to-b from-transparent via-accent/12 to-transparent"
            >
              <span
                className="absolute inset-x-0 bottom-0 h-px"
                style={{ background: "linear-gradient(90deg, transparent, var(--c-accent), transparent)" }}
              />
            </motion.div>
          )}
          {keyword_hits.length ? (
            <ul className="divide-y divide-border">
              {keyword_hits.slice(0, 8).map((h, i) => (
                <motion.li
                  key={h.child_chunk_id}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.15 + i * 0.08, duration: 0.4 }}
                  className="px-3 py-2 cursor-pointer hover:bg-accent-soft/20 transition-colors"
                  onClick={() => navigate(`/kb/${kbId}/dissect?doc=${h.doc_id}&child=${encodeURIComponent(h.child_chunk_id)}`)}
                >
                  <div className="mb-1 flex items-center gap-2">
                    <span className="font-mono text-[10px] text-ink-faint">#{h.rank + 1}</span>
                    <DocTag docId={h.doc_id} docs={docs} />
                    <span className="truncate text-[10px] text-ink-faint">{crumb(h.header_path)}</span>
                    <span className="ml-auto shrink-0 font-mono text-[10px] text-accent">
                      bm25 {fmtScore(h.score, 2)}
                    </span>
                  </div>
                  <p className="line-clamp-2 font-mono text-[11px] leading-relaxed text-ink-soft">
                    {highlightKeywords(h.text, h.matched_tokens ?? [])}
                  </p>
                </motion.li>
              ))}
            </ul>
          ) : (
            <div className="flex items-start gap-2 px-3 py-4 text-xs text-ink-soft">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
              <span>
                关键词路命中较少。FTS5 默认 unicode61 对中文不分词，纯中文关键词召回弱；
                <span className="text-ink">语义向量路（下一站）兜底中文语义</span>。
              </span>
            </div>
          )}
        </div>
      </div>
    </StageShell>
  )
}

// ═══════════════════════════════════════════════════════════
// ③ 语义空间近邻（向量）
// ═══════════════════════════════════════════════════════════

const GOLDEN = 2.399963229728653 // 黄金角，用于均匀铺散方位

export function StageVector({ trace, docs, state, current }: StageProps) {
  const { vector_hits, counts, timings_ms } = trace
  const navigate = useNavigate()
  const { kbId } = useParams<{ kbId: string }>()
  const hits = vector_hits.slice(0, 12)

  // 节点坐标：半径 ∝ (1−相似度)（越相关越靠近中心，诚实映射）；方位用黄金角铺散
  const W = 360, H = 300, CX = W / 2, CY = H / 2
  const layout = useMemo(() => {
    if (!hits.length) return []
    const scores = hits.map((h) => h.score)
    const min = Math.min(...scores)
    const max = Math.max(...scores)
    const rInner = 48, rOuter = 132
    return hits.map((h, i) => {
      const norm = max > min ? (h.score - min) / (max - min) : 1
      const r = rInner + (1 - norm) * (rOuter - rInner)
      const a = i * GOLDEN - Math.PI / 2
      return { h, x: CX + r * Math.cos(a), y: CY + r * Math.sin(a), norm }
    })
  }, [hits, CX, CY])

  return (
    <StageShell
      index={3}
      icon={Radar}
      title="语义向量检索"
      subtitle="把『假设答案』嵌入成向量，在 Qdrant 语义空间里找最近邻 —— 距离越近越相关"
      state={state}
      current={current}
      badge={<CountBadge>命中 {counts.vector} · {timings_ms.recall} ms</CountBadge>}
    >
      <div className="grid gap-3 sm:grid-cols-[auto_1fr]">
        {/* 语义空间投影 */}
        <div className="mx-auto">
          <svg width={W} height={H} className="overflow-visible">
            <defs>
              <radialGradient id="xray-vglow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="var(--c-accent)" stopOpacity="0.26" />
                <stop offset="100%" stopColor="var(--c-accent)" stopOpacity="0" />
              </radialGradient>
            </defs>
            {/* 语义场光晕 */}
            <circle cx={CX} cy={CY} r={72} fill="url(#xray-vglow)" />
            {/* 同心参考圈（缓慢旋转，营造语义空间纵深） */}
            <motion.g
              style={{ transformOrigin: `${CX}px ${CY}px` }}
              animate={state === "active" ? { rotate: 360 } : {}}
              transition={{ duration: 64, repeat: Infinity, ease: "linear" }}
            >
              {[44, 90, 132].map((r) => (
                <circle
                  key={r}
                  cx={CX} cy={CY} r={r}
                  fill="none"
                  stroke="var(--c-border)"
                  strokeWidth={1}
                  strokeDasharray="3 5"
                />
              ))}
            </motion.g>
            {/* 中心→节点连线 */}
            {layout.map(({ h, x, y, norm }, i) => (
              <motion.line
                key={`l-${h.child_chunk_id}`}
                x1={CX} y1={CY} x2={x} y2={y}
                stroke="var(--c-accent)"
                strokeWidth={1}
                initial={{ pathLength: 0, opacity: 0 }}
                animate={state === "active" ? { pathLength: 1, opacity: 0.25 + norm * 0.5 } : {}}
                transition={{ delay: 0.3 + i * 0.07, duration: 0.5 }}
              />
            ))}
            {/* 沿连线流动的"语义信号"粒子（中心→近邻） */}
            {layout.slice(0, 6).map(({ h, x, y }, i) => (
              <motion.circle
                key={`c-${h.child_chunk_id}`}
                cx={CX} cy={CY} r={2.4}
                fill="var(--c-accent)"
                initial={{ x: 0, y: 0, opacity: 0 }}
                animate={
                  state === "active"
                    ? { x: [0, x - CX], y: [0, y - CY], opacity: [0, 0.95, 0] }
                    : { opacity: 0 }
                }
                transition={{
                  duration: 1.5, delay: 0.6 + i * 0.18,
                  repeat: Infinity, repeatDelay: 1.5, ease: "easeInOut",
                }}
              />
            ))}
            {/* 候选节点 */}
            {layout.map(({ h, x, y, norm }, i) => (
              <motion.g
                key={`n-${h.child_chunk_id}`}
                initial={{ opacity: 0, scale: 0 }}
                animate={state === "active" ? { opacity: 1, scale: 1 } : {}}
                transition={{ delay: 0.35 + i * 0.07, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
                style={{ transformOrigin: `${x}px ${y}px` }}
              >
                <circle cx={x} cy={y} r={i < 3 ? 7 : 5} fill="var(--c-accent)" opacity={0.35 + norm * 0.55} />
                <text
                  x={x} y={y + 3}
                  textAnchor="middle"
                  className="fill-[var(--c-accent-ink)] font-mono"
                  style={{ fontSize: 8, fontWeight: 600 }}
                >
                  {h.rank + 1}
                </text>
              </motion.g>
            ))}
            {/* 中心：假设答案查询 */}
            <motion.circle
              cx={CX} cy={CY} r={13}
              fill="var(--c-accent)"
              style={{ transformOrigin: "center", transformBox: "fill-box" }}
              initial={{ scale: 0 }}
              animate={state === "active" ? { scale: [0, 1.15, 1] } : {}}
              transition={{ duration: 0.5 }}
            />
            {/* 脉冲环：用 scale 动画（不直接动 SVG r 属性，避免 motion 把 r 置为 undefined 报错）*/}
            <motion.circle
              cx={CX} cy={CY} r={13}
              fill="none" stroke="var(--c-accent)" strokeWidth={2}
              style={{ transformOrigin: "center", transformBox: "fill-box" }}
              initial={{ scale: 1, opacity: 0.6 }}
              animate={state === "active" ? { scale: [1, 2], opacity: [0.6, 0] } : { opacity: 0 }}
              transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
            />
            <text x={CX} y={CY + 28} textAnchor="middle" className="fill-[var(--c-ink-soft)]" style={{ fontSize: 9 }}>
              假设答案查询
            </text>
          </svg>
          <p className="mt-1 text-center text-[10px] text-ink-faint">距离 ∝ 1 − 余弦相似度</p>
        </div>

        {/* 近邻列表 */}
        <ul className="min-w-0 space-y-1.5">
          {hits.slice(0, 6).map((h, i) => (
            <motion.li
              key={h.child_chunk_id}
              initial={{ opacity: 0, x: 10 }}
              animate={state === "active" ? { opacity: 1, x: 0 } : {}}
              transition={{ delay: 0.4 + i * 0.08 }}
              className="flex items-center gap-2 rounded-md border border-border bg-surface-2/40 px-2.5 py-1.5 cursor-pointer hover:bg-accent-soft/20 transition-colors"
              onClick={() => navigate(`/kb/${kbId}/dissect?doc=${h.doc_id}&child=${encodeURIComponent(h.child_chunk_id)}`)}
            >
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft font-mono text-[10px] font-semibold text-accent">
                {h.rank + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <DocTag docId={h.doc_id} docs={docs} />
                  {isImageType(h.chunk_type) && <ImageIcon className="h-3 w-3 text-accent" />}
                </div>
                <p className="truncate text-[11px] text-ink-soft">{h.text}</p>
              </div>
              <ScoreBar value={h.score} max={hits[0]?.score ?? 1} min={0} width={48} />
            </motion.li>
          ))}
        </ul>
      </div>
    </StageShell>
  )
}

// ═══════════════════════════════════════════════════════════
// ④ RRF 融合
// ═══════════════════════════════════════════════════════════

export function StageFusion({ trace, docs, state, current }: StageProps) {
  const { fusion, counts, timings_ms } = trace
  const navigate = useNavigate()
  const { kbId } = useParams<{ kbId: string }>()
  const maxRrf = Math.max(...fusion.map((f) => f.rrf_score), 0.0001)
  const rows = fusion.slice(0, 10)

  return (
    <StageShell
      index={4}
      icon={GitMerge}
      title="RRF 倒数排名融合"
      subtitle="两路名次各算 1/(60+rank) 再相加 —— 不依赖分数量纲，被两路都看好的块脱颖而出"
      state={state}
      current={current}
      badge={<CountBadge>融合 {counts.fused} · {timings_ms.fuse} ms</CountBadge>}
    >
      <div className="space-y-2">
        <div className="flex items-center justify-end gap-3 pb-1 text-[10px] font-semibold text-ink-faint">
          <span className="w-14 text-center">向量名次</span>
          <span className="w-14 text-center">关键词名次</span>
          <span className="w-24 text-center">RRF 分数</span>
        </div>
        {rows.map((f, i) => (
          <motion.div
            key={f.child_chunk_id}
            initial={{ opacity: 0, y: 8 }}
            animate={state === "active" ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: 0.1 + i * 0.06 }}
            className="flex items-center gap-3 rounded-md border border-border bg-surface-2/30 px-2.5 py-1.5 cursor-pointer hover:bg-accent-soft/20 transition-colors"
            onClick={() => navigate(`/kb/${kbId}/dissect?doc=${f.doc_id}&child=${encodeURIComponent(f.child_chunk_id)}`)}
          >
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft font-mono text-[10px] font-semibold text-accent">
              {f.rank + 1}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <DocTag docId={f.doc_id} docs={docs} />
                <span className="truncate text-[10px] text-ink-faint">{crumb(f.header_path)}</span>
              </div>
              <p className="truncate text-[11px] text-ink-soft">{f.text}</p>
            </div>
            <RankToken rank={f.vec_rank} tone="accent" />
            <RankToken rank={f.kw_rank} tone="ink" />
            <span className="w-24">
              <ScoreBar value={f.rrf_score} max={maxRrf} width={64} />
            </span>
          </motion.div>
        ))}
      </div>
    </StageShell>
  )
}

function RankToken({ rank, tone }: { rank: number | null; tone: "accent" | "ink" }) {
  if (rank === null || rank === undefined) {
    return <span className="w-14 text-center font-mono text-[11px] text-ink-faint">—</span>
  }
  return (
    <span
      className={cn(
        "w-14 text-center font-mono text-[11px] font-semibold",
        tone === "accent" ? "text-accent" : "text-ink-soft",
      )}
    >
      #{rank + 1}
    </span>
  )
}

// ═══════════════════════════════════════════════════════════
// ⑤ 重排（rerank 重新排序）
// ═══════════════════════════════════════════════════════════

const ROW_H = 46

export function StageRerank({ trace, docs, state, current }: StageProps) {
  const { fusion, reranked, counts, timings_ms, rerank_degraded } = trace
  const left = fusion.slice(0, 12)
  const leftIndex = useMemo(() => {
    const m = new Map<string, number>()
    left.forEach((f, i) => m.set(f.child_chunk_id, i))
    return m
  }, [left])
  const maxScore = Math.max(...reranked.map((r) => r.rerank_score), 0.0001)
  const minScore = Math.min(...reranked.map((r) => r.rerank_score), 0)
  const svgH = Math.max(left.length, reranked.length) * ROW_H
  const CONN_W = 52

  return (
    <StageShell
      index={5}
      icon={ArrowUpNarrowWide}
      title="交叉编码器重排 · qwen3-rerank"
      subtitle="把融合候选连同问句逐一送进重排模型深读打分 —— 真正语义相关的块被提到最前"
      state={state}
      current={current}
      badge={
        rerank_degraded ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2.5 py-1 text-[11px] font-medium text-warn">
            <AlertTriangle className="h-3 w-3" /> 重排降级
          </span>
        ) : (
          <CountBadge>终选 {counts.final} · {timings_ms.rerank} ms</CountBadge>
        )
      }
    >
      <div className="grid gap-0" style={{ gridTemplateColumns: `1fr ${CONN_W}px 1fr` }}>
        {/* 左：融合序 */}
        <div className="min-w-0">
          <div className="mb-1 text-center text-[10px] font-semibold text-ink-faint">融合序</div>
          {left.map((f, i) => (
            <ReorderRow
              key={f.child_chunk_id}
              h={{ rank: i, doc_id: f.doc_id, text: f.text, child_chunk_id: f.child_chunk_id }}
              docs={docs}
              side="left"
            />
          ))}
        </div>

        {/* 中：连线 */}
        <div className="relative">
          <div className="mb-1 h-[14px]" />
          <svg width={CONN_W} height={svgH} className="overflow-visible">
            {reranked.map((r, j) => {
              const li = r.prev_rank !== null && r.prev_rank < left.length
                ? r.prev_rank
                : leftIndex.get(r.child_chunk_id)
              if (li === undefined || li === null) return null
              const y0 = li * ROW_H + ROW_H / 2
              const y1 = j * ROW_H + ROW_H / 2
              const moved = (r.delta ?? 0) !== 0
              const d = `M 0 ${y0} C ${CONN_W * 0.5} ${y0}, ${CONN_W * 0.5} ${y1}, ${CONN_W} ${y1}`
              return (
                <g key={r.child_chunk_id}>
                  <motion.path
                    d={d}
                    fill="none"
                    stroke={moved ? "var(--c-accent)" : "var(--c-border-strong)"}
                    strokeWidth={moved ? 1.75 : 1}
                    initial={{ pathLength: 0, opacity: 0 }}
                    animate={state === "active" ? { pathLength: 1, opacity: moved ? 0.7 : 0.4 } : {}}
                    transition={{ delay: 0.2 + j * 0.1, duration: 0.6 }}
                  />
                  {/* 位次变化的连线：叠加流光（流动虚线），表现语义能量流向 */}
                  {moved && (
                    <motion.path
                      d={d}
                      fill="none"
                      stroke="var(--c-accent)"
                      strokeWidth={1.75}
                      strokeDasharray="3 11"
                      initial={{ opacity: 0 }}
                      animate={state === "active" ? { opacity: 0.9, strokeDashoffset: [0, -28] } : { opacity: 0 }}
                      transition={{
                        opacity: { delay: 0.6 + j * 0.1, duration: 0.4 },
                        strokeDashoffset: { duration: 1.1, repeat: Infinity, ease: "linear" },
                      }}
                    />
                  )}
                </g>
              )
            })}
          </svg>
        </div>

        {/* 右：重排序 */}
        <div className="min-w-0">
          <div className="mb-1 text-center text-[10px] font-semibold text-accent">重排序</div>
          {reranked.map((r, j) => (
            <ReorderRow
              key={r.child_chunk_id}
              h={{ rank: j, doc_id: r.doc_id, text: r.text, chunk_type: r.chunk_type, child_chunk_id: r.child_chunk_id }}
              docs={docs}
              side="right"
              delta={r.delta}
              score={r.rerank_score}
              scoreMax={maxScore}
              scoreMin={minScore}
              animateInDelay={0.3 + j * 0.1}
              active={state === "active"}
            />
          ))}
        </div>
      </div>
    </StageShell>
  )
}

function ReorderRow({
  h, docs, side, delta, score, scoreMax, scoreMin, animateInDelay = 0, active = true,
}: {
  h: { rank: number; doc_id: string; text: string; chunk_type?: string; child_chunk_id?: string }
  docs: Record<string, DocMeta>
  side: "left" | "right"
  delta?: number | null
  score?: number
  scoreMax?: number
  scoreMin?: number
  animateInDelay?: number
  active?: boolean
}) {
  const navigate = useNavigate()
  const { kbId } = useParams<{ kbId: string }>()
  const content = (
    <div
      className={cn(
        "flex items-center gap-2 rounded-md border px-2 py-1.5 cursor-pointer hover:bg-accent-soft/20 transition-colors",
        side === "right" ? "border-accent/25 bg-accent-soft/20" : "border-border bg-surface-2/30",
      )}
      style={{ height: ROW_H - 6 }}
      onClick={() => h.child_chunk_id && navigate(`/kb/${kbId}/dissect?doc=${h.doc_id}&child=${encodeURIComponent(h.child_chunk_id)}`)}
    >
      <span
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full font-mono text-[10px] font-semibold",
          side === "right" ? "bg-accent text-accent-ink" : "bg-surface-2 text-ink-faint",
        )}
      >
        {h.rank + 1}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1">
          <DocTag docId={h.doc_id} docs={docs} />
          {isImageType(h.chunk_type) && <ImageIcon className="h-3 w-3 shrink-0 text-accent" />}
          {side === "right" && delta !== undefined && <DeltaBadge delta={delta} />}
        </div>
        <p className="truncate text-[10px] text-ink-soft">{h.text}</p>
      </div>
      {side === "right" && score !== undefined && (
        <ScoreBar value={score} max={scoreMax ?? 1} min={scoreMin ?? 0} width={40} />
      )}
    </div>
  )
  if (side !== "right") {
    return <div className="py-[3px]">{content}</div>
  }
  return (
    <motion.div
      className="py-[3px]"
      initial={{ opacity: 0, x: 12 }}
      animate={active ? { opacity: 1, x: 0 } : {}}
      transition={{ delay: animateInDelay, duration: 0.4 }}
    >
      {content}
    </motion.div>
  )
}

function DeltaBadge({ delta }: { delta?: number | null }) {
  if (delta === null || delta === undefined) return null
  if (delta === 0) {
    return (
      <span className="inline-flex items-center gap-0.5 rounded bg-surface-2 px-1 text-[9px] font-medium text-ink-faint">
        <Minus className="h-2.5 w-2.5" />持平
      </span>
    )
  }
  const up = delta > 0
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 rounded px-1 text-[9px] font-semibold",
        up ? "bg-accent-soft text-accent-strong" : "bg-surface-2 text-ink-faint",
      )}
    >
      {up ? <ArrowUp className="h-2.5 w-2.5" /> : <ArrowDown className="h-2.5 w-2.5" />}
      {Math.abs(delta)}
    </span>
  )
}

// ═══════════════════════════════════════════════════════════
// ⑥ 终选 top-K
// ═══════════════════════════════════════════════════════════

export function StageFinal({ trace, docs, state, current }: StageProps) {
  const { reranked, timings_ms } = trace
  const navigate = useNavigate()
  const { kbId } = useParams<{ kbId: string }>()
  const maxScore = Math.max(...reranked.map((r) => r.rerank_score), 0.0001)
  const minScore = Math.min(...reranked.map((r) => r.rerank_score), 0)
  const hasImage = reranked.some((r) => isImageType(r.chunk_type))

  return (
    <StageShell
      index={6}
      icon={Trophy}
      title="终选 · 交给大模型"
      subtitle="重排后的 top-K 命中块流向问答模型生成答案"
      state={state}
      current={current}
      isLast
      badge={<CountBadge>全链路 {timings_ms.total} ms</CountBadge>}
    >
      <div className="space-y-2.5">
        {reranked.map((r, i) => (
          <motion.div
            key={r.child_chunk_id}
            initial={{ opacity: 0, y: 10 }}
            animate={state === "active" ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: 0.1 + i * 0.1, duration: 0.45 }}
            className={cn(
              "rounded-lg border p-3 cursor-pointer hover:bg-accent-soft/20 transition-colors",
              isImageType(r.chunk_type)
                ? "border-accent/30 bg-accent-soft/20"
                : "border-border bg-surface-2/30",
            )}
            onClick={() => navigate(`/kb/${kbId}/dissect?doc=${r.doc_id}&child=${encodeURIComponent(r.child_chunk_id)}`)}
          >
            <div className="mb-1.5 flex items-center gap-2">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent font-mono text-xs font-bold text-accent-ink">
                {r.rank + 1}
              </span>
              <DocTag docId={r.doc_id} docs={docs} />
              <ChunkTypeBadge type={r.chunk_type} />
              <span className="ml-auto">
                <ScoreBar value={r.rerank_score} max={maxScore} min={minScore} width={72} />
              </span>
            </div>
            <p className="mb-1 text-[10px] text-ink-faint">{crumb(r.header_path)}</p>
            <p className="line-clamp-2 text-xs leading-relaxed text-ink-soft">{r.text}</p>
          </motion.div>
        ))}

        <div className="flex items-center gap-2 pt-1 text-xs text-ink-soft">
          <ArrowUpNarrowWide className="h-4 w-4 rotate-90 text-accent" />
          <span>
            命中的是子块；实际喂给大模型的是其
            <span className="font-medium text-ink">父块全文</span>
            （Small-to-Big）
            {hasImage && (
              <>
                ，命中图片时
                <span className="font-medium text-accent">原图随描述一并交给多模态模型</span>
              </>
            )}
            。
          </span>
        </div>
      </div>
    </StageShell>
  )
}

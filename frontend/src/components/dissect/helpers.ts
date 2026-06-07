// 解析透视 · 纯助手（无组件，便于 fast-refresh 与复用）
// 块类型视觉图例（颜色/标签/图标）、bbox 归一、文档树构建、派生映射。

import {
  Code2, Hash, Heading, ImageIcon, List, PanelBottom, PanelTop, Sigma, Square,
  Table2, Text, type LucideIcon,
} from "lucide-react"
import type {
  ChildChunkRow, ChunksResponse, IRBlock, IRResponse, IRSection, ParentChunkRow,
} from "@/api/types"

// ── 块类型图例（X 光配色：暖纸上克制的层位色）─────────────────
// 颜色直接作用在白底 PDF 上的描边/半透明填充，故用固定 hex（不随主题变）。

export interface TypeMeta { label: string; color: string; Icon: LucideIcon }

const TYPE_META: Record<string, TypeMeta> = {
  title: { label: "标题", color: "#b15c34", Icon: Heading },
  paragraph: { label: "正文", color: "#5b6b8c", Icon: Text },
  list: { label: "列表", color: "#6b8359", Icon: List },
  table: { label: "表格", color: "#b0832a", Icon: Table2 },
  image: { label: "图片", color: "#3c8c8c", Icon: ImageIcon },
  code: { label: "代码", color: "#8a5a8a", Icon: Code2 },
  equation: { label: "公式", color: "#7068b0", Icon: Sigma },
  // 页面附属块（MinerU 额外类型，页眉/页脚/页码）—— 灰调，作版面噪声
  page_header: { label: "页眉", color: "#a39684", Icon: PanelTop },
  page_footer: { label: "页脚", color: "#a39684", Icon: PanelBottom },
  page_number: { label: "页码", color: "#a39684", Icon: Hash },
}

const DEFAULT_META: TypeMeta = { label: "其它", color: "#9c937f", Icon: Square }

export function typeMeta(type?: string): TypeMeta {
  return (type && TYPE_META[type]) || DEFAULT_META
}

/** 图例里要展示的类型顺序（仅列出文档实际出现的）。 */
export const LEGEND_ORDER: string[] = [
  "title", "paragraph", "list", "table", "image", "code", "equation",
  "page_header", "page_footer", "page_number",
]

export function legendItems(usedTypes: Set<string>): Array<TypeMeta & { type: string }> {
  return LEGEND_ORDER
    .filter((t) => usedTypes.has(t))
    .map((t) => ({ type: t, ...TYPE_META[t] }))
}

export function isImageType(t?: string): boolean {
  return t === "image"
}

// ── bbox ────────────────────────────────────────────────────

export interface Box { left: number; top: number; width: number; height: number }

/** 把 [x0,y0,x1,y1]（0~1000）转成百分比定位框；无效/零面积返回 null。 */
export function normBox(coords?: number[]): Box | null {
  if (!coords || coords.length < 4) return null
  const [x0, y0, x1, y1] = coords
  const left = Math.max(0, Math.min(1000, x0))
  const top = Math.max(0, Math.min(1000, y0))
  const right = Math.max(0, Math.min(1000, x1))
  const bottom = Math.max(0, Math.min(1000, y1))
  if (right <= left || bottom <= top) return null
  return { left: left / 10, top: top / 10, width: (right - left) / 10, height: (bottom - top) / 10 }
}

/** 该文档是否有可用版面坐标（PDF/图片有，Office 文档 bbox 全 0）。 */
export function hasGeometry(blocks: IRBlock[]): boolean {
  return blocks.some((b) => normBox(b.bbox_norm1000) !== null)
}

// ── 文档树（LLM 重建后的层级）───────────────────────────────

export interface TreeNode { section: IRSection; depth: number; children: TreeNode[] }

/** 由 sections 构建层级树：根 = 无父或父不存在的节点，按 child_section_ids 展开。 */
export function buildSectionTree(sections: IRSection[]): TreeNode[] {
  const byId = new Map(sections.map((s) => [s.section_id, s]))
  const isRoot = (s: IRSection) =>
    !s.parent_section_id || !byId.has(s.parent_section_id)

  const build = (s: IRSection, depth: number, seen: Set<string>): TreeNode => {
    seen.add(s.section_id)
    const children = (s.child_section_ids || [])
      .map((id) => byId.get(id))
      .filter((c): c is IRSection => !!c && !seen.has(c.section_id))
      .map((c) => build(c, depth + 1, seen))
    return { section: s, depth, children }
  }

  const seen = new Set<string>()
  const roots: TreeNode[] = []
  for (const s of sections) {
    if (isRoot(s) && !seen.has(s.section_id)) roots.push(build(s, 0, seen))
  }
  // 兜底：任何没被任一根挂上的 section（环/脏数据）平铺到末尾
  for (const s of sections) {
    if (!seen.has(s.section_id)) roots.push(build(s, 0, seen))
  }
  return roots
}

export function sectionLabel(s: IRSection): string {
  return s.title?.trim() || s.header_path?.filter(Boolean).slice(-1)[0] || "（无标题段）"
}

// ── 派生映射（页面 useMemo 一次算好）────────────────────────

/** 父块在某一页上的成员块 bbox 并集（真正的「父块大框」，跨多 section 聚合）。 */
export interface ParentBoxEntry { page_idx: number; box: Box }

export interface DerivedMaps {
  blockById: Map<string, IRBlock>
  sectionById: Map<string, IRSection>
  parentById: Map<string, ParentChunkRow>
  /** block_id → 命中它的子切片（source_block_ids 含该块）。 */
  childrenByBlock: Map<string, ChildChunkRow[]>
  /** block_id → 含它的父切片（block_ids 含该块）。 */
  parentByBlock: Map<string, ParentChunkRow>
  /** parent_chunk_id → 其子切片。 */
  childrenByParent: Map<string, ChildChunkRow[]>
  /** page_idx → 按 order_in_page 排序的块。 */
  blocksByPage: Map<number, IRBlock[]>
  /** section_id → 其成员块（按 order_in_doc）。 */
  blocksBySection: Map<string, IRBlock[]>
  /** parent_chunk_id → 各页的成员块 bbox 并集（父块大框，L1 聚合后跨多 section/页）。 */
  parentBoxes: Map<string, ParentBoxEntry[]>
  usedTypes: Set<string>
}

/** 用父块成员块坐标按页求并集 → 真正的父块大框（替代旧的 section 级框）。 */
function computeParentBoxes(
  parents: ParentChunkRow[],
  blockById: Map<string, IRBlock>,
): Map<string, ParentBoxEntry[]> {
  const out = new Map<string, ParentBoxEntry[]>()
  for (const p of parents) {
    const acc = new Map<number, [number, number, number, number]>()
    for (const bid of p.block_ids || []) {
      const b = blockById.get(bid)
      const c = b?.bbox_norm1000
      if (!b || !c || c.length < 4) continue
      const cur = acc.get(b.page_idx)
      if (!cur) acc.set(b.page_idx, [c[0], c[1], c[2], c[3]])
      else {
        cur[0] = Math.min(cur[0], c[0]); cur[1] = Math.min(cur[1], c[1])
        cur[2] = Math.max(cur[2], c[2]); cur[3] = Math.max(cur[3], c[3])
      }
    }
    const entries: ParentBoxEntry[] = []
    for (const [pg, coords] of [...acc.entries()].sort((a, b) => a[0] - b[0])) {
      const box = normBox(coords)
      if (box) entries.push({ page_idx: pg, box })
    }
    if (entries.length) out.set(p.parent_chunk_id, entries)
  }
  return out
}

export function buildMaps(ir: IRResponse, chunks: ChunksResponse | null): DerivedMaps {
  const blockById = new Map(ir.blocks.map((b) => [b.block_id, b]))
  const sectionById = new Map(ir.sections.map((s) => [s.section_id, s]))

  const blocksByPage = new Map<number, IRBlock[]>()
  const blocksBySection = new Map<string, IRBlock[]>()
  const usedTypes = new Set<string>()
  for (const b of ir.blocks) {
    usedTypes.add(b.type)
    const pg = blocksByPage.get(b.page_idx) ?? []
    pg.push(b)
    blocksByPage.set(b.page_idx, pg)
    if (b.section_id) {
      const sec = blocksBySection.get(b.section_id) ?? []
      sec.push(b)
      blocksBySection.set(b.section_id, sec)
    }
  }
  for (const list of blocksByPage.values()) list.sort((a, b) => a.order_in_page - b.order_in_page)
  for (const list of blocksBySection.values()) list.sort((a, b) => a.order_in_doc - b.order_in_doc)

  const parentById = new Map<string, ParentChunkRow>()
  const parentByBlock = new Map<string, ParentChunkRow>()
  const childrenByBlock = new Map<string, ChildChunkRow[]>()
  const childrenByParent = new Map<string, ChildChunkRow[]>()

  if (chunks) {
    for (const p of chunks.parents) {
      parentById.set(p.parent_chunk_id, p)
      for (const bid of p.block_ids || []) parentByBlock.set(bid, p)
    }
    for (const c of chunks.children) {
      const byP = childrenByParent.get(c.parent_chunk_id) ?? []
      byP.push(c)
      childrenByParent.set(c.parent_chunk_id, byP)
      for (const bid of c.source_block_ids || []) {
        const byB = childrenByBlock.get(bid) ?? []
        byB.push(c)
        childrenByBlock.set(bid, byB)
      }
    }
  }

  const parentBoxes = computeParentBoxes(chunks?.parents ?? [], blockById)

  return {
    blockById, sectionById, parentById, childrenByBlock, parentByBlock,
    childrenByParent, blocksByPage, blocksBySection, parentBoxes, usedTypes,
  }
}

export function crumb(headerPath: string[]): string {
  return headerPath.filter(Boolean).join(" › ") || "（无标题层级）"
}

export function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + "…" : s
}

import { useEffect, useState } from "react"
import { Document, Page, pdfjs } from "react-pdf"
import { getOriginPdfUrl } from "@/api/client"
import type { CitationItem } from "@/api/types"
import { Dialog, DialogClose, DialogHeader, DialogTitle } from "@/components/ui/dialog"

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString()

interface PreviewState { url: string; pageNumber: number; bboxes: number[][]; title: string }

const toUserPage = (z?: number) => Math.max(1, (z ?? 0) + 1)
const normalizeBBoxes = (boxes?: number[][]): number[][] =>
  (boxes ?? [])
    .filter((b) => Array.isArray(b) && b.length >= 4)
    .map((b) => b.slice(0, 4).map((v) => Math.max(0, Math.min(1000, Number(v) || 0))))
    .filter((b) => b[2] > b[0] && b[3] > b[1])

/**
 * 引用「查看原文」PDF 预览（带 bbox 高亮）的可复用 hook。
 * 返回 openPreview(引用) 与要挂到页面里的 previewNode（一个受控 Dialog）。
 * 供 ChatPage / ReviewPage / CourseInfoPage 复用，避免重复实现。
 */
export function usePdfPreview(kbId: string | undefined) {
  const [preview, setPreview] = useState<PreviewState | null>(null)
  const [pdfWidth, setPdfWidth] = useState(760)

  useEffect(() => {
    const onResize = () => setPdfWidth(Math.max(360, Math.min(1000, window.innerWidth - 320)))
    onResize()
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [])

  const openPreview = (c: CitationItem) => {
    if (!kbId || !c.anchor_origin_pdf_path) return
    setPreview({
      url: getOriginPdfUrl(kbId, c.doc_id),
      pageNumber: toUserPage(c.page_span_start),
      bboxes: normalizeBBoxes(c.bbox_norm1000),
      title: c.header_path?.length ? c.header_path.join(" › ") : c.doc_id,
    })
  }

  const previewNode = (
    <Dialog open={!!preview} onClose={() => setPreview(null)} className="w-full max-w-6xl">
      <DialogClose onClick={() => setPreview(null)} />
      <DialogHeader>
        <DialogTitle>原文预览 (p.{preview?.pageNumber ?? 1}){preview?.title ? ` · ${preview.title}` : ""}</DialogTitle>
      </DialogHeader>
      <div className="h-[72vh] overflow-auto rounded-lg bg-surface-2 p-4">
        {preview && (
          <div className="mx-auto w-fit">
            <div className="relative shadow-pop">
              <Document
                file={preview.url}
                loading={<div className="p-6 text-sm text-ink-soft">PDF 加载中…</div>}
                error={<div className="p-6 text-sm text-accent">PDF 加载失败（origin.pdf 可能不存在）</div>}
              >
                <Page pageNumber={preview.pageNumber} width={pdfWidth} renderAnnotationLayer={false} renderTextLayer={false} />
              </Document>
              {preview.bboxes.map((bbox, idx) => (
                <div
                  key={`${idx}-${bbox.join("-")}`}
                  className="pointer-events-none absolute border-2 border-accent bg-accent/15"
                  style={{
                    left: `${bbox[0] / 10}%`, top: `${bbox[1] / 10}%`,
                    width: `${(bbox[2] - bbox[0]) / 10}%`, height: `${(bbox[3] - bbox[1]) / 10}%`,
                  }}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </Dialog>
  )

  return { openPreview, previewNode }
}

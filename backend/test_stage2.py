"""
Stage 2 集成测试脚本

测试内容：
1. 批量上传：sample.pdf + sample.pptx + sample.docx（批量预签名 PUT）
2. 批量上传：sampleJPG/*.jpg（多图批量）
3. 单文件 URL 测试（跳过，因本地无公网 URL）
4. ZIP 下载 → Bundle 解析 → 归一化 → DOM 建树 → IR 写出

运行方式：
  cd backend
  python test_stage2.py

注意：需要 MINERU_API_KEY 系统变量已配置。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# 让 app 包可以被导入
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_stage2")

from app.config import settings
from app.services.mineru_client import (
    download_zip,
    poll_batch_results,
    request_batch_upload_urls,
    upload_file_to_presigned_url,
)
from app.adapters.bundle_parser import extract_zip, parse_bundle_manifest
from app.adapters.normalizer import normalize
from app.adapters.dom_builder import build_dom
from app.adapters.footnote_linker import link_footnotes
from app.writers.ir_writer import write_ir

settings.ensure_dirs()

TEST_INPUTS = Path(__file__).parent.parent / "test_inputs"
SAMPLE_PDF  = TEST_INPUTS / "sample.pdf"
SAMPLE_PPT  = TEST_INPUTS / "sample.pptx"
SAMPLE_DOCX = TEST_INPUTS / "sample.docx"
SAMPLE_JPGS = sorted((TEST_INPUTS / "sampleJPG").glob("*.jpg"))


# ─────────────────────────────────────────────────────────────
# 通用：上传一批文件 → 等待 MinerU → 下载 ZIP → 解析 IR
# ─────────────────────────────────────────────────────────────

async def run_batch(
    files: list[Path],
    label: str,
) -> list[Path]:
    """
    对 files 中的一批本地文件执行完整流水线。
    返回每个文件生成的 document_ir.json 路径列表。
    """
    logger.info("=== [%s] 开始批量上传 %d 个文件 ===", label, len(files))

    # 1. 申请预签名 URL
    files_info = [{"name": f.name, "data_id": f.stem[:32]} for f in files]
    batch_id, presigned_urls = await request_batch_upload_urls(files_info)

    if len(presigned_urls) != len(files):
        raise RuntimeError(
            f"预签名 URL 数量 ({len(presigned_urls)}) 与文件数 ({len(files)}) 不匹配"
        )

    # 2. 上传文件
    for file_path, url in zip(files, presigned_urls):
        logger.info("上传: %s", file_path.name)
        await upload_file_to_presigned_url(url, file_path)

    # 3. 轮询批量结果
    logger.info("[%s] 等待 MinerU 解析 … batch_id=%s", label, batch_id[:8])
    results = await poll_batch_results(batch_id, poll_interval=8.0, max_wait=900.0)

    ir_paths: list[Path] = []

    for i, (file_path, result) in enumerate(zip(files, results)):
        state = result.get("state")
        if state == "failed":
            logger.error("文件 %s 解析失败: %s", file_path.name, result.get("err_msg"))
            continue

        zip_url = result.get("full_zip_url", "")
        if not zip_url:
            logger.error("文件 %s 无 full_zip_url", file_path.name)
            continue

        # 4. 下载 ZIP（用 stem + 无扩展名后缀作 doc_id，避免不同格式同名互相覆盖）
        stem_suffix = file_path.suffix.lower().lstrip(".")  # pdf / pptx / docx / jpg
        doc_id = f"test-{file_path.stem[:16]}-{stem_suffix}"
        zip_dir = settings.mineru_zip_dir / "test" / doc_id
        zip_dir.mkdir(parents=True, exist_ok=True)
        zip_path = zip_dir / f"{doc_id}.zip"

        logger.info("[%s] 下载 ZIP: %s", label, file_path.name)
        await download_zip(zip_url, zip_path)

        # 5. 解压 + Bundle 识别
        extract_dir = zip_dir / "extracted"
        zip_root = extract_zip(zip_path, extract_dir)
        manifest = parse_bundle_manifest(zip_root)

        if not manifest.content_list_v2_path:
            logger.error("文件 %s 无 content_list_v2.json，跳过 IR 生成", file_path.name)
            continue

        # 6. 归一化
        source_fmt = _detect_format(file_path)
        blocks, pages, degraded = normalize(
            content_list_v2_path=manifest.content_list_v2_path,
            layout_path=manifest.layout_path,
            doc_id=doc_id,
            source_filename=file_path.name,
            source_format=source_fmt,
            images_dir=manifest.images_dir,
        )
        logger.info(
            "[%s] 归一化完成: %d 页, %d 块, %d 条降级",
            label, len(pages), len(blocks), len(degraded),
        )

        # 7. DOM 重建
        blocks, sections = build_dom(blocks)
        logger.info("[%s] DOM 重建: %d sections", label, len(sections))

        # 8. 脚注关联
        blocks = link_footnotes(blocks, pages)

        # 9. 写出 IR
        ir_path = write_ir(
            doc_id=doc_id,
            source_filename=file_path.name,
            source_format=source_fmt,
            manifest=manifest,
            blocks=blocks,
            pages=pages,
            sections=sections,
            degraded_modes=degraded,
        )
        logger.info("[%s] ✓ IR 写出: %s", label, ir_path)
        ir_paths.append(ir_path)

    return ir_paths


def _detect_format(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


# ─────────────────────────────────────────────────────────────
# 测试入口
# ─────────────────────────────────────────────────────────────

async def main():
    logger.info("=== Stage 2 测试开始 ===")
    logger.info("MINERU_API_KEY 已配置: %s", bool(settings.mineru_api_key))

    all_ir_paths: list[Path] = []

    # 测试 1：三种文档格式
    doc_files = [f for f in [SAMPLE_PDF, SAMPLE_PPT, SAMPLE_DOCX] if f.exists()]
    if not doc_files:
        logger.warning("test_inputs 中无 pdf/pptx/docx 文件，跳过测试 1")
    else:
        ir_paths = await run_batch(doc_files, "文档批量")
        all_ir_paths.extend(ir_paths)

    # 测试 2：图片批量（取全部 jpg，最多 200 个限制）
    jpg_files = SAMPLE_JPGS[:200]
    if not jpg_files:
        logger.warning("sampleJPG/ 目录为空，跳过测试 2")
    else:
        ir_paths = await run_batch(jpg_files, "图片批量")
        all_ir_paths.extend(ir_paths)

    logger.info("=== 测试完成，共生成 %d 个 document_ir.json ===", len(all_ir_paths))
    for p in all_ir_paths:
        logger.info("  %s", p)


if __name__ == "__main__":
    asyncio.run(main())

"""
Phase A — ZIP 解包与文件角色识别

功能：
1. 将 MinerU 返回的 zip 包解压到指定目录
2. 按文件名规则识别各文件角色 → RawBundleManifest
3. 同时兼容固定文件名和 UUID 前缀两种命名格式

命名规则（SaaS 实测，两种格式均存在）：
  固定名：layout.json  full.md
  可能带UUID前缀：content_list_v2.json 或 {uuid}_content_list_v2.json
  UUID前缀：{uuid}_content_list.json  {uuid}_model.json
  原文件：{uuid}_origin.{ext}  — ext 跟随上传文件（pdf/docx/pptx 等）
  目录：images/
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from app.models.models_raw_mineru import RawBundleManifest

logger = logging.getLogger(__name__)


def extract_zip(zip_path: Path, dest_dir: Path) -> Path:
    """
    解压 zip 到 dest_dir，返回 zip 根目录路径。
    如果 zip 包内容都在一个子目录下，则返回该子目录；否则返回 dest_dir。
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)

    # 判断是否有单层根目录（zip 内所有文件都在同一顶层子目录下）
    # 同时兼容固定名 content_list_v2.json 和 UUID 前缀 *_content_list_v2.json
    children = list(dest_dir.iterdir())
    if (
        len(children) == 1
        and children[0].is_dir()
        and any(
            f.name == "content_list_v2.json" or f.name.endswith("_content_list_v2.json")
            for f in children[0].rglob("*.json")
        )
    ):
        return children[0]

    return dest_dir


def parse_bundle_manifest(zip_root: Path) -> RawBundleManifest:
    """
    扫描解压目录，按名称模式识别文件角色，返回 RawBundleManifest。

    兼容两种命名格式：
      固定名（旧格式）：content_list_v2.json  layout.json  full.md
      UUID前缀（新格式）：{uuid}_content_list_v2.json
      UUID前缀通用：{uuid}_content_list.json  {uuid}_model.json
      origin 文件：{uuid}_origin.{ext}  — ext 跟随原始文件（仅 .pdf 时可用于 PDF 预览）
      images/  — 资源目录
    """
    # 支持的 origin 文件扩展名（仅 .pdf 用于前端 PDF 预览）
    _ORIGIN_EXTS = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".png", ".jpg", ".jpeg"}

    content_list_v2: str | None = None
    layout: str | None = None
    full_md: str | None = None
    content_list_compat: str | None = None
    model_raw: str | None = None
    origin_pdf: str | None = None   # 仅当 origin 文件是 .pdf 时才设置（用于 PDF 预览）
    images_dir: str | None = None

    for path in zip_root.iterdir():
        name = path.name.lower()
        suffix = path.suffix.lower()

        # content_list_v2.json — 固定名 或 {uuid}_content_list_v2.json
        if name == "content_list_v2.json" or name.endswith("_content_list_v2.json"):
            if content_list_v2 is None:
                content_list_v2 = str(path)

        elif name == "layout.json":
            layout = str(path)

        elif name == "full.md":
            full_md = str(path)

        elif name.endswith("_content_list.json") and not name.endswith("_content_list_v2.json"):
            # 兼容层旧格式，取第一个
            if content_list_compat is None:
                content_list_compat = str(path)

        elif name.endswith("_model.json"):
            if model_raw is None:
                model_raw = str(path)

        elif "_origin." in name and suffix in _ORIGIN_EXTS:
            # {uuid}_origin.{ext} — 只有 .pdf 可用于前端 PDF 预览
            if suffix == ".pdf" and origin_pdf is None:
                origin_pdf = str(path)
            elif origin_pdf is None and suffix != ".pdf":
                # 非 PDF origin 文件：记录日志，不用于预览
                logger.info(
                    "[bundle] origin 文件为非 PDF 格式（%s），PDF 预览不可用", suffix
                )

        elif path.is_dir() and name == "images":
            images_dir = str(path)

        else:
            logger.warning(
                "[MinerU ZIP 未知文件] %s 发现未预期文件: %s"
                " — 可能来自新版 API，请检查是否需要解析该文件以避免信息丢失",
                zip_root.name,
                path.name,
            )

    manifest = RawBundleManifest(
        content_list_v2_path=content_list_v2,
        layout_path=layout,
        full_md_path=full_md,
        content_list_compat_path=content_list_compat,
        model_raw_path=model_raw,
        origin_pdf_path=origin_pdf,
        images_dir=images_dir,
        zip_root=str(zip_root),
    )

    _log_manifest(manifest, zip_root)
    return manifest


def _log_manifest(m: RawBundleManifest, root: Path) -> None:
    found = []
    missing = []
    for field, label in [
        (m.content_list_v2_path, "content_list_v2.json"),
        (m.layout_path, "layout.json"),
        (m.full_md_path, "full.md"),
        (m.content_list_compat_path, "*_content_list.json"),
        (m.model_raw_path, "*_model.json"),
        (m.origin_pdf_path, "*_origin.pdf"),
        (m.images_dir, "images/"),
    ]:
        (found if field else missing).append(label)

    logger.info("Bundle (%s) 识别到: %s", root.name, ", ".join(found))
    if missing:
        logger.warning("Bundle 缺失（可选）: %s", ", ".join(missing))

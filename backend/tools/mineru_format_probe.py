"""
MinerU 输出格式探针脚本

用途
----
定期运行本脚本，检测 MinerU SaaS API 输出格式是否发生变化。
任何与格式推断文档（doc/在线API输出文件格式（SaaS推断版）.md）不一致的情况均会报告。

两种运行模式
-----------

1. 在线模式（--online）：调用 MinerU API 上传测试文件，下载 ZIP，进行严格格式校验
   需要 .env 中配置 MINERU_API_KEY

2. 离线模式（--offline，默认）：使用已有的 ZIP 解压目录（data/mineru_zips/）进行校验
   无需 API Key，适合日常快速检测

用法示例
--------
# 使用已有解析结果进行离线格式校验（推荐日常使用）
cd backend
uv run python tools/mineru_format_probe.py

# 指定测试文件实时上传并校验（会消耗 MinerU API 配额）
uv run python tools/mineru_format_probe.py --online

# 只检查特定目录
uv run python tools/mineru_format_probe.py --zip-dirs data/mineru_zips/42a0ebb6-...

# 输出 JSON 报告到文件
uv run python tools/mineru_format_probe.py --output report.json

退出码
------
0 = 所有文件格式完全符合预期
1 = 发现至少一个错误（未知块类型、JSON 结构异常等）
2 = 发现警告但无错误（未知字段、类型不符等）
3 = 仅有提示信息
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

# ── 路径设置：确保可以从 tools/ 导入 backend/app ──────────────────────────
_BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.adapters.format_checker import (
    FormatCheckReport,
    check_bundle,
    log_report_to_file,
)
from app.adapters.bundle_parser import extract_zip

# ── 颜色输出（ANSI，Windows 10+ 支持）────────────────────────────────────

def _red(s: str) -> str:    return f"\033[91m{s}\033[0m"
def _yellow(s: str) -> str: return f"\033[93m{s}\033[0m"
def _green(s: str) -> str:  return f"\033[92m{s}\033[0m"
def _cyan(s: str) -> str:   return f"\033[96m{s}\033[0m"
def _bold(s: str) -> str:   return f"\033[1m{s}\033[0m"


# ═══════════════════════════════════════════════════════════════════════════
# 离线模式：扫描已有 ZIP 解压目录
# ═══════════════════════════════════════════════════════════════════════════

def scan_existing_zips(zip_base_dir: Path) -> list[tuple[str, Path]]:
    """
    扫描 data/mineru_zips/ 目录，返回 (doc_id, extracted_root) 列表。
    每个子目录代表一个文档的解析结果。
    """
    results: list[tuple[str, Path]] = []
    if not zip_base_dir.exists():
        print(_red(f"[ERROR] 目录不存在: {zip_base_dir}"))
        return results

    for doc_dir in sorted(zip_base_dir.iterdir()):
        if not doc_dir.is_dir():
            continue
        extracted = doc_dir / "extracted"
        if not extracted.exists() or not extracted.is_dir():
            continue
        results.append((doc_dir.name, extracted))

    return results


def run_offline(args: argparse.Namespace) -> list[FormatCheckReport]:
    """离线模式：检查已有的解压目录"""

    # 确定检查哪些目录
    if args.zip_dirs:
        targets: list[tuple[str, Path]] = []
        for d in args.zip_dirs:
            p = Path(d)
            # 如果传入的是 extracted 目录本身
            if p.is_dir() and (p / ".." / ".." / ".." ).exists():
                targets.append((p.parent.name, p))
            else:
                print(_yellow(f"[SKIP] 目录不存在或格式不符: {d}"))
    else:
        zip_base = _BACKEND_DIR.parent / "data" / "mineru_zips"
        targets = scan_existing_zips(zip_base)

    if not targets:
        print(_yellow("[WARN] 未找到任何解压目录，请先上传文件并解析，或使用 --online 模式"))
        return []

    print(_bold(f"\n离线模式：检查 {len(targets)} 个已解析文档\n"))

    reports: list[FormatCheckReport] = []
    for doc_id, extracted_root in targets:
        # 尝试从子目录内文件名推断原始文件名
        source_filename = _guess_source_filename(extracted_root, doc_id)
        print(f"  检查: {source_filename!r}  (doc_id={doc_id[:8]}...)")

        report = check_bundle(
            zip_root=extracted_root,
            source_filename=source_filename,
            doc_id=doc_id,
        )
        reports.append(report)
        _print_report_summary(report)

    return reports


def _guess_source_filename(extracted_root: Path, doc_id: str) -> str:
    """从解压目录内的文件名猜测原始文件名"""
    for f in extracted_root.iterdir():
        name = f.name.lower()
        if "_origin." in name:
            ext = f.suffix
            return f"<source{ext}>"
    return f"<unknown-{doc_id[:8]}>"


# ═══════════════════════════════════════════════════════════════════════════
# 在线模式：实时上传 test_inputs/ 并校验
# ═══════════════════════════════════════════════════════════════════════════

async def run_online_async(args: argparse.Namespace) -> list[FormatCheckReport]:
    """在线模式：上传 test_inputs/ 文件到 MinerU，下载 ZIP 后校验"""
    from app.config import settings
    from app.services.mineru_client import (
        request_batch_upload_urls,
        upload_file_to_presigned_url,
        poll_batch_results,
        download_zip,
    )

    test_inputs_dir = _BACKEND_DIR.parent / "test_inputs"
    if not test_inputs_dir.exists():
        print(_red(f"[ERROR] test_inputs 目录不存在: {test_inputs_dir}"))
        return []

    # 收集测试文件（支持递归，但限制最大文件数）
    supported_exts = {".pdf", ".docx", ".doc", ".pptx", ".ppt",
                      ".png", ".jpg", ".jpeg"}
    test_files: list[Path] = []
    for ext in supported_exts:
        test_files.extend(test_inputs_dir.rglob(f"*{ext}"))
    test_files = sorted(test_files)[:args.max_files]  # 限制数量避免过度消耗配额

    if not test_files:
        print(_yellow(f"[WARN] {test_inputs_dir} 中未找到支持的测试文件"))
        return []

    print(_bold(f"\n在线模式：上传 {len(test_files)} 个测试文件到 MinerU API"))
    for f in test_files:
        print(f"  • {f.relative_to(_BACKEND_DIR.parent)}")
    print()

    # 批量申请预签名 URL
    files_info = [
        {"name": f.name, "data_id": str(uuid.uuid4())}
        for f in test_files
    ]
    print("正在申请预签名 URL...")
    batch_id, upload_urls = await request_batch_upload_urls(files_info)
    print(f"  batch_id={batch_id[:8]}..., 获得 {len(upload_urls)} 个 URL")

    # 上传文件
    print("正在上传文件...")
    for file_path, url in zip(test_files, upload_urls):
        print(f"  ↑ {file_path.name}")
        await upload_file_to_presigned_url(url, file_path)

    # 轮询结果
    print("等待 MinerU 解析完成（可能需要数分钟）...")
    results = await poll_batch_results(batch_id, poll_interval=8.0, max_wait=900.0)

    # 处理结果
    reports: list[FormatCheckReport] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        for file_path, result in zip(test_files, results):
            state = result.get("state", "?")
            if state != "done":
                print(_yellow(f"  [SKIP] {file_path.name}: state={state}, "
                              f"err={result.get('err_msg', '')}"))
                continue

            zip_url = result.get("full_zip_url", "")
            if not zip_url:
                print(_yellow(f"  [SKIP] {file_path.name}: 无 full_zip_url"))
                continue

            # 下载 ZIP
            doc_id = str(uuid.uuid4())
            zip_path = tmp_path / f"{doc_id}.zip"
            extract_dir = tmp_path / doc_id
            print(f"  ↓ {file_path.name}")
            await download_zip(zip_url, zip_path)

            # 解压
            zip_root = extract_zip(zip_path, extract_dir)

            # 严格格式校验
            report = check_bundle(
                zip_root=zip_root,
                source_filename=file_path.name,
                doc_id=doc_id,
            )
            reports.append(report)
            _print_report_summary(report)

    return reports


def run_online(args: argparse.Namespace) -> list[FormatCheckReport]:
    return asyncio.run(run_online_async(args))


# ═══════════════════════════════════════════════════════════════════════════
# 报告输出
# ═══════════════════════════════════════════════════════════════════════════

def _print_report_summary(report: FormatCheckReport) -> None:
    """打印单个文档的摘要行"""
    if report.is_clean:
        print(_green(f"    ✅ 格式完全符合预期（{report.block_count} 块 / {report.page_count} 页）"))
    else:
        status = _red(f"❌ {report.error_count}错误") if report.has_errors else _yellow(f"⚠  {report.warning_count}警告")
        if report.info_count:
            status += f" {report.info_count}提示"
        print(f"    {status}  ({report.block_count} 块 / {report.page_count} 页)")


def print_full_reports(reports: list[FormatCheckReport]) -> None:
    """打印所有报告的详细内容"""
    for report in reports:
        if not report.is_clean or True:  # 总是打印
            print()
            print(report.to_text_report())


def print_aggregate_summary(reports: list[FormatCheckReport]) -> None:
    """打印所有文档的汇总信息"""
    total = len(reports)
    clean = sum(1 for r in reports if r.is_clean)
    has_errors = sum(1 for r in reports if r.has_errors)
    has_warnings = sum(1 for r in reports if r.warning_count > 0 and not r.has_errors)

    print()
    print("=" * 70)
    print(_bold("汇总"))
    print(f"  总检查文件数: {total}")
    print(_green(f"  ✅ 格式完全符合: {clean}"))
    if has_errors:
        print(_red(f"  ❌ 含错误（需立即修复）: {has_errors}"))
    if has_warnings:
        print(_yellow(f"  ⚠  仅含警告: {has_warnings}"))

    # 跨文件汇总所有块类型
    all_types: dict[str, int] = {}
    for r in reports:
        for t, c in r.block_type_counts.items():
            all_types[t] = all_types.get(t, 0) + c
    if all_types:
        print(f"\n  全局块类型分布:")
        for t, c in sorted(all_types.items(), key=lambda x: -x[1]):
            print(f"    {t}: {c}")

    # 汇总所有偏差
    from collections import Counter
    all_deviations = [d for r in reports for d in r.deviations]
    if all_deviations:
        print(f"\n  共 {len(all_deviations)} 条偏差")
        issue_counter: Counter[str] = Counter()
        for d in all_deviations:
            key = d.issue[:60]
            issue_counter[key] += 1
        print("  高频偏差（Top 10）:")
        for issue, count in issue_counter.most_common(10):
            print(f"    [{count}x] {issue}")

    print("=" * 70)

    # 操作建议
    if has_errors or sum(r.warning_count for r in reports) > 0:
        print()
        print(_bold("📋 建议操作："))
        if has_errors:
            print(_red("  1. 立即检查上面报告中的 ❌ ERROR 条目"))
            print(_red("     → 通常表示出现了新块类型或 JSON 结构发生了根本性变化"))
            print(_red("     → 需要更新 normalizer.py 和 format_checker.py 的 KNOWN_BLOCK_TYPES"))
        if sum(r.warning_count for r in reports) > 0:
            print(_yellow("  2. 检查 ⚠  WARNING 条目（出现未知字段等）"))
            print(_yellow("     → 通常表示 MinerU 新增了可选字段"))
            print(_yellow("     → 需要更新 BLOCK_OPTIONAL_FIELDS / CONTENT_KNOWN_FIELDS 等白名单"))
            print(_yellow("     → 同时更新 doc/在线API输出文件格式（SaaS推断版）.md 第 9 节"))
        print()
        print("  修复后重新运行此脚本，直到所有文件显示 ✅ 为止。")


def save_json_report(reports: list[FormatCheckReport], output_path: Path) -> None:
    """保存 JSON 格式的汇总报告"""
    data = {
        "probe_count": len(reports),
        "clean_count": sum(1 for r in reports if r.is_clean),
        "error_count": sum(r.error_count for r in reports),
        "warning_count": sum(r.warning_count for r in reports),
        "reports": [r.to_dict() for r in reports],
    }
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON 报告已保存: {output_path}")


# ═══════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="MinerU 输出格式探针 — 检测 API 格式变化",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="在线模式：上传 test_inputs/ 文件到 MinerU API（会消耗配额）",
    )
    parser.add_argument(
        "--zip-dirs",
        nargs="+",
        metavar="DIR",
        help="指定要检查的 extracted 目录（离线模式）",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=10,
        help="在线模式最多上传的文件数（默认 10，避免过度消耗配额）",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="保存 JSON 格式报告到文件",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="打印每个文件的完整详细报告",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="仅在有偏差时打印输出",
    )
    return parser


def main() -> int:
    # Windows 控制台 UTF-8 支持
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    # 启用 ANSI 颜色（Windows 10+）
    if sys.platform == "win32":
        os.system("")

    parser = build_parser()
    args = parser.parse_args()

    print(_bold("\n🔍 MinerU 输出格式探针"))
    print("   校验格式规范来源: doc/在线API输出文件格式（SaaS推断版）.md §9\n")

    # 运行校验
    if args.online:
        reports = run_online(args)
    else:
        print(_cyan("模式: 离线（扫描已有 mineru_zips/ 解压目录）"))
        print(_cyan("  如需在线上传测试文件，请加 --online 参数\n"))
        reports = run_offline(args)

    if not reports:
        print(_yellow("\n未找到可检查的数据，退出。"))
        return 0

    # 打印详细报告（verbose 模式或存在偏差时）
    if args.verbose:
        print_full_reports(reports)
    else:
        # 仅打印有偏差的报告
        problem_reports = [r for r in reports if not r.is_clean]
        if problem_reports:
            for r in problem_reports:
                print()
                print(r.to_text_report())

    # 汇总
    print_aggregate_summary(reports)

    # 保存 JSON 报告
    if args.output:
        save_json_report(reports, Path(args.output))

    # 返回退出码
    total_errors = sum(r.error_count for r in reports)
    total_warnings = sum(r.warning_count for r in reports)
    total_infos = sum(r.info_count for r in reports)

    if total_errors > 0:
        return 1
    elif total_warnings > 0:
        return 2
    elif total_infos > 0:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())

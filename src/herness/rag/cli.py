"""RAG 知识库 CLI — 文档入库与社区摘要构建。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from herness.config import get_settings
from herness.middleware.embeddings import build_embedding_client
from herness.middleware.factory import close_middleware, create_middleware
from herness.rag.ingest import build_community_summaries, ingest_file, ingest_text


async def _run_ingest(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.rag_enabled:
        print("RAG_ENABLED=false，请先启用 RAG。", file=sys.stderr)
        return 1

    middleware = await create_middleware(settings)
    try:
        kb = _get_kb(middleware)
        if kb is None:
            print("当前中台不支持 RAG 知识库。", file=sys.stderr)
            return 1

        embedding_client = None
        if settings.rag_vector_enabled:
            embedding_client = build_embedding_client(settings)

        collection_id = args.collection
        collection_name = args.name or collection_id
        persona = args.persona

        if args.file:
            path = Path(args.file)
            if not path.is_file():
                print(f"文件不存在: {path}", file=sys.stderr)
                return 1
            ids = await ingest_file(
                kb,
                path=path,
                collection_id=collection_id,
                collection_name=collection_name,
                settings=settings,
                embedding_client=embedding_client,
                persona=persona,
            )
        elif args.text:
            ids = await ingest_text(
                kb,
                collection_id=collection_id,
                collection_name=collection_name,
                text=args.text,
                source=args.source or "cli",
                settings=settings,
                embedding_client=embedding_client,
                persona=persona,
            )
        else:
            print("请指定 --file 或 --text。", file=sys.stderr)
            return 1

        print(f"已入库 {len(ids)} 个 chunk 到集合「{collection_id}」。")

        if args.build_communities:
            count = await build_community_summaries(kb, collection_id=collection_id)
            print(f"已生成 {count} 个社区摘要。")
        return 0
    finally:
        await close_middleware(middleware)


def _get_kb(middleware: object) -> object | None:
    inner = getattr(middleware, "_inner", middleware)
    return getattr(inner, "knowledge_store", None) or getattr(inner, "_kb_store", None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Herness RAG 知识库入库工具")
    sub = parser.add_subparsers(dest="command")

    ingest = sub.add_parser("ingest", help="导入文档到知识库")
    ingest.add_argument("--collection", default="default", help="集合 ID")
    ingest.add_argument("--name", default="", help="集合显示名")
    ingest.add_argument("--persona", default=None, choices=["consumer", "merchant"])
    ingest.add_argument("--file", default="", help="文本文件路径")
    ingest.add_argument("--text", default="", help="直接传入文本")
    ingest.add_argument("--source", default="", help="来源标识")
    ingest.add_argument(
        "--build-communities",
        action="store_true",
        help="入库后构建社区摘要",
    )

    args = parser.parse_args()
    if args.command != "ingest":
        parser.print_help()
        sys.exit(1)

    sys.exit(asyncio.run(_run_ingest(args)))


if __name__ == "__main__":
    main()

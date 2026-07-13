"""一次性为现有数据库应用全部表/字段注释。"""
from __future__ import annotations

import asyncio
import os
import sys

import asyncpg

from herness.middleware.postgres import PostgresMiddleware
from herness.observability.usage_store import usage_schema_comments_sql


async def main() -> None:
    dsn = os.getenv("POSTGRES_DSN", "postgresql://postgres:root@localhost:5432/herness")
    try:
        conn = await asyncpg.connect(dsn)
    except Exception as exc:
        print(f"连接失败: {exc}")
        sys.exit(1)

    from importlib.resources import files

    middleware_comments = files("herness.middleware").joinpath("schema_comments.sql").read_text(
        encoding="utf-8"
    )
    rag_comments = files("herness.rag.store").joinpath("schema_comments.sql").read_text(
        encoding="utf-8"
    )

    await conn.execute(middleware_comments)
    await conn.execute(usage_schema_comments_sql())
    await conn.execute(rag_comments)

    # 向量列可能尚未创建，单独尝试
    for stmt in (
        "COMMENT ON COLUMN beliefs.fact_embedding IS "
        "'信念语义向量（pgvector，用于 Hereness 相似度检索）'",
        "COMMENT ON COLUMN kb_chunks.embedding IS "
        "'分块语义向量（pgvector，用于 RAG 向量检索）'",
    ):
        try:
            await conn.execute(stmt)
        except asyncpg.UndefinedColumnError:
            print(f"跳过（列不存在）: {stmt[:60]}...")

    rows = await conn.fetch(
        """
        SELECT c.relname AS table_name, count(*) AS comment_count
        FROM pg_description d
        JOIN pg_class c ON c.oid = d.objoid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND d.objsubid = 0
        GROUP BY c.relname
        ORDER BY c.relname
        """
    )
    print("=== 已添加表注释 ===")
    for row in rows:
        print(f"  {row['table_name']}")

    col_rows = await conn.fetch(
        """
        SELECT c.relname AS table_name, count(*) AS comment_count
        FROM pg_description d
        JOIN pg_class c ON c.oid = d.objoid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND d.objsubid > 0
        GROUP BY c.relname
        ORDER BY c.relname
        """
    )
    print("\n=== 字段注释数量 ===")
    for row in col_rows:
        print(f"  {row['table_name']}: {row['comment_count']} 列")

    await conn.close()
    print("\n完成。")


if __name__ == "__main__":
    asyncio.run(main())

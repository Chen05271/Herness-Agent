"""RAG 分块策略测试。"""

from herness.rag.chunker import chunk_text


def test_chunk_empty() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_chunk_short_text_unchanged() -> None:
    text = "短文本不切分。"
    assert chunk_text(text, chunk_size=512) == [text]


def test_chunk_prefers_paragraph_break() -> None:
    para_a = "A" * 200
    para_b = "B" * 200
    text = f"{para_a}\n\n{para_b}"
    chunks = chunk_text(text, chunk_size=250, chunk_overlap=0)
    assert len(chunks) >= 2
    assert chunks[0].endswith("A")
    assert chunks[1].startswith("B")


def test_chunk_prefers_sentence_break() -> None:
    sent_a = "这是第一句。" + "补" * 180
    sent_b = "这是第二句。" + "充" * 180
    text = sent_a + sent_b
    chunks = chunk_text(text, chunk_size=220, chunk_overlap=0)
    assert len(chunks) >= 2
    assert chunks[0].endswith("。")
    assert "第一句" in chunks[0]
    assert "第二句" in chunks[0]


def test_chunk_markdown_sections() -> None:
    text = (
        "# 订单模块\n"
        "OrderService 负责创建与查询订单。\n\n"
        "## 物流接口\n"
        "LogisticsAPI 提供轨迹查询。"
    )
    chunks = chunk_text(text, chunk_size=512)
    assert len(chunks) == 2
    assert chunks[0].startswith("# 订单模块")
    assert "OrderService" in chunks[0]
    assert chunks[1].startswith("## 物流接口")
    assert "LogisticsAPI" in chunks[1]


def test_chunk_overlap_preserved() -> None:
    text = "X" * 300 + "\n\n" + "Y" * 300
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=50)
    assert len(chunks) >= 2
    # 第二块应包含重叠区域的尾部内容
    tail = chunks[0][-30:]
    assert tail in chunks[1]


def test_chunk_hard_cut_when_no_boundary() -> None:
    text = "Z" * 600
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=0)
    assert len(chunks) == 3
    assert all(len(c) <= 200 for c in chunks)

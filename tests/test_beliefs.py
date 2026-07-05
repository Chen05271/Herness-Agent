"""信念库匹配与 Hereness 深度检索单元测试。"""

from herness.middleware.beliefs import (
    classify_claim_status,
    extract_claims_from_text,
    extract_search_terms,
    is_contradiction,
    match_beliefs,
    resolve_belief_write_conflict,
    score_belief_match,
)


def test_match_beliefs_supported_and_unknown() -> None:
    beliefs = [{"fact": "Herness Agent 是多 Agent 框架", "source": "manual"}]
    results = match_beliefs(beliefs, ["Herness Agent", "不存在的声明"])
    assert results[0]["status"] == "supported"
    assert results[1]["status"] == "unknown"


def test_deep_match_fuzzy_terms() -> None:
    """Hereness 深度模式：词项重叠匹配同义表述。"""
    beliefs = [{"fact": "偏好 Python 编程", "source": "dreaming", "confidence": 0.9}]
    results = match_beliefs(beliefs, ["用户喜欢 Python"], deep=True)
    assert results[0]["status"] == "supported"
    assert len(results[0]["matches"]) == 1


def test_deep_match_contradiction() -> None:
    beliefs = [{"fact": "用户不喜欢 Python", "source": "manual", "confidence": 1.0}]
    results = match_beliefs(beliefs, ["用户喜欢 Python"], deep=True)
    assert results[0]["status"] == "contradicted"


def test_score_belief_match_partial_overlap() -> None:
    score = score_belief_match("喜欢 Python 语言", "偏好 Python 编程")
    assert score >= 0.25


def test_is_contradiction_opposite_polarity() -> None:
    assert is_contradiction("用户不喜欢 Java", "用户喜欢 Java")
    assert not is_contradiction("用户喜欢 Java", "用户喜欢 Java")


def test_extract_search_terms_mixed() -> None:
    terms = extract_search_terms("用户偏好 Python 编程")
    assert "python" in terms
    assert any("用户" in t or "偏好" in t or "编程" in t for t in terms)


def test_extract_claims_from_text() -> None:
    claims = extract_claims_from_text("第一句较长的事实描述。第二句也很长需要被提取。")
    assert len(claims) == 2


def test_classify_claim_status_confidence_disambiguation() -> None:
    """高置信度支持信念应覆盖低置信度矛盾信念。"""
    matches = [
        {"fact": "用户不喜欢 Python", "confidence": 0.4, "status": "active"},
        {"fact": "用户偏好 Python 编程", "confidence": 0.9, "status": "active"},
    ]
    assert classify_claim_status("用户喜欢 Python", matches) == "supported"


def test_classify_claim_status_contradiction_wins() -> None:
    matches = [
        {"fact": "用户不喜欢 Python", "confidence": 0.95, "status": "active"},
        {"fact": "用户偏好 Python 编程", "confidence": 0.5, "status": "active"},
    ]
    assert classify_claim_status("用户喜欢 Python", matches) == "contradicted"


def test_classify_claim_status_ignores_superseded() -> None:
    matches = [
        {"fact": "用户不喜欢 Python", "confidence": 1.0, "status": "superseded"},
        {"fact": "用户偏好 Python 编程", "confidence": 0.8, "status": "active"},
    ]
    assert classify_claim_status("用户喜欢 Python", matches) == "supported"


def test_resolve_belief_write_conflict_supersedes_weaker() -> None:
    existing = [{"id": 1, "fact": "用户不喜欢 Python", "confidence": 0.6, "status": "active"}]
    adjusted, status, updates = resolve_belief_write_conflict(
        "用户喜欢 Python",
        0.9,
        existing,
    )
    assert adjusted == 0.9
    assert status == "active"
    assert updates == [{"id": 1, "status": "superseded"}]


def test_resolve_belief_write_conflict_decays_newer() -> None:
    existing = [{"id": 1, "fact": "用户不喜欢 Python", "confidence": 0.9, "status": "active"}]
    adjusted, status, updates = resolve_belief_write_conflict(
        "用户喜欢 Python",
        0.5,
        existing,
        decay_factor=0.5,
        superseded_threshold=0.3,
    )
    assert adjusted == 0.25
    assert status == "superseded"
    assert updates == []


async def test_stub_seed_belief_conflict_supersedes_old() -> None:
    from herness.middleware.stub import InMemoryMiddleware

    mw = InMemoryMiddleware(hereness_enabled=True)
    mw.seed_belief("u1", "用户不喜欢 Python", confidence=0.6)
    mw.seed_belief("u1", "用户喜欢 Python", confidence=0.9)

    results = await mw.query_beliefs("u1", ["用户喜欢 Python"])
    assert results[0]["status"] == "supported"

    beliefs = mw._beliefs["u1"]
    old = next(b for b in beliefs if b["fact"] == "用户不喜欢 Python")
    assert old["status"] == "superseded"

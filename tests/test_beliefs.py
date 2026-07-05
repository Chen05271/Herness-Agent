"""信念库匹配逻辑单元测试。"""

from herness.middleware.beliefs import match_beliefs


def test_match_beliefs_supported_and_unknown() -> None:
    beliefs = [{"fact": "Herness Agent 是多 Agent 框架", "source": "manual"}]
    results = match_beliefs(beliefs, ["Herness Agent", "不存在的声明"])
    assert results[0]["status"] == "supported"
    assert results[1]["status"] == "unknown"

"""persona 工具白名单与身份隔离测试。"""

import pytest

from herness.config import Settings
from herness.models.task import TaskRequest
from herness.personas import (
    PersonaValidationError,
    agent_user_id,
    default_allowed_tools,
    enrich_metadata_with_persona,
    get_persona,
    is_merchant_user_id,
    normalize_session_id,
    prepare_task_request,
    supervisor_domain_block,
    supervisor_persona_block,
    validate_persona_identity,
)


def test_consumer_persona_defaults():
    meta = enrich_metadata_with_persona({})
    assert get_persona(meta) == "consumer"
    assert meta["allowed_tools"] == ["fetch_task_context"]
    assert "admin_get_dashboard" not in meta["allowed_tools"]


def test_consumer_persona_with_domain_integration():
    settings = Settings(agri_commerce_enabled=True)
    meta = enrich_metadata_with_persona({}, settings=settings)
    assert "search_produce" in meta["allowed_tools"]
    assert "admin_get_dashboard" not in meta["allowed_tools"]


def test_merchant_persona_defaults():
    meta = enrich_metadata_with_persona({"persona": "merchant"})
    assert get_persona(meta) == "merchant"
    assert meta["allowed_tools"] == ["fetch_task_context"]
    assert "search_produce" not in meta["allowed_tools"]


def test_merchant_persona_with_domain_integration():
    settings = Settings(agri_commerce_enabled=True)
    meta = enrich_metadata_with_persona({"persona": "merchant"}, settings=settings)
    assert "admin_get_dashboard" in meta["allowed_tools"]
    assert "search_produce" not in meta["allowed_tools"]


def test_supervisor_persona_block_differs():
    assert "管理端" in supervisor_persona_block("merchant")
    assert "用户端" in supervisor_persona_block("consumer")


def test_supervisor_domain_block_empty_when_all_disabled():
    assert supervisor_domain_block(
        Settings(agri_commerce_enabled=False, skills_enabled=False)
    ) == ""


def test_supervisor_domain_block_includes_skills_when_enabled():
    block = supervisor_domain_block(Settings(skills_enabled=True))
    assert "presentation" in block
    assert "ppt-master" in block


def test_supervisor_domain_block_when_enabled():
    block = supervisor_domain_block(Settings(agri_commerce_enabled=True))
    assert "order_ops" in block


def test_is_merchant_user_id():
    assert is_merchant_user_id("merchant:m1:ops:op1")
    assert not is_merchant_user_id("user-123")
    assert not is_merchant_user_id("merchant:m1")


def test_validate_persona_identity():
    validate_persona_identity("user-123", "consumer")
    validate_persona_identity("merchant:m1:ops:op1", "merchant")

    with pytest.raises(PersonaValidationError):
        validate_persona_identity("merchant:m1:ops:op1", "consumer")

    with pytest.raises(PersonaValidationError):
        validate_persona_identity("user-123", "merchant")


def test_normalize_session_id_consumer():
    assert normalize_session_id("consumer", "u1", "") == "consumer-u1"
    assert normalize_session_id("consumer", "u1", "consumer-u1") == "consumer-u1"
    assert normalize_session_id("consumer", "u1", "chat-1") == "consumer-u1:chat-1"

    with pytest.raises(PersonaValidationError):
        normalize_session_id("consumer", "u1", "admin-u1")


def test_normalize_session_id_merchant():
    merchant_id = "merchant:m1:ops:op1"
    assert normalize_session_id("merchant", merchant_id, "") == f"admin-{merchant_id}"
    assert normalize_session_id("merchant", merchant_id, f"admin-{merchant_id}") == f"admin-{merchant_id}"

    with pytest.raises(PersonaValidationError):
        normalize_session_id("merchant", merchant_id, "consumer-u1")


def test_prepare_task_request_consumer():
    prepared = prepare_task_request(
        TaskRequest(user_id="u1", session_id="chat", input="你好")
    )
    assert prepared.session_id == "consumer-u1:chat"
    assert prepared.metadata["persona"] == "consumer"


def test_prepare_task_request_merchant():
    merchant_user = "merchant:m1:ops:op1"
    prepared = prepare_task_request(
        TaskRequest(
            user_id=merchant_user,
            session_id=f"admin-{merchant_user}",
            input="查看待处理订单",
            metadata={"persona": "merchant"},
        )
    )
    assert prepared.session_id == f"admin-{merchant_user}"
    assert prepared.metadata["persona"] == "merchant"
    assert prepared.metadata["allowed_tools"] == ["fetch_task_context"]


def test_agent_user_id():
    assert agent_user_id("consumer", consumer_user_id="u1", merchant_id="m1", operator_id="op1") == "u1"
    assert (
        agent_user_id("merchant", consumer_user_id="u1", merchant_id="m1", operator_id="op1")
        == "merchant:m1:ops:op1"
    )


def test_default_allowed_tools_are_disjoint():
    consumer_tools = set(default_allowed_tools("consumer", domain_tools_enabled=True))
    merchant_tools = set(default_allowed_tools("merchant", domain_tools_enabled=True))
    assert "admin_get_dashboard" not in consumer_tools
    assert "search_produce" not in merchant_tools

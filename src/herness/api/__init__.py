"""HTTP API 层 — FastAPI 入口。

请从 ``herness.api.app`` 直接导入，避免 ``python -m herness.api.app`` 时
eager import 触发 RuntimeWarning。
"""

__all__ = ["app", "create_app"]

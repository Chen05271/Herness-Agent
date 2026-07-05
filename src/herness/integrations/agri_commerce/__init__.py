"""智慧农业电商 BFF 集成 — mock / HTTP 双模式，便于后续接入真实果园 API。"""

from herness.integrations.agri_commerce.factory import build_agri_commerce_client
from herness.integrations.agri_commerce.protocol import AgriCommerceClient, AgriCommerceError

__all__ = [
    "AgriCommerceClient",
    "AgriCommerceError",
    "build_agri_commerce_client",
]

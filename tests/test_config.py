"""配置单例缓存测试。"""

from herness.config import clear_settings_cache, get_settings


def test_get_settings_is_cached() -> None:
    clear_settings_cache()
    first = get_settings()
    second = get_settings()
    assert first is second


def test_clear_settings_cache() -> None:
    first = get_settings()
    clear_settings_cache()
    second = get_settings()
    assert first is not second

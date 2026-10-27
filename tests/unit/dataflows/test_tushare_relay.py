"""Tushare 中转配置回归测试，不访问真实数据源或数据库。"""
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from tradingagents.config.tushare_config import (
    configure_tushare_http_url,
    resolve_tushare_http_url,
)
from tradingagents.dataflows.providers.china import tushare as provider_module


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "env-token")
    monkeypatch.delenv("TUSHARE_HTTP_URL", raising=False)
    monkeypatch.setattr(provider_module, "TUSHARE_AVAILABLE", True)
    instance = provider_module.TushareProvider()
    instance.config = {"token": "env-token"}
    return instance


def test_endpoint_from_environment_and_default(monkeypatch):
    monkeypatch.delenv("TUSHARE_HTTP_URL", raising=False)
    assert resolve_tushare_http_url() == ""
    monkeypatch.setenv("TUSHARE_HTTP_URL", " https://env.example/ ")
    assert resolve_tushare_http_url() == "https://env.example/"


@pytest.mark.parametrize("endpoint", ["relay.example", "ftp://relay.example", "https://"])
def test_invalid_endpoint_rejected(endpoint, monkeypatch):
    monkeypatch.setenv("TUSHARE_HTTP_URL", endpoint)
    with pytest.raises(ValueError, match="HTTP"):
        resolve_tushare_http_url()


def test_default_does_not_override_sdk_url():
    api = SimpleNamespace(_DataApi__http_url="sdk-default")
    configure_tushare_http_url(api, "")
    assert api._DataApi__http_url == "sdk-default"


def test_requests_supports_socks_proxy():
    """检查真实 Requests 传输依赖，不连接代理服务器。"""
    from requests.adapters import HTTPAdapter
    from urllib3.contrib.socks import SOCKSProxyManager

    adapter = HTTPAdapter()
    try:
        manager = adapter.proxy_manager_for("socks5h://127.0.0.1:1080")
        assert isinstance(manager, SOCKSProxyManager)
        assert manager.connection_pool_kw["_socks_options"]["rdns"] is True
    finally:
        adapter.close()


@pytest.mark.parametrize("enabled", [False, True])
def test_proxy_environment_matches_settings(enabled):
    """隔离配置模块的启动副作用，验证 ALL_PROXY 不绕过代理开关。"""
    import os
    import subprocess
    import sys

    proxy_keys = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                  "http_proxy", "https_proxy", "all_proxy")
    env = os.environ.copy()
    env.update({key: "socks5h://127.0.0.1:1080" for key in proxy_keys})
    env["PROXY_ENABLED"] = str(enabled).lower()
    script = """
import os
from app.core.config import settings
from requests.utils import get_environ_proxies
enabled = os.environ['PROXY_ENABLED'] == 'true'
assert settings.PROXY_ENABLED is enabled
proxies = get_environ_proxies('https://relay.example/')
if enabled:
    assert proxies['https'] == 'socks5h://127.0.0.1:1080'
else:
    assert not {'http', 'https', 'all'}.intersection(proxies)
    assert all(key not in os.environ for key in (
        'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
        'http_proxy', 'https_proxy', 'all_proxy'))
"""
    result = subprocess.run([sys.executable, "-c", script], env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_client_reused_and_rebuilt_on_endpoint_change(provider, monkeypatch):
    sdk = Mock()
    sdk.pro_api.side_effect = lambda token: SimpleNamespace(_DataApi__http_url="sdk-default")
    monkeypatch.setattr(provider_module, "ts", sdk)
    monkeypatch.setenv("TUSHARE_HTTP_URL", "https://env.example/")
    assert provider.is_available()
    first = provider.api
    assert first._DataApi__http_url == "https://env.example/"
    assert provider.is_available()
    assert provider.api is first

    monkeypatch.setenv("TUSHARE_HTTP_URL", "https://db.example/")
    assert provider.is_available()
    assert provider.api is not first
    assert provider.api._DataApi__http_url == "https://db.example/"

    monkeypatch.delenv("TUSHARE_HTTP_URL")
    assert provider.is_available()
    assert provider.api._DataApi__http_url == "sdk-default"
    assert sdk.pro_api.call_count == 3


def test_provider_ignores_database_and_cached_config(provider, monkeypatch):
    from app.core import database

    database_access = Mock(side_effect=AssertionError("Tushare 不应读取数据库"))
    monkeypatch.setattr(database, "get_mongo_db_sync", database_access)
    provider.config = {"token": "db-token", "endpoint": "https://db.example/"}
    monkeypatch.setenv("TUSHARE_HTTP_URL", "https://env.example/")
    sdk = Mock()
    monkeypatch.setattr(provider_module, "ts", sdk)
    assert provider.is_available()
    sdk.pro_api.assert_called_once_with("env-token")
    assert provider.api._DataApi__http_url == "https://env.example/"
    assert provider.token_source == "env"
    database_access.assert_not_called()

    # 删除环境配置后，不回退到旧客户端或缓存 Token。
    monkeypatch.delenv("TUSHARE_TOKEN")
    assert not provider.is_available()
    assert provider.api is None
    sdk.pro_api.assert_called_once()



def test_validation_uses_relay(provider, monkeypatch):
    monkeypatch.setenv("TUSHARE_HTTP_URL", "https://relay.example/")
    api = Mock()
    api.trade_cal.side_effect = lambda **kwargs: (
        pd.DataFrame({"ts_code": ["000001.SZ"]})
        if api._DataApi__http_url == "https://relay.example/" else None
    )
    monkeypatch.setattr(provider_module, "ts", SimpleNamespace(pro_api=lambda token: api))
    assert provider.connect_sync()
    api.trade_cal.assert_called_once()


@pytest.mark.asyncio
async def test_pro_bar_uses_configured_client(provider, monkeypatch):
    monkeypatch.setenv("TUSHARE_HTTP_URL", "https://relay.example/")
    sdk = Mock()
    sdk.pro_bar.return_value = pd.DataFrame({
        "trade_date": ["20260105"], "open": [10.0], "high": [11.0],
        "low": [9.0], "close": [10.5], "vol": [100], "amount": [1000],
    })
    monkeypatch.setattr(provider_module, "ts", sdk)
    result = await provider.get_historical_data("000001", "2026-01-05", "2026-01-05")
    assert result is not None
    assert sdk.pro_bar.call_args.kwargs["api"] is provider.api
    assert provider.api._DataApi__http_url == "https://relay.example/"
    assert sdk.pro_bar.call_args.kwargs["adj"] == "qfq"


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["https://db.example/", None])
@pytest.mark.parametrize("submitted_token", ["db-token", "db...token", ""])
async def test_web_connection_uses_environment_only(endpoint, submitted_token, monkeypatch):
    import tushare as ts
    from app.models.config import DataSourceConfig
    from app.services.config_service import ConfigService

    monkeypatch.setenv("TUSHARE_HTTP_URL", "https://env.example/")
    monkeypatch.setenv("TUSHARE_TOKEN", "env-token")
    expected = "https://env.example/"
    api = Mock()

    def trade_cal(**kwargs):
        assert api._DataApi__http_url == expected
        return pd.DataFrame({"cal_date": ["20240101"]})

    api.trade_cal.side_effect = trade_cal
    sdk_factory = Mock(return_value=api)
    monkeypatch.setattr(ts, "pro_api", sdk_factory)
    config = DataSourceConfig(name="tushare", type="tushare", api_key=submitted_token, endpoint=endpoint)
    service = ConfigService()
    from unittest.mock import AsyncMock
    service.get_system_config = AsyncMock(side_effect=AssertionError("不应读取数据库"))
    result = await service.test_data_source_config(config)
    assert result["success"], result
    assert result["details"]["used_env_credentials"] is True
    assert result["details"]["used_db_credentials"] is False
    sdk_factory.assert_called_once_with("env-token")
    service.get_system_config.assert_not_called()


@pytest.mark.asyncio
async def test_financial_requests_reach_relay(provider, monkeypatch):
    import json
    import tushare as ts
    import requests

    monkeypatch.setenv("TUSHARE_HTTP_URL", "https://relay.example/")
    monkeypatch.setattr(provider_module, "ts", ts)
    calls = []

    def post(url, **kwargs):
        payload = kwargs["json"]
        calls.append((url, payload))
        return SimpleNamespace(text=json.dumps({
            "code": 0, "data": {"fields": ["ts_code", "end_date"], "items": [["600000.SH", "20180630"]]}
        }))

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(provider, "_standardize_tushare_financial_data", lambda data, code: data)
    result = await provider.get_financial_data("600000.SH", period="20180630")
    assert result
    assert {p["api_name"] for _, p in calls} >= {"income", "balancesheet", "cashflow", "fina_indicator"}
    for url, payload in calls:
        assert url.startswith("https://relay.example/")
        assert payload["token"] == "env-token"
        assert payload["params"]["ts_code"] == "600000.SH"


def test_validation_does_not_fall_back_to_other_token(provider, monkeypatch):
    provider.config = {"token": "db-token"}
    sdk = Mock()
    sdk.pro_api.return_value.trade_cal.side_effect = ValueError("invalid env-token")
    monkeypatch.setattr(provider_module, "ts", sdk)
    assert not provider.connect_sync()
    sdk.pro_api.assert_called_once_with("env-token")
    assert provider.last_error == "invalid [REDACTED]"


@pytest.mark.asyncio
async def test_test_sources_reports_error_without_touching_shared_provider(monkeypatch):
    from app.routers.multi_source_sync import _test_single_adapter

    isolated = Mock()
    isolated.connect_sync.return_value = False
    isolated.last_error = "Token 校验失败"
    isolated.token_source = None
    monkeypatch.setattr(provider_module, "TushareProvider", lambda: isolated)
    shared = SimpleNamespace(connected=True, api=object())
    adapter = SimpleNamespace(name="tushare", priority=3, _provider=shared)
    result = await _test_single_adapter(adapter)
    assert not result["available"]
    assert "Token 校验失败" in result["message"]
    assert result["test_api"] == "trade_cal"
    assert shared.connected is True


@pytest.mark.asyncio
async def test_web_connection_requires_env_token(monkeypatch):
    import tushare as ts
    from app.models.config import DataSourceConfig
    from app.services.config_service import ConfigService
    from unittest.mock import AsyncMock

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    factory = Mock()
    monkeypatch.setattr(ts, "pro_api", factory)
    service = ConfigService()
    service.get_system_config = AsyncMock(side_effect=AssertionError("不应读取数据库"))
    result = await service.test_data_source_config(DataSourceConfig(
        name="tushare", type="tushare", api_key="db-token", endpoint="https://db.example/"))
    assert not result["success"]
    assert "TUSHARE_TOKEN" in result["message"]
    factory.assert_not_called()
    service.get_system_config.assert_not_called()


def test_config_bridge_preserves_env_tushare_settings(monkeypatch):
    from app.core.config_bridge import _bridge_datasource_details, clear_bridged_config
    from app.models.config import DataSourceConfig

    monkeypatch.setenv("TUSHARE_TOKEN", "env-token")
    monkeypatch.setenv("TUSHARE_HTTP_URL", "https://env.example/")
    monkeypatch.setenv("TUSHARE_TIMEOUT", "42")
    config = DataSourceConfig(name="tushare", type="tushare", api_key="db-token", timeout=99)
    assert _bridge_datasource_details([config]) == 0
    # clear_bridged_config 会修改多个环境变量，在 monkeypatch 上下文中隔离。
    import os
    with monkeypatch.context() as isolated:
        for key, value in os.environ.copy().items():
            isolated.setenv(key, value)
        clear_bridged_config()
        assert os.environ["TUSHARE_TOKEN"] == "env-token"
        assert os.environ["TUSHARE_HTTP_URL"] == "https://env.example/"
        assert os.environ["TUSHARE_TIMEOUT"] == "42"


@pytest.mark.parametrize("enabled,token,expected", [
    ("true", "env-token", True),
    ("false", "env-token", False),
    ("true", "", False),
    ("true", "your-token", False),
])
def test_source_availability_uses_env_config(enabled, token, expected, monkeypatch):
    from app.core import database
    from tradingagents.dataflows.data_source_manager import DataSourceManager, ChinaDataSource

    monkeypatch.setenv("TUSHARE_ENABLED", enabled)
    monkeypatch.setenv("TUSHARE_TOKEN", token)
    db = Mock()
    db.system_configs.find_one.return_value = {
        "data_source_configs": [
            {"type": "tushare", "enabled": False, "api_key": "db-token"},
        ],
    }
    monkeypatch.setattr(database, "get_mongo_db_sync", lambda: db)
    manager = DataSourceManager.__new__(DataSourceManager)
    manager.use_mongodb_cache = False
    assert (ChinaDataSource.TUSHARE in manager._check_available_sources()) is expected

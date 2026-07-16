import httpx

from app.shared.errors import AppError


class ProviderError(AppError):
    pass


def _error(code: str, message: str, status_code: int = 422) -> ProviderError:
    return ProviderError(code=code, message=message, status_code=status_code)


def map_http_error(response: httpx.Response) -> ProviderError:
    mapping = {
        401: ("upstream_auth_failed", "API Key 未通过验证，请检查或重新填写密钥。", 422),
        403: ("upstream_forbidden", "服务拒绝访问，请检查账户权限和模型授权。", 422),
        404: ("upstream_endpoint_not_found", "服务端点不存在，请核对 API 地址；模型也可以手动填写。", 422),
        405: ("upstream_method_not_allowed", "服务端点不接受当前请求，请核对协议类型和 API 地址。", 422),
        429: ("upstream_rate_limited", "服务请求过于频繁，请稍后重试或检查额度。", 429),
    }
    code, message, status = mapping.get(
        response.status_code,
        ("upstream_invalid_response", "服务返回了无法使用的响应，请检查服务状态。", 422),
    )
    return _error(code, message, status)


def map_transport_error(error: Exception) -> ProviderError:
    if isinstance(error, httpx.TimeoutException):
        return _error("upstream_timeout", "连接服务超时，请检查地址、代理或稍后重试。", 504)
    if isinstance(error, httpx.ConnectError) and "SSL" in str(error).upper():
        return _error("upstream_tls_failed", "TLS 连接失败，请检查证书和 API 地址。", 502)
    return _error("upstream_network_failed", "无法连接服务，请检查网络、代理和 API 地址。", 502)


def invalid_response_error() -> ProviderError:
    return _error("upstream_invalid_response", "服务响应格式不正确，请确认所选协议与服务兼容。")


def model_unavailable_error() -> ProviderError:
    return _error("model_unavailable", "模型不可用，请刷新模型列表或选择其他模型。")


def prompt_cache_unsupported_error() -> ProviderError:
    return _error("prompt_cache_unsupported", "当前服务不支持提示词缓存，请关闭缓存后重试。")

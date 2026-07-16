from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from app.providers.schemas import ProviderProtocol


@dataclass(frozen=True)
class ResolvedEndpoints:
    base_url: str
    models_url: str
    inference_url: str


def resolve_endpoints(protocol: ProviderProtocol, entered: str) -> ResolvedEndpoints:
    value = entered.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("API 地址必须使用 http 或 https。")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("API 地址必须包含有效主机，且不能嵌入用户名或密码。")
    if parsed.query or parsed.fragment:
        raise ValueError("API 地址不能包含查询参数或片段。")

    path = parsed.path.rstrip("/")
    if not path.endswith("/v1"):
        path = f"{path}/v1"
    base_url = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    inference_path = "chat/completions" if protocol == "openai_compatible" else "messages"
    return ResolvedEndpoints(
        base_url=base_url,
        models_url=f"{base_url}/models",
        inference_url=f"{base_url}/{inference_path}",
    )

import httpx
import pytest

from app.providers.errors import map_http_error


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "upstream_auth_failed"), (403, "upstream_forbidden"), (404, "upstream_endpoint_not_found"), (405, "upstream_method_not_allowed"), (429, "upstream_rate_limited")],
)
def test_http_status_has_actionable_code(status, code):
    response = httpx.Response(status, request=httpx.Request("GET", "https://x"), text="secret upstream body")
    error = map_http_error(response)
    assert error.code == code
    assert "secret upstream body" not in error.message

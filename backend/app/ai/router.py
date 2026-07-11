from fastapi import APIRouter, Request

from app.ai.schemas import ConnectionTestResult
from app.ai.settings import AISettingsInput, AISettingsResponse

router = APIRouter(prefix="/api/settings/ai", tags=["ai-settings"])


@router.get("", response_model=AISettingsResponse)
def get_ai_settings(request: Request) -> AISettingsResponse:
    return request.app.state.ai_settings_service.get()


@router.put("", response_model=AISettingsResponse)
def save_ai_settings(settings: AISettingsInput, request: Request) -> AISettingsResponse:
    return request.app.state.ai_settings_service.save(settings)


@router.post("/test", response_model=ConnectionTestResult)
async def test_ai_settings(settings: AISettingsInput, request: Request) -> ConnectionTestResult:
    return await request.app.state.ai_settings_service.test(settings)

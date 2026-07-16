from fastapi import APIRouter, Request, Response, status

from app.providers.endpoints import resolve_endpoints
from app.providers.schemas import ModelProfileCreate, ModelProfileRead, ProviderProfileCreate, ProviderProfileRead, ProviderProfileUpdate
from app.system.service import invalidate_setup


router = APIRouter(prefix="/api/providers", tags=["providers"])


def service(request: Request):
    return request.app.state.provider_profile_service


@router.post("/endpoints:preview")
def preview_endpoints(payload: dict) -> dict:
    return resolve_endpoints(payload["protocol"], payload["base_url"]).__dict__


@router.post("", response_model=ProviderProfileRead, status_code=status.HTTP_201_CREATED)
def create_provider(payload: ProviderProfileCreate, request: Request):
    created = service(request).create(payload)
    invalidate_setup(request.app.state.paths.data)
    return created


@router.get("", response_model=list[ProviderProfileRead])
def list_providers(request: Request):
    return service(request).list()


@router.get("/{profile_id}", response_model=ProviderProfileRead)
def get_provider(profile_id: str, request: Request):
    return service(request).get(profile_id)


@router.patch("/{profile_id}", response_model=ProviderProfileRead)
def update_provider(profile_id: str, payload: ProviderProfileUpdate, request: Request):
    updated = service(request).update(profile_id, payload)
    invalidate_setup(request.app.state.paths.data)
    return updated


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(profile_id: str, request: Request):
    service(request).delete(profile_id)
    invalidate_setup(request.app.state.paths.data)
    return Response(status_code=204)


@router.get("/{profile_id}/models", response_model=list[ModelProfileRead])
def list_models(profile_id: str, request: Request):
    return service(request).list_models(profile_id)


@router.post("/{profile_id}/models", response_model=ModelProfileRead, status_code=status.HTTP_201_CREATED)
def add_model(profile_id: str, payload: ModelProfileCreate, request: Request):
    return service(request).add_model(profile_id, payload)


@router.post("/{profile_id}/models:refresh", response_model=list[ModelProfileRead])
async def refresh_models(profile_id: str, request: Request, force: bool = False):
    return await service(request).refresh_models(profile_id, force)


@router.post("/{profile_id}/models/{model_profile_id}:probe", response_model=ModelProfileRead)
async def probe(profile_id: str, model_profile_id: str, request: Request):
    return await service(request).probe(profile_id, model_profile_id)


@router.post("/{profile_id}:enable", response_model=ProviderProfileRead)
def enable(profile_id: str, request: Request):
    enabled = service(request).enable(profile_id)
    invalidate_setup(request.app.state.paths.data)
    return enabled


@router.post("/{profile_id}:disable", response_model=ProviderProfileRead)
def disable(profile_id: str, request: Request):
    disabled = service(request).disable(profile_id)
    invalidate_setup(request.app.state.paths.data)
    return disabled


@router.post("/{profile_id}:default", response_model=ProviderProfileRead)
def set_default(profile_id: str, request: Request):
    selected = service(request).set_default(profile_id)
    invalidate_setup(request.app.state.paths.data)
    return selected

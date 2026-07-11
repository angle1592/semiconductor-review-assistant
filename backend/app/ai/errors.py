from app.shared.errors import AppError


class AIProviderError(AppError):
    pass


class AINotConfiguredError(AIProviderError):
    def __init__(self, message: str = "The selected AI provider is not configured."):
        super().__init__(code="AI_NOT_CONFIGURED", message=message, status_code=422)


class UpstreamAuthFailedError(AIProviderError):
    def __init__(self):
        super().__init__(
            code="UPSTREAM_AUTH_FAILED",
            message="The AI provider rejected the configured credentials.",
            status_code=401,
        )


class UpstreamTimeoutError(AIProviderError):
    def __init__(self):
        super().__init__(
            code="UPSTREAM_TIMEOUT", message="The AI provider timed out.", status_code=504
        )


class InvalidModelOutputError(AIProviderError):
    def __init__(self):
        super().__init__(
            code="INVALID_MODEL_OUTPUT",
            message="The AI provider returned an invalid structured result.",
            status_code=502,
        )


class VisionRequiredError(AIProviderError):
    def __init__(self):
        super().__init__(
            code="VISION_REQUIRED",
            message="The selected provider is not configured for image input.",
            status_code=422,
        )


class ProviderUnavailableError(AIProviderError):
    def __init__(self, message: str = "The selected AI provider is unavailable."):
        super().__init__(code="PROVIDER_UNAVAILABLE", message=message, status_code=503)


class UpstreamProviderError(AIProviderError):
    def __init__(self, message: str = "The AI provider request failed."):
        super().__init__(code="UPSTREAM_ERROR", message=message, status_code=502)

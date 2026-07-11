from app.shared.errors import AppError


class UnsupportedDocumentTypeError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="UNSUPPORTED_DOCUMENT_TYPE",
            message="Only PDF, PPT, and PPTX documents are supported.",
            status_code=422,
        )


class EmptyDocumentError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="EMPTY_DOCUMENT",
            message="The uploaded document is empty.",
            status_code=422,
        )


class InvalidDocumentError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="INVALID_DOCUMENT",
            message="The uploaded document could not be read.",
            status_code=422,
        )


class PowerPointUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="POWERPOINT_UNAVAILABLE",
            message="Microsoft PowerPoint is unavailable; convert the presentation to PDF first.",
            status_code=503,
        )

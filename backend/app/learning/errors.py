from app.shared.errors import AppError


class SourceSelectionRequiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="SOURCE_SELECTION_REQUIRED",
            message="Select at least one page or Notebook import.",
            status_code=422,
        )


class SourceCourseMismatchError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="SOURCE_COURSE_MISMATCH",
            message="Every selected source must belong to the lesson course.",
            status_code=422,
        )


class VisionUnsupportedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="VISION_UNSUPPORTED",
            message="The selected provider cannot process lesson page images.",
            status_code=422,
        )


class ProviderUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="AI_PROVIDER_UNAVAILABLE",
            message="No AI provider is configured.",
            status_code=503,
        )


class GenerationFailedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="GENERATION_FAILED",
            message="Learning-item generation failed.",
            status_code=502,
        )


class QuestionNotInSessionError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="QUESTION_NOT_IN_SESSION",
            message="The question does not belong to this review session.",
            status_code=422,
        )


class AnswerAlreadyRecordedError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="ANSWER_ALREADY_RECORDED",
            message="This question already has an attempt in the review session.",
            status_code=409,
        )

class InvalidSelfRatingError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="INVALID_SELF_RATING",
            message="Answered questions require a supported self rating.",
            status_code=422,
        )


class ReviewSessionExpiredError(AppError):
    def __init__(self) -> None:
        super().__init__(
            code="REVIEW_SESSION_EXPIRED",
            message="The 15-minute review window has ended.",
            status_code=409,
        )

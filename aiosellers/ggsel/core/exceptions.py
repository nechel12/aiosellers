from ...core.exceptions import AiosellersError, AuthError, TransientError
from ...core.exceptions import RateLimitedError as CommonRateLimitedError


class GGselError(AiosellersError):
    pass


class RequestFailedError(GGselError):
    pass


class RateLimitedError(CommonRateLimitedError, RequestFailedError):
    pass


class TransientRequestError(TransientError, RequestFailedError):
    pass


class UnauthorizedError(AuthError, GGselError):
    pass


class ApiError(RequestFailedError):
    """GGsel returned a non-negative HTTP status with a negative retval."""

    def __init__(self, message: str, retval: int | None = None) -> None:
        super().__init__(message)
        self.retval = retval

class GGselError(Exception):
    pass


class RequestFailedError(GGselError):
    pass


class RateLimitedError(RequestFailedError):
    pass


class UnauthorizedError(GGselError):
    pass


class ApiError(RequestFailedError):
    """GGsel returned a non-negative HTTP status with a negative retval."""

    def __init__(self, message: str, retval: int | None = None) -> None:
        super().__init__(message)
        self.retval = retval

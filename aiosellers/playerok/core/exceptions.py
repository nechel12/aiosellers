from ...core.exceptions import AiosellersError, AuthError, TransientError
from ...core.exceptions import RateLimitedError as CommonRateLimitedError


class CloudflareDetected(AiosellersError):
    pass


class RequestFailedError(AiosellersError):
    pass


class RateLimitedError(CommonRateLimitedError, RequestFailedError):
    pass


class TransientRequestError(TransientError, RequestFailedError):
    pass


class Unauthorized(AuthError):
    pass


class DownloadTooLargeError(RequestFailedError):
    """The attachment exceeded the configured byte limit."""


class GraphQLError(AiosellersError):
    pass


class PersistedQueryExpired(GraphQLError):
    """Playerok rejected a stored query hash, so the frontend contract has changed."""


class UnsupportedPaymentProvider(Exception):
    pass


class MessageNotDeliveredError(Exception):
    pass

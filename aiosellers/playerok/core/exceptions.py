class CloudflareDetected(Exception):
    pass


class RequestFailedError(Exception):
    pass


class RateLimitedError(RequestFailedError):
    pass


class Unauthorized(Exception):
    pass


class GraphQLError(Exception):
    pass


class PersistedQueryExpired(GraphQLError):
    """Playerok rejected a stored query hash, so the frontend contract has changed."""


class UnsupportedPaymentProvider(Exception):
    pass


class MessageNotDeliveredError(Exception):
    pass

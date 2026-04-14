class CamcommandError(Exception):
    """Base exception for camcommand."""


class DiscoveryError(CamcommandError):
    """Raised when device discovery fails."""


class ConnectionError(CamcommandError):
    """Raised when serial connection cannot be established or is lost."""


class ProtocolError(CamcommandError):
    """Raised for malformed commands/responses."""

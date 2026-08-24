"""Connector failures with explicit model/runner/environment provenance."""

from harness import faults


class ConnectorError(Exception):
    """Base for connector configuration and availability errors."""


class ConnectorConfigError(ConnectorError, ValueError):
    """A checked-in connector declaration is incomplete or unsafe."""


class ConnectorUnavailable(ConnectorError):
    """A connector cannot start on this host or is not authorized yet."""


class CatalogDrift(ConnectorUnavailable):
    """The live provider schema no longer matches the reviewed binding."""


class ProviderRejected(faults.ModelInputFault):
    """The provider rejected arguments the model can correct."""


class ProviderEnvironmentFault(faults.EnvironmentFault):
    """Authentication, transport, rate-limit, or provider infrastructure failed."""


class AmbiguousWrite(ProviderEnvironmentFault):
    """A mutating request may have reached the provider; never retry blindly."""

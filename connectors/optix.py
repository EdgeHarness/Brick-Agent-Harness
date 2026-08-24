"""Direct Optix GraphQL transport for fixed, reviewed operation documents."""
from collections import deque
import threading
import time

import requests

from harness.privacy import redact, redact_text

from .errors import AmbiguousWrite, ProviderEnvironmentFault, ProviderRejected


OPTIX_RATE_LIMIT = 60
OPTIX_RATE_WINDOW_SECONDS = 60.0
_MODEL_ERROR_CODES = frozenset(
    ("BAD_USER_INPUT", "GRAPHQL_VALIDATION_FAILED", "VALIDATION_ERROR")
)
INTROSPECTION_DOCUMENT = """query BrickConnectorSchema {
  __schema {
    queryType { name }
    mutationType { name }
    types {
      kind
      name
      enumValues { name }
      inputFields {
        name
        defaultValue
        type {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
                ofType { kind name }
              }
            }
          }
        }
      }
      fields {
        name
        args {
          name
          defaultValue
          type {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
                ofType {
                  kind
                  name
                  ofType { kind name }
                }
              }
            }
          }
        }
        type {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
                ofType { kind name }
              }
            }
          }
        }
      }
    }
  }
}"""


class RateLimiter:
    def __init__(
        self,
        limit=OPTIX_RATE_LIMIT,
        window=OPTIX_RATE_WINDOW_SECONDS,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        self.limit = limit
        self.window = float(window)
        self.clock = clock
        self.sleep = sleep
        self.calls = deque()
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = self.clock()
            while self.calls and now - self.calls[0] >= self.window:
                self.calls.popleft()
            if len(self.calls) >= self.limit:
                wait = self.window - (now - self.calls[0])
                if wait > 0:
                    self.sleep(wait)
                    now = self.clock()
                    while self.calls and now - self.calls[0] >= self.window:
                        self.calls.popleft()
            self.calls.append(self.clock())


class OptixGraphQLClient:
    def __init__(
        self,
        *,
        endpoint,
        token,
        session=None,
        limiter=None,
        sleep=time.sleep,
        timeout=30.0,
    ):
        if not isinstance(token, str) or not token:
            raise ProviderEnvironmentFault("Optix credential is unavailable")
        self.endpoint = endpoint
        self.token = token
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.limiter = limiter or RateLimiter(sleep=sleep)
        self.sleep = sleep
        self.timeout = timeout
        self.closed = False

    def _post(
        self, document, variables, *, mutating, safe_retry,
        error_origin="environment",
    ):
        if error_origin not in ("model", "environment"):
            raise ValueError("Optix error origin must be model or environment")
        attempts = 2 if safe_retry and not mutating else 1
        for index in range(attempts):
            self.limiter.acquire()
            response = None
            try:
                response = self.session.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                        "User-Agent": "brick-agent-harness/connector-1",
                    },
                    json={"query": document, "variables": variables or {}},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if mutating:
                    raise AmbiguousWrite(
                        "Optix write outcome is unknown; reconcile before another write"
                    ) from exc
                if index + 1 < attempts:
                    continue
                raise ProviderEnvironmentFault("Optix transport failed") from exc

            if response.status_code == 429:
                if index + 1 < attempts:
                    try:
                        delay = min(max(float(response.headers.get("Retry-After", "1")), 0), 10)
                    except ValueError:
                        delay = 1
                    self.sleep(delay)
                    continue
                raise ProviderEnvironmentFault("Optix rate limit was reached")
            if response.status_code in (401, 403):
                raise ProviderEnvironmentFault("Optix authorization was rejected")
            if response.status_code >= 500:
                if mutating:
                    raise AmbiguousWrite(
                        "Optix write outcome is unknown; reconcile before another write"
                    )
                if index + 1 < attempts:
                    continue
                raise ProviderEnvironmentFault("Optix service failed")
            if response.status_code >= 400:
                raise ProviderEnvironmentFault(
                    f"Optix returned HTTP {response.status_code}"
                )
            try:
                payload = response.json()
            except ValueError as exc:
                if mutating:
                    raise AmbiguousWrite(
                        "Optix write returned an unusable response; reconcile before another write"
                    ) from exc
                raise ProviderEnvironmentFault("Optix returned invalid JSON") from exc
            if not isinstance(payload, dict):
                raise ProviderEnvironmentFault("Optix returned an invalid GraphQL envelope")
            errors = payload.get("errors") or []
            if errors:
                messages = []
                model_error = True
                for item in errors:
                    if not isinstance(item, dict):
                        model_error = False
                        continue
                    messages.append(redact_text(item.get("message", "Optix rejected the request")))
                    code = ((item.get("extensions") or {}).get("code"))
                    if code not in _MODEL_ERROR_CODES:
                        model_error = False
                message = "; ".join(messages) or "Optix rejected the request"
                if error_origin == "model" and model_error:
                    raise ProviderRejected(message)
                raise ProviderEnvironmentFault(message)
            if "data" not in payload:
                raise ProviderEnvironmentFault("Optix GraphQL response omitted data")
            return redact(payload["data"])
        raise ProviderEnvironmentFault("Optix request did not complete")

    def catalog(self):
        data = self._post(
            INTROSPECTION_DOCUMENT, {}, mutating=False, safe_retry=True,
            error_origin="environment",
        )
        schema = data.get("__schema") if isinstance(data, dict) else None
        if not isinstance(schema, dict):
            raise ProviderEnvironmentFault("Optix schema introspection was unavailable")
        return schema

    def call(
        self,
        operation,
        arguments,
        *,
        document,
        mutating=False,
        safe_retry=False,
        error_origin="environment",
    ):
        del operation  # operation is bound for audit, not model-controlled
        return self._post(
            document,
            arguments,
            mutating=bool(mutating),
            safe_retry=bool(safe_retry),
            error_origin=error_origin,
        )

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.session.close()

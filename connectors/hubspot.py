"""Official HubSpot remote-MCP transport, kept optional and out of bench."""
import contextlib
import json
import queue
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from harness.privacy import redact, redact_text

from .errors import ConnectorUnavailable, ProviderEnvironmentFault, ProviderRejected


HUBSPOT_MCP_ENDPOINT = "https://mcp.hubspot.com/"
HUBSPOT_CALLBACK_PORT = 8765
HUBSPOT_CALLBACK_PATH = "/oauth/callback"


def _require_sdk():
    if sys.version_info < (3, 10):
        raise ConnectorUnavailable("HubSpot MCP requires Python 3.10 or newer")
    try:
        import anyio
        import httpx2
        from anyio.from_thread import start_blocking_portal
        from mcp import ClientSession
        from mcp.client.auth import OAuthClientProvider
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared.auth import OAuthClientMetadata
        from mcp.types import PaginatedRequestParams
    except ImportError as exc:
        raise ConnectorUnavailable(
            "HubSpot MCP requires the optional connectors dependencies"
        ) from exc
    return {
        "anyio": anyio,
        "httpx2": httpx2,
        "start_blocking_portal": start_blocking_portal,
        "ClientSession": ClientSession,
        "OAuthClientProvider": OAuthClientProvider,
        "streamable_http_client": streamable_http_client,
        "OAuthClientMetadata": OAuthClientMetadata,
        "PaginatedRequestParams": PaginatedRequestParams,
    }


class HubSpotTokenStorage:
    """MCP SDK TokenStorage implementation backed by the OS keyring."""

    def __init__(self, secrets, account_alias):
        self.secrets = secrets
        self.account_alias = account_alias

    async def get_tokens(self):
        value = self.secrets.get_json("hubspot", self.account_alias, "oauth_tokens")
        if value is None:
            return None
        try:
            from mcp.shared.auth import OAuthToken
            value = dict(value)
            expires_at = value.pop("_brick_expires_at", None)
            token = OAuthToken.model_validate(value)
            # The SDK does not reconstruct its in-memory expiry clock after a
            # process restart.  Return an empty access token for an expired
            # stored grant so its normal refresh-token path is selected rather
            # than replaying a stale bearer token until the server rejects it.
            if expires_at is not None and float(expires_at) <= time.time():
                token.access_token = ""
                token.expires_in = 0
            return token
        except Exception as exc:
            raise ConnectorUnavailable("stored HubSpot OAuth token is invalid") from exc

    async def set_tokens(self, tokens):
        value = tokens.model_dump(mode="json", exclude_none=True)
        if tokens.expires_in is not None:
            value["_brick_expires_at"] = time.time() + max(
                0, int(tokens.expires_in)
            )
        self.secrets.set_json(
            "hubspot", self.account_alias, "oauth_tokens",
            value,
        )

    async def get_client_info(self):
        value = self.secrets.get_json("hubspot", self.account_alias, "oauth_client")
        if value is None:
            return None
        try:
            from mcp.shared.auth import OAuthClientInformationFull
            return OAuthClientInformationFull.model_validate(value)
        except Exception as exc:
            raise ConnectorUnavailable("stored HubSpot OAuth client is invalid") from exc

    async def set_client_info(self, client_info):
        self.secrets.set_json(
            "hubspot", self.account_alias, "oauth_client",
            client_info.model_dump(mode="json", exclude_none=True),
        )


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/oauth/callback":
            self.send_error(404)
            return
        values = {key: items[-1] for key, items in parse_qs(parsed.query).items()}
        self.server.results.put(values)
        body = b"Brick connector authorization received. You may close this window."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


class LoopbackOAuthCallback:
    def __init__(
        self, interactive=False, timeout=300, port=HUBSPOT_CALLBACK_PORT
    ):
        self.interactive = bool(interactive)
        self.timeout = timeout
        self.port = int(port)
        self.results = None
        self.server = None
        self.expected_state = None
        self.redirect_uri = (
            f"http://127.0.0.1:{self.port}{HUBSPOT_CALLBACK_PATH}"
        )

    def _start_server(self):
        if self.server is not None:
            return
        try:
            self.results = queue.Queue(maxsize=1)
            self.server = HTTPServer(
                ("127.0.0.1", self.port), _OAuthCallbackHandler
            )
        except OSError as exc:
            raise ConnectorUnavailable(
                f"HubSpot OAuth callback port {self.port} is unavailable"
            ) from exc
        self.server.results = self.results
        self.server.timeout = self.timeout

    async def redirect(self, authorization_url):
        if not self.interactive:
            raise ConnectorUnavailable(
                "HubSpot OAuth is not authorized; run the connector authorize command first"
            )
        state = parse_qs(urlparse(str(authorization_url)).query).get("state", [])
        if len(state) != 1 or not state[0]:
            raise ConnectorUnavailable(
                "HubSpot OAuth authorization URL did not include one state value"
            )
        self.expected_state = state[0]
        # Bind the loopback listener before opening the browser. A browser with
        # an existing HubSpot session may redirect immediately.
        self._start_server()
        if not webbrowser.open(str(authorization_url)):
            self.close()
            raise ConnectorUnavailable("could not open the HubSpot authorization browser")

    async def callback(self):
        sdk = _require_sdk()

        def wait_for_one():
            self._start_server()
            self.server.handle_request()
            try:
                return self.results.get_nowait()
            except queue.Empty as exc:
                raise ConnectorUnavailable("HubSpot OAuth callback timed out") from exc

        values = await sdk["anyio"].to_thread.run_sync(wait_for_one)
        if values.get("error"):
            raise ConnectorUnavailable(
                "HubSpot OAuth was rejected: " + redact_text(values["error"])
            )
        code = values.get("code")
        if not code:
            raise ConnectorUnavailable("HubSpot OAuth callback did not include a code")
        if (
            not self.expected_state
            or values.get("state") != self.expected_state
        ):
            raise ConnectorUnavailable("HubSpot OAuth callback state mismatch")
        from mcp.shared.auth import AuthorizationCodeResult
        return AuthorizationCodeResult(
            code=code, state=values.get("state"), iss=values.get("iss")
        )

    def close(self):
        if self.server is not None:
            self.server.server_close()
            self.server = None


def store_client_credentials(
    secrets,
    account_alias,
    *,
    client_id,
    client_secret,
    redirect_uri=None,
    token_endpoint_auth_method="client_secret_post",
):
    """Store one HubSpot MCP auth-app identity without exposing it to argv."""
    _require_sdk()
    if not isinstance(client_id, str) or not client_id.strip():
        raise ValueError("HubSpot client ID must be nonempty")
    if not isinstance(client_secret, str) or not client_secret:
        raise ValueError("HubSpot client secret must be nonempty")
    if token_endpoint_auth_method not in (
        "client_secret_post", "client_secret_basic"
    ):
        raise ValueError("unsupported HubSpot token authentication method")
    redirect_uri = redirect_uri or (
        f"http://127.0.0.1:{HUBSPOT_CALLBACK_PORT}{HUBSPOT_CALLBACK_PATH}"
    )
    from mcp.shared.auth import OAuthClientInformationFull
    client = OAuthClientInformationFull(
        client_id=client_id.strip(),
        client_secret=client_secret,
        redirect_uris=[redirect_uri],
        token_endpoint_auth_method=token_endpoint_auth_method,
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        application_type="native",
        client_name="Brick Agent Harness",
    )
    secrets.set_json(
        "hubspot",
        account_alias,
        "oauth_client",
        client.model_dump(mode="json", exclude_none=True),
    )
    return redirect_uri


def validate_stored_scope(secrets, account_alias, required_scope):
    """Require the post-auth/refresh token to include every reviewed scope."""
    if required_scope in (None, ""):
        return True
    token = secrets.get_json("hubspot", account_alias, "oauth_tokens")
    if not isinstance(token, dict):
        raise ProviderEnvironmentFault("HubSpot OAuth token is unavailable")
    actual = set(str(token.get("scope") or "").split())
    required = set(str(required_scope).split())
    missing = required - actual
    if missing:
        raise ProviderEnvironmentFault(
            "HubSpot authorization is missing reviewed scopes: "
            + ", ".join(sorted(missing))
        )
    return True


class HubSpotMCPClient:
    """Synchronous facade over one persistent official MCP SDK session."""

    def __init__(
        self,
        *,
        account_alias,
        secrets,
        endpoint=HUBSPOT_MCP_ENDPOINT,
        oauth_scope=None,
        interactive_auth=False,
        callback=None,
    ):
        if endpoint != HUBSPOT_MCP_ENDPOINT:
            raise ConnectorUnavailable("HubSpot must use its official MCP endpoint")
        self.account_alias = account_alias
        self.endpoint = endpoint
        self.oauth_scope = oauth_scope
        self.secrets = secrets
        self.callback = callback or LoopbackOAuthCallback(interactive_auth)
        self._sdk = _require_sdk()
        self._portal_cm = None
        self._portal = None
        self._stack = None
        self._session = None
        self._closed = False
        self._lock = threading.RLock()
        try:
            self._portal_cm = self._sdk["start_blocking_portal"](
                name="brick-hubspot-mcp"
            )
            self._portal = self._portal_cm.__enter__()
            self._portal.call(self._connect)
            validate_stored_scope(
                self.secrets, self.account_alias, self.oauth_scope
            )
        except BaseException:
            self.close()
            raise

    async def _connect(self):
        sdk = self._sdk
        self._stack = contextlib.AsyncExitStack()
        metadata = sdk["OAuthClientMetadata"](
            client_name="Brick Agent Harness",
            redirect_uris=[self.callback.redirect_uri],
            scope=self.oauth_scope,
        )
        auth = sdk["OAuthClientProvider"](
            self.endpoint,
            metadata,
            HubSpotTokenStorage(self.secrets, self.account_alias),
            redirect_handler=self.callback.redirect,
            callback_handler=self.callback.callback,
        )
        http = sdk["httpx2"].AsyncClient(
            auth=auth,
            follow_redirects=True,
            trust_env=False,
            timeout=120.0,
            headers={"User-Agent": "brick-agent-harness/connector-1"},
        )
        http = await self._stack.enter_async_context(http)
        streams = await self._stack.enter_async_context(
            sdk["streamable_http_client"](
                self.endpoint, http_client=http, terminate_on_close=True
            )
        )
        self._session = sdk["ClientSession"](
            streams[0], streams[1], read_timeout_seconds=120.0
        )
        self._session = await self._stack.enter_async_context(self._session)
        await self._session.initialize()

    async def _list_tools(self):
        tools = []
        cursor = None
        while True:
            params = (
                self._sdk["PaginatedRequestParams"](cursor=cursor)
                if cursor
                else None
            )
            page = await self._session.list_tools(params=params)
            tools.extend(page.tools)
            cursor = page.next_cursor
            if not cursor:
                return tools

    def catalog(self):
        with self._lock:
            if self._closed:
                raise ConnectorUnavailable("HubSpot MCP client is closed")
            try:
                tools = self._portal.call(self._list_tools)
            except ConnectorUnavailable:
                raise
            except Exception as exc:
                raise ProviderEnvironmentFault("HubSpot MCP discovery failed") from exc
        return {
            tool.name: {
                "description": tool.description or "",
                "input_schema": tool.input_schema,
            }
            for tool in tools
        }

    async def _call_tool(self, operation, arguments):
        return await self._session.call_tool(operation, arguments=arguments)

    def call(self, operation, arguments, *, error_origin="environment"):
        with self._lock:
            if self._closed:
                raise ConnectorUnavailable("HubSpot MCP client is closed")
            try:
                result = self._portal.call(self._call_tool, operation, arguments)
            except ConnectorUnavailable:
                raise
            except Exception as exc:
                raise ProviderEnvironmentFault("HubSpot MCP call failed") from exc
        texts = []
        for block in result.content:
            if getattr(block, "type", None) == "text":
                texts.append(getattr(block, "text", ""))
            else:
                texts.append(f"[MCP content block: {getattr(block, 'type', 'unknown')}]")
        payload = {
            "data": redact(result.structured_content),
            "message": redact_text("\n".join(texts) or "(no content)"),
        }
        if result.is_error:
            message = payload["message"] or "HubSpot rejected the operation"
            if error_origin == "model":
                raise ProviderRejected(message)
            raise ProviderEnvironmentFault(message)
        return payload

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self._portal is not None and self._stack is not None:
                self._portal.call(self._stack.aclose)
        finally:
            try:
                if self._portal_cm is not None:
                    self._portal_cm.__exit__(None, None, None)
            finally:
                self.callback.close()

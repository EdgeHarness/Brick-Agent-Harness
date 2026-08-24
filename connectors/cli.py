"""Operator-only setup and score-free discovery for Brick connectors."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys

from . import config
from .credentials import KeyringSecretStore
from .errors import ConnectorError
from .hubspot import (
    HUBSPOT_MCP_ENDPOINT,
    HubSpotMCPClient,
    store_client_credentials,
)
from .optix import OptixGraphQLClient
from .runtime import discovery_record, validate_reviewed_bindings


OPTIX_GRAPHQL_ENDPOINT = "https://api.optixapp.com/graphql"


def _nonempty_prompt(label, *, secret=False):
    reader = getpass.getpass if secret else input
    value = reader(label).strip()
    if not value:
        raise ValueError(f"{label.rstrip(': ')} must be nonempty")
    return value


def _identity(secrets, provider, account):
    value = secrets.get(provider, account, "account_identity")
    if value is None:
        raise ValueError(
            f"{provider} account identity is not configured for alias {account!r}"
        )
    return value


def _write_record(record, output):
    encoded = (
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    if output is None:
        sys.stdout.write(encoded)
        return
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    print(f"wrote secret-free discovery record: {target}")


def _configure_hubspot(args, secrets):
    identity = _nonempty_prompt("HubSpot portal/account identifier: ")
    client_id = _nonempty_prompt("HubSpot MCP auth-app client ID: ")
    client_secret = _nonempty_prompt("HubSpot MCP auth-app client secret: ", secret=True)
    redirect = store_client_credentials(
        secrets,
        args.account,
        client_id=client_id,
        client_secret=client_secret,
        token_endpoint_auth_method=args.token_auth_method,
    )
    secrets.set("hubspot", args.account, "account_identity", identity)
    print("HubSpot credentials were stored in the OS keyring.")
    print(f"The auth app redirect URL must be exactly: {redirect}")


def _configure_optix(args, secrets):
    identity = _nonempty_prompt("Optix organization/account identifier: ")
    token = _nonempty_prompt("Optix API token: ", secret=True)
    secrets.set("optix", args.account, "account_identity", identity)
    secrets.set("optix", args.account, "api_token", token)
    print("Optix credentials were stored in the OS keyring.")


def _authorize_hubspot(args, secrets):
    _identity(secrets, "hubspot", args.account)
    client = HubSpotMCPClient(
        account_alias=args.account,
        secrets=secrets,
        interactive_auth=True,
    )
    try:
        count = len(client.catalog())
    finally:
        client.close()
    print(f"HubSpot OAuth completed and exposed {count} tools for review.")


def _discover(args, secrets):
    identity = _identity(secrets, args.provider, args.account)
    if args.provider == "hubspot":
        client = HubSpotMCPClient(
            account_alias=args.account,
            secrets=secrets,
            endpoint=HUBSPOT_MCP_ENDPOINT,
            interactive_auth=False,
        )
        endpoint = HUBSPOT_MCP_ENDPOINT
    else:
        token = secrets.get("optix", args.account, "api_token")
        if token is None:
            raise ValueError("Optix API token is not configured")
        endpoint = OPTIX_GRAPHQL_ENDPOINT
        client = OptixGraphQLClient(endpoint=endpoint, token=token)
    try:
        catalog = client.catalog()
    finally:
        client.close()
    _write_record(
        discovery_record(
            args.provider, args.account, identity, catalog, endpoint
        ),
        args.output,
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Configure and inspect Brick's fixed business connectors."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list declared connectors and binding status")
    setup = sub.add_parser("setup", help="print setup requirements")
    setup.add_argument("provider", choices=("hubspot", "optix"))
    sub.add_parser("validate", help="validate declarations and provider bindings")

    hubspot = sub.add_parser(
        "configure-hubspot", help="store HubSpot app credentials in the OS keyring"
    )
    hubspot.add_argument("--account", required=True)
    hubspot.add_argument(
        "--token-auth-method",
        choices=("client_secret_post", "client_secret_basic"),
        default="client_secret_post",
    )
    optix = sub.add_parser(
        "configure-optix", help="store an Optix token in the OS keyring"
    )
    optix.add_argument("--account", required=True)
    authorize = sub.add_parser(
        "authorize-hubspot", help="run HubSpot OAuth 2.1 with PKCE"
    )
    authorize.add_argument("--account", required=True)
    discover = sub.add_parser(
        "discover", help="write a secret-free authenticated catalog for review"
    )
    discover.add_argument("--provider", required=True, choices=("hubspot", "optix"))
    discover.add_argument("--account", required=True)
    discover.add_argument("--output")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            for name, summary, status in config.available():
                print(f"{name:<10} {status:<7} {summary}")
            return 0
        if args.command == "setup":
            print(config.setup_notes(args.provider))
            return 0
        if args.command == "validate":
            declarations, bindings = validate_reviewed_bindings()
            print(
                "connector declarations and bindings are valid: "
                + config.digest(
                    {"declarations": declarations, "bindings": bindings}
                )
            )
            return 0
        secrets = KeyringSecretStore()
        if args.command == "configure-hubspot":
            _configure_hubspot(args, secrets)
        elif args.command == "configure-optix":
            _configure_optix(args, secrets)
        elif args.command == "authorize-hubspot":
            _authorize_hubspot(args, secrets)
        elif args.command == "discover":
            _discover(args, secrets)
        return 0
    except (ConnectorError, ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())

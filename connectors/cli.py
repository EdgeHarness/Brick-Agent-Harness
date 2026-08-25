"""Operator-only setup and score-free discovery for Brick connectors."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import tempfile

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
from harness.privacy import redact


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
    client_id = _nonempty_prompt("HubSpot MCP auth-app client ID: ")
    client_secret = _nonempty_prompt("HubSpot MCP auth-app client secret: ", secret=True)
    redirect = store_client_credentials(
        secrets,
        args.account,
        client_id=client_id,
        client_secret=client_secret,
        token_endpoint_auth_method=args.token_auth_method,
    )
    # A newly configured OAuth client cannot inherit a previous grant or its
    # verified portal binding.  Leaving either behind could make the UI report
    # "ready" before this app has authorized the reviewed account.
    for key in ("oauth_tokens", "account_identity", "account_profile"):
        secrets.delete("hubspot", args.account, key)
    print("HubSpot app credentials were stored in the OS keyring.")
    print(f"The auth app redirect URL must be exactly: {redirect}")


def _configure_optix(args, secrets):
    identity = _nonempty_prompt("Optix organization/account identifier: ")
    token = _nonempty_prompt("Optix API token: ", secret=True)
    secrets.set("optix", args.account, "account_identity", identity)
    secrets.set("optix", args.account, "api_token", token)
    print("Optix credentials were stored in the OS keyring.")


def _named_values(value, names):
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in names and item not in (None, "", [], {}):
                found.append(item)
            found.extend(_named_values(item, names))
    elif isinstance(value, list):
        for item in value:
            found.extend(_named_values(item, names))
    return found


def _one_profile_value(data, names, label, *, required=False):
    values = []
    for value in _named_values(data, set(names)):
        text = str(value)
        if text not in values:
            values.append(text)
    if len(values) > 1:
        raise ValueError(f"get_user_details returned ambiguous {label}")
    if not values:
        if required:
            raise ValueError(f"get_user_details did not return {label}")
        return None
    return values[0]


def hubspot_user_profile(payload):
    """Extract only unambiguous identity fields from get_user_details data."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ValueError("get_user_details returned no structured account data")
    portal_id = _one_profile_value(
        data,
        ("portalId", "portal_id", "hubId", "hub_id", "accountId", "account_id"),
        "portal ID",
        required=True,
    )
    user_email = _one_profile_value(
        data, ("userEmail", "user_email", "email"), "authenticated user email",
        required=True,
    )
    accessible = _named_values(
        data,
        {
            "accessibleObjects", "accessible_objects", "availableObjects",
            "available_objects", "objectDataAvailability",
        },
    )
    return redact(
        {
            "account_identity": portal_id,
            "portal_id": portal_id,
            "account_name": _one_profile_value(
                data, ("accountName", "account_name", "portalName", "portal_name"),
                "account name",
            ),
            "user_id": _one_profile_value(
                data, ("userId", "user_id"), "authenticated user ID"
            ),
            "user_name": _one_profile_value(
                data, ("userName", "user_name", "fullName", "full_name"),
                "authenticated user name",
            ),
            "user_email": user_email,
            "owner_id": _one_profile_value(
                data, ("ownerId", "owner_id"), "owner ID"
            ),
            "accessible_objects": accessible[0] if len(accessible) == 1 else accessible,
        }
    )


def _authorize_hubspot(args, secrets):
    if secrets.get_json("hubspot", args.account, "oauth_client") is None:
        raise ValueError("configure the HubSpot auth app before authorizing")
    client = HubSpotMCPClient(
        account_alias=args.account,
        secrets=secrets,
        interactive_auth=True,
    )
    try:
        catalog = client.catalog()
        if "get_user_details" not in catalog:
            raise ValueError("HubSpot did not expose get_user_details")
        profile = hubspot_user_profile(
            client.call("get_user_details", {}, error_origin="environment")
        )
    finally:
        client.close()
    print("HubSpot authorization returned:")
    print(f"  account: {profile.get('account_name') or '(name unavailable)'}")
    print(f"  portal ID: {profile['portal_id']}")
    print(
        "  user: "
        + (profile.get("user_name") or "(name unavailable)")
        + f" <{profile['user_email']}>"
    )
    print(f"  accessible objects: {profile.get('accessible_objects') or '(not reported)'}")
    answer = input("Store this verified account binding? Type yes to confirm: ").strip()
    if answer.casefold() != "yes":
        for key in ("oauth_tokens", "account_identity", "account_profile"):
            secrets.delete("hubspot", args.account, key)
        raise ValueError("HubSpot authorization was not confirmed; grant discarded")
    secrets.set(
        "hubspot", args.account, "account_identity", profile["account_identity"]
    )
    secrets.set_json("hubspot", args.account, "account_profile", profile)
    print(
        f"HubSpot account verified and {len(catalog)} provider tools are available for review."
    )


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


def _install_bindings(args, secrets):
    source = Path(args.input).resolve()
    declarations = config.load_declarations()
    document = config.load_bindings(source, declarations)
    hubspot = document["providers"]["hubspot"]
    if hubspot["status"] == "bound" and config.binding_status(
        "hubspot", hubspot, secrets
    ) != "ready":
        raise ValueError(
            "reviewed HubSpot binding does not match the authorized keyring account"
        )
    target = Path(config.local_bindings_path()).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=target.parent, delete=False
    ) as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"installed reviewed connector bindings: {target}")


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
    install = sub.add_parser(
        "install-bindings",
        help="validate and install a reviewed secret-free binding outside Git",
    )
    install.add_argument("--input", required=True)
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
        elif args.command == "install-bindings":
            _install_bindings(args, secrets)
        return 0
    except (ConnectorError, ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())

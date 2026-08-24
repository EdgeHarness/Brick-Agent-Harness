# HubSpot and Optix connectors

This package gives Brick one fixed tool surface for business systems. It is
separate from `bench/`: benchmark protocols, graders, evidence, and frozen
result roots never import it.

The checked-in provider bindings are deliberately `unbound`. No real account is
reachable until an operator completes authenticated sandbox discovery, reviews
the exact provider operations, commits their schema digests, and restarts Brick.

## Architecture

```text
local model -> Brick ToolRegistry -> fixed Brick tool -> provider adapter
                                                    |-> HubSpot official MCP
                                                    `-> Optix fixed GraphQL
```

The model sees short names such as `hs_find_contact` and
`optix_room_availability`. It never sees HubSpot's full dynamic catalog or a
free-form GraphQL query parameter.

- `connectors.json` declares the stable model-facing names, flat parameter
  schemas, examples, their exact normalized schema digests, effects, allowed
  modes, retry rules, and rate-limit bucket.
- `bindings.json` binds an authenticated account, catalog digest, live identity
  probe, exact provider operation, argument conversion, and result projection.
- `runtime.py` compares the live account and catalog with those bindings before
  exposing any tool. It checks the catalog again immediately before a write.
- `ledger.py` records only minimal write status and hashed object identifiers in
  an append-only file outside the repository. It atomically blocks replay after
  a prepared, completed, or uncertain non-idempotent write.

Every unknown mode, field, operation, account, schema, or catalog change fails
closed. A run may expose at most 8 external tools and 25 tools total.

## Install

Brick core continues to support Python 3.9. Normalized business connectors
require Python 3.10 or newer:

```powershell
python -m pip install -r requirements-connectors.txt
python -m connectors.cli validate
python -m connectors.cli list
```

Credentials are prompted on the terminal and stored through the operating
system keyring. There is intentionally no `--token` or `--client-secret` flag.

## HubSpot sandbox setup

HubSpot documents its CRM MCP endpoint at `https://mcp.hubspot.com/`, using
Streamable HTTP and OAuth with required PKCE:
<https://developers.hubspot.com/docs/apps/developer-platform/build-apps/integrate-with-the-remote-hubspot-mcp-server>

1. Create an MCP auth app in a HubSpot developer or sandbox portal.
2. Register this exact redirect URL:
   `http://127.0.0.1:8765/oauth/callback`.
3. Store the app credentials and operator-selected portal identifier:

   ```powershell
   python -m connectors.cli configure-hubspot --account sandbox
   ```

4. Complete OAuth 2.1/PKCE:

   ```powershell
   python -m connectors.cli authorize-hubspot --account sandbox
   ```

5. Capture a secret-free authenticated catalog:

   ```powershell
   python -m connectors.cli discover --provider hubspot --account sandbox `
     --output C:\safe-review\hubspot-discovery.json
   ```

Do not infer tool names from this repository. Review the discovered catalog and
bind only operations actually present for the selected portal and permissions.
The first release excludes mail sending, conversation replies, marketing
actions, deletes, merges, owner changes, bulk edits, and cross-portal tools.

## Optix sandbox setup

Optix documents a token-authenticated GraphQL API and a two-step booking flow:
`bookingsDraft` validates and returns a booking session, while
`bookingsCommit` saves the booking using the reviewed inputs.

- <https://developer.optixapp.com/using-the-api/>
- <https://developer.optixapp.com/using-the-api/api-example-bookings/>
- <https://developer.optixapp.com/using-the-api/api-throttling/>

The adapter uses only fixed reviewed documents and enforces Optix's documented
60 requests per minute per token. It sends the token only as a Bearer header.

1. Confirm that Brix's plan includes developer API access and create a sandbox
   app in Optix.
2. Store the token and operator-selected organization identifier:

   ```powershell
   python -m connectors.cli configure-optix --account sandbox
   ```

3. Capture the authenticated schema:

   ```powershell
   python -m connectors.cli discover --provider optix --account sandbox `
     --output C:\safe-review\optix-discovery.json
   ```

4. Build the fixed query documents in GraphQL Playground, review them, and bind
   their exact SHA-256 digests. Keep every document narrow. The model never
   supplies a document.

Optix tokens can expire. Webhook-based token rotation is deliberately deferred;
the operator replaces the keyring value in this first interactive release.
Browser automation is not a fallback when developer API access is unavailable.

## Binding review

`bindings.json` stays unbound until the discovery record has been reviewed. A
bound provider must include:

- one account alias and hash of the independently verified account identifier;
- the full authenticated catalog hash;
- a read-only identity operation that returns exactly `account_identity`;
- only provider operations proved by discovery;
- an argument map and any explicit `iso8601_to_unix` conversions;
- a narrow result projection;
- an exact provider schema or GraphQL document digest;
- an optional read-back operation for a write.

Run `python -m connectors.cli validate` after every edit. Runtime discovery must
match the committed digests byte for byte. A HubSpot tool-list change or Optix
schema change blocks the connector until it is reviewed and rebound.

HubSpot argument-map destinations are provider argument names. Optix
destinations are restricted JSON pointers into the fixed GraphQL variables
object, for example `/input/bookings/0/resource_id`. They cannot overlap, index
unbounded lists, refer to variables absent from the document, or expose a query
document through model arguments. Read and verification bindings must be
GraphQL queries; introspection and mutations are rejected there.

Discovery output contains no credential, but it can describe a tenant-specific
catalog. Keep the review file outside Git and commit only the reviewed digests,
operation documents, and account fingerprint in `bindings.json`.

## Modes and privacy

- `read_only`: only declared reads.
- `draft`: reads plus confirmed non-transmitting external writes. Any operation
  declared to notify or invite is absent, regardless of configuration.
- `live`: reviewed writes are available, but each call still requires explicit
  operator confirmation showing provider, account alias, target, date/time, and
  notification/invitation classification.

Real-account runs use empty run-only memory and do not save their task,
transcript, tool observations, or answer into normal logs or chat history. The
operation ledger keeps only time, provider, operation, status, and hashed object
identifier. Their workspace and generated artifacts are also run-only and are
removed when the command ends. Secrets never enter prompts, tool docs, browser
events, transcripts, or repository files.

Inference remains local. A provider tool call necessarily sends the requested
business fields to HubSpot or Optix. This is not an offline-data claim.

## Run

After bindings are reviewed:

```powershell
# Show the exact normalized tools without model inference
python agents\8b\run_agent.py --connector hubspot --connector-mode read_only `
  --connector-list

# Run with one bound account
python agents\8b\run_agent.py --connector hubspot --connector-mode read_only `
  "Find the lead and summarize recent activity"
```

Use the Agent Lab real-accounts panel for the same flow. Unbound providers are
visible but disabled.

## Rollout gates

1. Authenticated read-only sandbox discovery and binding review.
2. Read-only lead, member, room, and availability workflows.
3. Confirmed sandbox booking draft and local follow-up drafting.
4. One confirmed internal HubSpot note and one confirmed Optix booking, each
   read back exactly once.
5. Brix approval, then production read-only access.
6. Enable each production write separately after workflow and notification
   review.

Webhooks, scheduled automation, onboarding account creation, outbound messages,
marketing, deletes, billing, browser automation, tenant switching, and unattended
writes remain out of scope.

If a write times out, Brick never retries it blindly. A separately reviewed
read-back binding may close the operation only when it can verify the same
request from the original arguments. Otherwise the operation remains `unknown`
and replay-blocked for manual reconciliation.

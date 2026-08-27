# HubSpot and Optix connectors

This package gives Brick one fixed tool surface for business systems. It is
separate from `bench/`: benchmark protocols, graders, evidence, and frozen
result roots never import it.

The checked-in provider bindings are deliberately `unbound`. No real account is
reachable until an operator completes authenticated sandbox discovery, reviews
the exact provider operations, and installs a secret-free binding in the
operator-local configuration directory.

For the exact HubSpot pilot status, changed files, takeover procedure, fictional
records, and acceptance checklist, start with
[`HUBSPOT_PILOT_HANDOFF.md`](HUBSPOT_PILOT_HANDOFF.md).

## Architecture

```text
local model -> Brick ToolRegistry -> fixed Brick tool -> provider adapter
                                                    |-> HubSpot official MCP
                                                    `-> Optix fixed GraphQL
```

The Brix lead workflow exposes exactly `hs_find_contact`, `hs_get_contact`,
`hs_recent_activity`, and `hs_my_open_followups`. All four are reads. The model
never sees HubSpot's full dynamic catalog, provider operation names, object
types, property lists, filters, owner identifiers, or limits. Optix similarly
never exposes a free-form GraphQL query parameter.

- `connectors.json` declares the stable model-facing names, flat parameter
  schemas, examples, their exact normalized schema digests, effects, allowed
  modes, retry rules, and rate-limit bucket.
- `bindings.json` is the checked-in unbound fallback. A reviewed local binding
  pins the authenticated account, full catalog digest, live identity probe,
  exact provider operations, fixed literals, nested argument destinations,
  deterministic conversions, and narrow result projections.
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

## HubSpot developer-account setup

HubSpot documents its CRM MCP endpoint at `https://mcp.hubspot.com/`, using
Streamable HTTP and OAuth with required PKCE:
<https://developers.hubspot.com/docs/apps/developer-platform/build-apps/integrate-with-the-remote-hubspot-mcp-server>

1. Create a free standard HubSpot account. Under **Development > Testing > Test
   Accounts**, create the developer test account that will hold only fictional
   records. Under **Development > MCP Auth Apps**, create the auth app that Brick
   will use, then select the developer test account during OAuth.
2. Register these redirect URLs in the auth app:
   - `http://localhost:6274/oauth/callback/debug` for MCP Inspector;
   - `http://127.0.0.1:8766/oauth/callback` for Brick.
3. Store only the app client credentials:

   ```powershell
   python -m connectors.cli configure-hubspot --account sandbox
   ```

4. Complete OAuth 2.1/PKCE:

   ```powershell
   python -m connectors.cli authorize-hubspot --account sandbox
   ```

   Brick calls `get_user_details`, shows the sanitized portal and user identity,
   and stores the portal binding only after the operator types `yes`.

5. Independently connect MCP Inspector to `https://mcp.hubspot.com/`, list the
   catalog, and call only `get_user_details`. Confirm it is the same developer
   test portal.

6. Capture a secret-free authenticated catalog outside Git:

   ```powershell
   python -m connectors.cli discover --provider hubspot --account sandbox `
     --output C:\safe-review\hubspot-discovery.json
   ```

Do not infer provider input or result schemas from this repository. Review the
discovered catalog and bind only operations actually present for the selected
portal and permissions. The only permitted provider operation names are
`get_user_details`, `search_crm_objects`, `get_crm_objects`, and, when owner
resolution requires it, `search_owners`. The first release rejects
`manage_crm_objects`, conversation search, mail sending, conversation replies,
marketing actions, deletes, merges, owner changes, bulk edits, and cross-portal
tools.

7. Build a reviewed binding from the discovered schemas, then install it:

   ```powershell
   python -m connectors.cli install-bindings `
     --input C:\safe-review\reviewed-bindings.json
   ```

   The command validates the document and authenticated account before
   atomically installing it under `%LOCALAPPDATA%\BrickAgentHarness\connectors`.

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

The checked-in `bindings.json` stays unbound. A reviewed operator-local provider
binding must include:

- one account alias and hash of the independently verified account identifier;
- the full authenticated catalog hash;
- a read-only identity operation that returns exactly `account_identity`;
- only provider operations proved by discovery;
- fixed provider literals for object types, properties, filters, sorts, and
  limits;
- JSON-pointer argument destinations and only named deterministic conversions;
- a narrow result projection;
- an exact provider schema or GraphQL document digest;
- an optional read-back operation for a write.

Run `python -m connectors.cli validate` after every edit. Runtime discovery must
match the installed binding digests byte for byte. A HubSpot tool-list change or
Optix schema change blocks the connector until it is reviewed and rebound.

HubSpot and Optix argument destinations are restricted JSON pointers. For
example, `/filters/2/value` can receive an operator-supplied due date after a
reviewed conversion while the filter property and operator remain fixed.
Destinations cannot overwrite fixed literals, overlap, index unbounded lists,
refer to variables absent from an Optix document, or expose a query document
through model arguments. Read and verification bindings must be GraphQL queries;
introspection and mutations are rejected there.

Discovery output contains no credential, but it can describe a tenant-specific
catalog. Keep discovery and account-specific reviewed bindings outside Git.
Only provider-neutral declarations and fictional fixture expectations belong in
the repository.

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
visible but disabled. The panel distinguishes `unbound`, `authorization
required`, `account mismatch`, and `ready`. Choose the
`brix_hubspot_leads` domain for the Brix lead workflow. Its answer is displayed
in the current run only and must end with `Draft, not sent`.

## Rollout gates

1. Authenticated HubSpot developer-account discovery and binding review.
2. Find Dana, read her record and activities, and list only her open owned
   follow-up from the fictional fixture.
3. Produce a screen-only draft and prove HubSpot state did not change.
4. Restart Brick and repeat a read using the stored grant.
5. Obtain Brix approval, map Brix's actual lead objects and properties, and make
   a separately reviewed read-only Brix binding.

HubSpot writes and outbound messages are not part of this release. Optix write
gates remain separate from the Brix HubSpot lead pilot.

Webhooks, scheduled automation, onboarding account creation, outbound messages,
marketing, deletes, billing, browser automation, tenant switching, and unattended
writes remain out of scope.

If a write times out, Brick never retries it blindly. A separately reviewed
read-back binding may close the operation only when it can verify the same
request from the original arguments. Otherwise the operation remains `unknown`
and replay-blocked for manual reconciliation.

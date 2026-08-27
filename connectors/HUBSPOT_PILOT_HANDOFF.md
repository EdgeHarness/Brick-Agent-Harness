# HubSpot read-only pilot handoff

Last updated: 26 August 2026

This is the teammate handoff for the Brix lead-follow-up pilot. It describes
what is already implemented, what has been tested without HubSpot, and the exact
work that still requires a HubSpot developer account.

## Current status

- Branch: `feature/hubspot-mcp-pilot`
- Connector implementation commit: `47b0577`
- Generic connector foundation commit: `5c0fa03`
- Checked-in HubSpot status: `unbound`
- Operator-local reviewed binding: not installed on the implementation machine
- Authenticated HubSpot developer-account test: not run
- HubSpot writes, outbound email, webhooks, Optix workflow work, production Brix
  access, and benchmark changes: not included

Use the status words precisely: the connector is **implemented** and
**offline-tested**. It is not yet **integrated**, because no authenticated
HubSpot call has passed the developer-account acceptance gate.

## Implemented behavior

The model sees exactly four stable Brick tools:

| Brick tool | Purpose | Maximum returned |
|---|---|---:|
| `hs_find_contact(query)` | Find contacts by a name or email fragment | 5 contacts |
| `hs_get_contact(contact_id)` | Read one HubSpot-returned contact ID | 1 contact |
| `hs_recent_activity(contact_id)` | Read recent calls, emails, meetings, notes, and tasks | 10 activities |
| `hs_my_open_followups(due_before)` | Read incomplete tasks owned by the authenticated user | 10 tasks |

All four are reads in every mode. There is no HubSpot provider operation that
can create, update, send, delete, merge, or assign anything.

Provider details are hidden behind Brick's fixed interface. Model arguments
cannot select HubSpot object types, properties, filter operators, owner IDs,
limits, or provider operation names. A reviewed binding must fix those values
after authenticated discovery.

## Important files

| File | Responsibility |
|---|---|
| `connectors/connectors.json` | Four public tool declarations and safety classifications |
| `connectors/bindings.json` | Safe checked-in fallback; both providers remain unbound |
| `connectors/config.py` | Strict binding-v2 validation and operator-local binding path |
| `connectors/hubspot.py` | Official remote MCP transport and OAuth/PKCE callback on port 8766 |
| `connectors/cli.py` | Credential setup, authorization, discovery, and binding installation |
| `connectors/runtime.py` | Provider allowlist, account/catalog checks, fixed calls, and normalized results |
| `domains/brix_hubspot_leads/` | Brix lead-review prompt rules with no synthetic CRM implementation |
| `connectors/fixtures/brix_hubspot_leads.json` | Secret-free fictional records to create in the developer account |
| `webui/server.py` and `webui/static/app.js` | Agent Lab status, inspection, privacy disclosure, and disabled-until-ready controls |

## Security and privacy boundary

- HubSpot uses only its official remote MCP endpoint:
  `https://mcp.hubspot.com/`.
- Client credentials, OAuth tokens, refresh tokens, and verified account identity
  stay in Windows Credential Manager.
- Credentials are not accepted in command arguments and must not be committed.
- The operator chooses and confirms the account. The model cannot switch it.
- The full provider catalog is never exposed to the model.
- Only `get_user_details`, `search_crm_objects`, `get_crm_objects`, and the
  optional `search_owners` lookup can be bound.
- A catalog, schema, or account mismatch disables the connector.
- Connector runs cannot be attached to persistent Agent Lab chat history.
- Model inference stays local, but requested CRM data is exchanged with HubSpot.

## Developer-account procedure

1. Create a free standard HubSpot account.
2. Under **Development > Testing > Test Accounts**, create a developer test
   account containing fictional data only.
3. Under **Development > MCP Auth Apps**, create an auth app and register:
   - `http://localhost:6274/oauth/callback/debug`
   - `http://127.0.0.1:8766/oauth/callback`
4. Use MCP Inspector with Streamable HTTP at `https://mcp.hubspot.com/`. List
   tools and call only `get_user_details`. Confirm the selected test portal.
5. Install connector dependencies and configure Brick:

   ```powershell
   python -m pip install -r requirements-connectors.txt
   python -m connectors.cli configure-hubspot --account sandbox
   python -m connectors.cli authorize-hubspot --account sandbox
   ```

6. Capture discovery outside Git:

   ```powershell
   python -m connectors.cli discover --provider hubspot --account sandbox `
     --output C:\safe-review\hubspot-discovery.json
   ```

7. Review the exact discovered schemas. Build a binding-v2 document containing
   only the required fixed reads, catalog digest, schema digests, narrow result
   projections, and the verified account fingerprint.
8. Install that reviewed document outside Git:

   ```powershell
   python -m connectors.cli install-bindings `
     --input C:\safe-review\reviewed-bindings.json
   python -m connectors.cli list
   ```

The final command must report HubSpot as `ready`. Do not edit the checked-in
`connectors/bindings.json` with an account-specific binding.

## Fictional test data

Create the records described in `connectors/fixtures/brix_hubspot_leads.json`
through HubSpot's interface. Use the generated HubSpot IDs only during the live
test; do not add them to Git.

The required markers are:

- Dana Reed: open lead, test-user owned, interested in a four-person office.
- Evan Park: open lead with a later follow-up.
- Morgan Lee: customer record that must not be treated as an open lead.
- One incomplete Dana task due on the fixture date.
- One completed Dana task that must not appear as open.
- One Dana note saying she asked about a tour.
- One unrelated activity on Evan.

## Acceptance checklist

Run these checks only after HubSpot reports `ready`:

```powershell
python agents\8b\run_agent.py --connector hubspot `
  --connector-mode read_only --connector-list
```

It must list exactly four reads and zero writes. Then run the Agent Lab domain
`brix_hubspot_leads` with this prompt:

```text
Find Dana Reed in HubSpot, summarize her recent activity,
identify the next follow-up, and draft a concise reply.
Do not change HubSpot or send anything.
```

Acceptance requires all of the following:

- Dana is found without including Morgan or Evan's unrelated activity.
- The seeded note and incomplete owned task appear in the correct order.
- The completed task does not appear as open.
- The answer uses `Lead summary`, `HubSpot evidence`, `Recommended next step`,
  and `Draft, not sent`.
- No name, date, availability, ownership, or communication is invented.
- Contact modification times, activity counts, task counts, and message counts
  are identical before and after the run.
- Brick is restarted and a second read succeeds without entering credentials
  again.

If activity access is missing, stop and record the permission result. HubSpot
blocks activities through MCP when Sensitive Data is enabled; do not work around
that with a write tool, browser automation, or guessed API calls.

## Offline validation already completed

- Full repository suite: 1,284 passed and 4 skipped.
- Final connector, Agent Lab, and Brix-domain suite: 103 passed.
- Connector declaration and unbound binding validation: passed.
- Python compilation: passed.
- Rendered desktop Agent Lab check: no console, page, or request errors.
- No files under `bench/`, result roots, graders, or evidence were changed.

The existing Agent Lab shell still exceeds a 390-pixel mobile viewport. That is
not caused by the connector and is not part of the HubSpot acceptance gate.

## References

- HubSpot remote MCP:
  <https://developers.hubspot.com/docs/apps/developer-platform/build-apps/integrate-with-the-remote-hubspot-mcp-server>
- HubSpot developer test accounts:
  <https://developers.hubspot.com/docs/getting-started/account-types>

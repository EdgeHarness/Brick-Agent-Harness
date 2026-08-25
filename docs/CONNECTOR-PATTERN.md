# Writing a connector

What building the first one taught us. `mcp/ADDING-A-CONNECTOR.md` covers
registering a third-party server in this repository; this covers writing a
server of our own, which is a different job with different traps.

The worked example is `ms365-mcp`, a sibling checkout, fourteen tools, built
2026-08-24 to 25. Everything below is something that actually happened, not
something that might.

## The one decision that shapes every other

**How many tools?**

Decide this before writing any of them, because the tool list is the product.
An 8B model at 8k context carries the entire list in its system prompt, so
each addition costs accuracy on every task rather than only the tasks that use
it. Past roughly twenty-five tools a small model starts choosing at random.

The reference Microsoft 365 server generates 326 tools from the Graph OpenAPI
spec. That is the right answer for a frontier model and the wrong one here.
We wrote fourteen by hand and enforced a ceiling of twenty with a test, so the
budget is a property of the codebase rather than an intention.

The corollary: **no OpenAPI codegen.** A generator cannot decide what to leave
out, and leaving things out is the entire design.

## Order of work, and why

1. **Scaffold, licence, CI, secret scan.** Before any auth code exists. A
   pre-commit hook scanning staged diffs for credential-shaped strings costs
   an hour and means committing one takes deliberate effort rather than a slip.
2. **Speak the protocol.** Server, stdio transport, and a `--list-tools`
   self-check that needs no account. That flag is worth more than it looks: it
   answers "what would a host be offered?" before anything is wired up, and it
   stays useful forever.
3. **Declare the whole surface, with stub handlers.** Names, descriptions,
   parameter schemas and effect annotations, all fourteen, all returning "not
   implemented". Review it as one table. This is the expensive thing to change
   later, because a host may already have classified these and a model may
   already have been prompted against them.
4. **Sign in.** The riskiest step and the first that needs a real account.
5. **One HTTP client, one error shape.** No retries yet.
6. **Implement, one area at a time**, behind the fixed surface.
7. **Resilience.** Retries, backoff, breaker. Late, deliberately: a retry
   policy tangled into the transport is one nobody can test.
8. **Wire it to the host and run it.** Not last because it is least important.
   Last because it is the step that finds what the others missed.

Steps 3 and 8 are the two most people skip. Both earned their place here.

## Design rules that transfer

**Draft-first.** Exactly one tool may reach another person. It takes the id of
something that already exists rather than a recipient, so a model that
invented an address cannot use it, and a person or host had the chance to look
at the thing first. Put it in its own module, alone. That is what makes a test
in the write module asserting "this file contains no send path" mean anything.

**Every tool declares its own effect.** `readOnlyHint` and `destructiveHint`
on all of them. We ask this of third-party servers, so we meet it. The payoff
is visible: the harness classifies all fourteen as `declared` with zero
registry overrides, which is the standard, and no other connector reaches it.

**Descriptions are written for a small model.** Each says what the tool does
and, where it is easy to get wrong, what to do instead. They are not salvaged
from API metadata. A description is the cheapest place to prevent a failure:
`resolve_person` exists entirely because a small model asked to mail "Sarah"
invents an address with total confidence, and its description and its returned
text both say, in words, not to.

**Shape the response, always.** One HTML email is forty thousand characters
against a window of eight thousand tokens shared with the whole tool surface.
Ask the API to convert server side if it can. Trim from the middle, since the
middle of a long message is quoted history and both ends are what a person
would have read. Cap lists. Put the id on every line that names a thing,
because the id is what the next call needs.

**Say when you truncated.** Silent truncation reads to a model as "that was
everything". And ask the API for one more item than you will show, or you
cannot tell a full page from a complete answer.

**Errors are written for the model.** One line, carrying the status, the
provider's code, and a remedy in plain English. A 404 should say "that id does
not exist, list first and use an id from the list", because inventing an id is
the failure a small model actually produces.

## Traps, all of which cost real time

**The SDK blanks an exception's message.** Any ordinary exception raised by a
handler becomes "Error executing tool X", so the server cannot leak internals.
Every actionable sentence we had written was being discarded. Raise the SDK's
`ToolError` instead, which is its deliberate-failure channel and keeps its
text while still flagging the result as an error. **Only running it through a
host revealed this.**

**A dict cannot hold two headers of the same name.** Asking for a plain text
body and a named timezone in one request silently dropped one of them. The
request succeeded and the answer was the wrong shape.

**Timezones.** Most calendar APIs answer in UTC unless a header names a zone.
A small model does not notice a one hour offset. It books the meeting at the
wrong hour and nobody finds out until the meeting. Name the zone on every line.

**Pagination is a correctness issue, not a performance one.** A free-time
search that reads one page reports a busy slot as free, and that answer feeds
a tool that mails invitations to real people.

**Namespace collisions with the host.** This repository has a local package
called `mcp/` and the official SDK on PyPI is also `mcp`. Installing a server
into the host's virtualenv shadows the host's own package. Run the server
under its own interpreter. The process boundary is the point of MCP anyway,
and it means the server's language is not the host's problem.

**Read the SDK, do not assume it.** Model attributes were snake_case while the
wire format was camelCase, so reading the documented spelling returned None
for every tool and silently classified the whole server as writes. And a
handler taking only `**kwargs` made the SDK advertise one required string
called "kwargs" as the entire schema.

## What testing actually has to cover

Assert the **request**, not only the returned text. A handler that fetches
every field of every record is the failure this whole approach exists to
avoid, and only a request assertion catches it.

Make the fake behave like the real API, especially about paging. Every fake we
wrote first returned the whole list regardless of `$top`, which made the
truncation branches unreachable in production and passing in the suite. Four
tests proved nothing until the fake started paging.

And run the thing. Five separate bugs on this project were invisible to code
reading and obvious on the first real run. That is not a coincidence about
these five; it is what the class of bug is.

## The next connector

Copy `ms365-mcp` and delete. The scaffold, the CI, the secret hook, the
declarative tool table, the session, the handler registry, the shaping helpers
and the retry module are all domain-free. What is domain-specific is the tool
table and one module per area.

Candidates, in the order they would pay off:

| connector | why | the hard part |
|---|---|---|
| GitHub | read-heavy, has a natural draft equivalent in an unposted comment, token auth with no OAuth dance | the API is enormous, so the twenty-tool budget is the whole design problem |
| Local documents | the office domain is the one this harness benchmarks against | hard rule 9 forbids general filesystem capability, so it has to be a narrow, rooted, read-mostly surface, and that is a rule change to discuss first |
| Slack | drafts map cleanly, and the read surface is genuinely useful | it is a firehose, so retrieval and trimming matter more than anywhere else |
| Notion or Obsidian | matches how this user already works | Obsidian is local files, so the same hard rule 9 question applies |

Whichever comes next, decide the tool count first.

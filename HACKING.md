# Hacking on Pinser

This document is for contributors and implementers.

## Goals

- Recreate the documented user experience of Claude Code through independent implementation.
- Use independently written architecture documentation as the basis for the rewrite rather than copying source code.
- Prefer stable, public, and user-controlled interfaces where possible.
- Make internal API support optional, explicit, and clearly labeled.
- Offer workarounds when internal-only features are unavailable.
- Keep the implementation understandable, hackable, and easy to audit.

## Non-goals

- Shipping proprietary Anthropic code.
- Copying leaked source code into this repository.
- Pretending undocumented or internal endpoints are official or stable.
- Making internal integrations the default path when a public or local substitute is viable.

## Clean-room approach

Pinser is intended as a clean-room implementation. In this project, that means:

- the implementation is written from independently produced architecture documentation generated from analysis of the leaked Claude Code source code
- the repository does not include leaked source code
- contributors should not paste proprietary code or large verbatim excerpts from leaked materials
- compatibility should be expressed in terms of behavior, interfaces, and architecture rather than copied implementation text

If you contribute, please keep changes based on independently written documentation and original implementation work.

## Architecture documentation

Architecture notes and rewrite guidance live under [`docs/architecture/`](./docs/architecture/).

Start with:

- [`docs/architecture/INDEX.md`](./docs/architecture/INDEX.md)
- [`docs/architecture/hld.md`](./docs/architecture/hld.md)
- [`docs/architecture/feature-prioritization.md`](./docs/architecture/feature-prioritization.md)

## API strategy

Pinser is expected to use Anthropic APIs.

That includes two categories of integration:

- **Public Anthropic APIs**, which are part of the normal supported integration surface
- **Internal Anthropic APIs**, which are undocumented, unstable, and not part of the normal supported integration surface

The default user experience should aim to work with public APIs plus local substitutes. Internal API support may exist, but only as an explicit opt-in compatibility feature.

## Internal API support

Some Claude Code behavior appears to rely on internal APIs that are not part of a public, supported integration surface.

If Pinser supports those APIs, the support should be treated as experimental compatibility work and should be:

- disabled by default
- clearly marked in configuration and docs
- isolated from default code paths where practical
- easy to turn off

Important caveats:

- internal APIs may be unstable, incomplete, rate-limited, or removed without notice
- they may require credentials, account state, or access patterns that are not publicly documented
- their use may violate Anthropic's terms of service

## Default strategy: public APIs and local substitutes

When the user does **not** opt into internal APIs, Pinser should prefer public APIs and local substitutes.

Examples include:

- calling Anthropic's public APIs directly
- supporting OpenAI-compatible endpoints and other provider adapters
- running workers locally
- managing task and session state in local files or a lightweight local database
- executing tools directly in the user environment
- replacing convenience endpoints with local logic such as git inspection, ripgrep-based search, subprocess-backed background tasks, and documented plugin interfaces
- degrading gracefully when exact compatibility is impossible

## Design principles

- **Free software first**
- **Public-first**: prefer documented, user-accessible integrations
- **Local-first where possible**: run as much as possible on the user's machine
- **Explicitness**: no silent fallback to internal APIs
- **Modularity**: keep provider-specific logic isolated
- **Auditability**: favor simple, readable code paths
- **Graceful fallback**: degrade clearly when parity is impossible

## Contribution guidelines

If you want to help:

- keep the implementation clean-room
- avoid copying leaked code or proprietary strings wholesale
- document behavior in your own words when extending the architecture docs
- prefer public equivalents over internal dependencies where practical
- clearly label any compatibility work that touches internal behavior
- do not represent internal Anthropic APIs as stable or officially supported

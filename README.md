# Pinser

Pinser is a free-software reimplementation of Claude Code.

The project aims to provide a user-controlled, inspectable alternative that reproduces useful Claude Code workflows while remaining independently developed.

## Status

Pinser is in an early stage.

## What Pinser is trying to do

- provide a free-software alternative to Claude Code
- reproduce useful Claude Code workflows
- support Anthropic's public APIs
- make internal API support, if present, explicitly opt-in
- provide local or public-API-based workarounds when internal-only features are unavailable

## API support

Pinser is expected to use Anthropic APIs.

There are two broad categories:

- **Public Anthropic APIs**: the normal supported integration surface
- **Internal Anthropic APIs**: undocumented APIs that are not part of the normal supported integration surface

The intended default is to rely on public APIs and local implementations where possible.

## Internal API disclaimer

Some Claude Code behavior appears to rely on internal Anthropic APIs.

Pinser may support some of those APIs as an **opt-in** compatibility feature, but they come with important caveats:

- they may be unstable, incomplete, rate-limited, or removed without notice
- they may require credentials or account state that are not publicly documented
- their use may violate Anthropic's terms of service
- they are not required for the default Pinser experience

If internal API support exists, it should be disabled by default and clearly labeled.

## When internal APIs are not used

When users do **not** opt into internal APIs, Pinser should prefer public APIs and local substitutes.

Examples include:

- calling Anthropic's public APIs directly
- supporting other compatible model providers
- using local subprocesses for worker execution
- storing session and task state locally
- reimplementing convenience features with local tooling such as git and ripgrep
- degrading gracefully when exact compatibility is impossible

## Project principles

- **Free software first**
- **Public APIs first**
- **Local-first where possible**
- **No silent fallback to internal APIs**
- **Clear disclosure of compatibility risks**
- **Readable and auditable implementation**

## Contributing / developer docs

If you want implementation details, architecture notes, or clean-room rewrite guidance, see [HACKING.md](./HACKING.md).

## Disclaimer

Pinser is an independent project. It is not affiliated with, endorsed by, or supported by Anthropic.

Any optional support for undocumented internal Anthropic APIs, if added, is experimental and provided strictly as a user-enabled compatibility path, not as the recommended default. Such use may be unstable and may violate Anthropic's terms of service.

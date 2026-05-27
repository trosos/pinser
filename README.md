# Pinser

Pinser is a free-software reimplementation of Claude Code.

The project aims to provide a user-controlled, inspectable alternative that reproduces useful Claude Code workflows while remaining independently developed.

## Status

Pinser is in an early stage.

## What Pinser is trying to do

- provide a free-software alternative to Claude Code
- reproduce useful Claude Code workflows
- support documented and user-accessible APIs
- make any support for undocumented APIs, if present, explicitly opt-in
- provide local or public-API-based workarounds when undocumented features are unavailable

## API support

Pinser is intended to work primarily with supported public APIs and local implementations where possible.

Some compatibility features may depend on undocumented APIs. If such support exists, it should be treated as experimental, explicitly enabled by the user, and not considered part of the default Pinser experience.

## If undocumented APIs are not used

When users do **not** opt into undocumented APIs, Pinser should prefer public APIs and local substitutes.

Examples include:

- calling supported public APIs directly
- supporting other compatible model providers
- using local subprocesses for worker execution
- storing session and task state locally
- reimplementing convenience features with local tooling such as git and ripgrep
- degrading gracefully when exact compatibility is impossible

## Project principles

- **Free software first**
- **Public APIs first**
- **Local-first where possible**
- **No silent fallback to undocumented APIs**
- **Clear disclosure of compatibility risks**
- **Readable and auditable implementation**

## Contributing / developer docs

If you want implementation details, architecture notes, or rewrite guidance, see [HACKING.md](./HACKING.md).

## Disclaimer

Pinser is an independent project. It is not affiliated with, endorsed by, or supported by Anthropic.

Any optional support for undocumented APIs, if added, is experimental and provided strictly as a user-enabled compatibility path, not as the recommended default. Such use may be unstable, may stop working without notice, and may be subject to provider terms and restrictions.

# Contributing to PurrCat

An Agent foundation designed around information theory. Let expression no longer be a lossy compression — let the Agent work your way.

## What we are looking for

- Improvements to the built-in UI plugins
- Fixes for existing bugs
- macOS and other OS compatibility fixes
- Packaging on macOS and other platforms: no packaged artifact exists for these platforms yet, and we cannot debug them locally. We are looking for contributors to verify the build and identify the adjustments required

## Setup

```powershell
uv sync
npm install
npm run dev
```

## Code conventions

- Host TypeScript stays strict: no `@ts-ignore`, `@ts-nocheck`, or `@ts-expect-error`.
- `ui/web-minimal/assets/host.js` and `host.js.map` are generated files. Edit `ui/web-minimal/src/host/*.ts`, rebuild with `npm run build:ui`, and commit the rebuilt assets in the same commit.
- Do not commit user data under `~/.purrcat`, secrets, or build output.
- Commit messages are one line, in English.

## Issues and pull requests

- Search existing issues before opening a new one.
- For significant changes, open an issue and agree on the approach before writing code.
- A human must self-review every PR. Do not submit unreviewed AI-generated code.

## Documentation

- Any change to HTTP routes must update `docs/api`.
- Behavior changes must update the relevant `docs/` pages and `AGENTS.md`.

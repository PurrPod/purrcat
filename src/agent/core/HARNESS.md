---
name: System Heartbeat Harness
description: Injected as <heartbeat> every 30 minutes. Guides maintenance of in-development projects.
---

## Constraints

1. Operate only in sandbox (`/agent_vm/`). Do not access files outside this boundary.
2. No major architecture rebuilds without user approval. Iterate, don't rewrite.
3. If nothing needs doing, take no action — this suspends you until next heartbeat.

## Maintenance Checklist

When reviewing code during heartbeat:

- **Does it work?** Run a quick smoke test after every change. Don't assume — verify.
- **Is it safe?** Check for path traversal, unvalidated inputs, hardcoded secrets.
- **Is it stable?** Network calls and file ops must have timeouts. Shared state must have locks.
- **Is it clear?** Would another developer understand it? Add comments for non-obvious logic.
- **Is it minimal?** If a feature isn't used, consider removing it before adding new ones.

## Suggested Activities

- Fix TODOs and FIXMEs you left in earlier sessions
- Check if recently added code has proper error handling
- Look for duplicated logic that could be unified
- Flag potential issues (race conditions, resource leaks) to the user

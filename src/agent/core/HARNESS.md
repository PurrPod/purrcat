---
name: System Heartbeat Harness
description: Injected every 30 minutes as <heartbeat> block. Guides agent on maintenance, architecture review, security audit, and idle-time productive work.
---

## Rules

1. During heartbeat, you operate exclusively within the sandbox (`/agent_vm/`). Do not attempt to access files outside this boundary.
2. Do not waste tokens on meaningless loops or self-reflection. If no task is actionable, take no tool action — this effectively suspends you until the next heartbeat.
3. Never introduce breaking changes to production code paths without explicit user approval.
4. All file modifications must stay within the project root. Validate paths before writing.
5. Do not assume external services (databases, APIs, network) are available. Always implement fallback or degradation paths.

## Architecture Quality Checklist

When you have active projects, use heartbeat cycles to assess:

- **Modularity**: Are modules single-responsibility? Can they be tested in isolation? If a module exceeds 500 lines, consider splitting.
- **Dependency direction**: Does low-level code depend on high-level abstractions (good) or concrete implementations (bad)? Enforce dependency inversion.
- **Interface surface**: Are public APIs minimal and well-documented? Every exposed function is a maintenance contract.
- **Configuration drift**: Are magic numbers or hardcoded paths lurking? All tunables should route through config.yaml or environment.

## Security Posture

- **Input validation**: Every user-facing entry point must sanitize inputs. Assume all data is hostile.
  - File paths: reject directory traversal (`../`, symlink escapes)
  - API payloads: validate types, lengths, and ranges before processing
  - Shell commands: never interpolate user input directly into command strings
- **Secrets management**: API keys, tokens, and credentials must never be hardcoded or logged. Use the secrets/ config directory with restricted file permissions.
- **Least privilege**: Tools should request the minimum scope necessary. Avoid exposing full filesystem access where a scoped path is sufficient.
- **Audit trail**: All destructive operations (file writes, deletions, config changes) must be logged with timestamp and caller identity.

## Concurrency & Stability

- **Thread safety**: Shared mutable state must be protected by locks. Prefer `threading.Lock` over ad-hoc synchronization.
  - Known shared resources: `TASK_INSTANCES`, `MEMO_FILE_LOCK`, `_config_cache`, `_task_log_cache`
  - Rule of thumb: if two threads can read/write the same object, it needs a lock.
- **Deadlock prevention**: Never acquire multiple locks in different orders. If lock A then B is required, enforce this order universally. Use `try_lock` with timeout where possible.
- **Resource cleanup**: Every background thread must be a daemon thread. File handles, network connections, and temporary files must have guaranteed cleanup paths (try/finally or context managers).
- **Error boundaries**: Isolate failure domains. A crash in one sensor or tool should not bring down the entire agent. Use try/except at module boundaries.
- **Timeout everything**: Network calls, subprocesses, and file operations should all have explicit timeouts. A hung operation must not block the agent indefinitely.

## Code Quality Standards

- **Error messages**: Every error returned to the user should include: what went wrong, why it might have happened, and how to fix it. Never expose raw stack traces.
- **Logging**: Use structured logging. Include context (user ID, task ID, session ID) for traceability.
- **Defensive programming**: Validate preconditions at the start of every public function. Fail fast with clear messages rather than propagating `None` or silent failures.
- **Testing**: Each heartbeat is an opportunity to verify that core paths still work. If you have test infrastructure, run a smoke test suite.

## Suggested Idle-Time Activities

If you find yourself with no urgent task during a heartbeat:

1. **Audit recent work**: Review the last few conversation turns. Are there any unresolved issues, open questions, or half-finished refactors?
2. **Check for technical debt**: Look for `TODO`, `FIXME`, `HACK`, `XXX` comments in the codebase. Prioritize by risk.
3. **Review dependency health**: Are any pinned dependencies outdated? Check for known vulnerabilities.
4. **Improve documentation**: If you notice undocumented functions or stale comments, update them.
5. **Proactive suggestions**: If you identify a potential issue (security hole, performance bottleneck, race condition), surface it to the user in the next response.

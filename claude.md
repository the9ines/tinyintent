# Claude Working Agreement — TinyIntent
Read **PRD.md** first. Then implement milestones as small PRs with tests.

## Output contract for every task
1) **A) Unified diff patch** (git-style).
2) **B) PR description** (what/why/how; risks).
3) **C) Single shell command block** that applies the patch end-to-end:
   - write patch to /tmp/*.patch
   - `git checkout -b <feature>` (or reuse)
   - `git apply --whitespace=fix /tmp/*.patch`
   - `chmod +x` any new scripts/tests
   - install deps if needed
   - create/refresh LaunchAgent if needed
   - run tests/smokes
   - print useful URLs/secret if relevant

## Privacy
Local-only. **No cloud inference**. LLMs via **Ollama** on the Mac.

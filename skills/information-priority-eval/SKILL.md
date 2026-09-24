---
name: information-priority-eval
description: Collect and evaluate human-priority omissions in AI answers. Use when a user says an answer missed the point, corrects a key omission, asks for answer-quality evaluation, or wants to compare answer versions against independently specified requirements. Do not invoke for ordinary editing or generic summaries.
---

# Information priority evaluation

Record a compact, source-grounded case when the user identifies a concrete missed requirement or requests this evaluation. Use `scripts/casebook.py capture` for one correction, or `add` for an independently reviewed set of requirements. The script stores local JSON; it makes no model calls.

Only `user_feedback` and `independent_review` labels count in the report. For independent review, derive explicit questions, conclusion-changing conditions, and key unknowns from the original request/source before judging the answer. An agent may suggest a requirement, but record it as `agent_hypothesis` until a person independently verifies it. Never infer that silence means coverage. A `complete` review means the reviewer checked the original request/source for omissions beyond the model's candidates; otherwise use `partial`.

For broader local evidence collection, run `python3 scripts/discover.py --store STORE [--path OTHER_DIR]`. It scans Codex user history and sessions for direct user corrections and writes bounded, unverified candidates. `--include-all-messages` saves a full local user-message archive; `--include-context-candidates` also searches Memory and explicit Markdown paths. Neither file is read by upload commands. Review candidates against the source before turning any into cases. Memory and task logs are background context, not independent human labels. Use an appropriate compute worker when a full session scan would burden the local machine.

Keep publishable cases short: task goal, one observable finding, its consequence, answer or artifact reference, and failure stage (`goal`, `retrieval`, `selection`, `generation`, `presentation`, or `unknown`). Do not put raw conversations, credentials, or source documents in cases. Discovery candidates may retain local conversation context but must never be uploaded directly. Put any private local path only in `artifact`; publishing excludes that field. Prefer a local project `results/information-priority-eval/` store; for cross-project cases use the workspace `results/information-priority-eval/`.

Examples:

```bash
python3 scripts/casebook.py capture --store results/information-priority-eval \
  --goal 'Decide whether deployment is safe' --finding 'The answer omitted the unsupported device' \
  --impact 'Reader may approve an incompatible deployment' --stage selection --importance critical
python3 scripts/casebook.py report --store results/information-priority-eval
```

For a full reviewed case, run `python3 scripts/casebook.py template`, fill the JSON, then `add --input FILE --store STORE`. Uploads default to private GitHub repository `bigshuaige1/agent-eval-data`. The maintainer must invite the contributor, who must accept and authenticate with `gh auth login` or their own `GH_TOKEN`/`GITHUB_TOKEN`; installing the skill grants no repository access. `capture` and `add` offer to upload the new case immediately. Enter approves once; `ALWAYS` enables future automatic uploads for this store and repository; `policy --manual` revokes it. Never select `ALWAYS` on a contributor's behalf. `sync` handles pending cases; `watch` checks every hour while running. Without GitHub access or login, cases remain local. Contributors with access can read and write the private repository, so do not claim issue-only access.

Report observed case counts separately from omission rates. Compute a critical omission rate only on independently labelled `complete` reviews, and say the result applies to that reviewed sample. Do not claim skill-trigger performance without observable trigger evidence.

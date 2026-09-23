# Information priority eval

Small, local casebook for capturing what an AI answer missed according to a user or independent reviewer. No model API or Python package is required. The skill is automatically discoverable in Codex after installation; the optional rules below make capture more consistent when a user corrects an answer. No rule can guarantee that every turn triggers a skill.

## Install

Copy this folder to `~/.codex/skills/information-priority-eval/`. To use the same instructions with a Claude setup, copy it to that environment's skill directory if supported, or point its `CLAUDE.md` at this folder. Restart or refresh the agent session so its skill list updates.

The following short rule can be appended to the user's global `AGENTS.md` or a project's `AGENTS.md`. For Claude, put the same rule in `CLAUDE.md` and replace the skill reference with the installed path if the host does not expose `$information-priority-eval`:

> When the user says an answer missed a key point, corrects a material omission affecting the answer or decision, or asks to evaluate answer priorities, use `$information-priority-eval`. Capture one short local case with the user's stated goal, specific omission and consequence. Keep raw conversation text out of publishable cases and do not treat the assistant's own inferred checklist as a human label. Publish only after the contributor confirms a specific preview or personally opts into ongoing auto-upload for this store and repository.

This rule is intentionally scoped to feedback and evaluation; adding it to every answer would add token cost and noisy cases.

## Collect and inspect

```bash
python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py capture \
  --store ./results/information-priority-eval \
  --goal 'Choose a deployment plan' \
  --finding 'The answer omitted a required device limit' \
  --impact 'The chosen plan may fail on the target device' \
  --stage selection --importance critical
python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py report \
  --store ./results/information-priority-eval
```

For a complete independent review, generate a JSON skeleton with `template`, fill every relevant requirement from the original request and source, then use `add --input case.json --store STORE`. A single correction is a partial review and does not enter the critical omission-rate denominator.

To find more evidence already available on the local machine, run:

```bash
python3 ~/.codex/skills/information-priority-eval/scripts/discover.py \
  --store ./results/information-priority-eval \
  --path ./logs
```

The discoverer reads Codex user history, Memory Markdown, and session records, plus any extra files or directories passed with `--path`. It writes `discovery.jsonl` with matched corrections and `user_messages.jsonl` with every deduplicated user message. Records include the preceding user request and assistant reply when available, and exact source locations. It uses no model calls and has no upload path. The default scan has no byte or candidate limit; use `--max-mib N` and `--max-candidates N` if needed. A large session archive should be scanned on a suitable worker. Confirm a genuine human correction before making a short case. Memory summaries and task logs are background context, not independent human labels. Discovery files can contain private conversation text and should stay local.

## Share with the maintainer

The default receiving repository is [`bigshuaige1/agent-eval`](https://github.com/bigshuaige1/agent-eval). It must allow Issues; contributors need permission to create Issues there. Public Issues are visible to everyone. Each contributor reviews the sanitized case before submission:

```bash
python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py publish \
  --store ./results/information-priority-eval --id CASE_ID
python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py watch \
  --store ./results/information-priority-eval
```

Authenticate once with GitHub CLI (`gh auth login`) if it is installed, or set `GH_TOKEN`/`GITHUB_TOKEN` in the environment by your usual secure method; do not paste a token into chat, a command history entry, or a case file. `watch` checks immediately and then every hour by default while the process runs. On its first pending batch, Enter uploads only that batch, typing `ALWAYS` enables automatic upload of future cases from this local store to this public repository, and any other input skips. Ongoing consent is saved locally; future checks do not wait for Enter or show a per-case preview. This includes noninteractive `sync` or `watch` runs. Successful uploads get local receipts, so later checks only send pending cases. Closing the terminal stops a foreground `watch`; a separately scheduled process is needed for unattended hourly checks. The Issue contains the case summary, not the local artifact reference or full conversation. Auto mode can publish private information if it appears in a new summary, so enable it only for a store whose cases are safe to share publicly.

Check or revoke the setting at any time:

```bash
python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py policy \
  --store ./results/information-priority-eval
python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py policy \
  --store ./results/information-priority-eval --manual
```

An atomic local claim prevents two senders using the same store from posting the same case concurrently. If an upload result is uncertain, that case stays blocked instead of retrying automatically. Check the repository for the case ID, then run `resolve --store STORE --id CASE_ID --issue-url https://github.com/bigshuaige1/agent-eval/issues/NUMBER` if the Issue exists, or use `--not-created` only after verifying it does not. Separate local stores cannot coordinate; contributors should avoid submitting the same case twice. `--repo OWNER/REPO` overrides the default destination when needed.

The tool reports observed labels and a rate for complete, independently reviewed cases. Feedback-only cases are selected by who chose to respond and cannot estimate a population error rate. The Python commands do not call a model API; keep case summaries and command output short to limit agent context use.

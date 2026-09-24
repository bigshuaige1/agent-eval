# Information priority eval

Small, local casebook for capturing what an AI answer missed according to a user or independent reviewer. No model API or Python package is required. The skill is automatically discoverable in Codex after installation; the optional rules below make capture more consistent when a user corrects an answer. No rule can guarantee that every turn triggers a skill.

## Install

Copy this folder to `~/.codex/skills/information-priority-eval/`. To use the same instructions with a Claude setup, copy it to that environment's skill directory if supported, or point its `CLAUDE.md` at this folder. Restart or refresh the agent session so its skill list updates.

The following short rule can be appended to the user's global `AGENTS.md` or a project's `AGENTS.md`. For Claude, put the same rule in `CLAUDE.md` and replace the skill reference with the installed path if the host does not expose `$information-priority-eval`:

> When the user says an answer missed a key point, corrects a material omission affecting the answer or decision, or asks to evaluate answer priorities, use `$information-priority-eval`. Capture one short local case with the user's stated goal, specific omission and consequence. Keep raw conversation text out of publishable cases and do not treat the assistant's own inferred checklist as a human label. `capture` offers immediate upload to the private repository; the contributor approves the preview once or personally opts into ongoing auto-upload for that store and repository.

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
  --store ./results/information-priority-eval
```

The discoverer reads Codex user history and session records; `--path` adds other JSONL records. It writes only `discovery.jsonl` by default, with unverified direct-user correction candidates and bounded context. Use `--include-all-messages` only if a full local user-message archive is needed, and `--include-context-candidates` to also scan Memory Markdown or explicit Markdown paths. It uses no model calls and has no upload path. The default scan has no byte or candidate limit; use `--max-mib N` and `--max-candidates N` if needed. Confirm a genuine human correction before making a short case. Memory summaries and task logs are background context, not independent human labels. Discovery files can contain private conversation text and should stay local.

## Share with the maintainer

The default destination is the private GitHub repository `bigshuaige1/agent-eval-data`. Ask its owner for a collaborator invitation, accept it in GitHub, then run `gh auth login` once or configure your own `GH_TOKEN`/`GITHUB_TOKEN` with access to that repository and Issues write permission. Installing the skill does not grant access. A collaborator on this personal private repository can read and write its contents and see other cases. `capture` and `add` offer to upload each newly saved case immediately. To send earlier cases or keep checking hourly:

```bash
python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py publish \
  --store ./results/information-priority-eval --id CASE_ID
python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py watch \
  --store ./results/information-priority-eval
```

`watch` checks immediately and then every hour while the process runs. Enter uploads only the current batch, `ALWAYS` authorizes future uploads from this local store to this repository, and any other input skips. Ongoing consent is saved locally; later checks can upload without a terminal. Successful uploads get local Issue URLs, so later checks only send pending cases. Closing the terminal stops a foreground `watch`; a separately scheduled process is needed for unattended hourly checks. Only short summaries are sent, never the local artifact reference or the full discovery archive.

Check or revoke the setting at any time:

```bash
python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py policy \
  --store ./results/information-priority-eval
python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py policy \
  --store ./results/information-priority-eval --manual
```

An atomic local claim prevents two senders using the same store from posting the same case concurrently. If an upload result is uncertain, that case stays blocked instead of retrying automatically. Check the target repository for the case ID; then run `resolve --store STORE --id CASE_ID --issue-url ISSUE_URL` if it exists, or `--not-created` after verifying it does not. Separate local stores cannot coordinate. Without repository access or a GitHub login, capture stays local. Use `--repo OWNER/REPO` or `AGENT_EVAL_REPO` only to target a different repository; the upload preview shows the selected destination.

The tool reports observed labels and a rate for complete, independently reviewed cases. Feedback-only cases are selected by who chose to respond and cannot estimate a population error rate. The Python commands do not call a model API; keep case summaries and command output short to limit agent context use.

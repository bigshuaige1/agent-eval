# agent-eval

Collect short, independently grounded examples of important information that an AI answer missed. The collector uses Python's standard library and makes no model API calls.

## Install the skill

```bash
git clone https://github.com/bigshuaige1/agent-eval.git
mkdir -p ~/.codex/skills
cp -a agent-eval/skills/information-priority-eval ~/.codex/skills/
```

Restart the agent session after installation. The [skill instructions](skills/information-priority-eval/SKILL.md) explain when to collect a case; the [usage guide](skills/information-priority-eval/README.md) includes a short optional rule for `AGENTS.md` or `CLAUDE.md`.

To inspect existing local Codex history and sessions for possible missed priorities, run `python3 ~/.codex/skills/information-priority-eval/scripts/discover.py --store ./results/information-priority-eval`. It saves unverified candidates locally. Use `--include-all-messages` only when a full local archive is useful. Large archives should be scanned on a suitable worker.

## Share cases

The private receiving repository is `bigshuaige1/agent-eval-data`. Its [Cloudflare HTTPS intake](intake/README.md) keeps the GitHub write credential on the server. The Worker route exists but production secrets and an external request test are still required before distributing it. Once the maintainer confirms it is ready, contributors configure `AGENT_EVAL_ENDPOINT=https://agent-eval-intake.bigshuaige1-agent-eval.workers.dev/v1/cases` and their own `AGENT_EVAL_UPLOAD_TOKEN`. Each `capture` or `add` then offers to upload its short case immediately; Enter approves once, or `ALWAYS` enables future automatic uploads for that store and endpoint. Contributors need no GitHub repository access. To send previously collected cases or check hourly in a running terminal:

```bash
python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py watch \
  --store ./results/information-priority-eval
```

`watch` checks immediately and every hour while running. Revoke ongoing consent with `python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py policy --store ./results/information-priority-eval --manual`. Closing the terminal stops `watch`; unattended hourly checks require a separate scheduler. Only short case summaries go to the private intake. Discovery files and local artifact references stay local. Until the intake URL is configured, collection stays local. Public GitHub publishing requires an explicit `--repo OWNER/REPO` and a GitHub login.

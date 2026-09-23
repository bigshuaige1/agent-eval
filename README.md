# agent-eval

Collect short, independently grounded examples of important information that an AI answer missed. The collector uses Python's standard library and makes no model API calls.

## Install the skill

```bash
git clone https://github.com/bigshuaige1/agent-eval.git
mkdir -p ~/.codex/skills
cp -a agent-eval/skills/information-priority-eval ~/.codex/skills/
```

Restart the agent session after installation. The [skill instructions](skills/information-priority-eval/SKILL.md) explain when to collect a case; the [usage guide](skills/information-priority-eval/README.md) includes a short optional rule for `AGENTS.md` or `CLAUDE.md`.

## Share cases

The default destination is this repository's public Issues. Authenticate once with `gh auth login`, or provide `GH_TOKEN`/`GITHUB_TOKEN` through your usual secure environment setup. Run the collector in an interactive terminal:

```bash
python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py watch \
  --store ./results/information-priority-eval --every-minutes 1440
```

It checks for pending cases immediately and then every 24 hours while the terminal remains open. It previews each batch and creates Issues only after you press Enter; typing anything else skips the batch. No interactive terminal means no upload. Review the preview for private information: Issues in this public repository are visible to everyone. The local artifact reference and full conversation are never included in the Issue body.

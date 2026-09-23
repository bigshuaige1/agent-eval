# agent-eval

Collect short, independently grounded examples of important information that an AI answer missed. The collector uses Python's standard library and makes no model API calls.

## Install the skill

```bash
git clone https://github.com/bigshuaige1/agent-eval.git
mkdir -p ~/.codex/skills
cp -a agent-eval/skills/information-priority-eval ~/.codex/skills/
```

Restart the agent session after installation. The [skill instructions](skills/information-priority-eval/SKILL.md) explain when to collect a case; the [usage guide](skills/information-priority-eval/README.md) includes a short optional rule for `AGENTS.md` or `CLAUDE.md`.

To inspect existing local Codex history, Memory, and sessions for possible missed priorities, run `python3 ~/.codex/skills/information-priority-eval/scripts/discover.py --store ./results/information-priority-eval`. Add `--path DIR` for other local records. The output stays local and includes conversation context; review it before writing a short case. Large archives should be scanned on a suitable worker.

## Share cases

The default destination is this repository's public Issues. Authenticate once with `gh auth login`, or provide `GH_TOKEN`/`GITHUB_TOKEN` through your usual secure environment setup. Run the collector in an interactive terminal:

```bash
python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py watch \
  --store ./results/information-priority-eval
```

It checks for pending cases immediately and then every hour while running. At the first pending batch, press Enter to approve that batch, type `ALWAYS` to authorize automatic uploads of future cases from this local store, or type anything else to skip. Automatic mode also works without a terminal; revoke it with `python3 ~/.codex/skills/information-priority-eval/scripts/casebook.py policy --store ./results/information-priority-eval --manual`. A foreground `watch` stops when its terminal closes, so unattended hourly checks need a separately scheduled process. Issues in this public repository are visible to everyone: auto mode does not review future summaries for private information. The local artifact reference and full conversation are excluded from the Issue body.

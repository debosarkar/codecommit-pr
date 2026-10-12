# codecommit-pr
Triggers an agentic code review whenever a PR is raised in a CodeCommit Repository

When a pull request in AWS CodeCommit is created or gets new commits, an
EventBridge rule invokes a Lambda that reviews the changed Python,
TypeScript/JavaScript and Java/Kotlin files with Claude (Claude in Amazon
Bedrock) and posts inline comments plus one summary comment. It is
comment-only: it never approves or blocks a merge.

It reviews for two things:
- **Bugs and risks:** correctness, security, resource and performance problems.
- **Team standards:** the rules in [`standards/code-review.md`](standards/code-review.md),
  fetched at runtime from the `nda-skills` repo, with a bundled copy as fallback.

## Layout

| Path | What it is |
|---|---|
| `src/pr_reviewer/` | Lambda code: handler, review pipeline, CodeCommit gateway, Claude reviewer, publisher |
| `template.yaml` | SAM template: function, EventBridge rule, IAM role, error alarm |
| `standards/code-review.md` | Review standards (rule IDs such as `PY-001`) |
| `tests/` | pytest suite |
| `demo/`, `scripts/` | Demo PR with planted issues, and a scorer for the bot's comments |
| `.scratch/codecommit-pr-reviewer/` | Spec, implementation plan, progress ledger, tickets |

## Develop

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
```

## Deploy

Prerequisites:
- AWS credentials for the target account, and the [SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html).
- Amazon Bedrock model access for `anthropic.claude-opus-5-5` in the deploy region.
- `standards/code-review.md` published in the public `nda-skills` repo.

```bash
sam build
sam deploy --guided --stack-name pr-reviewer --capabilities CAPABILITY_IAM \
  --parameter-overrides StandardsUrl=https://raw.githubusercontent.com/<owner>/nda-skills/main/standards/code-review.md
```

Optional parameters: `ModelId`, `Effort`, `RepositoryNames` (comma-separated
allow-list), `MaxFiles`, `MaxInlineComments`, `MaxFileBytes`, `InlineSeverities`.

## Demo

```bash
PR_ID=$(scripts/open_demo_pr.sh)            # creates a CodeCommit repo + PR with planted issues
.venv/bin/python scripts/score_review.py "$PR_ID"   # recall and noise of the bot's comments
```

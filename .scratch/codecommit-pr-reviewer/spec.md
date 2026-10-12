# Spec: CodeCommit PR Reviewer (Approach A)

Status: approved
Date: 2026-10-12

## Intent

An automated agent reviews pull requests in AWS CodeCommit when they are created or updated, and posts review comments.

- **Context:** built as an SDLC challenge entry, but the problem is real and the team intends to use it. It must demo end-to-end and stay production-viable (least-privilege IAM, bounded cost, low noise).
- **Objectives:** (1) catch bugs and risks; (2) enforce the team's coding standards.
- **Success looks like:** on a seeded demo PR, the bot posts accurate inline comments on planted bugs and standards violations across Python, TS/JS and Java/Kotlin, plus one summary comment, with no duplicate comments on re-push and no crash or silent failure.

## Decisions

| Topic | Decision |
|---|---|
| Trigger | CodeCommit PR events: `pullRequestCreated`, `pullRequestSourceBranchUpdated` |
| Effect | Comment-only (advisory). Never approves, revokes or blocks merges. |
| LLM | Claude in Amazon Bedrock via the Anthropic Python SDK (`anthropic[bedrock]`, `AnthropicBedrockMantle` client, Messages API). Default model `anthropic.claude-opus-5-5`, effort `high`; both are deploy parameters. |
| Reviewed languages | Python, TypeScript/JavaScript, Java/Kotlin |
| Standards source | New doc in public GitHub repo `nda-skills`, fetched anonymously over HTTPS |
| Stack | Python 3.12 Lambda, AWS SAM |
| Architecture | Approach A: EventBridge → single Lambda. (B, an SQS-buffered variant, and C, a CodeBuild agentic reviewer, are deferred. The handler is kept thin so B can be added by swapping only the entry point.) |
| CodePipeline | Context only. No role in this design. Deployment is a manual `sam deploy`. |

## Architecture

```
CodeCommit PR event ──► EventBridge rule ──► Lambda: pr-reviewer
                                              ├─► CodeCommit API (PR, diffs, blobs, comments)
                                              ├─► GitHub raw URL (standards doc)
                                              ├─► Bedrock (Claude review)
                                              └─► CodeCommit API (post comments)
```

### EventBridge rule

- `source: aws.codecommit`, `detail-type: CodeCommit Pull Request State Change`, `detail.event` ∈ {`pullRequestCreated`, `pullRequestSourceBranchUpdated`}.
- Optional repository allow-list parameter (`RepositoryNames`, comma-separated). If it is empty, all repositories are covered.

### Lambda modules

| Module | Responsibility | Depends on |
|---|---|---|
| `handler.py` | Parse the EventBridge event into a `ReviewRequest` (repo, PR id, source commit, destination commit, merge base). Call the pipeline. The only module that changes for Approach B. | `review_pipeline` |
| `review_pipeline.py` | Orchestrate: fetch changes → load standards → review → validate → publish. Enforce the time budget. | all below |
| `codecommit_gateway.py` | Wrap CodeCommit: get PR, list differences, get blobs, list existing comments, post comments. | boto3 |
| `diffing.py` | Build unified diffs from old/new blobs with `difflib`. Expose the set of added/modified line numbers (AFTER version) per file. | stdlib |
| `file_filter.py` | Decide which files are reviewable (by extension, deleted, binary, lockfile, generated/minified, size > ~100 KB). Apply the 30-file cap. | stdlib |
| `standards.py` | Fetch the standards doc from a configured URL, cache it in module scope for 10 minutes while the Lambda stays warm, and fall back to a bundled default on failure. Report the source (URL or `built-in default`) and a version (first 12 hex chars of the content's SHA-256). | HTTPS (urllib) |
| `reviewer.py` | Build prompts, batch files to a size budget, call the Messages API with a `report_findings` tool (`tool_choice: auto` plus an instruction to call it; forced tool choice and structured outputs are unavailable for this model/endpoint), and parse findings. | `anthropic` SDK |
| `findings.py` | `Finding` model, validation against changed lines, fingerprinting. | stdlib |
| `publisher.py` | Route findings to inline vs. summary, de-duplicate against existing comments, cap inline comments, render comment bodies. | `codecommit_gateway` |

### IAM (least privilege)

- `codecommit:GetPullRequest`, `GetDifferences`, `GetBlob`, `GetCommentsForPullRequest`, `PostCommentForPullRequest`, scoped to `arn:aws:codecommit:<region>:<account>:*`. The repository allow-list is enforced in the handler (CloudFormation cannot expand a comma-separated list into ARNs).
- `bedrock-mantle:CreateInference`. Resource `*` until the Mantle model ARN format is confirmed; tightening it is a tracked follow-up.
- CloudWatch Logs (SAM basic execution).

## Data flow

1. **Resolve target.** `GetPullRequest` returns the source commit, the destination commit and the merge base. Exit without posting if the PR is not `OPEN`. The review range is always merge base → current source commit (the whole PR), for both event types.
2. **Fetch changes.** `GetDifferences` (paginated) over the range; `GetBlob` for before/after. Build unified diffs and changed-line sets. Filter files. Files beyond the 30-file cap are listed as "not reviewed".
3. **Load standards.** Fetch from `StandardsUrl`. On failure, use the bundled default and record it.
4. **Review.**
   - **System prompt:** reviewer role, objectives (bugs/risks + standards), the standards doc, and these instructions: report only high-confidence issues; comment only on added/modified lines; ignore anything the formatter would fix; cite `standard_ref` for standards findings.
   - **User content per file:** path, language, unified diff (with AFTER line numbers), and the full AFTER file for context, truncated to the per-file budget.
   - Files are grouped into batches under a per-call token budget, and batches are called sequentially.
   - The model is instructed to call the `report_findings` tool exactly once (`tool_choice: auto`). The system prompt is marked with a prompt-cache breakpoint so later batches reuse it. Code in the diff is treated as untrusted data, never as instructions. Schema per finding: `file`, `line` (AFTER), `severity` (critical|high|medium|low), `category` (bug|security|performance|standards), `title`, `explanation`, `suggestion`, `standard_ref` (nullable).
5. **Validate.** Drop findings whose file is not in the batch, or whose line is not an added/modified AFTER line.
6. **Publish.**
   - **Fingerprint:** a short hash of (file, category, standard_ref or normalised title). It is rendered in each comment's footer (e.g. `pr-reviewer · fp:3fa9c1`).
   - **De-duplication:** read existing PR comments with `GetCommentsForPullRequest` and skip findings whose fingerprint is already present.
   - **Inline:** critical/high/medium findings, at most 15 per run, highest severity first. Each post carries a `clientRequestToken` (fingerprint + source commit) so CodeCommit treats retried posts as idempotent. Posted with `PostCommentForPullRequest`: `beforeCommitId` = destination commit, `afterCommitId` = source commit, `location` = {`filePath`, `filePosition`, `relativeFileVersion: AFTER`}.
   - **Summary (one per reviewed source commit, no location; it carries its own commit-based fingerprint so retries never duplicate it):** reviewed commit, counts by severity/category, low-severity findings, overflow findings past the inline cap, skipped/unreviewed files with reasons, partial-review notice if any, and the standards source and version.
   - Every comment body is capped below CodeCommit's 10,240-character limit and is truncated with a note if needed.

## Error handling

| Failure | Behaviour |
|---|---|
| Bedrock throttling / transient errors | Anthropic SDK retries (`max_retries=4`, exponential backoff on 429/5xx/connection errors). If a batch still fails, continue with the other batches and list the failed files in the summary. |
| Malformed or missing tool output, or `stop_reason: refusal` | Retry the batch once, then skip it and note it in the summary. |
| Time budget | Before each batch, if remaining time is < 60 s, stop, publish what has been gathered, and mark the summary as partial. Lambda timeout: 300 s. |
| GitHub unreachable | Use the bundled default standards; the summary states this. |
| Unhandled exception | The pipeline catches it at the top level, posts a single "automated review could not complete (request id …)" comment with a fixed failure fingerprint (so retries never duplicate it), then re-raises. Lambda async retries (max 2) are idempotent through fingerprint de-duplication. A CloudWatch alarm watches Lambda `Errors`. |
| PR not open / repository not allowed | No-op exit, logged. |

Logging: structured JSON with `repository`, `pullRequestId`, `sourceCommit`, stage, durations, finding counts.

## Configuration (SAM parameters / env)

`ModelId`, `Effort` (high), `StandardsUrl` (required; no default), `RepositoryNames`, `MaxFiles` (30), `MaxInlineComments` (15), `MaxFileBytes` (~100 KB), `InlineSeverities` (critical,high,medium).

## Testing

- **Unit (pytest, TDD):** diffing and line mapping (new file, rename, no trailing newline), file filter and cap, finding validation, fingerprint stability and dedupe, publisher routing and caps (fake gateway), reviewer against stubbed Bedrock (valid / malformed / throttled), handler parsing of sample EventBridge payloads for both event types, standards fallback.
- **End-to-end demo:** a demo CodeCommit repo, plus a script that opens a PR seeded with known bugs (e.g. SQL injection, unchecked null/None, resource leak) and standards violations in all three languages. Verify the posted comments manually.
- **Quality benchmark:** the seeded issues act as a labelled fixture. Record recall (planted issues found) and noise (unplanted comments) for model and prompt comparisons.

## Standards document (deliverable in `nda-skills`)

- **Path:** `standards/code-review.md` (URL configurable).
- **Structure:** general rules, then Python, TypeScript/JavaScript and Java/Kotlin sections. Each rule has a stable ID (e.g. `PY-003`), a default severity, a rationale, and good/bad examples.
- **Scope:** no formatting rules (owned by the formatter in `nda-skills`). Focus on error handling, logging, secrets, input validation, resource management, testing expectations and API conventions.
- **First version:** drafted by us as a starter set for the team to prune. Delivered as its own PR to `nda-skills`. The Lambda bundles a copy as the fallback default.

## Out of scope

- Approving, revoking or gating merges.
- Approach B (SQS buffering, DLQ, concurrency control) and Approach C (agentic CodeBuild reviewer).
- CodePipeline integration, including the reviewer's own CI/CD.
- Replying to or resolving human comment threads.
- Languages other than Python, TS/JS and Java/Kotlin.

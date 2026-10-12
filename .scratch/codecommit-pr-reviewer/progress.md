# SDD ledger — plan: .scratch/codecommit-pr-reviewer/plan.md
Spec: .scratch/codecommit-pr-reviewer/spec.md
Setup: Ruling: no git repo (user declined git init) — no worktree, no commits; this ledger + test runs are the record; sdd scripts (git-based) not used — cost if wrong: no per-task diff ranges for review.
Pre-flight: interfaces checked T1→T6/T7/T8 (Finding, parse_findings, severity_rank), T2→T6/T8 (FileDiff), T3→T5/T7/T8 (ChangedFile, SkippedFile), T4→T6/T7/T8 (Standards), T5→T8 (gateway methods), T6→T8 (ReviewFile, build_batches, review_batch), T7→T8 (publisher fns), T8→T9 (Config, ReviewRequest, run_review): consistent.
Task 1: complete (tests: .venv/bin/pytest -q → 16 passed; RED seen: ModuleNotFoundError pr_reviewer.findings)
Task 2: complete (tests: pytest -q → 22 passed; RED: ModuleNotFoundError pr_reviewer.diffing)
Task 3: complete (tests: pytest -q → 28 passed; RED: ModuleNotFoundError pr_reviewer.file_filter)
Task 4: complete (tests: pytest -q → 33 passed; RED: ImportError pr_reviewer.standards; standards doc 23 rules)
Task 5: complete (tests: pytest -q → 39 passed; RED: ModuleNotFoundError pr_reviewer.codecommit_gateway; Stubber validated param names)
Task 6: complete (tests: pytest -q → 47 passed; RED: ModuleNotFoundError pr_reviewer.reviewer; verified anthropic 1.13.0 has AnthropicBedrockMantle + output_config)
Task 7: complete (tests: pytest -q → 55 passed; RED: ModuleNotFoundError pr_reviewer.publisher)
Task 8: complete (tests: pytest -q → 64 passed; RED: ModuleNotFoundError pr_reviewer.review_pipeline)
Task 9: Ruling: SAM CLI installed into local .venv-sam via pip instead of `brew install` — avoids a system-wide install — cost if wrong: none (user can brew install later)
Task 9: complete (tests: pytest -q → 70 passed; RED: ImportError handler; sam validate --lint → valid; sam build → succeeded, pydantic_core aarch64-linux .so packaged)
Task 10: steps 1-5 complete (tests: pytest -q → 71 passed; RED: FileNotFoundError scripts/score_review.py; demo line numbers verified against expected.json, 16 planted issues; bash -n ok)
Task 10: Ruling: steps 6-8 (Bedrock model access, nda-skills PR, sam deploy, demo PR, e2e scoring) NOT run — they create AWS resources / publish to GitHub and need the user's GitHub owner + credentials; stop condition "side effect outside the workspace" — cost if wrong: e2e unverified until user runs them
Final review: fresh reviewer (Fable 5.1) → "With fixes": 1 Critical, 5 Important, 5 Minor.
Final: fixed Bedrock call not bounded by Lambda time (Critical) — test_time_budget_bounds_each_call, test_time_budget_caps_timeout_at_120s, test_too_little_budget_raises_without_calling_model, test_reviewer_gets_time_budget_minus_publish_reserve, test_reviewer_budget_exhaustion_marks_partial RED→GREEN, suite 82/82
Final: fixed all-batches-failed reported as "No reviewable files" — test_all_batches_failing_is_a_failed_run_not_an_empty_review, test_partial_review_with_nothing_reviewed_does_not_claim_nothing_reviewable RED→GREEN, suite 82/82
Final: fixed one post error aborting publishing / idempotency mismatch — test_inline_post_errors_do_not_abort_publishing RED→GREEN, suite 82/82
Final: fixed same-rule repeats in a file silently dropped — test_repeated_rule_in_same_file_is_listed_not_lost RED→GREEN, suite 82/82
Final: fixed prompt tag breakout + pasted-footer suppression — test_render_file_neutralises_tag_breakout, test_fingerprint_only_counts_when_it_is_the_footer RED→GREEN, suite 82/82
Final: Ruling: min_remaining_ms default 60s→90s and 30s publish reserve passed as reviewer budget — keeps headroom for one bounded call plus posting — cost if wrong: slightly earlier partial reviews on huge PRs
Final: Ruling: test fakes in test_review_pipeline.py updated for the new review_batch(time_budget_s) parameter and the extra remaining_ms() read per batch — interface change from the Critical fix — cost if wrong: none
Final: Ruling: model-text link stripping (part of reviewer item 5) not done — the comment body cap already bounds length, and comments only appear on the team's own PRs — cost if wrong: a crafted PR could make the bot post a link
Final: minor (deferred): summary lists every unsupported file individually; group them, and keep the "Standards:" line through truncation
Final: minor (deferred): score_review.py/demo not yet verified against a deployed run (blocked on deploy)
Final: minor (deferred): rename-with-edits reported by CodeCommit as A may be reviewed in full; confirm against real GetDifferences output
Final: minor (deferred): pin anthropic[bedrock] version in src/requirements.txt; clearer error for missing env config
Final: minor (deferred): add reserved concurrency to cap Bedrock cost per burst of pushes
Final: Ruling: ledger kept (not deleted) — no git history exists to serve as the record — cost if wrong: one small file in .scratch
Declined-to-judge rulings: Mantle IAM `*` stands (ticket 01); e2e unverified stands (blocked on user); no git stands (user choice); beforeCommitId=destination stands (API contract, verify in e2e); standards content is the team's to prune; anonymous standards fetch is mandated by spec; Opus 5.5/Mantle facts verified from docs this session.

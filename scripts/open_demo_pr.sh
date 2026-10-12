#!/usr/bin/env bash
# Creates CodeCommit repo $REPO with a clean main branch and a feature branch
# containing seeded issues, then opens a PR. Requires aws cli + jq.
set -euo pipefail
REPO="${REPO:-pr-reviewer-demo}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! aws codecommit get-repository --repository-name "$REPO" >/dev/null 2>&1; then
  aws codecommit create-repository --repository-name "$REPO" \
    --repository-description "PR reviewer demo" >/dev/null
fi

main_commit=$(aws codecommit put-file --repository-name "$REPO" --branch-name main \
  --file-path orders.py --file-content "fileb://$ROOT/demo/base/orders.py" \
  --commit-message "Base orders module" --query commitId --output text)

branch="feature/seeded-$(date +%s)"
aws codecommit create-branch --repository-name "$REPO" --branch-name "$branch" --commit-id "$main_commit"

parent="$main_commit"
for f in orders.py userService.ts InvoiceRepository.java; do
  parent=$(aws codecommit put-file --repository-name "$REPO" --branch-name "$branch" \
    --file-path "$f" --file-content "fileb://$ROOT/demo/seeded/$f" \
    --parent-commit-id "$parent" --commit-message "Add $f" --query commitId --output text)
done

aws codecommit create-pull-request --title "Demo: seeded issues ($branch)" \
  --targets "repositoryName=$REPO,sourceReference=$branch,destinationReference=main" \
  --query pullRequest.pullRequestId --output text

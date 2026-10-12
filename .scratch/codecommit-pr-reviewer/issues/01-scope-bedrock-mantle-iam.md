# Scope bedrock-mantle:CreateInference to the model ARN

Status: needs-triage

The SAM template grants `bedrock-mantle:CreateInference` on `*` because the
resource ARN format for Claude in Amazon Bedrock models was not documented
when the reviewer was built. Find the ARN format (AWS "Prerequisites for
running model inference" page or a CloudTrail event from a real invocation),
then restrict the statement in `template.yaml` to the configured `ModelId`.

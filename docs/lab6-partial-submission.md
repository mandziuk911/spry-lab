# Lab 6 — partial submission

## Status and verification

Implementation and local tests are submitted, but AWS CLI authentication failed (expired/pending authorization). Consequently, no new AWS stack was deployed, no live Bedrock model call or quota check was performed, and the deployed-app video, five real model outputs with token/cost/latency table, and real CloudWatch log line are **not available**. This is a partial submission, not a claim that the deployed acceptance criteria passed. The Nova Micro default is provisional, not proof of a permitted or working Claude alternative. Claude access/zero quotas and instructor permission to use a different model have **not** been verified.

Local validation: backend Python 3.12 with isolated PostgreSQL: 187 tests passed; frontend: 83 tests, production build and lint passed in Node 24 Docker; infrastructure: 35 offline tests and cfn-lint passed. These tests use mocks for model calls and do not establish live model behavior. See ADR 0006 and architecture diagram for implementation and tradeoffs.

## Step 5 answers (limited by missing live evaluation)

1. Which cases went wrong and why? **Unknown: none of the five were run against a real model.** Cases and flags are implemented in `back/app/ai/cli.py` for a later real evaluation. Schema validation, a bounded single repair and UI review address different classes of errors, but their effectiveness on the five cases has not been measured.
2. Injection case: **actual model response unknown**. Parser output cannot write the database: the person must review and use the normal authenticated Save API. Structured validation and source-presence checks reduce some unsupported-owner outputs, but they do not prevent `admin@example.com` being selected when it appears in the attack text. Human review and stronger source/assignment verification are required.
3. Actual cost per parse is **unknown** without a live log. At 20 × 30 agendas/week, projected monthly parses are approximately 20 × 30 × 52 / 12 = 2,600. If measured average inference cost is `c` USD per parse, monthly inference is about `2600c`, excluding Lambda/logs/transfer and retries. The supplied $7.30/month endpoint comparison equals inference cost at `c ≈ $0.00281`. Nova Micro's configurable published input/output reference rates are given in ADR 0006; actual pricing depends on the selected model and profile. The $5 budget alerts but does not cap charges.
4. For 500 saved agendas, obtain consented original source text, local date/timezone and human-corrected final agendas, split by organization/time and reserve a held-out set. Run v1 and v2 on the same held-out inputs, blind adjudicate ambiguity, and compare per-field extraction precision/recall, owner and date accuracy, unsupported-value rate, latency and cost using paired differences and uncertainty intervals. Saved `ai_suggestion` alone does not preserve enough source/context to rerun the prompt. Avoid treating unreviewed edits as perfectly labeled truth.

After grading, destroy AI stacks if deployed and review all other AWS resources and charges.

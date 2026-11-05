# Conversation review

Each night Muse offers every unjudged turn from the last three days of private conversations, oldest first,
in fixed batches until all are reviewed. No language or keyword filter excludes a turn. The current
exchange includes the preceding user message and assistant reply when available; read the original
through the packet when a judgment needs more context. Unretried tool failures are additional hints.

The model judges each pick:
- `agent_gap`: the assistant fell short. It claimed work it did not do, dropped a failure, or missed what the user meant. This opens a finding for 14 days.
- `friction`: the user corrected or redid something a skill or rule could have settled. This opens a finding tagged `friction`, counted in the weekly digest. It is a suggestion: nothing changes a rule or skill by itself.
- `latent_need`: the user showed a need nobody recorded. This becomes an idea candidate.
- `fine`: nothing needs attention.

`reason` is one sentence that names the evidence: the claim, the failed tool, or the user's words.

Findings appear in nightly and briefing summaries and are never pushed to the user right away. In the main conversation, `read(kind=finding)` lists the open ones. When the user reacts, `feedback(kind=finding, value=useful)` resolves it. A finding that suggests a fix becomes a goal only after the user accepts it.

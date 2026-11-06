# Retained changes

This fork follows upstream and retains semantic review: nightly review includes every unjudged
private conversation turn from the existing 72-hour window. Semantic classification uses the
model assigned to the nightly Hermes job. No classifier service or keyword admission gate is used.
All assistant messages in a turn, previous-turn context and optional tool-failure evidence accompany
the turn. Review reads page through the original user/assistant exchange, not just the user message.
Unreported findings and ideas cross batch boundaries into the final nightly synthesis, and can
wake a summary-only batch after the review queue is empty. Failed runs do not acknowledge them.
Existing host
source filtering, redaction, batching, receipts and per-turn deduplication remain in place.

Coverage: `tests/review_all_turns_acceptance.py` and the nightly cases in
`tests/kernel_acceptance.py`. Reassess this change on upstream updates; retire it when upstream
provides equivalent language-independent review. Install a committed revision through Hermes
plugin management instead of editing the deployed plugin tree.

Generated launchers live together in `scripts/hermes-muse/`. Installation moves previous generated
flat launchers through the native cron API, preserving job IDs, settings and history, and removes
obsolete generated files only after no job references them. User scripts stay untouched.
Upstream 0.5.3 does not supersede the semantic review, full-turn or cross-batch synthesis changes.

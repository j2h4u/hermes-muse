# Retained changes

This fork follows upstream and retains one behavior: nightly review includes every unjudged
private conversation turn from the existing 72-hour window. Semantic classification uses the
model assigned to the nightly Hermes job. No classifier service or keyword admission gate is used.
Previous-turn context and optional tool-failure evidence accompany the turn. Existing host
source filtering, redaction, batching, receipts and per-turn deduplication remain in place.

Coverage: `tests/review_all_turns_acceptance.py` and the nightly cases in
`tests/kernel_acceptance.py`. Reassess this change on upstream updates; retire it when upstream
provides equivalent language-independent review. Install a committed revision through Hermes
plugin management instead of editing the deployed plugin tree.

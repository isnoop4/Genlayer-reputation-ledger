# 🛡️ ReputationLedger

Evidence-verified, time-decaying on-chain reputation, built as a [GenLayer](https://genlayer.com) Intelligent Contract.

- **Contract (Studio):** [`0xA1230a1FE664FEf1c83223337d1235D96e9EfcdA`](https://explorer-studio.genlayer.com/address/0xA1230a1FE664FEf1c83223337d1235D96e9EfcdA)
- **Frontend:** `index.html` (static, GitHub Pages ready)
- **Contract source:** `ReputationLedger.py`

## Why this exists

On-chain reputation is only useful if scores can't simply be asserted by a single party. A plain ledger records whatever a trusted reporter says. ReputationLedger instead makes every outcome **prove itself**, and lets anyone **dispute it**, using GenLayer's validator LLM consensus.

## v2 changes (steward feedback)

The first version was a centrally governed, deterministic ledger that did not verify the evidence behind outcomes. v2 fixes both:

| Problem | v2 fix |
| --- | --- |
| No verification of outcome evidence | Every outcome carries an `https` evidence URL. Validators fetch the page (`gl.nondet.web.render`) and an LLM judges `SUPPORTED` / `UNSUPPORTED` / `INCONCLUSIVE`, with consensus via `gl.eq_principle.strict_eq`. Only `SUPPORTED` changes a score. |
| Centrally governed | Reporting is **permissionless**. Registered sources only get a higher weight (unregistered reporters use a low default weight of 10). The owner can only tune source weights and the half-life, and **cannot write or edit scores or events**. |
| No way to correct bad data | `challenge_event` lets anyone submit counter-evidence. If validators judge the claim `CONTRADICTED`, the event is reversed on-chain. |

## How it works

1. **Report.** Anyone calls `record_outcome(subject, kind, delta, claim, evidence_url)`.
2. **Verify.** Validators fetch the evidence and agree on whether it supports the claim. Unsupported claims revert and never touch the score.
3. **Score.** Impact is `delta × weight`. Scores decay exponentially with a configurable half-life, so recent behaviour matters most.
4. **Challenge.** Anyone can call `challenge_event(event_id, counter_evidence_url)` with different evidence. A `CONTRADICTED` verdict reverses the event.
5. **Assess.** `assess(subject)` asks validators for a short AI trust summary of recent history.

Anti-abuse rules: delta must match the outcome kind's sign and cannot be 0; a reporter cannot rate themselves or challenge their own event; the same evidence URL cannot score the same subject and kind twice, regardless of who reports it; page content is passed to the LLM as untrusted data.

## Contract API

**Write**

| Method | Who | Purpose |
| --- | --- | --- |
| `record_outcome(subject, kind, delta, claim, evidence_url)` | anyone | Report a verified outcome |
| `challenge_event(event_id, counter_evidence_url)` | anyone (not the original reporter) | Reverse an event with counter-evidence |
| `assess(subject)` | anyone | AI trust summary |
| `register_source` / `update_weight` / `revoke_source` | owner | Tune weights only |
| `set_half_life` / `transfer_ownership` | owner | Config |

**Read:** `get_score`, `get_raw_score`, `get_event`, `get_history`, `get_subjects`, `get_source`, `get_sources`, `get_assessment`, `get_counts`, `get_owner`.

Outcome kinds: `DISPUTE_WIN`, `DISPUTE_LOSS`, `ESCROW_COMPLETED`, `ESCROW_FAILED`, `VERIFICATION_PASSED`, `VERIFICATION_FAILED`. Positive kinds need a positive delta, negative kinds a negative one.

## Tested on GenLayer Studio

- ✅ Valid public evidence → validators return `SUPPORTED`, score increases
- ✅ Irrelevant evidence (`https://example.com`) → rejected with `Evidence not verified: UNSUPPORTED`, score unchanged
- ✅ Counter-evidence → validators return `CONTRADICTED`, event reversed (`reversed: true`), score returns to 0
- ✅ Weak counter-evidence → `UPHELD`, event stays

## Run the frontend

It is a single static file using [`genlayer-js`](https://github.com/genlayerlabs/genlayer-js) from a CDN.

1. Open `index.html` locally or via GitHub Pages (Settings → Pages → deploy from `main`).
2. Click **Connect wallet** (MetaMask) to send transactions. Reads work without a wallet.
3. The contract address is set in `DEFAULT_ADDRESS` at the top of the script. The ⚙︎ button overrides it in the browser. Leave it empty for demo mode with sample data.

## Deploy your own

1. Open [GenLayer Studio](https://studio.genlayer.com), paste `ReputationLedger.py`, and deploy (no constructor args).
2. Optionally call `register_source` for trusted contracts that should carry higher weight.
3. Put the new address into `DEFAULT_ADDRESS` in `index.html`.

## Notes

- Evidence must be a public `https` page. Validators only see what they can fetch, and page text is truncated to 6000 characters.
- Verdicts are LLM-based, so keep claims specific and evidence explicit. Ambiguous evidence resolves to `INCONCLUSIVE` / `UPHELD` by design.

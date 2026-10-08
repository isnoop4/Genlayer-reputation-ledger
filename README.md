# 🛡️ ReputationLedger

Time-decaying, source-weighted on-chain reputation for GenLayer, with AI trust summaries.

**Live demo:** https://isnoop4.github.io/Genlayer-reputation-ledger/

**Repo:** https://github.com/isnoop4/Genlayer-reputation-ledger

## Deployed contract
- Network: GenLayer Studio (studionet)
- Address: `0x94853F7De40e60431424E6a58E91B8d24E248B3B`
- Explorer: https://explorer-studio.genlayer.com/address/0x94853F7De40e60431424E6a58E91B8d24E248B3B

## What it does
- **Trusted sources** (escrow, dispute court, verifiers) are registered by the owner with a weight 0–100.
- Sources call `record_outcome(subject, kind, delta, context_hash)`; impact = `delta × weight`.
- Scores **decay with a half-life** (default 180 days), so recent behaviour matters most.
- `assess(subject)` asks validators' LLMs for a one-sentence trust summary, reduced to one constrained verdict (POSITIVE/MIXED/NEGATIVE) that validators agree on via strict equivalence.
- Tiers: `UNRATED · RISKY · NEUTRAL · TRUSTED · ELITE`.

## Safety rules
Only owner-approved sources can write · a source can't rate itself · same (source, subject, context) can't be replayed · bounded deltas and score cap · revocable sources · ownership transfer.

## Deploy
1. Open [GenLayer Studio](https://studio.genlayer.com), paste `contracts/reputation_ledger.py`, deploy (no constructor args).
2. Put the contract address in `DEFAULT_ADDRESS` inside `index.html` (already set to the deployment above; or use ⚙︎ Contract on the page).
3. Push to GitHub → Settings → Pages → deploy from `main` / root.
4. Register sources with `register_source`, report with `record_outcome`, then try `assess`.

## Files
- `contracts/reputation_ledger.py` — Intelligent Contract
- `index.html` — single-file frontend (genlayer-js via esm.sh; demo mode without an address)

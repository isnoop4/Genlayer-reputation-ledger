# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
from datetime import datetime
import json


KINDS = (
    "DISPUTE_WIN",
    "DISPUTE_LOSS",
    "ESCROW_COMPLETED",
    "ESCROW_FAILED",
    "VERIFICATION_PASSED",
    "VERIFICATION_FAILED",
)

DEFAULT_HALF_LIFE = 180 * 24 * 60 * 60
SCALE = 1000
MAX_DELTA = 100 * SCALE
MAX_SCORE = 1000 * SCALE


class ReputationLedger(gl.Contract):
    """
    On-chain reputation ledger. Registered sources (escrow, dispute court,
    verifiers, ...) report outcomes about a subject address. Each outcome is
    weighted by the source's trust weight, and the running score decays
    exponentially with a configurable half-life, so old behaviour matters less.
    An optional AI assessment (LLM verdict agreed via strict equivalence) turns
    the numeric history into a short human-readable trust summary.
    """

    owner: Address

    source_weight: TreeMap[str, u256]
    source_label: TreeMap[str, str]
    sources: DynArray[str]

    raw_score: TreeMap[str, i256]
    last_update: TreeMap[str, u256]
    event_count: TreeMap[str, u256]
    subject_events: TreeMap[str, u256]
    subjects: DynArray[str]
    events: TreeMap[u256, str]
    seen: TreeMap[str, u256]
    assessments: TreeMap[str, str]

    next_event_id: u256
    half_life: u256

    def __init__(self) -> None:
        self.owner = gl.message.sender_address
        self.next_event_id = u256(0)
        self.half_life = u256(DEFAULT_HALF_LIFE)

    # ------------------------------------------------------------------ helpers

    def _norm(self, address: str) -> str:
        if not isinstance(address, str):
            raise Exception("Address must be a string.")
        value = address.strip()
        if len(value) != 42 or not value.startswith("0x"):
            raise Exception("Invalid address.")
        if not all(c in "0123456789abcdefABCDEF" for c in value[2:]):
            raise Exception("Invalid address.")
        return value.lower()

    def _now(self) -> int:
        # Transaction timestamp agreed by consensus (deterministic across validators).
        try:
            raw = gl.message_raw["datetime"]
            return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
        except Exception:
            return 0

    def _is_owner(self) -> bool:
        return gl.message.sender_address == self.owner

    def _decay(self, value: int, elapsed: int) -> int:
        """Half-life decay in integer math: whole halvings by shift, remainder linear."""
        if value == 0 or elapsed <= 0:
            return value
        hl = int(self.half_life)
        sign = -1 if value < 0 else 1
        mag = abs(value)
        halvings = elapsed // hl
        if halvings >= 64:
            return 0
        mag >>= halvings
        rem = elapsed % hl
        mag = (mag * (2 * hl - rem)) // (2 * hl)
        return sign * mag

    def _round_score(self, scaled: int) -> int:
        """Round scaled value to nearest whole point (symmetric for negatives)."""
        sign = -1 if scaled < 0 else 1
        return sign * ((abs(scaled) + SCALE // 2) // SCALE)

    def _current(self, key: str, now: int) -> int:
        raw = int(self.raw_score.get(key, i256(0)))
        last = int(self.last_update.get(key, u256(0)))
        if last == 0:
            return raw
        return self._decay(raw, now - last)

    def _tier(self, score: int, events: int) -> str:
        if events == 0:
            return "UNRATED"
        if score < -20:
            return "RISKY"
        if score < 20:
            return "NEUTRAL"
        if score < 100:
            return "TRUSTED"
        return "ELITE"

    # -------------------------------------------------------------------- admin

    @gl.public.write
    def register_source(self, source: str, label: str, weight: int) -> None:
        if not self._is_owner():
            raise Exception("Only the owner can register sources.")
        key = self._norm(source)
        if weight < 0 or weight > 100:
            raise Exception("Weight must be 0-100.")
        lbl = (label or "").strip()
        if not lbl:
            raise Exception("Label cannot be empty.")
        if len(lbl) > 64:
            raise Exception("Label too long (max 64).")
        if key not in self.source_weight:
            self.sources.append(key)
        self.source_weight[key] = u256(weight)
        self.source_label[key] = lbl

    @gl.public.write
    def update_weight(self, source: str, weight: int) -> None:
        if not self._is_owner():
            raise Exception("Only the owner can update weights.")
        key = self._norm(source)
        if key not in self.source_weight:
            raise Exception("Source not registered.")
        if weight < 0 or weight > 100:
            raise Exception("Weight must be 0-100.")
        self.source_weight[key] = u256(weight)

    @gl.public.write
    def revoke_source(self, source: str) -> None:
        if not self._is_owner():
            raise Exception("Only the owner can revoke sources.")
        key = self._norm(source)
        if key not in self.source_weight:
            raise Exception("Source not registered.")
        self.source_weight[key] = u256(0)

    @gl.public.write
    def set_half_life(self, seconds: int) -> None:
        if not self._is_owner():
            raise Exception("Only the owner can set half-life.")
        if seconds < 3600 or seconds > 10 * 365 * 24 * 3600:
            raise Exception("Half-life out of range.")
        self.half_life = u256(seconds)

    @gl.public.write
    def transfer_ownership(self, new_owner: str) -> None:
        if not self._is_owner():
            raise Exception("Only the owner can transfer ownership.")
        self.owner = Address(self._norm(new_owner))

    # ------------------------------------------------------------------- scoring

    @gl.public.write
    def record_outcome(self, subject: str, kind: str, delta: int, context_hash: str) -> int:
        sender = self._norm(str(gl.message.sender_address))

        if sender not in self.source_weight:
            raise Exception("Caller is not a registered source.")
        weight = int(self.source_weight[sender])
        if weight <= 0:
            raise Exception("Source has been revoked.")

        subj = self._norm(subject)
        if subj == sender:
            raise Exception("A source cannot rate itself.")

        event_kind = (kind or "").strip().upper()
        if event_kind not in KINDS:
            raise Exception("Unknown kind.")

        if not isinstance(delta, int) or isinstance(delta, bool):
            raise Exception("Delta must be an integer.")
        if delta < -100 or delta > 100:
            raise Exception("Delta must be -100..100.")

        ctx = (context_hash or "").strip()
        if not ctx:
            raise Exception("context_hash required.")
        if len(ctx) > 128:
            raise Exception("context_hash too long (max 128).")

        # Replay protection: same source cannot report the same context twice for a subject.
        dedupe = sender + "|" + subj + "|" + ctx
        if dedupe in self.seen:
            raise Exception("Outcome already recorded for this context.")
        self.seen[dedupe] = u256(1)

        effective = (delta * weight * SCALE) // 100
        effective = max(-MAX_DELTA, min(MAX_DELTA, effective))

        now = self._now()
        current = self._current(subj, now)
        updated = max(-MAX_SCORE, min(MAX_SCORE, current + effective))

        event_id = self.next_event_id
        self.next_event_id = event_id + u256(1)

        event = {
            "id": int(event_id),
            "source": sender,
            "subject": subj,
            "kind": event_kind,
            "delta": delta,
            "weight": weight,
            "effective": effective,
            "context_hash": ctx,
            "timestamp": now,
        }
        self.events[event_id] = json.dumps(event, separators=(",", ":"))

        count = int(self.event_count.get(subj, u256(0)))
        if count == 0:
            self.subjects.append(subj)
        self.subject_events[subj + ":" + str(count)] = event_id
        self.event_count[subj] = u256(count + 1)

        self.raw_score[subj] = i256(updated)
        self.last_update[subj] = u256(now)

        return int(event_id)

    # ------------------------------------------------------------- AI assessment

    @gl.public.write
    def assess(self, subject: str) -> str:
        """Ask validators' LLMs for a short trust summary of a subject's history."""
        subj = self._norm(subject)
        count = int(self.event_count.get(subj, u256(0)))
        if count == 0:
            raise Exception("No history for this subject.")

        score = self._round_score(self._current(subj, self._now()))
        tier = self._tier(score, count)

        lines = []
        for i in range(max(0, count - 10), count):
            ev = json.loads(self.events[self.subject_events[subj + ":" + str(i)]])
            lines.append(ev["kind"] + " (impact " + str(self._round_score(ev["effective"])) + ")")

        prompt = (
            "You assess on-chain reputation. Subject tier: " + tier
            + ", score: " + str(score) + ", events: " + str(count)
            + ". Recent events: " + "; ".join(lines)
            + ". Classify overall trustworthiness. Reply with EXACTLY one word from: "
            "POSITIVE, MIXED, NEGATIVE. No other text."
        )

        def run() -> str:
            out = gl.nondet.exec_prompt(prompt).strip().upper()
            for word in ("POSITIVE", "NEGATIVE", "MIXED"):
                if word in out:
                    return word
            return "MIXED"

        # Single constrained token -> validators can reach strict agreement.
        verdict = gl.eq_principle.strict_eq(run)

        sentences = {
            "POSITIVE": "Reliable track record with mostly favorable outcomes.",
            "MIXED": "Mixed track record; outcomes are not clearly favorable or unfavorable.",
            "NEGATIVE": "Unfavorable track record; treat with caution.",
        }
        summary = (
            tier + " | AI verdict: " + verdict + " - "
            + sentences.get(verdict, sentences["MIXED"])
            + " (" + str(count) + " events, score " + str(score) + ")"
        )
        self.assessments[subj] = summary
        return summary

    # --------------------------------------------------------------------- views

    @gl.public.view
    def get_counts(self) -> dict:
        return {
            "sources": len(self.sources),
            "subjects": len(self.subjects),
            "events": int(self.next_event_id),
            "half_life": int(self.half_life),
        }

    @gl.public.view
    def get_owner(self) -> str:
        return str(self.owner)

    @gl.public.view
    def get_source(self, source: str) -> dict:
        key = self._norm(source)
        if key not in self.source_weight:
            return {"registered": False}
        weight = int(self.source_weight.get(key, u256(0)))
        return {
            "registered": True,
            "address": key,
            "label": self.source_label.get(key, ""),
            "weight": weight,
            "revoked": weight <= 0,
        }

    @gl.public.view
    def get_sources(self) -> list:
        result = []
        for source in self.sources:
            weight = int(self.source_weight.get(source, u256(0)))
            result.append({
                "address": source,
                "label": self.source_label.get(source, ""),
                "weight": weight,
                "revoked": weight <= 0,
            })
        return result

    @gl.public.view
    def get_event(self, event_id: int) -> dict:
        if event_id < 0:
            raise Exception("Invalid event ID.")
        key = u256(event_id)
        if key not in self.events:
            raise Exception("Event not found.")
        return json.loads(self.events[key])

    @gl.public.view
    def get_history(self, subject: str, offset: int, limit: int) -> list:
        key = self._norm(subject)
        count = int(self.event_count.get(key, u256(0)))
        if offset < 0 or limit <= 0:
            return []
        limit = min(limit, 50)
        out = []
        # newest first
        start = count - 1 - offset
        i = start
        while i >= 0 and len(out) < limit:
            out.append(json.loads(self.events[self.subject_events[key + ":" + str(i)]]))
            i -= 1
        return out

    @gl.public.view
    def get_subjects(self, offset: int, limit: int) -> list:
        if offset < 0 or limit <= 0:
            return []
        limit = min(limit, 50)
        total = len(self.subjects)
        return [self.subjects[i] for i in range(offset, min(total, offset + limit))]

    @gl.public.view
    def get_raw_score(self, subject: str) -> int:
        return int(self.raw_score.get(self._norm(subject), i256(0)))

    @gl.public.view
    def get_assessment(self, subject: str) -> str:
        return self.assessments.get(self._norm(subject), "")

    @gl.public.view
    def get_score(self, subject: str) -> dict:
        key = self._norm(subject)
        stored = int(self.raw_score.get(key, i256(0)))
        count = int(self.event_count.get(key, u256(0)))
        decayed = self._current(key, self._now())
        score = self._round_score(decayed)
        return {
            "address": key,
            "score": score,
            "raw_scaled": decayed,
            "stored_scaled": stored,
            "events": count,
            "tier": self._tier(score, count),
            "last_update": int(self.last_update.get(key, u256(0))),
            "half_life": int(self.half_life),
        }

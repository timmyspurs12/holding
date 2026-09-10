# {
#   "Seq": [
#     { "Depends": "py-lib-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
#   ]
# }
"""HOLDING — PrecedentAdjudicator.

The reference consumer contract. It closes the loop:

    CASE -> ADJUDICATION -> FINALITY -> HOLDING -> INDEX ->
    PRECEDENT RETRIEVAL -> NEW ADJUDICATION -> FOLLOW OR DISTINGUISH -> NEW HOLDING

Two things here are the whole point of the product:

1. Precedent is fetched *before* the panel rules, with a synchronous cross-contract
   view call. The retrieval happens inside GenVM, so every validator recomputes it
   and nobody can curate what the panel sees.

2. The holding is emitted with `on='finalized'`, not `on='accepted'`. A holding is
   therefore created only after the originating adjudication has passed its appeal
   window — never because a leader merely proposed a verdict.

The prompt constants below are mirrored from `shared/holding_core/precedent.py`;
`tests/test_mirror_sync.py` fails if they drift.

This contract is a reference implementation for integrators. It is deliberately
small: register it as a source on the HoldingRegistry and it will produce holdings.
"""

from genlayer import *
from dataclasses import dataclass

# --- BEGIN MIRRORED PROMPT (shared/holding_core/precedent.py) ---
ADJUDICATION_OUTPUT_CONTRACT = """{
  "issue": "the question actually decided, in one sentence",
  "facts": ["material fact", "material fact"],
  "verdict": "APPROVED | REJECTED | PARTIAL",
  "ratio": "the reason, in one sentence — the binding part",
  "reason_codes": ["UPPER_SNAKE_CASE"],
  "precedent_used": ["HLD-000184"],
  "followed": true,
  "distinguished": false,
  "distinguishment_reason": "one sentence naming the material difference, or empty string",
  "reasoning": "short explanation of how the precedent was applied or departed from"
}"""

DISTINGUISHING_INSTRUCTION = """PRECEDENT RULE
Consider the retrieved precedent. Follow materially applicable precedent unless
the current facts contain a material distinction.

If you depart from a relevant holding, you must explicitly identify the material
difference in `distinguishment_reason`, set `distinguished` to true, and name the
holding you departed from in `precedent_used`.

A material difference names something concrete about the facts.
REJECTED: "The circumstances differ." / "This case is different."
ACCEPTED: "The previous holding involved a service that had not yet been fully
delivered; this case concerns a service completed before cancellation."

If no precedent was retrieved, decide the case on its own facts and return an
empty `precedent_used` list."""
# --- END MIRRORED PROMPT (shared/holding_core/precedent.py) ---

SEP = "\u241f"
MIN_DISTINGUISHMENT_CHARS = 40
GENERIC_DISTINGUISHMENTS = (
    "the circumstances differ",
    "circumstances are different",
    "this case is different",
    "the facts differ",
    "not applicable here",
    "does not apply here",
    "different situation",
)


@allow_storage
@dataclass
class CaseRecord:
    case_id: str
    domain: str
    contract_class: str
    facts: str
    status: str
    verdict: str
    issue: str
    ratio: str
    reason_codes: str
    precedent_used: str
    distinguishment: str
    panel_size: u256
    submitted_at: u256


class PrecedentAdjudicator(gl.Contract):
    """An adjudicator that asks HOLDING for precedent before it rules."""

    registry: Address
    domain: str
    contract_class: str
    panel_size: u256
    cases: TreeMap[str, CaseRecord]
    case_ids: DynArray[str]

    def __init__(self, registry: str, domain: str, contract_class: str, panel_size: int = 5):
        self.registry = Address(registry)
        self.domain = str(domain)
        self.contract_class = str(contract_class)
        self.panel_size = u256(int(panel_size))

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _split(self, value: str):
        if value is None or value == "":
            return []
        return value.split(SEP)

    def _format_precedent(self, precedent) -> str:
        if precedent is None or len(precedent) == 0:
            return "No precedent was retrieved. The registry has no comparable holding yet."
        blocks = []
        for item in precedent:
            blocks.append(
                "\n".join(
                    [
                        "HOLDING " + str(item["holding_id"]),
                        "  domain      : " + str(item["domain"]),
                        "  issue       : " + str(item["issue"]),
                        "  facts       : " + str(item["facts_digest"]),
                        "  verdict     : " + str(item["verdict"]),
                        "  ratio       : " + str(item["ratio"]),
                        "  similarity  : " + str(item["similarity"]),
                        "  authority   : " + str(item["authority_bp"]) + " bp",
                    ]
                )
            )
        return "\n\n".join(blocks)

    def _build_prompt(self, case_id: str, facts, precedent) -> str:
        facts_block = "\n".join(["- " + str(f) for f in facts])
        if facts_block == "":
            facts_block = "- (none supplied)"
        return "\n".join(
            [
                "Decide this case.",
                "",
                "CASE " + str(case_id),
                "DOMAIN " + str(self.domain),
                "",
                "MATERIAL FACTS",
                facts_block,
                "",
                "RETRIEVED PRECEDENT",
                self._format_precedent(precedent),
                "",
                DISTINGUISHING_INSTRUCTION,
                "",
                "Return ONLY a JSON object with this shape, no commentary:",
                ADJUDICATION_OUTPUT_CONTRACT,
            ]
        )

    def _decision(self, payload):
        """The stable decision fields validators compare. None means malformed."""
        if not isinstance(payload, dict):
            return None
        verdict = str(payload.get("verdict", "")).strip().upper()
        if verdict not in ("APPROVED", "REJECTED", "PARTIAL"):
            return None
        issue = str(payload.get("issue", "")).strip()
        ratio = str(payload.get("ratio", "")).strip()
        if len(issue) < 8 or len(ratio) < 20:
            return None
        facts = payload.get("facts", [])
        if not isinstance(facts, list) or len(facts) == 0:
            return None
        followed = bool(payload.get("followed", False))
        distinguished = bool(payload.get("distinguished", False))
        reason = str(payload.get("distinguishment_reason", "") or "").strip()
        used = []
        raw_used = payload.get("precedent_used", [])
        if isinstance(raw_used, list):
            for item in raw_used:
                candidate = str(item).strip().upper()
                if candidate.startswith("HLD-") and len(candidate) == 10:
                    used.append(candidate)
        used.sort()
        decided = "DISTINGUISH" if distinguished else "FOLLOW"
        return (verdict, decided, tuple(used), len(reason) > 0)

    def _validate_distinguishment(self, reason: str, distinguished: bool) -> None:
        if not distinguished:
            return
        cleaned = " ".join(str(reason or "").split()).strip()
        if len(cleaned) < MIN_DISTINGUISHMENT_CHARS:
            raise gl.UserError(
                "distinguishment: too short to state a material difference (minimum "
                + str(MIN_DISTINGUISHMENT_CHARS)
                + " characters)"
            )
        lowered = cleaned.lower()
        for phrase in GENERIC_DISTINGUISHMENTS:
            if phrase in lowered:
                raise gl.UserError(
                    "distinguishment: '" + phrase + "' does not identify a material difference"
                )

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    @gl.public.write
    def submit_case(self, case_id: str, facts: list[str]) -> str:
        case_id = " ".join(str(case_id).split()).strip()
        if case_id == "":
            raise gl.UserError("submit_case: case_id required")
        existing = self.cases.get(case_id, None)
        if existing is not None:
            raise gl.UserError("submit_case: case already exists")
        cleaned = [" ".join(str(f).split()).strip() for f in (facts or [])]
        cleaned = [f for f in cleaned if f != ""]
        if len(cleaned) == 0:
            raise gl.UserError("submit_case: at least one material fact is required")

        self.cases[case_id] = CaseRecord(
            case_id=case_id,
            domain=self.domain,
            contract_class=self.contract_class,
            facts=SEP.join(cleaned),
            status="PROPOSED",
            verdict="",
            issue="",
            ratio="",
            reason_codes="",
            precedent_used="",
            distinguishment="",
            panel_size=self.panel_size,
            submitted_at=u256(int(gl.message.timestamp) if hasattr(gl.message, "timestamp") else 0),
        )
        self.case_ids.append(case_id)
        return "PROPOSED"

    @gl.public.write
    def adjudicate(self, case_id: str) -> str:
        case = self.cases.get(case_id, None)
        if case is None:
            raise gl.UserError("adjudicate: unknown case")
        if case.status not in ("PROPOSED",):
            raise gl.UserError("adjudicate: case is not open")

        case.status = "VALIDATING"

        facts = self._split(case.facts)
        registry = gl.get_contract_at(self.registry)
        precedent = registry.view().get_precedent(" ".join(facts), self.domain, 3)
        prompt = self._build_prompt(case_id, facts, precedent)

        def leader_fn():
            return gl.nondet.exec_prompt(prompt, response_format="json")

        def validator_fn(leader_result):
            if not isinstance(leader_result, gl.vm.Return):
                return False
            mine = self._decision(leader_fn())       # independent re-run
            theirs = self._decision(leader_result.calldata)
            if theirs is None or mine is None:
                return False
            return mine == theirs                    # compare decision fields only

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        if self._decision(result) is None:
            raise gl.UserError("adjudicate: malformed adjudication output")

        distinguished = bool(result.get("distinguished", False))
        reason = str(result.get("distinguishment_reason", "") or "").strip()
        self._validate_distinguishment(reason, distinguished)

        used = []
        raw_used = result.get("precedent_used", [])
        if isinstance(raw_used, list):
            for item in raw_used:
                candidate = str(item).strip().upper()
                if candidate.startswith("HLD-") and len(candidate) == 10:
                    used.append(candidate)
        used = sorted(set(used))

        codes = []
        raw_codes = result.get("reason_codes", [])
        if isinstance(raw_codes, list):
            for code in raw_codes:
                codes.append(str(code).strip().upper())

        case.issue = " ".join(str(result.get("issue", "")).split()).strip()
        case.ratio = " ".join(str(result.get("ratio", "")).split()).strip()
        case.verdict = str(result.get("verdict", "")).strip().upper()
        case.reason_codes = SEP.join(codes)
        case.precedent_used = SEP.join(used)
        case.distinguishment = reason if distinguished else ""
        case.status = "CONSENSUS"

        # A holding is created only when this adjudication finalizes.
        registry.emit(on="finalized").create_holding(
            case_id,
            "",
            self.domain,
            self.contract_class,
            case.issue,
            " ".join(facts),
            case.verdict,
            case.ratio,
            codes,
            [],
            int(self.panel_size),
            "NONE",
            "NONE",
            case.distinguishment,
        )

        # Relationships are declared by case id: the holding does not exist yet.
        for holding_id in used:
            if distinguished and holding_id in used:
                relationship = "DISTINGUISHES"
            else:
                relationship = "FOLLOWS"
            registry.emit(on="finalized").cite_by_case(case_id, holding_id, relationship, case_id)

        case.status = "APPEAL_WINDOW"
        return "APPEAL_WINDOW"

    # ------------------------------------------------------------------
    # views
    # ------------------------------------------------------------------
    @gl.public.view
    def get_case(self, case_id: str) -> dict:
        case = self.cases.get(case_id, None)
        if case is None:
            return {}
        return {
            "case_id": case.case_id,
            "domain": case.domain,
            "contract_class": case.contract_class,
            "facts": self._split(case.facts),
            "status": case.status,
            "verdict": case.verdict,
            "issue": case.issue,
            "ratio": case.ratio,
            "reason_codes": self._split(case.reason_codes),
            "precedent_used": self._split(case.precedent_used),
            "distinguishment": case.distinguishment,
            "distinguished": case.distinguishment != "",
            "followed": case.precedent_used != "" and case.distinguishment == "",
            "panel_size": int(case.panel_size),
            "submitted_at": int(case.submitted_at),
            "holding_id": self._holding_for_case(case.case_id),
        }

    def _holding_for_case(self, case_id: str) -> str:
        """The holding this case produced, or "" while the tx is not final."""
        registry = gl.get_contract_at(self.registry)
        record = registry.view().get_holding_by_case(case_id)
        return str(record.get("holding_id", "")) if isinstance(record, dict) else ""

    @gl.public.view
    def get_case_ids(self) -> list[str]:
        return [cid for cid in self.case_ids]

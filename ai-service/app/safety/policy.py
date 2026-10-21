from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

SAFETY_LAYER_VERSION = "1.0.0"


class Severity(str, enum.Enum):

    PROHIBITED = "prohibited"
    REDACTABLE = "redactable"
    REQUIRED = "required"
    STRUCTURAL = "structural"


class ViolationCode(str, enum.Enum):

    UNSUPPORTED_DIAGNOSIS = "UNSUPPORTED_DIAGNOSIS"
    MEDICATION_REFERENCE = "MEDICATION_REFERENCE"
    MEDICATION_DOSAGE = "MEDICATION_DOSAGE"
    UNSAFE_TREATMENT_INSTRUCTION = "UNSAFE_TREATMENT_INSTRUCTION"
    CERTAINTY_CLAIM = "CERTAINTY_CLAIM"
    REPLACES_PROFESSIONAL_CONSULTATION = "REPLACES_PROFESSIONAL_CONSULTATION"

    CLINICIAN_VOICE = "CLINICIAN_VOICE"
    UNPERMITTED_DIRECTIVE = "UNPERMITTED_DIRECTIVE"

    UNHEDGED_INTERPRETIVE_CLAIM = "UNHEDGED_INTERPRETIVE_CLAIM"
    UNGROUNDED_NUMERIC_CLAIM = "UNGROUNDED_NUMERIC_CLAIM"
    GROUNDING_REQUIRED_BUT_ABSENT = "GROUNDING_REQUIRED_BUT_ABSENT"
    MISSING_PROFESSIONAL_REFERRAL = "MISSING_PROFESSIONAL_REFERRAL"

    UNANALYSABLE_INPUT = "UNANALYSABLE_INPUT"
    EMPTY_OUTPUT = "EMPTY_OUTPUT"
    INPUT_TOO_LARGE = "INPUT_TOO_LARGE"
    VALIDATOR_ERROR = "VALIDATOR_ERROR"
    REDACTION_NOT_POSSIBLE = "REDACTION_NOT_POSSIBLE"


CODE_SEVERITY: Dict[ViolationCode, Severity] = {
    ViolationCode.UNSUPPORTED_DIAGNOSIS: Severity.PROHIBITED,
    ViolationCode.MEDICATION_REFERENCE: Severity.PROHIBITED,
    ViolationCode.MEDICATION_DOSAGE: Severity.PROHIBITED,
    ViolationCode.UNSAFE_TREATMENT_INSTRUCTION: Severity.PROHIBITED,
    ViolationCode.CERTAINTY_CLAIM: Severity.PROHIBITED,
    ViolationCode.CLINICIAN_VOICE: Severity.PROHIBITED,
    ViolationCode.UNHEDGED_INTERPRETIVE_CLAIM: Severity.PROHIBITED,
    ViolationCode.UNGROUNDED_NUMERIC_CLAIM: Severity.PROHIBITED,
    ViolationCode.GROUNDING_REQUIRED_BUT_ABSENT: Severity.PROHIBITED,
    ViolationCode.REPLACES_PROFESSIONAL_CONSULTATION: Severity.REDACTABLE,
    ViolationCode.UNPERMITTED_DIRECTIVE: Severity.REDACTABLE,
    ViolationCode.MISSING_PROFESSIONAL_REFERRAL: Severity.REQUIRED,
    ViolationCode.UNANALYSABLE_INPUT: Severity.STRUCTURAL,
    ViolationCode.EMPTY_OUTPUT: Severity.STRUCTURAL,
    ViolationCode.INPUT_TOO_LARGE: Severity.STRUCTURAL,
    ViolationCode.VALIDATOR_ERROR: Severity.STRUCTURAL,
    ViolationCode.REDACTION_NOT_POSSIBLE: Severity.STRUCTURAL,
}


@dataclass(frozen=True)
class SafetyRule:

    rule_id: str
    code: ViolationCode
    reason: str
    positive_control: bool = False
    pattern: Optional["re.Pattern[str]"] = None
    sentence_scoped: bool = False

    @property
    def severity(self) -> Severity:
        return CODE_SEVERITY[self.code]


def _p(pattern: str) -> "re.Pattern[str]":
    return re.compile(pattern, re.IGNORECASE)


_GAP = r"\W{1,4}"


def _phrase(pattern: str) -> str:
    return _GAP.join(part for part in pattern.split(" "))


PERMITTED_DIRECTIVE_VERBS: Tuple[str, ...] = (
    "discuss",
    "talk",
    "speak",
    "ask",
    "consult",
    "see",
    "contact",
    "share",
    "mention",
    "bring",
    "raise",
    "seek",
    "consider",
    "review",
    "check",
    "confirm",
    "note",
    "remember",
    "read",
    "upload",
    "keep",
)

IMPERATIVE_ACTION_VERBS: Tuple[str, ...] = (
    "take",
    "takes",
    "swallow",
    "chew",
    "inject",
    "administer",
    "apply",
    "start",
    "stop",
    "begin",
    "continue",
    "discontinue",
    "increase",
    "decrease",
    "reduce",
    "double",
    "halve",
    "split",
    "skip",
    "switch",
    "supplement",
    "medicate",
    "self-medicate",
    "dose",
    "cure",
    "eat",
    "drink",
    "consume",
    "ingest",
    "buy",
    "purchase",
    "order",
    "fast",
    "ignore",
    "delay",
    "postpone",
    "cancel",
    "avoid",
)

INTERPRETIVE_VERBS: Tuple[str, ...] = (
    "means",
    "indicates",
    "indicate",
    "shows",
    "show",
    "proves",
    "prove",
    "demonstrates",
    "reveals",
    "signals",
    "signifies",
    "implies",
    "reflects",
    "points to",
    "is a sign of",
    "is evidence of",
    "tells us",
    "tells you",
)

HEDGE_MARKERS: Tuple[str, ...] = (
    "may",
    "might",
    "can",
    "could",
    "would",
    "often",
    "usually",
    "typically",
    "generally",
    "commonly",
    "sometimes",
    "frequently",
    "in general",
    "tends to",
    "tend to",
    "possible",
    "possibly",
    "potentially",
    "likely",
    "unlikely",
    "not necessarily",
    "associated with",
    "in some",
    "for some",
    "rarely",
    "does not on its own",
    "on its own",
    "suggest",
    "suggests",
    "one of several",
)

def _clinical_subject_terms() -> Tuple[str, ...]:
    terms = {
        "you",
        "your",
        "you're",
        "patient",
        "patient's",
        "result",
        "results",
        "finding",
        "findings",
        "reading",
        "readings",
        "report",
        "risk",
        "condition",
        "disease",
        "deficiency",
        "levels",
        "level",
    }
    try:
        from app.data.conditions import CONDITIONS

        for condition in CONDITIONS:
            terms.add(str(condition).lower())
    except Exception:
        pass
    return tuple(sorted(terms, key=len, reverse=True))


CLINICAL_SUBJECT_TERMS: Tuple[str, ...] = _clinical_subject_terms()

CLINICAL_SUBJECT = _p(
    r"\b(" + "|".join(re.escape(t) for t in CLINICAL_SUBJECT_TERMS) + r")\b"
)


PROFESSIONAL_REFERENCE = _p(
    r"\b(qualified\s+)?(healthcare|health\s?care|health|medical)\s+"
    r"(professional|practitioner|provider|team)s?\b"
    r"|\b(doctor|physician|clinician|general\s+practitioner|"
    r"nephrologist|cardiologist|endocrinologist|pharmacist|nurse)s?\b"
    r"|\bGP\b"
)


_GAP_SAME_SENTENCE = r"[^\w.!?;]{1,4}"

_DIAGNOSIS_CARRIER = (
    r"(?:you" + _GAP + r"have|you've" + _GAP + r"got"
    r"|you" + _GAP + r"are" + _GAP + r"suffering(?:" + _GAP + r"from)?"
    r"|you" + _GAP + r"suffer" + _GAP + r"from"
    r"|patient" + _GAP + r"has)"
)

_DISEASE_SUFFIX = (
    r"\w{3,}(?:itis|osis|aemia|emia|opathy|oma|uria|penia|plasia|ataxia"
    r"|trophy|ectasis|itides|aemic|emic)"
)
_DISEASE_HEAD = (
    r"(?:disease|syndrome|disorder|deficiency|failure|insufficiency|infection"
    r"|attack|infarction|embolism|aneurysm)"
)
_DISEASE_NAMED = (
    r"(?:hiv|aids|covid(?:-?19)?|gout|lupus|tuberculosis|sepsis|asthma"
    r"|diabetes|diabetic|anaemia|anemia|anaemic|anemic|hypertension"
    r"|hypotension|hypothyroidism|hyperthyroidism|cancer|ckd|stroke"
    r"|cirrhosis|hepatitis|leukaemia|leukemia|lymphoma|myeloma)"
)


_DIAGNOSIS_EXCUSE = (
    r"(?:an?" + _GAP_SAME_SENTENCE + r")?(?:\w+" + _GAP_SAME_SENTENCE + r"){0,3}?"
    r"(?:risk|chance|likelihood|probability|predisposition|history"
    r"|screening|test|tests|result|results|value|values|reading|readings"
    r"|appointment|follow-?up|question|questions|copy|report|option|options)\b"
)


RULES: Tuple[SafetyRule, ...] = (
    SafetyRule(
        rule_id="diagnosis.assertion",
        code=ViolationCode.UNSUPPORTED_DIAGNOSIS,
        reason=(
            "Asserts, or reports as settled, a diagnosis. This system produces "
            "an educational analysis and is not permitted to diagnose."
        ),
        pattern=_p(
            r"\bdiagnos\w*"
            r"|\b(you" + _GAP + r"have|you've" + _GAP + r"got"
            r"|you" + _GAP + r"are" + _GAP + r"suffering(" + _GAP + r"from)?"
            r"|you" + _GAP + r"suffer" + _GAP + r"from"
            r"|patient" + _GAP + r"has|this" + _GAP + r"is)" + _GAP + r"(an?" + _GAP + r")?"
            + _phrase(
                r"(diabetes|diabetic|anaemia|anemia|anaemic|anemic|kidney disease"
                r"|chronic kidney disease|ckd|heart disease|hypertension"
                r"|hypothyroidism|hyperthyroidism|cancer|liver disease)"
            )
            + r"\b"
            r"|\byou" + _GAP + r"are" + _GAP + r"(diabetic|anaemic|anemic|hypertensive|pre-?diabetic)\b"
            + r"|\b" + _DIAGNOSIS_CARRIER
            + r"(?!" + _GAP_SAME_SENTENCE + _DIAGNOSIS_EXCUSE + r")"
            + _GAP_SAME_SENTENCE
            + r"(?:(?:an?|the|your)" + _GAP_SAME_SENTENCE + r")?"
            + r"(?:\w+" + _GAP_SAME_SENTENCE + r"){0,3}?"
            + r"(?:" + _DISEASE_SUFFIX + r"|" + _DISEASE_HEAD + r"|" + _DISEASE_NAMED + r")\b"
        ),
    ),
    SafetyRule(
        rule_id="assertion.clinical_state",
        code=ViolationCode.UNHEDGED_INTERPRETIVE_CLAIM,
        reason=(
            "States the reader's clinical condition as settled fact. This "
            "system reports what a value is and how it compares with a "
            "configured threshold; it may not tell someone what their state IS."
        ),
        pattern=_p(
            "|".join(
                (
                    _phrase(
                        r"your (kidneys?|livers?|hearts?|thyroids?|pancreas|lungs?"
                        r"|organs?|immune system|blood sugar|blood pressure)"
                        r" (is|are|has|have) "
                        r"(failing|failed|damaged|diseased|dying|deteriorating"
                        r"|compromised|shutting down|in failure|out of control"
                        r"|dangerously \w+)"
                    ),
                    _phrase(
                        r"(nothing (is wrong|to worry about)|no cause for concern"
                        r"|no need to worry)"
                    ),
                    _phrase(
                        r"(you|your results?|your report|everything) (is|are) "
                        r"((completely|perfectly|totally|entirely|absolutely) )?"
                        r"(fine|normal|healthy|okay|ok|clear|good)"
                    ),
                    _phrase(
                        r"you (do not|don't) have (an? )?"
                        r"(diabetes|anaemia|anemia|kidney disease|heart disease"
                        r"|hypertension|cancer|liver disease)"
                    ),
                )
            )
        ),
    ),
    SafetyRule(
        rule_id="medication.named",
        code=ViolationCode.MEDICATION_REFERENCE,
        reason=(
            "Names a medication or a drug class. Only a prescriber may raise a "
            "specific drug with a patient."
        ),
        pattern=_p(
            r"\b(?<!enough )(?<!little )(?<!much )(?<!produce )(?<!produces )"
            r"(?<!producing )(?<!make )(?<!makes )(?<!making )(?<!hormone )"
            r"(?<!uses )(?<!using )(?<!own )(?<!called )"
            r"insulin\b(?!\s+(?:resistance|resistant|sensitivity|production))"
            r"|\b(metformin|glimepiride|gliclazide|sitagliptin"
            r"|empagliflozin|atorvastatin|simvastatin|rosuvastatin|statins?"
            r"|fibrate|ezetimibe|aspirin|clopidogrel|warfarin|heparin"
            r"|ibuprofen|paracetamol|acetaminophen|levothyroxine|thyroxine"
            r"|amlodipine|lisinopril|ramipril|losartan|telmisartan|atenolol"
            r"|metoprolol|furosemide|spironolactone|prednisone|prednisolone"
            r"|antibiotics?|ferrous\s+\w+|iron\s+tablets?|cholecalciferol"
            r"|ergocalciferol|cyanocobalamin|hydroxocobalamin|erythropoietin"
            r"|allopurinol|omeprazole|pantoprazole|dapagliflozin|pioglitazone"
            r"|glibenclamide|glyburide|repaglinide|liraglutide|semaglutide"
            r"|fenofibrate|niacin|ezetimibe)\b"
        ),
    ),
    SafetyRule(
        rule_id="medication.class_stem",
        code=ViolationCode.MEDICATION_REFERENCE,
        reason=(
            "Uses a pharmacological class stem. Any word ending -statin, "
            "-pril, -sartan, -olol, -gliptin, -flozin and so on names a drug "
            "whether or not anyone thought to list it."
        ),
        pattern=_p(
            r"\b\w{3,}("
            r"statins?|prils?|sartans?|olols?|dipines?|zosins?|parins?"
            r"|prazoles?|azoles?|tidines?|gliptins?|glitazones?|flozins?"
            r"|glinides?|cillins?|mycins?|micins?|floxacins?|cyclines?"
            r"|sulfamethoxazole|mabs?|nibs?|triptans?|setrons?|caines?"
            r"|semides?|thiazides?|(?<!choles)terols?|sonides?|afils?|profens?"
            r"|oxetines?|udines?|navirs?|ciclovirs?|(?<!mag)azines?"
            r"|barbitals?|zepams?|zolams?|codones?|morphones?"
            r")\b"
        ),
    ),
    SafetyRule(
        rule_id="medication.supplementation",
        code=ViolationCode.MEDICATION_REFERENCE,
        reason=(
            "Recommends supplementation. A supplement has a dose and an "
            "interaction profile; it is a clinical decision, not education."
        ),
        pattern=_p(r"\b(supplements?|supplementation|supplementing)\b"),
    ),
    SafetyRule(
        rule_id="dosage.quantity",
        code=ViolationCode.MEDICATION_DOSAGE,
        reason="States a quantity of a substance to put in a body.",
        pattern=_p(
            r"\b\d+(\.\d+)?\s*"
            r"(mg|mcg|ug|µg|g|kg|ml|l|iu|units?|tablets?|capsules?|pills?)"
            r"\b(?!\s*/)"
        ),
    ),
    SafetyRule(
        rule_id="dosage.non_numeric",
        code=ViolationCode.MEDICATION_DOSAGE,
        reason=(
            "States a dose without using a numeral -- 'half a tablet', 'one "
            "capsule'. A dosage instruction does not need digits to be one."
        ),
        pattern=_p(
            r"\b(a|an|one|two|three|four|half|quarter|another|each|every)\s+"
            r"(of\s+)?(a\s+)?"
            r"(tablets?|capsules?|pills?|spoonfuls?|teaspoons?|tablespoons?"
            r"|sachets?|puffs?|drops?|injections?|shots?|scoops?)\b"
        ),
    ),
    SafetyRule(
        rule_id="dosage.word",
        code=ViolationCode.MEDICATION_DOSAGE,
        reason="Uses dosing vocabulary.",
        pattern=_p(r"\b(dose|doses|dosage|dosing|posology|titrat\w+)\b"),
    ),
    SafetyRule(
        rule_id="dosage.frequency",
        code=ViolationCode.MEDICATION_DOSAGE,
        reason="States a dosing frequency.",
        pattern=_p(
            r"\b(once|twice|three times|four times)\s+(a|per)\s+(day|week)\b"
            r"|\b(daily dose|bd|tds|qds|od|prn)\b"
            r"|\b(once|twice|three times|four times)\s+daily\b"
        ),
    ),
    SafetyRule(
        rule_id="dosage.administration_timing",
        code=ViolationCode.MEDICATION_DOSAGE,
        reason=(
            "Pairs an administration cue with a timing instruction -- the "
            "shape of 'take it at night' / 'with food'."
        ),
        pattern=_p(
            r"\b(tak(e|es|en|ing)|swallow\w*|chew\w*|apply|appli\w+|inject\w*"
            r"|tablets?|capsules?|pills?|doses?)\b[^.!?\n]{0,60}"
            r"\b(at night|at bedtime|before bed|with meals?|with food"
            r"|after meals?|after food|on an empty stomach|before breakfast"
            r"|every morning|every evening|every night|every \d+ hours)\b"
            r"|\b(at night|at bedtime|before bed|with meals?|with food"
            r"|after meals?|after food|on an empty stomach|before breakfast"
            r"|every morning|every evening|every night)\b[^.!?\n]{0,60}"
            r"\b(tak(e|es|en|ing)|swallow\w*|chew\w*|inject\w*|tablets?"
            r"|capsules?|pills?|doses?)\b"
        ),
    ),
    SafetyRule(
        rule_id="dosage.unit_word",
        code=ViolationCode.MEDICATION_DOSAGE,
        reason="Spells out a dosing unit.",
        pattern=_p(
            r"\b(milligrams?|micrograms?|international units?)\b(?!\s+per\s)"
        ),
    ),
    SafetyRule(
        rule_id="treatment.instruction",
        code=ViolationCode.UNSAFE_TREATMENT_INSTRUCTION,
        reason=(
            "Names a treatment, a therapy, a prescription or a procedure as "
            "something to do."
        ),
        pattern=_p(
            r"\b(prescrib\w*"
            r"|(?!treat(?:s|ed|ing)?\s+(?:it|this|that|these|them|such\s+values?|these\s+values?|those\s+values?|the\s+values?"
            r"|the\s+value|the\s+figure)\s+with\s+(?:reduced\s+confidence"
            r"|less\s+confidence|lower\s+confidence|caution|care|scepticism"
            r"|skepticism|suspicion)\s*(?:[.,;:)]|$))treat(?:s|ed|ing|ment|ments)?"
            r"|therapy|therapies|medication|medications|medicine|medicines"
            r"|drugs?|cure|cures|curing|regimen|surgery|injections?|infusions?"
            r"|dialysis|chemotherapy)\b"
        ),
    ),
    SafetyRule(
        rule_id="treatment.self_administration",
        code=ViolationCode.UNSAFE_TREATMENT_INSTRUCTION,
        reason="Tells the reader to start, stop or change something themselves.",
        pattern=_p(
            r"\byou (should|must|need to|ought to|have to)\s+"
            r"(take|start|stop|increase|decrease|reduce|double|halve|inject"
            r"|apply|swallow|use)\b"
            r"|\b(start|stop|continue|discontinue) taking\b"
            r"|\btake (this|these|it|them|one|two|half)\b"
        ),
    ),
    SafetyRule(
        rule_id="certainty.claim",
        code=ViolationCode.CERTAINTY_CLAIM,
        reason=(
            "Claims certainty. A single laboratory result never settles a "
            "question, and the platform must not say that it does."
        ),
        pattern=_p(
            r"\b(definitely|certainly|undoubtedly|guaranteed?|proves?|proven"
            r"|confirms|confirmed|conclusive(ly)?|always means|no doubt"
            r"|will develop|will get|is certain|beyond doubt|without a doubt"
            r"|there is no question|rest assured|nothing to worry about"
            r"|you are fine|you are healthy|perfectly normal|completely normal"
            r"|no cause for concern)\b|\b100\s*%"
        ),
    ),
    SafetyRule(
        rule_id="replacement.dismisses_clinician",
        code=ViolationCode.REPLACES_PROFESSIONAL_CONSULTATION,
        reason=(
            "Presents the system as a substitute for professional medical "
            "care, or tells the reader a consultation is unnecessary."
        ),
        pattern=_p(
            r"\b(no need to (see|consult|visit|contact)"
            r"|instead of (seeing|consulting|visiting)"
            r"|without (seeing|consulting) a (doctor|physician|clinician)"
            r"|do not need to (see|consult|visit)"
            r"|don'?t need to (see|consult|visit)"
            r"|need not (see|consult|visit)"
            r"|saves? you a trip to"
            r"|as good as (a|an) (doctor|physician|clinician|consultation))\b"
            r"|(?<!\bnot[\s])(?<!never[\s])(?<!cannot[\s])(?<!does[\s]not[\s])(?<!is[\s]not[\s])"
            r"(?<!\bno[\s])(?<!doesn't[\s])(?<!can't[\s])"
            r"\breplaces?\b[^.!?\n]{0,40}\b(consultation|consult|doctor"
            r"|physician|clinician|appointment|medical advice|assessment"
            r"|professional|check-?up|examination)\b"
            r"|(?<!\bnot[\s])(?<!never[\s])(?<!cannot[\s])(?<!does[\s]not[\s])(?<!is[\s]not[\s])"
            r"(?<!\bno[\s])\bsubstitutes? for\b"
        ),
    ),
    SafetyRule(
        rule_id="voice.clinician",
        code=ViolationCode.CLINICIAN_VOICE,
        reason=(
            "Speaks in a clinician's first-person voice. The platform is a "
            "tool, not a practitioner, and must never sound like one."
        ),
        pattern=_p(
            r"\bI (recommend|advise|suggest|think|believe|would recommend"
            r"|would advise|would suggest|am concerned)\b"
            r"|\bin my (clinical )?(opinion|view|judgement|judgment)\b"
            r"|\bmy (advice|recommendation|diagnosis)\b"
            r"|\bas your (doctor|physician|clinician)\b"
            r"|\bwe (recommend|advise|prescribe)\b"
        ),
    ),
)


MODIFICATION_POLICY: Dict[str, object] = {
    "verdict": "approve_with_modification",
    "permitted_actions": [
        {
            "action": "append_safety_framing",
            "what_it_does": (
                "Appends fixed text taken verbatim from the reviewed "
                "recommendation catalogue (NOT_A_DIAGNOSIS), which names a "
                "qualified healthcare professional as where the question "
                "belongs."
            ),
            "changes_existing_words": False,
        },
        {
            "action": "redact_sentence",
            "what_it_does": (
                "Removes an entire offending sentence and replaces it with a "
                "fixed notice. Applied ONLY to REPLACES_PROFESSIONAL_"
                "CONSULTATION and UNPERMITTED_DIRECTIVE, whose constructions "
                "are instructions rather than findings, so a redaction cannot "
                "delete an abnormality."
            ),
            "changes_existing_words": False,
        },
    ],
    "forbidden_actions": [
        "paraphrasing or rewording any clinical statement",
        "softening an abnormal finding into reassurance",
        "removing or altering a statement that reports a value or a finding",
        "editing within a sentence (only whole-sentence removal is possible)",
        "salvaging text that contains a PROHIBITED violation",
    ],
    "post_conditions": [
        "the modified text is re-validated in full; any residual violation "
        "turns the verdict into a rejection",
        "if redaction would remove more than half the sentences, or leave "
        "less than 40 characters of original prose, the text is rejected "
        "instead of modified",
    ],
}

SAFETY_POLICY: Dict[str, object] = {
    "module": 24,
    "version": SAFETY_LAYER_VERSION,
    "pipeline": ["LLM Output", "Safety Validation", "Approved Educational Response"],
    "verdicts": ["approve", "approve_with_modification", "reject"],
    "fail_closed": (
        "Anything the validator cannot analyse -- a non-string, an "
        "un-encodable string, control characters, an over-long input, or an "
        "internal error -- is REJECTED. There is no code path that returns "
        "'no violations found' because analysis did not happen."
    ),
    "never_logged": (
        "The text under validation is never written to logs at any level. "
        "Only violation codes, counts and the verdict are logged."
    ),
    "restricted_classes": [
        "unsupported diagnosis",
        "prescription of medication",
        "medication dosage recommendations",
        "unsafe treatment instructions",
        "claims of certainty",
        "replacement of professional medical consultation",
    ],
    "modification": MODIFICATION_POLICY,
    "positive_controls": [
        "a patient-facing explanation must name a qualified healthcare "
        "professional (REQUIRED_PROFESSIONAL_REFERRAL)",
        "an interpretive claim must be hedged (REQUIRED_HEDGING)",
        "a directive to the reader must use a verb from a short permitted "
        "list (DIRECTIVE_VERB_ALLOWLIST)",
        "every number must appear in the retrieved knowledge or the "
        "patient's own validated values (NUMERIC_GROUNDING)",
    ],
    "limitations": [
        "The prohibition rules are a BLOCKLIST. A blocklist cannot enumerate "
        "everything an LLM might say, and this one does not claim to.",
        "The positive controls are lexical, not semantic. They constrain the "
        "REGISTER of a statement and the provenance of its numbers; they "
        "cannot establish that a clinically true statement is clinically "
        "appropriate for this reader.",
        "Nothing here verifies factual correctness. A grounded, hedged, "
        "referral-carrying sentence can still be wrong.",
        "The layer sees text only. It cannot tell whether the explanation "
        "corresponds to the report it claims to describe -- that has to come "
        "from Module 23 passing real grounding.",
        "Paraphrase evades patterns. 'The sugar-control number over three "
        "months' avoids every drug and dosage pattern here; only the hedging "
        "and directive controls would catch an unsafe use of it.",
    ],
}


def rule_document() -> Dict[str, object]:
    pattern_rules: List[Dict[str, object]] = [
        {
            "rule_id": rule.rule_id,
            "code": rule.code.value,
            "severity": rule.severity.value,
            "reason": rule.reason,
            "kind": "positive_control" if rule.positive_control else "blocklist",
        }
        for rule in RULES
    ]
    derived_rules: List[Dict[str, object]] = [
        {
            "rule_id": rule_id,
            "code": code.value,
            "severity": CODE_SEVERITY[code].value,
            "reason": reason,
            "kind": "positive_control",
        }
        for rule_id, code, reason in (
            (
                "positive.required_professional_referral",
                ViolationCode.MISSING_PROFESSIONAL_REFERRAL,
                "A patient-facing explanation must name a qualified "
                "healthcare professional as where the question belongs.",
            ),
            (
                "positive.required_hedging",
                ViolationCode.UNHEDGED_INTERPRETIVE_CLAIM,
                "An interpretive claim must carry a hedge. Unhedged "
                "interpretation is the register of a diagnosis.",
            ),
            (
                "positive.directive_verb_allowlist",
                ViolationCode.UNPERMITTED_DIRECTIVE,
                "A directive aimed at the reader must use a verb from the "
                "permitted list; every other instruction is refused.",
            ),
            (
                "positive.numeric_grounding",
                ViolationCode.UNGROUNDED_NUMERIC_CLAIM,
                "Every number must appear in the retrieved knowledge or in "
                "the patient's own validated values.",
            ),
            (
                "positive.grounding_required",
                ViolationCode.GROUNDING_REQUIRED_BUT_ABSENT,
                "When grounding is required, an ungrounded generation is "
                "refused before its content is considered.",
            ),
        )
    ]
    structural_rules = [
        {
            "rule_id": f"structural.{code.value.lower()}",
            "code": code.value,
            "severity": Severity.STRUCTURAL.value,
            "reason": "Fail-closed: the input could not be analysed.",
            "kind": "fail_closed",
        }
        for code in (
            ViolationCode.UNANALYSABLE_INPUT,
            ViolationCode.EMPTY_OUTPUT,
            ViolationCode.INPUT_TOO_LARGE,
            ViolationCode.VALIDATOR_ERROR,
            ViolationCode.REDACTION_NOT_POSSIBLE,
        )
    ]
    all_rules = pattern_rules + derived_rules + structural_rules
    return {
        "version": SAFETY_LAYER_VERSION,
        "rule_count": len(all_rules),
        "blocklist_rule_count": sum(1 for r in all_rules if r["kind"] == "blocklist"),
        "positive_control_rule_count": sum(
            1 for r in all_rules if r["kind"] == "positive_control"
        ),
        "rules": all_rules,
        "codes": [code.value for code in ViolationCode],
        "severities": [severity.value for severity in Severity],
        "permitted_directive_verbs": list(PERMITTED_DIRECTIVE_VERBS),
    }


def _self_check() -> None:
    seen = set()
    for rule in RULES:
        if rule.rule_id in seen:
            raise ValueError(f"duplicate safety rule id {rule.rule_id!r}")
        seen.add(rule.rule_id)
        if rule.code not in CODE_SEVERITY:
            raise ValueError(f"{rule.rule_id}: {rule.code} has no severity")
        if rule.pattern is None:
            raise ValueError(f"{rule.rule_id}: pattern rules must carry a pattern")
        if not rule.reason.strip():
            raise ValueError(f"{rule.rule_id}: every rule must record why it exists")
    for code in ViolationCode:
        if code not in CODE_SEVERITY:
            raise ValueError(f"{code} has no severity -- it would be un-actionable")
    canary = (
        "Take metformin 500 mg twice a day; this confirms you have diabetes "
        "and you do not need to see a doctor."
    )
    hits = {rule.code for rule in RULES if rule.pattern.search(canary)}
    if len(hits) < 5:
        raise ValueError(
            "the Module 24 rule table no longer detects an obviously unsafe "
            f"sentence -- it has been broken (only matched {sorted(hits)})"
        )


_self_check()


__all__ = [
    "CLINICAL_SUBJECT",
    "CLINICAL_SUBJECT_TERMS",
    "CODE_SEVERITY",
    "HEDGE_MARKERS",
    "IMPERATIVE_ACTION_VERBS",
    "INTERPRETIVE_VERBS",
    "MODIFICATION_POLICY",
    "PERMITTED_DIRECTIVE_VERBS",
    "PROFESSIONAL_REFERENCE",
    "RULES",
    "SAFETY_LAYER_VERSION",
    "SAFETY_POLICY",
    "SafetyRule",
    "Severity",
    "ViolationCode",
    "rule_document",
]

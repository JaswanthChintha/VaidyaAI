"""How to use VaidyaAI -- the help notes the chatbot answers app questions from.

Fixed, reviewed text (owner, 2026-10-09), like the knowledge base: the chatbot
is GROUNDED in these notes for questions about the app, so it cannot invent a
button or a page. Every statement here was checked against the code the day
it was written (file names in the comments). If the app changes, change the
note -- a stale note is a wrong answer.

Matching is deliberately plain: a note is chosen when the question shares its
keywords. No embedding and no model call -- the same reason the knowledge
retriever anchors free text to the catalogue first.

KEYWORDS ARE APP WORDS ONLY (2026-10-09). A matched note is now served WORD
FOR WORD (see `chatbot.answer_question`), so a health word here ("weight",
"results", "doctor") would answer a health question with an app note.
Hyphens are written as spaces ("re analyse"): the question is normalised to
letters and digits before matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class HelpNote:
    note_id: str
    title: str
    keywords: Tuple[str, ...]
    text: str


HELP_NOTES: Tuple[HelpNote, ...] = (
    HelpNote(
        "upload",
        "Uploading a report",
        ("upload", "uploading", "add report", "add a report", "pdf", "jpg", "png", "file size", "attach"),
        # Reports.jsx: accept=".pdf,.jpg,.jpeg,.png", "up to 10 MB".
        "Open the Reports page and use the 'Upload a report' box. Choose a PDF or "
        "a clear photo (JPG or PNG) of a blood test report, up to 10 MB. You can "
        "also type the date printed on the report and say whose report it is. "
        "Then press Upload. Uploading does not start the analysis by itself: "
        "press the Analyse button on the report afterwards.",
    ),
    HelpNote(
        "analyse",
        "Analysing a report",
        ("analyse", "analyze", "analysis", "analysing", "progress bar", "slow", "taking long",
         "taking so long", "stuck", "re analyse", "reanalyse", "how long"),
        # Reports.jsx STEP labels; the free hosting sleeps (MEMORY 6bu).
        "Press Analyse on a report in the Reports page. A progress bar walks "
        "through four steps: reading the report, checking the values, clinical rules and "
        "models, and writing explanations. It usually takes one to three "
        "minutes. On the online version the service sleeps when nobody has used "
        "it for a while, so the first analysis after a quiet spell can take a "
        "few minutes longer. Press it only once. Re-analyse runs a report again "
        "and replaces its earlier result.",
    ),
    HelpNote(
        "whose_report",
        "Whose report?",
        ("whose", "someone else", "family member", "my mother", "my father", "other person", "not mine"),
        "Each report can be marked as yours or as someone else's, with the "
        "'Whose report?' button. Your own details are used only for your own "
        "reports. For someone else's report you can type their age and sex "
        "instead, and your details are not used for it.",
    ),
    HelpNote(
        "profile",
        "Your details (profile)",
        ("profile", "your details", "my details", "personal details", "enter my age",
         "change my age", "change my weight", "change my height", "update my details"),
        # Profile.jsx hints.
        "The 'Your details' page holds your age, sex, height, weight, smoking "
        "history, and whether you have high blood pressure or heart disease. "
        "The analysis uses them, for example age and sex for limits that differ "
        "for men and women. Anything left blank stays blank and is never "
        "guessed. BMI is worked out from your height and weight. Changes are "
        "used the next time a report is analysed.",
    ),
    HelpNote(
        "dashboard",
        "The report dashboard",
        ("dashboard", "result page", "results page", "risk gauge", "overall status", "view dashboard"),
        "After an analysis, press 'View dashboard' on the report. It has an "
        "overall summary, the topics that were checked, each of your results "
        "with its usual range, and plain-language explanations that are "
        "safety-checked before you see them. From there you can open the "
        "summary for a clinician and the population comparison.",
    ),
    HelpNote(
        "not_assessed",
        "'Not assessed' and 'partial assessment'",
        ("not assessed", "partial", "partly", "incomplete", "nothing assessed", "not checked"),
        "'Not assessed' is used when none of the test results on the report "
        "are ones VaidyaAI checks, so it gives no overall status rather than "
        "guessing. 'Partial assessment' is used when some topics could be "
        "checked and others could not. A missing result is never counted as a "
        "normal one.",
    ),
    HelpNote(
        "timeline",
        "Timeline",
        ("timeline", "trend", "trends", "over time", "compare reports", "compare my reports",
         "previous report", "went up", "went down", "arrows"),
        "The Timeline page compares your analysed reports over time, test by "
        "test. It needs at least two analysed reports. Arrows mark whether a "
        "result went up, went down or stayed the same, and whether that change "
        "is larger than normal day-to-day variation.",
    ),
    HelpNote(
        "population",
        "How your results compare (population context)",
        ("population", "percentile", "people my age", "nhanes", "how my results compare",
         "how your results compare", "compared with others", "compare with others"),
        "'How your results compare' places some of your results among people "
        "of the same age band and sex in a large public health survey from the "
        "United States (NHANES). It is general information only: it is not an "
        "Indian population and not a diagnosis.",
    ),
    HelpNote(
        "doctor_summary",
        "Summary for a clinician",
        ("clinician", "summary for", "doctor summary", "share with my doctor", "show my doctor",
         "print", "handover"),
        "'Summary for a clinician' is a short summary of one report that you "
        "can show your doctor. Open it from the report's dashboard.",
    ),
    HelpNote(
        "read_aloud",
        "Read aloud",
        ("read aloud", "listen", "speak", "voice", "audio"),
        "Explanations on the dashboard have a 'Read aloud' button that reads "
        "them using your browser's own voice. It appears only when your "
        "browser has a voice installed.",
    ),
    HelpNote(
        "account",
        "Account, password and deleting data",
        ("password", "account", "delete my", "delete a report", "remove a report", "sign out",
         "log out", "logout", "privacy", "my data"),
        "On the 'Your details' page you can change your password or delete "
        "your account. Deleting the account removes your reports and their "
        "files. A single report can be removed with its Delete button on the "
        "Reports page.",
    ),
    HelpNote(
        "about",
        "What VaidyaAI is",
        # NOT the bare word "about": "write me a poem about cricket" matched it
        # live (2026-10-09) and the model answered instead of redirecting.
        ("what is vaidyaai", "about vaidyaai", "what does this app", "how does it work", "is it accurate"),
        "VaidyaAI reads a laboratory report, checks each value against "
        "published clinical limits and machine-learning models, and explains "
        "what it found in plain words. It is health education, not a "
        "diagnosis: please discuss your results with a doctor.",
    ),
    HelpNote(
        "no_results",
        "'No test results were found'",
        ("no test results", "no results", "nothing found", "not a lab report", "analysis failed", "failed"),
        "If no test results can be read from a file, the analysis stops and "
        "nothing is assessed. Check that the file is a lab report and that the "
        "photo or PDF is clear, then upload it again.",
    ),
)

_WORD = re.compile(r"[a-z0-9]+")


def match_help(question: str, limit: int = 2) -> List[HelpNote]:
    """The notes whose keywords appear in the question, best first."""
    text = " ".join(_WORD.findall((question or "").lower()))
    if not text:
        return []
    scored = []
    for note in HELP_NOTES:
        hits = sum(1 for k in note.keywords if re.search(rf"\b{re.escape(k)}\b", text))
        if hits:
            scored.append((hits, note))
    scored.sort(key=lambda pair: -pair[0])
    return [note for _, note in scored[:limit]]


__all__ = ["HELP_NOTES", "HelpNote", "match_help"]

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


SITE_MAP = HelpNote(
    "site_map",
    "Finding your way around VaidyaAI",
    ("where", "menu", "navigate", "navigation", "go to", "find", "page", "pages", "section",
     "sections", "button", "buttons", "click", "open", "settings", "sidebar", "app", "website",
     "screen", "share", "send", "email", "icon", "download", "export", "save"),
    "The menu is on the left of the screen (on a phone it is a bar at the top). "
    "It has: Reports, Timeline and Your details, then your name, a Dark or Light "
    "button for the colour theme, and Sign out. Clicking the VaidyaAI logo goes "
    "to Reports. The Reports page is where you upload, analyse and open your "
    "reports. A report's dashboard opens with its 'View dashboard' button, and "
    "at the top of a dashboard are two more buttons: 'Summary for a clinician' "
    "and 'How your results compare'. The Timeline page compares your reports "
    "over time. 'Your details' holds your profile and your account settings. "
    "The chat button at the bottom right opens this help chat.",
)

HELP_NOTES: Tuple[HelpNote, ...] = (
    SITE_MAP,
    HelpNote(
        "upload",
        "Uploading a report",
        ("upload", "uploading", "add report", "add a report", "jpg", "png", "file size", "attach",
         "new report"),
        "Click Reports in the menu. In the 'Upload a report' box, choose a PDF or "
        "a clear photo (JPG or PNG) of a blood test report, up to 10 MB. You can "
        "also type the date printed on the report and say whose report it is "
        "(yours or someone else's). Then press Upload. Uploading does not start "
        "the analysis by itself: press the Analyse button on the report "
        "afterwards.",
    ),
    HelpNote(
        "analyse",
        "Analysing a report",
        ("analyse", "analyze", "analysis", "analysing", "progress bar", "slow", "taking long",
         "taking so long", "stuck", "re analyse", "reanalyse", "how long", "being analysed"),
        "On the Reports page, press Analyse on a report. A progress bar walks "
        "through four steps: reading the report, checking the values, clinical "
        "rules and models, and writing explanations. It usually takes one to "
        "three minutes. On the online version the service sleeps when nobody has "
        "used it for a while, so the first analysis after a quiet spell can take "
        "a few minutes longer. Press it only once. Re-analyse runs a report again "
        "and replaces its earlier result, for example after you change your "
        "details.",
    ),
    HelpNote(
        "reports_page",
        "The Reports page",
        ("reports page", "your reports", "uploaded reports", "report list", "status", "badge",
         "not yet analysed", "original file", "open the file"),
        "Click Reports in the menu. At the top is the 'Upload a report' box, and "
        "below it 'Your uploaded reports'. Each report has a label: 'Uploaded, not "
        "yet analysed', 'Being analysed', 'Analysed', 'Analysed, with some stages "
        "incomplete', or 'Analysis failed'. Its buttons are Analyse (or Re-analyse), "
        "View dashboard, Whose report? and Delete. The small file icon opens the "
        "original file you uploaded.",
    ),
    HelpNote(
        "whose_report",
        "Whose report?",
        ("whose", "someone else", "family member", "my mother", "my father", "other person",
         "not mine"),
        "Each report can be marked as yours or as someone else's, with its "
        "'Whose report?' button on the Reports page. Your own details are used "
        "only for your own reports. For someone else's report you can type their "
        "age and sex instead, and your details are not used for it. Press "
        "Re-analyse afterwards so the change is used.",
    ),
    HelpNote(
        "report_date",
        "The report's date",
        ("report date", "date", "typed in", "printed date", "wrong date"),
        "When you upload, you can type the date printed on the report. If the "
        "report itself prints a date, VaidyaAI reads it too, and the Reports page "
        "lists both, for example '(typed in)' next to your date and 'the report "
        "itself prints' next to the printed one. The Timeline uses these dates to "
        "put your reports in order.",
    ),
    HelpNote(
        "profile",
        "Your details (profile)",
        ("profile", "your details", "my details", "personal details", "enter my age",
         "change my age", "change my weight", "change my height", "update my details",
         "fill details"),
        "Click 'Your details' in the menu. It holds your age, sex, height, "
        "weight, smoking history, and whether you have high blood pressure or "
        "heart disease. The analysis uses them, for example age and sex for "
        "limits that differ for men and women. Anything left blank stays blank "
        "and is never guessed. BMI is worked out from your height and weight. "
        "Press Save after changing anything; changes are used the next time a "
        "report is analysed.",
    ),
    HelpNote(
        "dashboard",
        "The report dashboard",
        ("dashboard", "result page", "results page", "view dashboard", "report page",
         "open a report", "open my report"),
        "On the Reports page, press 'View dashboard' on an analysed report. From "
        "top to bottom it has: the Overall card and 'In short', the 'Overall "
        "risk' gauge, 'Coverage of the conditions checked', 'Worth a closer look' "
        "(topics that were flagged), 'Everything else that was checked', 'What "
        "these results mean' (plain-language explanations), 'Your results' (each "
        "value with the range printed on the report), 'From your profile', and "
        "'Topics you could read about'. At the top are the buttons 'Summary for a "
        "clinician' and 'How your results compare'.",
    ),
    HelpNote(
        "overall",
        "Overall, overall risk and coverage",
        ("overall", "overall status", "overall risk", "risk gauge", "gauge", "coverage",
         "radar", "in short", "needs monitoring", "needs medical attention", "worth a closer look"),
        "The Overall card at the top of a dashboard gives one summary of the "
        "report: Healthy, Needs Monitoring, Needs Medical Attention, or Not "
        "assessed. 'Overall risk' is a gauge of the highest risk found (Low, "
        "Medium or High). 'Coverage of the conditions checked' is a chart of "
        "which topics could be checked. 'Worth a closer look' lists the topics "
        "that were flagged, and 'Everything else that was checked' lists the "
        "ones that were not.",
    ),
    HelpNote(
        "explanations",
        "What these results mean, and Read aloud",
        ("what these results mean", "explanations", "explanation", "read aloud", "listen",
         "speak", "voice", "audio", "topics you could read about", "reading links"),
        "On a dashboard, 'What these results mean' has a plain-language "
        "explanation for each topic. They are written by an AI and "
        "safety-checked before you see them. Each one has a 'Read aloud' button "
        "that reads it using your browser's own voice; it appears only when your "
        "browser has a voice installed. 'Topics you could read about' links to "
        "trusted NHS pages on general health topics.",
    ),
    HelpNote(
        "your_results",
        "Your results and From your profile",
        ("your results section", "results table", "from your profile", "patient details",
         "entered for this report", "usual range", "range printed"),
        "On a dashboard, 'Your results' lists every value VaidyaAI read from the "
        "report, with the range printed on the report. 'From your profile' lists "
        "the details from your profile that were used (or 'Entered for this "
        "report' for someone else's report); they help interpret the results "
        "and are not results themselves.",
    ),
    HelpNote(
        "not_assessed",
        "'Not assessed' and 'partial assessment'",
        ("not assessed", "partial", "partly", "incomplete", "nothing assessed", "not checked",
         "some stages incomplete"),
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
         "previous report", "went up", "went down", "arrows", "progress score",
         "comparing two reports"),
        "Click Timeline in the menu. It compares your analysed reports over "
        "time and needs at least two of them. It has three parts: 'Trends over "
        "time' (a chart for each test), 'Comparing two reports' (two reports side "
        "by side), and 'Progress score'. Arrows mark whether a result went up, "
        "went down or stayed the same, and whether that change is larger than "
        "normal day-to-day variation.",
    ),
    HelpNote(
        "population",
        "How your results compare (population context)",
        ("population", "percentile", "people my age", "nhanes", "how my results compare",
         "how your results compare", "compared with others", "compare with others"),
        "Open a report's dashboard and press 'How your results compare' at the "
        "top. It places some of your results among people of the same age band "
        "and sex in a large public health survey from the United States "
        "(NHANES). It is general information only: it is not an Indian "
        "population and not a diagnosis. 'What this comparison cannot account "
        "for' at the bottom lists its limits.",
    ),
    HelpNote(
        "doctor_summary",
        "Summary for a clinician",
        ("clinician", "summary for", "doctor summary", "share with my doctor", "show my doctor",
         "to my doctor", "to the doctor", "to a doctor", "for my doctor", "for the doctor",
         "print", "handover", "healthcare professional summary", "share my report",
         "share the report", "send my report"),
        "Open a report's dashboard and press 'Summary for a clinician' at the "
        "top. It opens a short 'Summary for a healthcare professional' of that "
        "one report that you can show your doctor on your screen, or print with "
        "your browser's own Print command. VaidyaAI has no share or email "
        "button; you can also show your doctor the original report file, which "
        "the file icon on the Reports page opens.",
    ),
    HelpNote(
        "save_print",
        "Saving or printing your results",
        ("download", "save", "save as pdf", "as pdf", "export", "keep a copy", "copy of my results",
         "print my results", "print the report"),
        "VaidyaAI has no download or export button for results. To keep a copy, "
        "open the report's dashboard or its 'Summary for a clinician' page and "
        "use your browser's own Print command (Ctrl+P on a computer); most "
        "browsers can 'Save as PDF' from there. The original file you uploaded "
        "opens from the file icon on the Reports page.",
    ),
    HelpNote(
        "account",
        "Account, password and deleting data",
        ("password", "account", "delete my", "delete a report", "remove a report", "sign out",
         "log out", "logout", "privacy", "my data", "forgot"),
        "Click 'Your details' in the menu; the Account section is at the bottom. "
        "There you can change your password or delete your account. Deleting the "
        "account removes your reports and their files. A single report can be "
        "removed with its Delete button on the Reports page. To sign out, use "
        "Sign out at the bottom of the menu. There is no 'forgot password' option "
        "in this version, so keep your password safe.",
    ),
    HelpNote(
        "theme",
        "Dark mode",
        ("dark mode", "dark theme", "light mode", "light theme", "theme", "colours", "colors"),
        "Use the Dark or Light button in the menu to switch the colour theme. "
        "Your choice is remembered on this device.",
    ),
    HelpNote(
        "sign_in",
        "Signing up and signing in",
        ("sign up", "signup", "register", "create an account", "sign in", "signin", "log in",
         "login"),
        "On the home page press 'Get started' or 'Create an account' to sign up "
        "with your name, email and a password, or 'Sign in' if you already have "
        "an account. A new account opens on 'Your details' first, so the "
        "analysis has your age and sex.",
    ),
    HelpNote(
        "chat",
        "This chat",
        ("chat", "chatbot", "bot", "assistant", "who are you", "what can you do"),
        "This chat answers questions about using VaidyaAI, general questions "
        "about lab tests and health, and, on a report's own pages, questions "
        "about that report. It cannot say whether you have a condition; that, "
        "and anything about what to take, is for your doctor or pharmacist. "
        "Your questions are not saved.",
    ),
    HelpNote(
        "about",
        "What VaidyaAI is",
        ("what is vaidyaai", "about vaidyaai", "what does this app", "how does it work",
         "is it accurate", "what can this app"),
        "VaidyaAI reads a laboratory report, checks each value against "
        "published clinical limits and machine-learning models, and explains "
        "what it found in plain words. It is health education, not a "
        "diagnosis: please discuss your results with a doctor.",
    ),
    HelpNote(
        "no_results",
        "'No test results were found' and other problems",
        ("no test results", "no results", "nothing found", "not a lab report", "analysis failed",
         "failed", "error", "not working"),
        "If no test results can be read from a file, the analysis stops and "
        "nothing is assessed: check that the file is a lab report and that the "
        "photo or PDF is clear, then upload it again. If an analysis stops "
        "partway or fails for another reason, press Analyse or Re-analyse again "
        "after a minute.",
    ),
)

_WORD = re.compile(r"[a-z0-9]+")


def match_help(question: str, limit: int = 3) -> List[HelpNote]:
    text = " ".join(_WORD.findall((question or "").lower()))
    if not text:
        return []
    scored = []
    for order, note in enumerate(HELP_NOTES):
        hits = sum(1 for k in note.keywords if re.search(rf"\b{re.escape(k)}\b", text))
        if hits:
            specific = 0 if note is SITE_MAP else 1
            scored.append((specific, hits, -order, note))
    scored.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
    return [t[3] for t in scored[:limit]]


__all__ = ["HELP_NOTES", "HelpNote", "SITE_MAP", "match_help"]

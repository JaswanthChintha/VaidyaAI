"""Orchestration: loaded document -> per-page model calls -> the contract.

Assembly rules live here (not in the model) so they are deterministic and
testable:
  * page numbers are stamped by the service, not trusted from the model
  * document `raw_text` is the concatenation of page texts in order
  * `extraction_confidence` aggregates page and row confidences
  * warnings are collected from intake, the model, and service-side checks

NOTHING in this module interprets results clinically. It transcribes and
assembles only. Test-name normalisation is Module 5; validation is Module 6.
"""

from __future__ import annotations

import contextvars
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Optional, Union

from pydantic import ValidationError

from app.config import Settings
from app.core.logging import get_logger, safe_meta
from app.core.errors import ErrorCode, ModelError
from app.prompts.extraction_prompt import build_page_prompt
from app.schemas.extraction import (
    ExtractedParameter,
    ExtractionData,
    PageExtraction,
    PageText,
    ReportMetadata,
    SourceInfo,
)
from app.services.document_loader import LoadedDocument
from app.services.gemini_client import GeminiClient

logger = get_logger(__name__)

# Guard against a model that ignores instructions and emits thousands of rows.
MAX_PARAMETERS_PER_PAGE = 300

# PAGES ARE READ AT THE SAME TIME, AT MOST THIS MANY AT ONCE (2026-10-03).
# They were read one after another, so a two-page report waited for two full
# model round trips (Test 3: ~17 s + ~19 s). The calls are independent; only
# the ASSEMBLY below depends on page order, and it still runs in page order
# over the collected results. Three keeps a long report from tripping the
# free tier's per-minute limit in one burst.
MAX_CONCURRENT_PAGES = 3

# WHICH FAILED PAGES GET ONE MORE TRY (2026-10-10). Only failures a later
# moment can fix: the provider unavailable (5xx), and an answer that came back
# empty or garbled -- plus a page whose answer did not fit the schema, checked
# separately. NOT a rate limit: the free tier's cap is daily, and asking again
# twenty seconds later only spends the time. NOT a timeout: one more full
# attempt chain on a page that already timed out would run past the backend's
# own extraction deadline. NOT a safety block or truncation: those are
# answers, and the same page gets the same answer.
PAGE_RETRY_CODES = frozenset(
    {
        ErrorCode.MODEL_UNAVAILABLE,
        ErrorCode.MODEL_RESPONSE_MALFORMED,
        ErrorCode.MODEL_RESPONSE_EMPTY,
    }
)


def _mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


class ExtractionService:
    def __init__(self, settings: Settings, client: GeminiClient) -> None:
        self._settings = settings
        self._client = client

    def _read_pages(self, pages: List[Any], total: int) -> List[Union[dict, ModelError]]:
        """Each page's payload or ModelError, IN PAGE ORDER.

        A single page is called inline -- no thread for nothing. Each worker
        runs in a copy of the caller's context, so the request id carried by
        `contextvars` still reaches every log line a page writes. Any error
        that is not a ModelError propagates exactly as it did from the loop.
        """

        def read(page: Any) -> Union[dict, ModelError]:
            prompt = build_page_prompt(page.page_number, total)
            try:
                return self._client.extract_page(page.image_bytes, page.mime_type, prompt)
            except ModelError as exc:
                return exc

        if len(pages) <= 1:
            return [read(page) for page in pages]

        workers = min(MAX_CONCURRENT_PAGES, len(pages))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(contextvars.copy_context().run, read, page) for page in pages
            ]
            return [future.result() for future in futures]

    @staticmethod
    def _worth_another_try(outcome: Union[dict, ModelError]) -> bool:
        if isinstance(outcome, ModelError):
            return outcome.code in PAGE_RETRY_CODES
        try:
            PageExtraction.model_validate(outcome)
        except ValidationError:
            return True
        return False

    def _retry_failed_pages(
        self, pages: List[Any], outcomes: List[Union[dict, ModelError]], total: int
    ) -> List[Union[dict, ModelError]]:
        """Read each page that failed in a fixable way ONCE more, after a pause.

        Every model in the chain already retries within seconds, so a provider
        outage longer than that took the page with it (Test 3, 2026-10-10: page
        2 -- glucose, creatinine, SGPT -- skipped as MODEL_UNAVAILABLE, and the
        report read "Healthy (partial assessment)"). One pause, one more read
        of just those pages, and then whatever happens is final: a page that
        fails again is skipped and reported exactly as before.
        """
        retry_at = [i for i, outcome in enumerate(outcomes) if self._worth_another_try(outcome)]
        if not retry_at:
            return outcomes
        delay = max(0.0, self._settings.page_retry_delay_seconds)
        logger.warning(
            "page_retry_scheduled %s",
            safe_meta(
                page_numbers=[pages[i].page_number for i in retry_at],
                delay_seconds=delay,
            ),
        )
        if delay:
            time.sleep(delay)
        again = self._read_pages([pages[i] for i in retry_at], total)
        result = list(outcomes)
        for i, outcome in zip(retry_at, again):
            result[i] = outcome
            logger.info(
                "page_retry_finished %s",
                safe_meta(
                    page_number=pages[i].page_number,
                    recovered=not self._worth_another_try(outcome)
                    and not isinstance(outcome, ModelError),
                ),
            )
        return result

    def extract(self, document: LoadedDocument) -> ExtractionData:
        warnings: List[str] = list(document.warnings)
        pages: List[PageText] = []
        parameters: List[ExtractedParameter] = []
        page_confidences: List[float] = []

        lab_name: Optional[str] = None
        report_date: Optional[str] = None
        patient_name_present: Optional[bool] = None
        patient_sex: Optional[str] = None
        patient_age: Optional[str] = None

        failed_pages = 0
        total = len(document.pages)

        # The model calls, concurrently. Each page's outcome is the payload or
        # the ModelError it raised -- the same two outcomes the old loop
        # branched on -- and nothing else is decided until every page is in.
        outcomes = self._read_pages(document.pages, total)
        outcomes = self._retry_failed_pages(document.pages, outcomes, total)

        for page, outcome in zip(document.pages, outcomes):
            try:
                if isinstance(outcome, ModelError):
                    raise outcome
                payload = outcome
            except ModelError as exc:
                # A single failed page degrades the result rather than failing
                # the whole request -- unless every page fails (checked below).
                failed_pages += 1
                warnings.append(
                    f"Page {page.page_number} could not be processed by the "
                    f"extraction model ({exc.code}); it was skipped."
                )
                logger.warning(
                    "page_extraction_failed %s",
                    safe_meta(page_number=page.page_number, error_code=exc.code),
                )
                pages.append(PageText(page_number=page.page_number, raw_text=None))
                continue

            try:
                page_result = PageExtraction.model_validate(payload)
            except ValidationError:
                # The top-level page object was unusable. Salvage nothing from
                # it rather than emit half-validated data.
                failed_pages += 1
                warnings.append(
                    f"Page {page.page_number} returned a response that did not "
                    f"match the expected schema; it was skipped."
                )
                logger.warning(
                    "page_schema_invalid %s",
                    safe_meta(page_number=page.page_number),
                )
                pages.append(PageText(page_number=page.page_number, raw_text=None))
                continue

            pages.append(
                PageText(page_number=page.page_number, raw_text=page_result.raw_text)
            )

            rows = page_result.parameters
            if len(rows) > MAX_PARAMETERS_PER_PAGE:
                warnings.append(
                    f"Page {page.page_number} returned an implausible number of "
                    f"rows ({len(rows)}); the list was truncated."
                )
                rows = rows[:MAX_PARAMETERS_PER_PAGE]

            for row in rows:
                # Page number is authoritative from the service, never the model.
                row.page_number = page.page_number
                parameters.append(row)
                self._flag_row_warnings(row, warnings)

            if page_result.page_confidence is not None:
                page_confidences.append(page_result.page_confidence)

            for warning in page_result.warnings:
                text = (warning or "").strip()
                if text:
                    warnings.append(f"Page {page.page_number}: {text}")

            # First non-null wins for document-level metadata; a later page
            # disagreeing is worth a warning (possible multi-report document).
            if page_result.lab_name:
                if lab_name is None:
                    lab_name = page_result.lab_name
                elif page_result.lab_name != lab_name:
                    warnings.append(
                        "Multiple laboratory names appear in the document; the "
                        "first was used."
                    )
            if page_result.report_date:
                if report_date is None:
                    report_date = page_result.report_date
                elif page_result.report_date != report_date:
                    warnings.append(
                        "Multiple report dates appear in the document; the "
                        "first was used."
                    )
            if page_result.patient_name_present:
                patient_name_present = True
            elif patient_name_present is None:
                patient_name_present = page_result.patient_name_present
            # Same rule for the printed sex and age. A later page printing a
            # DIFFERENT one is a document that may hold two people's results,
            # which is exactly what these fields exist to catch -- so it is
            # warned about, never silently merged.
            if page_result.patient_sex:
                if patient_sex is None:
                    patient_sex = page_result.patient_sex
                elif page_result.patient_sex.lower() != patient_sex.lower():
                    warnings.append(
                        "Different patient sexes are printed on different pages; "
                        "the first was used."
                    )
            if page_result.patient_age:
                if patient_age is None:
                    patient_age = page_result.patient_age
                elif page_result.patient_age.lower() != patient_age.lower():
                    warnings.append(
                        "Different patient ages are printed on different pages; "
                        "the first was used."
                    )

        if total > 0 and failed_pages == total:
            raise ModelError(
                "No page of the document could be extracted.",
                code=ErrorCode.MODEL_REQUEST_FAILED,
                status_code=502,
            )

        raw_text = "\n\n".join(p.raw_text for p in pages if p.raw_text)

        confidence = self._aggregate_confidence(page_confidences, parameters)

        if not parameters:
            warnings.append(
                "No laboratory parameters were extracted from the document."
            )
        if confidence is not None and confidence <= self._settings.low_confidence_threshold:
            warnings.append(
                f"Overall extraction confidence is low ({confidence:.2f}); "
                f"downstream results should be treated as provisional."
            )
        if not raw_text.strip():
            warnings.append("No readable text was recovered from the document.")

        data = ExtractionData(
            source=SourceInfo(
                filename=document.filename,
                mime_type=document.mime_type,
                page_count=document.page_count,
                size_bytes=document.size_bytes,
            ),
            raw_text=raw_text,
            pages=pages,
            extracted_parameters=parameters,
            report_metadata=ReportMetadata(
                lab_name=lab_name,
                report_date=report_date,
                patient_name_present=patient_name_present,
                patient_sex=patient_sex,
                patient_age=patient_age,
            ),
            extraction_confidence=confidence,
            warnings=_dedupe(warnings),
        )

        logger.info(
            "extraction_complete %s",
            safe_meta(
                page_count=document.page_count,
                parameter_count=len(parameters),
                failed_pages=failed_pages,
                extraction_confidence=confidence,
                warning_count=len(data.warnings),
            ),
        )
        return data

    # -- helpers -------------------------------------------------------------

    def _aggregate_confidence(
        self,
        page_confidences: List[float],
        parameters: List[ExtractedParameter],
    ) -> Optional[float]:
        """Combine page-level and row-level confidence into one number.

        Rows are weighted equally with pages when both exist: a page can read
        cleanly overall while individual rows are shaky, and Module 5 cares
        most about the rows.
        """
        row_confidences = [
            p.confidence for p in parameters if p.confidence is not None
        ]
        page_mean = _mean(page_confidences)
        row_mean = _mean(row_confidences)

        if page_mean is None and row_mean is None:
            return None
        if page_mean is None:
            value = row_mean
        elif row_mean is None:
            value = page_mean
        else:
            value = (page_mean + row_mean) / 2.0

        assert value is not None
        return round(min(1.0, max(0.0, value)), 4)

    @staticmethod
    def _flag_row_warnings(row: ExtractedParameter, warnings: List[str]) -> None:
        """Service-side sanity checks. Observational only -- no clinical logic."""
        if row.reference_low is not None and row.reference_high is not None:
            if row.reference_low > row.reference_high:
                warnings.append(
                    f"Reference range for '{row.test_name}' appears inverted; "
                    f"it was preserved as read."
                )
        if row.value_numeric is None and row.unit:
            warnings.append(
                f"'{row.test_name}' has a unit but a non-numeric value; the "
                f"unit may be misread."
            )


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out

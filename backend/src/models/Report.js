'use strict';

const mongoose = require('mongoose');
const { ALLOWED_MIME_TYPES, MAX_DISPLAY_NAME_LENGTH } = require('../utils/fileSecurity');
const Profile = require('./Profile');

/**
 * Module 3 - Medical Report Upload and Management.
 *
 * This collection stores METADATA ONLY. The bytes live behind the storage
 * adapter (src/storage/), addressed by the opaque `storageKey` + the
 * `storageDriver` that produced it. Nothing here may be used to build a
 * filesystem path - see localDiskAdapter.resolveKey.
 *
 * CHRONOLOGY (the spec's stated reason this module exists: Modules 28-30 need
 * to order and compare reports over time). Two dates are kept:
 *
 *   uploadedAt  - when the file reached us. Always present, never client-set.
 *   reportDate  - the date printed on the lab report. Optional, client-supplied,
 *                 and frequently EARLIER than uploadedAt: a patient uploading
 *                 three years of history in one sitting would otherwise produce
 *                 a timeline in which every report happened today.
 *
 * Ordering must therefore use "the report's own date if we know it, else the
 * upload date". Computing that at query time (`$ifNull`) would defeat any
 * index, so it is MATERIALISED into `chronoDate` by a pre-validate hook and
 * indexed with the owner. Modules 28/29 sort on `{ user, chronoDate }` and get
 * an index-covered scan.
 *
 * `status` exists for Module 4: OCR will move a report uploaded -> processing
 * -> processed | failed. Module 3 only ever sets `uploaded`; it implements no
 * extraction of any kind.
 */

/**
 * `partial` exists because the pipeline has five stages and they do not
 * all-or-nothing. Extraction (4) and feature engineering (5) are load-bearing:
 * without them there is nothing to store at all. Validation (6), the clinical
 * rules (8) and the ML predictors (9/10) are not - a validated feature set with
 * no rule decisions is still a usable result, and a report whose ML predictor
 * was unavailable is far more useful than no report.
 *
 * `processed` therefore means EVERY stage succeeded. When some downstream stage
 * did not, the status is `partial`: what succeeded is stored and returned, and
 * `analysis.stages` says exactly which stage failed and with which error code.
 * A stage that failed must never be able to hide behind `processed`.
 */
const REPORT_STATUS = Object.freeze({
  UPLOADED: 'uploaded',
  PROCESSING: 'processing',
  PROCESSED: 'processed',
  PARTIAL: 'partial',
  FAILED: 'failed',
});
const REPORT_STATUS_VALUES = Object.freeze(Object.values(REPORT_STATUS));

/**
 * The steps a running analysis reports, in order (2026-10-04). Each is
 * written when the step BEGINS, so the Reports page can show where a
 * one-to-two-minute run has got to. Real milestones only -- no percentage.
 */
const ANALYSIS_STEPS = Object.freeze(['reading', 'checking', 'deciding', 'explaining']);

/** Ordering keys a client may ask for. */
const SORT_FIELDS = Object.freeze(['chronoDate', 'uploadedAt', 'reportDate']);

const reportSchema = new mongoose.Schema(
  {
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User',
      required: [true, 'A report must belong to a user'],
      immutable: true, // a report can never be re-pointed at another account
      index: true,
    },

    /**
     * The client's filename AFTER sanitisation, kept for display and for the
     * Content-Disposition header. Never used to locate anything on disk.
     */
    originalName: {
      type: String,
      required: true,
      maxlength: MAX_DISPLAY_NAME_LENGTH,
      trim: true,
    },

    /** Opaque key handed back by the storage adapter. */
    storageKey: {
      type: String,
      required: true,
      immutable: true,
    },

    /** Which adapter produced `storageKey` (`local` today). */
    storageDriver: {
      type: String,
      required: true,
      immutable: true,
    },

    /**
     * The type DETECTED from the file's magic bytes - never the client's
     * declared Content-Type, which is an attacker-controlled string.
     */
    mimeType: {
      type: String,
      required: true,
      enum: {
        values: [...ALLOWED_MIME_TYPES],
        message: 'Unsupported report type',
      },
    },

    sizeBytes: {
      type: Number,
      required: true,
      min: [1, 'A report file cannot be empty'],
    },

    /** SHA-256 of the file contents, hex. Integrity + later duplicate detection. */
    checksumSha256: {
      type: String,
      required: true,
      match: [/^[a-f0-9]{64}$/, 'Invalid checksum'],
      index: true,
    },

    /** Server clock. Not settable by the client. */
    uploadedAt: {
      type: Date,
      required: true,
      default: Date.now,
      immutable: true,
    },

    /**
     * The date TYPED into the upload form. Named `reportDate` for history: the
     * form asks for "the date printed on the report", but nothing checks that
     * it is -- which is why `printedDate` below exists beside it.
     */
    reportDate: {
      type: Date,
      default: undefined,
    },

    /**
     * WHOSE REPORT THIS IS (owner, 2026-10-03).
     *
     * Every analysis used the ACCOUNT's profile for anything the report did
     * not print -- age, sex, and always BMI, smoking, blood pressure and heart
     * history -- so a relative's report was judged partly as the account
     * holder (02-diabetes-and-lipids: "Obesity, borderline" on the account
     * holder's BMI). `owner: 'other'` means the account profile is NOT used
     * for this report at all: age and sex come from what the report prints,
     * else from `age` / `sex` typed here, else they are unknown. The report
     * is also left out of the account holder's timeline.
     *
     * `updatedAt` lets a page say "re-analyse to apply" when this changed
     * after the stored analysis ran.
     */
    subject: {
      owner: { type: String, enum: ['self', 'other'], default: 'self' },
      age: { type: Number, min: 0, max: 120, default: undefined },
      sex: { type: String, enum: Profile.GENDER_VALUES, default: undefined },
      updatedAt: { type: Date, default: undefined },
    },

    /**
     * The date the DOCUMENT prints, read from extraction's
     * `report_metadata.report_date` by `utils/printedDate` -- UTC midnight of
     * that calendar day. Set only when it was READ; an ambiguous or unreadable
     * printed date is never turned into one. See `printedDateStatus`.
     */
    printedDate: {
      type: Date,
      default: undefined,
    },

    /**
     * What happened when the printed date was read: `read`, `ambiguous`
     * (`05/09/2026` -- day-first or month-first is not knowable), `unreadable`
     * (`02 Dec, 2X`), or `absent` (the report prints none). Unset on a report
     * not analysed since this field existed: nobody looked, which is not the
     * same as `absent`.
     */
    printedDateStatus: {
      type: String,
      enum: ['read', 'ambiguous', 'unreadable', 'absent'],
      default: undefined,
    },

    /**
     * The printed text, kept only so a page can SHOW what could not be read
     * ("the report prints '02 Dec, 2X'"). A date string, capped, never parsed
     * for anything else.
     */
    printedDateRaw: {
      type: String,
      maxlength: 64,
      default: undefined,
    },

    /**
     * The patient SEX and AGE the document prints, read by
     * `utils/printedIdentity` from extraction's `report_metadata`. NEVER a
     * name -- Module 4 does not copy one.
     *
     * UNSET MEANS NOBODY LOOKED: the report was analysed before extraction
     * returned these fields. Inside it each field is `read`, `absent` (not
     * printed) or `unreadable`; the raw text is kept only when unreadable, so
     * a page can quote it.
     *
     * Exists because every analysis used the ACCOUNT PROFILE's sex and age:
     * a report printing "34 Years / Female" on a "20, male" account was judged
     * with male thresholds and compared with a 63-year-old man's as one
     * person's history (2026-09-24).
     */
    printedIdentity: {
      type: new mongoose.Schema(
        {
          sex: { type: String, enum: ['male', 'female'] },
          sexStatus: { type: String, enum: ['read', 'absent', 'unreadable'], required: true },
          sexRaw: { type: String, maxlength: 32 },
          ageYears: { type: Number, min: 0, max: 130 },
          ageStatus: { type: String, enum: ['read', 'absent', 'unreadable'], required: true },
          ageRaw: { type: String, maxlength: 32 },
        },
        { _id: false }
      ),
      default: undefined,
    },

    /**
     * DERIVED: reportDate ?? printedDate ?? uploadedAt. The single
     * chronological sort key. Recomputed on every save so it can never drift
     * from its inputs -- and `deriveChronoDate` is exported for the writes that
     * bypass save (`updateOne`), which must compute it the same way.
     *
     * THE TYPED DATE STILL COMES FIRST. A reader may deliberately date a report
     * by when the sample was taken rather than when it was printed; overriding
     * what they typed with what a parser read would be this tool deciding it
     * knows their history better. A DISAGREEMENT between the two is shown on
     * the page instead of being settled silently in either direction.
     */
    chronoDate: {
      type: Date,
      required: true,
    },

    /** Downstream processing state. Module 3 only ever writes `uploaded`. */
    status: {
      type: String,
      required: true,
      enum: {
        values: [...REPORT_STATUS_VALUES],
        message: `Status must be one of: ${REPORT_STATUS_VALUES.join(', ')}`,
      },
      default: REPORT_STATUS.UPLOADED,
      index: true,
    },

    /**
     * Free-text detail about a processing failure, for Module 4. Never holds
     * report contents or extracted medical values - only an error label.
     */
    statusMessage: {
      type: String,
      maxlength: 500,
      default: undefined,
    },

    // --- Analysis pipeline (Modules 4 + 5, orchestrated by the backend) -----
    //
    // INTERIM HOME, DELIBERATELY. A formal Feature Repository is Module 7 and
    // is NOT being built here. Until it exists, the extraction output and the
    // engineered features live on the report that produced them, which is the
    // smallest thing that makes section 16's data flow real: it needs no new
    // abstraction, it inherits the report's ownership scoping for free, and it
    // is deleted with the report. Module 7 will formalise this - see the
    // README. Nothing here is designed as a general-purpose repository.
    //
    // `select: false` on the two payload fields is load-bearing, not tidiness:
    // they are the largest and most sensitive documents in the collection, and
    // `GET /reports` lists up to 100 of them. Without it every listing would
    // drag full report text out of Mongo and through the app. Only the two
    // analysis endpoints ask for them, explicitly.

    /**
     * Module 4's `data` object, REDACTED of bulk report text.
     *
     * `raw_text` (whole document and per page) is replaced by a
     * `raw_text_available` boolean; everything else - `extracted_parameters`,
     * `report_metadata`, `source`, `extraction_confidence`, `warnings` - is kept
     * verbatim. The full text is the largest concentration of PHI in the
     * pipeline and no downstream module consumes it, so a second verbatim copy
     * buys nothing and widens the blast radius of any database exposure. The
     * original file is still downloadable through Module 3.
     * See analysisService.redactExtraction.
     */
    extraction: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    /** Module 5's `data` object, exactly as the service returned it. */
    features: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    /**
     * Module 6's `data` object - the validation verdict.
     *
     * `valid` / `questionable` / `rejected` plus `clinically_extreme`,
     * `missing_features`, `unmapped`, `all_warnings`, `upstream` and `summary`.
     * Module 17's final report is required to carry validation warnings, so
     * this is stored whole rather than reduced to counts.
     */
    featureValidation: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    /**
     * Module 8's `data` object - the deterministic clinical rule decisions.
     * Each decision carries its evidence and its recommendations, both of which
     * Module 17 requires; nothing is flattened to a score here.
     */
    ruleDecisions: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    /** Modules 9/10's `data` object - the ML predictor decisions. */
    mlDecisions: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    /**
     * Modules 17-20's `ClinicalReport` - THE USER-VISIBLE DELIVERABLE.
     *
     * Everything above it is machine output: decisions, verdicts, feature maps.
     * This is the object a person reads, and it carries Module 16's fusion (and
     * through it Module 15's collection) nested verbatim under `fusion`, so the
     * exact rule or model behind any line is always reachable from it.
     *
     * `select: false` for the same reason the payloads above are: it is the
     * largest document in the collection - it contains laboratory values,
     * evidence lines and the whole nested fusion - and `GET /reports` lists up
     * to 100 rows. Only the analysis endpoints ask for it, explicitly.
     *
     * IT LEGITIMATELY CONTAINS LABORATORY VALUES. That is what a clinical
     * report is for. What it does NOT contain, and must never be given, is raw
     * report text: the ai-service carries pages forward as
     * `{page_number, raw_text_available}` only, and nothing here re-adds text.
     */
    clinicalReport: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    /**
     * Module 32's handover note, WRITTEN BY A MODEL and cached here.
     *
     * CACHED BECAUSE THE DOCUMENT IS BUILT PER REQUEST. The doctor summary is
     * assembled on every GET, so writing the prose inline would spend a model
     * call every time someone opened the page - on a free tier of 20 a day,
     * that is one reader. It is written once per analysis and re-used.
     *
     * `analysisVersion` is what makes the cache honest: a re-analysis bumps
     * the version and this narrative is then ignored, because prose describing
     * the previous run's findings is worse than no prose at all.
     */
    doctorNarrative: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    /**
     * Module 33's rewrite of the PATIENT's closing summary.
     *
     * Cached exactly like `doctorNarrative` and for the same reason: one model
     * call per analysis, never one per page view, on a free tier of twenty a
     * day. Keyed on the analysis version AND on a hash of the sentences that
     * were sent -- the page composes those from what it is rendering, so a
     * changed composition must not be served last week's prose about it.
     *
     * `text` is the ONLY renderable field and is absent on every refusal. A
     * caller that finds no text renders the sentences it already had, which
     * is what the page shows today.
     */
    summaryProse: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    /**
     * Module 34's general context for the tests marked out of range.
     *
     * Cached like `summaryProse` and for the same reason: one model call per
     * finding per analysis, never one per page view. Keyed on the analysis
     * version AND a hash of the findings sent, because the page derives those
     * from what it is rendering.
     */
    findingContext: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    /**
     * Module 23's `ReportExplanationSet` - THE PATIENT-FACING EXPLANATION.
     *
     * The clinical report above is written for a reader who already knows what
     * HbA1c is. This is the last hop: the same findings in language a patient
     * can act on, generated by the LLM and then approved by Module 24's safety
     * layer before it was allowed out. Spec section 14 puts that gate between
     * the model and the user, and this field is what came through it.
     *
     * WHAT IS AND IS NOT IN HERE, structurally:
     *
     *   IS      the APPROVED sentences, each finding's outcome, the reviewed
     *           fallback notice for the ones with no sentence, the retrieval
     *           sources the generation was grounded in, and the safety layer's
     *           violation CODES.
     *   IS NOT  any refused text, and any offending span. The ai-service never
     *           sends them (`explanation` is assigned only from
     *           `guarded_generation().approved_text`), and
     *           `analysisService.stripRefusedText` removes the key shapes that
     *           could carry them before this field is ever written. A refused
     *           sentence is one the safety layer judged unsafe to show a
     *           patient; storing it would put it in the database, in every
     *           backup, and one careless renderer away from the screen it was
     *           withheld from.
     *
     * EVERY ENTRY CARRIES `generated_explanation_available`, derived in exactly
     * one place from whether approved text exists, plus a non-empty `notice`
     * whenever it is false. A renderer must branch on that boolean and never on
     * the presence of the string: "the safety layer withheld this" and "there
     * was nothing to say" are different facts, and rendering the first as a
     * blank space is the failure Module 23's five-outcome contract exists to
     * prevent.
     *
     * `select: false` for the same reason as the payloads above.
     */
    patientExplanation: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    /**
     * Module 26's `LifestyleGuidance` - pre-approved educational guidance.
     *
     * Catalogue text resolved by recommendation code. NO MODEL IS INVOLVED: the
     * payload asserts `generated: false` itself, so the absence of generation
     * is checkable from the stored data rather than promised in a comment. Kept
     * separate from the explanation above precisely so that distinction stays
     * visible - the spec asks for pre-approved educational guidance rather than
     * unrestricted AI-generated advice, and one field holding both would erase
     * which half was which.
     */
    lifestyleGuidance: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    /**
     * Descriptions of laboratory tests this platform does NOT assess.
     *
     * Separate from `patientExplanation` for the same reason `lifestyleGuidance`
     * is: they are different kinds of statement and one field holding both
     * would erase which was which. An explanation is about a value that WAS
     * assessed, grounded in retrieved knowledge and tied to a decision. An
     * entry here is a definition of a test that was NOT assessed, generated
     * from the test's NAME with no patient data in the prompt, and it supports
     * no conclusion at all.
     */
    parameterGlossary: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    /**
     * Warnings from EVERY stage, each tagged with the stage it came from
     * (`extraction` 4, `feature_engineering` 5, `validation` 6, `rules` 8,
     * `ml` 9/10). The FULL list is stored - never only the last stage's.
     *
     * Kept as a separate array rather than left inside the two payloads because
     * they are the one part of the analysis that must survive to Module 17's
     * final report: MuPDF's silent PDF repair and Module 4's per-page partial
     * degradation surface ONLY as warnings, so a damaged, partly-unreadable
     * scan is otherwise indistinguishable from a clean one - an unreadable row
     * silently becomes "test not present". Origin is never flattened away.
     */
    analysisWarnings: {
      type: [mongoose.Schema.Types.Mixed],
      select: false,
      default: undefined,
    },

    /** Small, always-loaded metadata about the latest analysis run. */
    analysis: {
      /** Incremented on each SUCCESSFUL analysis. 0 = never analysed. */
      version: { type: Number, default: 0, min: 0 },
      /** Incremented on each attempt, successful or not. */
      runCount: { type: Number, default: 0, min: 0 },
      /** Correlation id of the latest attempt. Opaque; never PHI. */
      requestId: { type: String, maxlength: 64, default: undefined },
      startedAt: { type: Date, default: undefined },
      completedAt: { type: Date, default: undefined },
      durationMs: { type: Number, default: undefined },
      /** The step a RUNNING analysis is on; cleared when it ends. */
      progressStep: { type: String, enum: ANALYSIS_STEPS, default: undefined },
      progressAt: { type: Date, default: undefined },
      /** Whether a Module 2 profile existed and was sent with the features call. */
      profileUsed: { type: Boolean, default: undefined },
      /** Module 4's own confidence, surfaced without unpacking the payload. */
      extractionConfidence: { type: Number, default: undefined },
      /**
       * Page numbers Module 4 could not read, forwarded by Module 5 under
       * `upstream.pages_unreadable`. This is the difference between "the test
       * is not on the report" and "we could not read the page it was on" -
       * Module 17 has to be able to say which, so it is pulled up here rather
       * than left buried in the payload.
       */
      pagesUnreadable: { type: [Number], default: undefined },
      warningCount: { type: Number, default: undefined },

      // --- per-stage outcome, decision counts, risk ------------------------
      //
      // These are ALWAYS LOADED (no `select: false`) on purpose: they are the
      // questions a dashboard, a listing or an operator asks without wanting
      // the payload - did every stage run, how many decisions came out, what
      // was the worst risk. Pulling them up here keeps `GET /reports` light
      // while still answering them.

      /**
       * Per-stage outcome for the latest SUCCESSFUL-ENOUGH run, keyed by stage
       * name: `{ ok, errorCode?, skipped?, reasonCode?, durationMs? }`.
       *
       * `errorCode` and `reasonCode` are drawn from a fixed table of our own
       * machine codes (analysisService.SAFE_STATUS_MESSAGES /
       * STAGE_SKIP_REASONS), never from a service response body, so this field
       * carries the same structural PHI guarantee as `statusMessage`.
       */
      stages: { type: mongoose.Schema.Types.Mixed, default: undefined },

      /** Stage names that did not produce a result. Empty on a full success. */
      stagesFailed: { type: [String], default: undefined },

      ruleDecisionCount: { type: Number, default: undefined },
      mlDecisionCount: { type: Number, default: undefined },
      decisionCount: { type: Number, default: undefined },

      /** `Low` | `Medium` | `High`, the highest across BOTH decision sources. */
      highestRisk: { type: String, default: undefined },

      /** Conditions flagged by either source, de-duplicated. */
      conditionsFlagged: { type: [String], default: undefined },

      /** Module 6 partition sizes, so a consumer need not load the payload. */
      validFeatureCount: { type: Number, default: undefined },
      questionableFeatureCount: { type: Number, default: undefined },
      rejectedFeatureCount: { type: Number, default: undefined },

      // --- Modules 17-20: the clinical report, summarised ------------------
      //
      // These exist so a listing, a dashboard tile or an operator can answer
      // "how is this patient's report" without loading `clinicalReport`.

      /** `report_version` of the generator that produced the stored report. */
      reportVersion: { type: String, default: undefined },

      /**
       * MODULE 18 HAS FOUR CASES AND THIS FIELD IS NULLABLE ON PURPOSE.
       *
       *   null                        nothing could be assessed
       *   'Healthy'                   assessed, no abnormal finding
       *   'Needs Monitoring'          abnormal finding, no High risk
       *   'Needs Medical Attention'   abnormal finding + High risk
       *
       * `Mixed`, not `String`, precisely so an explicit `null` PERSISTS and
       * stays distinguishable from "the report stage did not run" (absent).
       * Collapsing the two would make a report whose every test was unreadable
       * indistinguishable from one that was never generated - and the next step
       * after that is rendering it as `Healthy`, which is the single most
       * dangerous thing this pipeline could say. `analysis.overallStatusLabel`
       * is the always-renderable companion; see below.
       */
      overallStatus: { type: mongoose.Schema.Types.Mixed, default: undefined },

      /**
       * The label a renderer shows. FIVE values, never three: the spec's three,
       * plus `Not Assessed`, plus `Healthy (partial assessment)` - matching the
       * producer's `OVERALL_STATUS_LABELS` in `ai-service/app/schemas/report.py`,
       * which is the source of truth for this vocabulary.
       *
       * CARRIED from the analysis service's `overall.status_label` and validated
       * by `analysisService.summariseReport` (vocabulary, pairing with
       * `overallStatus`, and agreement with `assessmentComplete`) - not derived
       * from `overallStatus`, which cannot express the fifth value at all. A
       * label that fails any of those checks degrades to `Not Assessed` and
       * takes `overallStatus` to `null` with it.
       */
      overallStatusLabel: { type: String, default: undefined },

      /**
       * WHY the label above was not taken at face value, as a fixed machine
       * code (`analysisService.STATUS_LABEL_DISAGREEMENTS`), or absent when it
       * was. Never a formatted string and never an echo of the offending value.
       *
       * This is the persisted half of the drift check: the same fact also
       * appears in `analysisWarnings` at the `report` stage, so it is visible
       * both to a reader of the summary and to a reader of the warnings.
       */
      statusLabelDisagreement: { type: String, default: undefined },

      /**
       * Highest risk across ASSESSED conditions. Nullable for the same reason
       * as `overallStatus`, and stored as `Mixed` for the same reason: "nothing
       * was assessed" must never read as `Low`.
       */
      overallRisk: { type: mongoose.Schema.Types.Mixed, default: undefined },

      /**
       * Module 18's `complete`. False means the status above rests on partial
       * information and the report's `overall.caveat` is non-null.
       */
      assessmentComplete: { type: Boolean, default: undefined },

      /** Module 18's `any_assessed`. False whenever `overallStatus` is null. */
      anyAssessed: { type: Boolean, default: undefined },

      conditionCount: { type: Number, default: undefined },
      criticalConditionCount: { type: Number, default: undefined },
      abnormalConditionCount: { type: Number, default: undefined },
      normalConditionCount: { type: Number, default: undefined },
      unassessedConditionCount: { type: Number, default: undefined },
      recommendationCount: { type: Number, default: undefined },
      laboratoryValueCount: { type: Number, default: undefined },

      // --- Modules 23 and 26: the patient-facing layer, summarised ---------

      /**
       * TRUE ONLY IF AT LEAST ONE APPROVED SENTENCE EXISTS.
       *
       * Three states, and all three are different:
       *   undefined  the explanation stage did not answer at all
       *   false      it answered and NOTHING was approved (withheld, not
       *              grounded, no model) - there is a reviewed notice to show
       *   true       at least one finding has a patient-facing explanation
       *
       * A dashboard tile that collapsed `false` into `undefined` would show a
       * report where the safety layer refused to speak exactly like one that
       * was never explained, and both like one with nothing to say.
       */
      explanationAvailable: { type: Boolean, default: undefined },

      /** Findings Module 23 attempted, approved and withheld. */
      explanationCount: { type: Number, default: undefined },
      explanationGeneratedCount: { type: Number, default: undefined },
      explanationWithheldCount: { type: Number, default: undefined },

      /**
       * Count PER OUTCOME - `{ generated: 2, withheld_by_safety: 1 }`.
       *
       * The operational question is "how often is the safety layer refusing",
       * which a list of repeated outcome words does not answer. `Mixed`
       * because the keys are Module 23's outcome vocabulary, and an outcome
       * added on the far side must land here rather than be dropped.
       */
      explanationOutcomes: { type: mongoose.Schema.Types.Mixed, default: undefined },

      /** Module 26 items resolved from the catalogue. */
      guidanceItemCount: { type: Number, default: undefined },

      /**
       * Module 26's own `generated` flag, stored rather than assumed. It is
       * always `false` - the route reaches no model - and a `true` here would
       * be a defect worth being able to see in a query.
       */
      guidanceGenerated: { type: Boolean, default: undefined },
    },
  },
  {
    timestamps: true,
    toJSON: {
      virtuals: false,
      transform(doc, ret) {
        delete ret.__v;
        // The storage key is an internal locator; there is no reason for a
        // client to see it, and echoing it back invites probing.
        delete ret.storageKey;
        return ret;
      },
    },
  }
);

/**
 * Primary access path: "this user's reports, newest first".
 * `_id` is the tiebreaker so pagination is stable when two reports share a
 * chronoDate (a bulk upload of same-dated reports is the normal case).
 */
reportSchema.index({ user: 1, chronoDate: -1, _id: -1 });

/**
 * THE ONE RULE FOR THE SORT KEY: typed, then printed, then uploaded.
 *
 * A function, not only a hook, because the analysis write is an `updateOne`
 * and skips the hook -- MEMORY.md records a hand `$set` that left `chronoDate`
 * disagreeing with its inputs for exactly that reason.
 */
function deriveChronoDate({ reportDate, printedDate, uploadedAt }) {
  return reportDate || printedDate || uploadedAt;
}

/** Keep the materialised sort key honest. */
reportSchema.pre('validate', function keepChronoDate(next) {
  if (!this.uploadedAt) this.uploadedAt = new Date();
  this.chronoDate = deriveChronoDate(this);
  return next();
});

/** Public-safe representation used inside the API success envelope. */
reportSchema.methods.toPublicJSON = function toPublicJSON() {
  return {
    id: this._id.toString(),
    user: this.user.toString(),
    originalName: this.originalName,
    mimeType: this.mimeType,
    sizeBytes: this.sizeBytes,
    checksumSha256: this.checksumSha256,
    storageDriver: this.storageDriver,
    uploadedAt: this.uploadedAt,
    reportDate: this.reportDate,
    printedDate: this.printedDate,
    printedDateStatus: this.printedDateStatus,
    // Only when it could NOT be read, so the page can quote it. A date that
    // was read is already `printedDate`.
    printedDateRaw:
      this.printedDateStatus === 'ambiguous' || this.printedDateStatus === 'unreadable'
        ? this.printedDateRaw
        : undefined,
    chronoDate: this.chronoDate,
    status: this.status,
    statusMessage: this.statusMessage,
    // Where a RUNNING analysis has got to (2026-10-04). Only while
    // processing: a finished report has no "current step", and a stale value
    // left by a crashed run must not read as live.
    analysisProgress:
      this.status === REPORT_STATUS.PROCESSING
        ? {
            step: ANALYSIS_STEPS.includes(this.analysis?.progressStep)
              ? this.analysis.progressStep
              : null,
            stepNumber: ANALYSIS_STEPS.includes(this.analysis?.progressStep)
              ? ANALYSIS_STEPS.indexOf(this.analysis.progressStep) + 1
              : null,
            totalSteps: ANALYSIS_STEPS.length,
            startedAt: this.analysis?.startedAt,
          }
        : undefined,
    // Whose report, and whether that changed since the stored analysis ran
    // (the analysis then still reflects the old answer -- see `subject`).
    subject: {
      owner: this.subject?.owner === 'other' ? 'other' : 'self',
      age: this.subject?.age,
      sex: this.subject?.sex,
    },
    // Against the analysis START, not its end (2026-10-04): the run reads
    // `subject` when it begins, so an answer changed WHILE it runs is not in
    // it. Compared with `completedAt`, Test 3 marked "mine" 30 s into a run
    // that had started as someone else's reported nothing to re-analyse.
    // `completedAt` is the fallback for an analysis stored without a start.
    subjectChangedSinceAnalysis: Boolean(
      this.subject?.updatedAt &&
        (this.analysis?.startedAt || this.analysis?.completedAt) &&
        this.subject.updatedAt > (this.analysis.startedAt || this.analysis.completedAt)
    ),
    createdAt: this.createdAt,
    updatedAt: this.updatedAt,
  };
};

/**
 * The stored analysis, for `GET /reports/:id/analyze` and
 * `GET /reports/:id/analysis`.
 *
 * `extraction`, `features` and `analysisWarnings` are `select: false`, so this
 * is only meaningful on a document loaded with them explicitly selected. It is
 * a SEPARATE method rather than an addition to `toPublicJSON` on purpose:
 * Module 3's list and detail responses must keep their existing shape, and
 * report text has no business in a paginated listing.
 */
reportSchema.methods.toAnalysisJSON = function toAnalysisJSON() {
  const meta = this.analysis || {};
  return {
    reportId: this._id.toString(),
    status: this.status,
    statusMessage: this.statusMessage,
    version: meta.version || 0,
    runCount: meta.runCount || 0,
    requestId: meta.requestId,
    startedAt: meta.startedAt,
    completedAt: meta.completedAt,
    durationMs: meta.durationMs,
    profileUsed: meta.profileUsed,
    extractionConfidence: meta.extractionConfidence,
    pagesUnreadable: Array.isArray(meta.pagesUnreadable) ? meta.pagesUnreadable : [],

    // Per-stage outcome. Always present so a consumer can branch on it rather
    // than inferring "the ML stage failed" from a missing key.
    stages: meta.stages || {},
    stagesFailed: Array.isArray(meta.stagesFailed) ? meta.stagesFailed : [],

    ruleDecisionCount: meta.ruleDecisionCount,
    mlDecisionCount: meta.mlDecisionCount,
    decisionCount: meta.decisionCount,
    highestRisk: meta.highestRisk,
    conditionsFlagged: Array.isArray(meta.conditionsFlagged) ? meta.conditionsFlagged : [],
    validFeatureCount: meta.validFeatureCount,
    questionableFeatureCount: meta.questionableFeatureCount,
    rejectedFeatureCount: meta.rejectedFeatureCount,

    // --- Modules 17-20 -----------------------------------------------------
    //
    // `overallStatus` is passed through EXACTLY as stored, `null` included.
    // It is never coalesced (`||`, `??`) to a string and never defaulted:
    // `null` is Module 18's fourth case ("nothing could be assessed") and a
    // consumer that turned it into `Healthy` would tell a patient whose
    // document could not be read that they are well. `overallStatusLabel` is
    // the always-renderable companion and carries FOUR values, never three;
    // `anyAssessed` and `assessmentComplete` are the machine-readable halves.
    reportVersion: meta.reportVersion,
    overallStatus: meta.overallStatus,
    overallStatusLabel: meta.overallStatusLabel,
    overallRisk: meta.overallRisk,
    assessmentComplete: meta.assessmentComplete,
    anyAssessed: meta.anyAssessed,
    conditionCount: meta.conditionCount,
    criticalConditionCount: meta.criticalConditionCount,
    abnormalConditionCount: meta.abnormalConditionCount,
    normalConditionCount: meta.normalConditionCount,
    unassessedConditionCount: meta.unassessedConditionCount,
    recommendationCount: meta.recommendationCount,
    laboratoryValueCount: meta.laboratoryValueCount,

    // --- Modules 23 and 26 -------------------------------------------------
    //
    // `explanationAvailable` is passed through EXACTLY as stored, `false`
    // included and never coalesced. `false` means the stage ran and the
    // platform has something to tell the patient - that no explanation could be
    // approved, and why - which is not the same as `undefined`, the stage never
    // having answered. A consumer that treated the two alike would render a
    // withheld explanation as an empty section.
    explanationAvailable: meta.explanationAvailable,
    explanationCount: meta.explanationCount,
    explanationGeneratedCount: meta.explanationGeneratedCount,
    explanationWithheldCount: meta.explanationWithheldCount,
    explanationOutcomes: meta.explanationOutcomes,
    guidanceItemCount: meta.guidanceItemCount,
    guidanceGenerated: meta.guidanceGenerated,

    extraction: this.extraction,
    features: this.features,
    // Modules 6, 8 and 9/10. `null` rather than `undefined` when the stage did
    // not produce a result, so "this stage was not stored" is visible in JSON
    // instead of vanishing from the response.
    validation: this.featureValidation === undefined ? null : this.featureValidation,
    ruleDecisions: this.ruleDecisions === undefined ? null : this.ruleDecisions,
    mlDecisions: this.mlDecisions === undefined ? null : this.mlDecisions,
    // Modules 17-20. `null`, not absent, when the report stage did not answer.
    report: this.clinicalReport === undefined ? null : this.clinicalReport,
    // Modules 23 and 26. `null`, not absent, when the stage did not answer -
    // so "we could not explain this report" is a value in the response rather
    // than a key a client has to notice is missing. A stage that DID answer but
    // approved nothing is NOT null: it is the full set, with every outcome, its
    // reviewed notice, and `explanation_available: false`.
    explanation: this.patientExplanation === undefined ? null : this.patientExplanation,
    guidance: this.lifestyleGuidance === undefined ? null : this.lifestyleGuidance,
    // Always an array, so a consumer never has to distinguish "no warnings"
    // from "warnings not loaded" by type.
    warnings: Array.isArray(this.analysisWarnings) ? this.analysisWarnings : [],
  };
};

const Report = mongoose.model('Report', reportSchema);

module.exports = Report;
module.exports.REPORT_STATUS = REPORT_STATUS;
module.exports.REPORT_STATUS_VALUES = REPORT_STATUS_VALUES;
module.exports.ANALYSIS_STEPS = ANALYSIS_STEPS;
module.exports.SORT_FIELDS = SORT_FIELDS;
module.exports.deriveChronoDate = deriveChronoDate;

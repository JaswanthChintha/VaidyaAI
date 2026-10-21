'use strict';

const mongoose = require('mongoose');
const { ALLOWED_MIME_TYPES, MAX_DISPLAY_NAME_LENGTH } = require('../utils/fileSecurity');
const Profile = require('./Profile');


const REPORT_STATUS = Object.freeze({
  UPLOADED: 'uploaded',
  PROCESSING: 'processing',
  PROCESSED: 'processed',
  PARTIAL: 'partial',
  FAILED: 'failed',
});
const REPORT_STATUS_VALUES = Object.freeze(Object.values(REPORT_STATUS));

const ANALYSIS_STEPS = Object.freeze(['reading', 'checking', 'deciding', 'explaining']);

const SORT_FIELDS = Object.freeze(['chronoDate', 'uploadedAt', 'reportDate']);

const reportSchema = new mongoose.Schema(
  {
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User',
      required: [true, 'A report must belong to a user'],
      immutable: true,
      index: true,
    },

    originalName: {
      type: String,
      required: true,
      maxlength: MAX_DISPLAY_NAME_LENGTH,
      trim: true,
    },

    storageKey: {
      type: String,
      required: true,
      immutable: true,
    },

    storageDriver: {
      type: String,
      required: true,
      immutable: true,
    },

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

    checksumSha256: {
      type: String,
      required: true,
      match: [/^[a-f0-9]{64}$/, 'Invalid checksum'],
      index: true,
    },

    uploadedAt: {
      type: Date,
      required: true,
      default: Date.now,
      immutable: true,
    },

    reportDate: {
      type: Date,
      default: undefined,
    },

    subject: {
      owner: { type: String, enum: ['self', 'other'], default: 'self' },
      age: { type: Number, min: 0, max: 120, default: undefined },
      sex: { type: String, enum: Profile.GENDER_VALUES, default: undefined },
      updatedAt: { type: Date, default: undefined },
    },

    printedDate: {
      type: Date,
      default: undefined,
    },

    printedDateStatus: {
      type: String,
      enum: ['read', 'ambiguous', 'unreadable', 'absent'],
      default: undefined,
    },

    printedDateRaw: {
      type: String,
      maxlength: 64,
      default: undefined,
    },

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

    chronoDate: {
      type: Date,
      required: true,
    },

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

    statusMessage: {
      type: String,
      maxlength: 500,
      default: undefined,
    },


    extraction: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    features: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    featureValidation: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    ruleDecisions: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    mlDecisions: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    clinicalReport: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    doctorNarrative: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    summaryProse: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    findingContext: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    patientExplanation: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    lifestyleGuidance: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    parameterGlossary: {
      type: mongoose.Schema.Types.Mixed,
      select: false,
      default: undefined,
    },

    analysisWarnings: {
      type: [mongoose.Schema.Types.Mixed],
      select: false,
      default: undefined,
    },

    analysis: {
      version: { type: Number, default: 0, min: 0 },
      runCount: { type: Number, default: 0, min: 0 },
      requestId: { type: String, maxlength: 64, default: undefined },
      startedAt: { type: Date, default: undefined },
      completedAt: { type: Date, default: undefined },
      durationMs: { type: Number, default: undefined },
      progressStep: { type: String, enum: ANALYSIS_STEPS, default: undefined },
      progressAt: { type: Date, default: undefined },
      profileUsed: { type: Boolean, default: undefined },
      extractionConfidence: { type: Number, default: undefined },
      pagesUnreadable: { type: [Number], default: undefined },
      warningCount: { type: Number, default: undefined },


      stages: { type: mongoose.Schema.Types.Mixed, default: undefined },

      stagesFailed: { type: [String], default: undefined },

      ruleDecisionCount: { type: Number, default: undefined },
      mlDecisionCount: { type: Number, default: undefined },
      decisionCount: { type: Number, default: undefined },

      highestRisk: { type: String, default: undefined },

      conditionsFlagged: { type: [String], default: undefined },

      validFeatureCount: { type: Number, default: undefined },
      questionableFeatureCount: { type: Number, default: undefined },
      rejectedFeatureCount: { type: Number, default: undefined },


      reportVersion: { type: String, default: undefined },

      overallStatus: { type: mongoose.Schema.Types.Mixed, default: undefined },

      overallStatusLabel: { type: String, default: undefined },

      statusLabelDisagreement: { type: String, default: undefined },

      overallRisk: { type: mongoose.Schema.Types.Mixed, default: undefined },

      assessmentComplete: { type: Boolean, default: undefined },

      anyAssessed: { type: Boolean, default: undefined },

      conditionCount: { type: Number, default: undefined },
      criticalConditionCount: { type: Number, default: undefined },
      abnormalConditionCount: { type: Number, default: undefined },
      normalConditionCount: { type: Number, default: undefined },
      unassessedConditionCount: { type: Number, default: undefined },
      recommendationCount: { type: Number, default: undefined },
      laboratoryValueCount: { type: Number, default: undefined },


      explanationAvailable: { type: Boolean, default: undefined },

      explanationCount: { type: Number, default: undefined },
      explanationGeneratedCount: { type: Number, default: undefined },
      explanationWithheldCount: { type: Number, default: undefined },

      explanationOutcomes: { type: mongoose.Schema.Types.Mixed, default: undefined },

      guidanceItemCount: { type: Number, default: undefined },

      guidanceGenerated: { type: Boolean, default: undefined },
    },
  },
  {
    timestamps: true,
    toJSON: {
      virtuals: false,
      transform(doc, ret) {
        delete ret.__v;
        delete ret.storageKey;
        return ret;
      },
    },
  }
);

reportSchema.index({ user: 1, chronoDate: -1, _id: -1 });

function deriveChronoDate({ reportDate, printedDate, uploadedAt }) {
  return reportDate || printedDate || uploadedAt;
}

reportSchema.pre('validate', function keepChronoDate(next) {
  if (!this.uploadedAt) this.uploadedAt = new Date();
  this.chronoDate = deriveChronoDate(this);
  return next();
});

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
    printedDateRaw:
      this.printedDateStatus === 'ambiguous' || this.printedDateStatus === 'unreadable'
        ? this.printedDateRaw
        : undefined,
    chronoDate: this.chronoDate,
    status: this.status,
    statusMessage: this.statusMessage,
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
    subject: {
      owner: this.subject?.owner === 'other' ? 'other' : 'self',
      age: this.subject?.age,
      sex: this.subject?.sex,
    },
    subjectChangedSinceAnalysis: Boolean(
      this.subject?.updatedAt &&
        (this.analysis?.startedAt || this.analysis?.completedAt) &&
        this.subject.updatedAt > (this.analysis.startedAt || this.analysis.completedAt)
    ),
    pagesUnreadable: Array.isArray(this.analysis?.pagesUnreadable)
      ? this.analysis.pagesUnreadable.filter((n) => Number.isInteger(n))
      : [],
    createdAt: this.createdAt,
    updatedAt: this.updatedAt,
  };
};

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

    explanationAvailable: meta.explanationAvailable,
    explanationCount: meta.explanationCount,
    explanationGeneratedCount: meta.explanationGeneratedCount,
    explanationWithheldCount: meta.explanationWithheldCount,
    explanationOutcomes: meta.explanationOutcomes,
    guidanceItemCount: meta.guidanceItemCount,
    guidanceGenerated: meta.guidanceGenerated,

    extraction: this.extraction,
    features: this.features,
    validation: this.featureValidation === undefined ? null : this.featureValidation,
    ruleDecisions: this.ruleDecisions === undefined ? null : this.ruleDecisions,
    mlDecisions: this.mlDecisions === undefined ? null : this.mlDecisions,
    report: this.clinicalReport === undefined ? null : this.clinicalReport,
    explanation: this.patientExplanation === undefined ? null : this.patientExplanation,
    guidance: this.lifestyleGuidance === undefined ? null : this.lifestyleGuidance,
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

'use strict';

const mongoose = require('mongoose');

/**
 * Module 2 - Patient Profile Management.
 *
 * Health data lives in its OWN collection, referencing `User` by id, rather
 * than being embedded in the user document. Section 19 (Security and Privacy)
 * asks for "restricted medical information exposure"; keeping credentials and
 * medical data in separate documents means an auth query never pulls health
 * data into memory, and the two can later be encrypted, retained or deleted
 * independently.
 *
 * UNITS ARE FIXED AND EXPLICIT (a unit mix-up silently corrupts every
 * downstream ML prediction):
 *   heightCm - centimetres
 *   weightKg - kilograms
 *   bmi      - kg/m^2, DERIVED, never accepted from the client
 *   age      - whole years
 */

// --- Enumerations ---------------------------------------------------------

/**
 * Stored gender. The user's actual answer is always what gets persisted.
 * The ML predictors of Modules 10-12 are trained on a binary Male/Female
 * feature, so `other` / `prefer_not_to_say` are represented faithfully here
 * and left for the predictor to treat as "not available" rather than being
 * forced into a category at write time.
 */
const GENDERS = Object.freeze({
  MALE: 'male',
  FEMALE: 'female',
  OTHER: 'other',
  PREFER_NOT_TO_SAY: 'prefer_not_to_say',
});
const GENDER_VALUES = Object.freeze(Object.values(GENDERS));

/** Gender values a binary-trained predictor can consume directly. */
const ML_GENDER_VALUES = Object.freeze([GENDERS.MALE, GENDERS.FEMALE]);

/**
 * Smoking history. These are exactly the categories used by the public
 * diabetes-prediction dataset the Module 10 predictor is modelled on, so the
 * stored string can be fed to the encoder without a translation table.
 * `no_info` is the explicit "unknown" category - it is a real level of the
 * feature, not a null.
 */
const SMOKING_HISTORY = Object.freeze({
  NEVER: 'never',
  FORMER: 'former',
  CURRENT: 'current',
  EVER: 'ever',
  NOT_CURRENT: 'not_current',
  NO_INFO: 'no_info',
});
const SMOKING_HISTORY_VALUES = Object.freeze(Object.values(SMOKING_HISTORY));

// --- Physiological bounds -------------------------------------------------
// Deliberately generous: these exist to reject data-entry nonsense (a height
// of 5 cm, a weight of 4000 kg) that would poison a model, NOT to second-guess
// real outliers. Lab-value validation is Module 6 and is out of scope here.
const BOUNDS = Object.freeze({
  age: { min: 0, max: 120 },
  heightCm: { min: 30, max: 275 },
  weightKg: { min: 1, max: 650 },
});

// --- Free-text array caps -------------------------------------------------
const TEXT_LIST = Object.freeze({
  maxItems: 30,
  maxItemLength: 200,
});
const NOTES_LIST = Object.freeze({
  maxItems: 10,
  maxItemLength: 500,
});

/** Core fields the ML predictors of Modules 10-12 consume as patient context. */
const COMPLETENESS_FIELDS = Object.freeze([
  'age',
  'gender',
  'heightCm',
  'weightKg',
  'hypertension',
  'heartDisease',
  'smokingHistory',
]);

const textListField = (cap) => ({
  type: [String],
  default: undefined,
  validate: [
    {
      validator: (list) => !Array.isArray(list) || list.length <= cap.maxItems,
      message: `At most ${cap.maxItems} entries are allowed`,
    },
    {
      validator: (list) =>
        !Array.isArray(list) ||
        list.every((v) => typeof v === 'string' && v.length <= cap.maxItemLength),
      // Never echoes the offending value back to the client.
      message: `Each entry must be text of at most ${cap.maxItemLength} characters`,
    },
  ],
});

const profileSchema = new mongoose.Schema(
  {
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User',
      required: [true, 'A profile must belong to a user'],
      unique: true, // one profile per user
      immutable: true, // a profile can never be re-pointed at another account
    },

    age: {
      type: Number,
      min: [BOUNDS.age.min, `Age must be at least ${BOUNDS.age.min}`],
      max: [BOUNDS.age.max, `Age must be at most ${BOUNDS.age.max}`],
      validate: {
        validator: (v) => v === undefined || v === null || Number.isInteger(v),
        message: 'Age must be a whole number of years',
      },
    },

    gender: {
      type: String,
      enum: {
        values: GENDER_VALUES,
        message: `Gender must be one of: ${GENDER_VALUES.join(', ')}`,
      },
    },

    /** Height in CENTIMETRES. */
    heightCm: {
      type: Number,
      min: [BOUNDS.heightCm.min, `Height must be at least ${BOUNDS.heightCm.min} cm`],
      max: [BOUNDS.heightCm.max, `Height must be at most ${BOUNDS.heightCm.max} cm`],
    },

    /** Weight in KILOGRAMS. */
    weightKg: {
      type: Number,
      min: [BOUNDS.weightKg.min, `Weight must be at least ${BOUNDS.weightKg.min} kg`],
      max: [BOUNDS.weightKg.max, `Weight must be at most ${BOUNDS.weightKg.max} kg`],
    },

    /**
     * BMI in kg/m^2. DERIVED from heightCm and weightKg by the pre-validate
     * hook below on every save. A client-supplied value is never trusted: the
     * controller allow-lists input fields and `bmi` is not among them, and the
     * hook overwrites the field regardless.
     */
    bmi: {
      type: Number,
      default: undefined,
    },

    /** Diagnosed hypertension. true / false / absent (= unknown). */
    hypertension: { type: Boolean },

    /** Diagnosed heart disease. true / false / absent (= unknown). */
    heartDisease: { type: Boolean },

    /** Free-text detail behind `heartDisease` (spec: "existing heart disease information"). */
    heartDiseaseDetails: textListField(TEXT_LIST),

    smokingHistory: {
      type: String,
      enum: {
        values: SMOKING_HISTORY_VALUES,
        message: `Smoking history must be one of: ${SMOKING_HISTORY_VALUES.join(', ')}`,
      },
    },

    allergies: textListField(TEXT_LIST),
    medicalConditions: textListField(TEXT_LIST),
    medications: textListField(TEXT_LIST),
    previousHealthInformation: textListField(NOTES_LIST),
  },
  {
    timestamps: true,
    toJSON: {
      virtuals: true,
      transform(doc, ret) {
        delete ret.__v;
        delete ret.id;
        return ret;
      },
    },
  }
);

/** Compute BMI (kg/m^2) or undefined when either input is missing. */
function computeBmi(heightCm, weightKg) {
  if (typeof heightCm !== 'number' || typeof weightKg !== 'number') return undefined;
  if (!Number.isFinite(heightCm) || !Number.isFinite(weightKg) || heightCm <= 0) {
    return undefined;
  }
  const metres = heightCm / 100;
  return Math.round((weightKg / (metres * metres)) * 100) / 100;
}

// BMI is recomputed before validation on EVERY save, so no code path - route,
// script or future module - can persist a client-supplied or stale value.
profileSchema.pre('validate', function deriveBmi(next) {
  this.bmi = computeBmi(this.heightCm, this.weightKg);
  return next();
});

/**
 * How much of the ML-relevant patient context is present.
 * Module 12's kidney predictor explicitly skips prediction when information is
 * insufficient; exposing this lets later modules degrade gracefully instead of
 * probing field by field.
 */
profileSchema.virtual('completeness').get(function completeness() {
  const missing = COMPLETENESS_FIELDS.filter(
    (field) => this[field] === undefined || this[field] === null
  );
  const filled = COMPLETENESS_FIELDS.length - missing.length;
  return {
    fields: COMPLETENESS_FIELDS.length,
    filled,
    percent: Math.round((filled / COMPLETENESS_FIELDS.length) * 100),
    missing,
  };
});

/** Public-safe representation used inside the API success envelope. */
profileSchema.methods.toPublicJSON = function toPublicJSON() {
  return {
    id: this._id.toString(),
    user: this.user.toString(),
    age: this.age,
    gender: this.gender,
    heightCm: this.heightCm,
    weightKg: this.weightKg,
    bmi: this.bmi,
    hypertension: this.hypertension,
    heartDisease: this.heartDisease,
    heartDiseaseDetails: this.heartDiseaseDetails,
    smokingHistory: this.smokingHistory,
    allergies: this.allergies,
    medicalConditions: this.medicalConditions,
    medications: this.medications,
    previousHealthInformation: this.previousHealthInformation,
    completeness: this.completeness,
    createdAt: this.createdAt,
    updatedAt: this.updatedAt,
  };
};

const Profile = mongoose.model('Profile', profileSchema);

module.exports = Profile;
module.exports.GENDERS = GENDERS;
module.exports.GENDER_VALUES = GENDER_VALUES;
module.exports.ML_GENDER_VALUES = ML_GENDER_VALUES;
module.exports.SMOKING_HISTORY = SMOKING_HISTORY;
module.exports.SMOKING_HISTORY_VALUES = SMOKING_HISTORY_VALUES;
module.exports.BOUNDS = BOUNDS;
module.exports.TEXT_LIST = TEXT_LIST;
module.exports.NOTES_LIST = NOTES_LIST;
module.exports.COMPLETENESS_FIELDS = COMPLETENESS_FIELDS;
module.exports.computeBmi = computeBmi;

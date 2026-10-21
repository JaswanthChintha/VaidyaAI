'use strict';

const mongoose = require('mongoose');


const GENDERS = Object.freeze({
  MALE: 'male',
  FEMALE: 'female',
  OTHER: 'other',
  PREFER_NOT_TO_SAY: 'prefer_not_to_say',
});
const GENDER_VALUES = Object.freeze(Object.values(GENDERS));

const ML_GENDER_VALUES = Object.freeze([GENDERS.MALE, GENDERS.FEMALE]);

const SMOKING_HISTORY = Object.freeze({
  NEVER: 'never',
  FORMER: 'former',
  CURRENT: 'current',
  EVER: 'ever',
  NOT_CURRENT: 'not_current',
  NO_INFO: 'no_info',
});
const SMOKING_HISTORY_VALUES = Object.freeze(Object.values(SMOKING_HISTORY));

const BOUNDS = Object.freeze({
  age: { min: 0, max: 120 },
  heightCm: { min: 30, max: 275 },
  weightKg: { min: 1, max: 650 },
});

const TEXT_LIST = Object.freeze({
  maxItems: 30,
  maxItemLength: 200,
});
const NOTES_LIST = Object.freeze({
  maxItems: 10,
  maxItemLength: 500,
});

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
      unique: true,
      immutable: true,
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

    heightCm: {
      type: Number,
      min: [BOUNDS.heightCm.min, `Height must be at least ${BOUNDS.heightCm.min} cm`],
      max: [BOUNDS.heightCm.max, `Height must be at most ${BOUNDS.heightCm.max} cm`],
    },

    weightKg: {
      type: Number,
      min: [BOUNDS.weightKg.min, `Weight must be at least ${BOUNDS.weightKg.min} kg`],
      max: [BOUNDS.weightKg.max, `Weight must be at most ${BOUNDS.weightKg.max} kg`],
    },

    bmi: {
      type: Number,
      default: undefined,
    },

    hypertension: { type: Boolean },

    heartDisease: { type: Boolean },

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

function computeBmi(heightCm, weightKg) {
  if (typeof heightCm !== 'number' || typeof weightKg !== 'number') return undefined;
  if (!Number.isFinite(heightCm) || !Number.isFinite(weightKg) || heightCm <= 0) {
    return undefined;
  }
  const metres = heightCm / 100;
  return Math.round((weightKg / (metres * metres)) * 100) / 100;
}

profileSchema.pre('validate', function deriveBmi(next) {
  this.bmi = computeBmi(this.heightCm, this.weightKg);
  return next();
});

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

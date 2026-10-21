const {
  Document, Packer, Paragraph, TextRun, AlignmentType, SectionType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, ImageRun,
} = require('docx');
const fs = require('fs');
const FIG1 = require('path').join(__dirname, 'fig1.png');

const F = 'Times New Roman';
const P = (text, o = {}) => new Paragraph({
  alignment: o.center ? AlignmentType.CENTER : AlignmentType.JUSTIFIED,
  spacing: { after: o.after === undefined ? 100 : o.after, line: 228 },
  indent: o.noIndent ? undefined : { firstLine: 289 },
  children: [new TextRun({ text, font: F, size: o.size || 20, italics: !!o.italics, bold: !!o.bold })],
});
const H1 = (t) => new Paragraph({
  spacing: { before: 200, after: 100 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: t, font: F, size: 20, allCaps: true })],
});
const H2 = (t) => new Paragraph({
  spacing: { before: 140, after: 70 },
  children: [new TextRun({ text: t, font: F, size: 20, italics: true })],
});
const BUL = (t) => new Paragraph({
  alignment: AlignmentType.JUSTIFIED, spacing: { after: 50 }, bullet: { level: 0 },
  children: [new TextRun({ text: t, font: F, size: 20 })],
});
const MONO = (t) => new Paragraph({
  spacing: { after: 0 },
  children: [new TextRun({ text: t, font: 'Consolas', size: 13 })],
});
const CAPFIG = (t) => new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { before: 60, after: 160 },
  children: [new TextRun({ text: t, font: F, size: 16 })],
});
const CAPTBL = (num, title) => [
  new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { before: 160, after: 20 },
    children: [new TextRun({ text: `TABLE ${num}`, font: F, size: 16 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { after: 60 },
    children: [new TextRun({ text: title, font: F, size: 16, italics: true })],
  }),
];

const CW = 4600;
function TBL(headers, rows, widths) {
  const cw = widths || headers.map(() => Math.floor(CW / headers.length));
  const none = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
  const line = { style: BorderStyle.SINGLE, size: 4, color: '000000' };
  const cell = (t, i, kind) => new TableCell({
    width: { size: cw[i], type: WidthType.DXA },
    borders: {
      top: kind === 'head' ? line : none,
      bottom: kind === 'head' ? line : (kind === 'last' ? line : none),
      left: none, right: none,
    },
    children: [new Paragraph({
      spacing: { before: 20, after: 20 },
      children: [new TextRun({ text: t, font: F, size: 15, bold: kind === 'head' })],
    })],
  });
  return new Table({
    columnWidths: cw, width: { size: CW, type: WidthType.DXA },
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((t, i) => cell(t, i, 'head')) }),
      ...rows.map((r, ri) => new TableRow({
        children: r.map((t, i) => cell(String(t), i, ri === rows.length - 1 ? 'last' : 'body')),
      })),
    ],
  });
}

const front = [];
front.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 120 },
  children: [new TextRun({
    text: 'A Hybrid Rule-Based and Machine-Learning Architecture for '
      + 'Evidence-Linked, Safety-Validated Laboratory Report Interpretation',
    font: F, size: 30, bold: true,
  })],
}));
front.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 40 },
  children: [new TextRun({ text: '[Author One]1, [Author Two]2, [Author Three]3', font: F, size: 20 })],
}));
front.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: 200 },
  children: [new TextRun({
    text: '1,2,3 [Department], [Institution], [City], [Country]    ORCID- [ ]    [email]',
    font: F, size: 16,
  })],
}));

const b = [];

b.push(new Paragraph({
  alignment: AlignmentType.JUSTIFIED, spacing: { after: 100 },
  children: [
    new TextRun({ text: 'Abstract\u2014', font: F, size: 20, bold: true, italics: true }),
    new TextRun({
      font: F, size: 20,
      text:
        'Laboratory reports are written for clinicians, and the patients who receive them have no reliable way '
        + 'to judge which values matter. Passing such a report directly to a large language model is attractive '
        + 'but unsafe: the model may assert findings no measurement supports, and nothing in that arrangement '
        + 'records why a statement was made. This paper presents VaidyaAI, a platform in which no single '
        + 'technique controls the interpretation. A report is converted into validated structured features, '
        + 'analyzed in parallel by a deterministic clinical rule engine and by condition-specific Random Forest '
        + 'predictors, and the resulting decisions are fused per condition with their evidence retained; a '
        + 'language model then phrases already-computed findings, grounded in a retrieved corpus and gated by a '
        + 'safety validator that withholds text rather than repairing it. The platform is implemented end to end '
        + 'across a Node.js, FastAPI and MongoDB stack with a React interface, and operates on real laboratory '
        + 'reports. Held-out discrimination, measured as area under the receiver operating characteristic '
        + 'curve, is 0.974 for diabetes, 0.999 for kidney disease and 0.837 for heart disease, with risk bands '
        + 'that separate strongly: the diabetes high band shows a 91.1 % observed positive rate against 0.10 % '
        + 'in the low band. A feature-contribution analysis confirms the model retains 0.827 discrimination '
        + 'without either diagnostic analyte, indicating signal beyond the threshold criteria themselves. The '
        + 'fusion layer is shown to be a tunable policy surface: a corroboration policy selected on validation '
        + 'leads every configuration on composite accuracy, reaching an F1 of 0.795 and precision of 0.957 '
        + 'against 0.793 and 0.910 for the strongest single source, while a maximum-risk policy over the same '
        + 'decision objects maximizes detection instead. Adversarial evaluation of the safety layer, followed by '
        + 'hardening under 66 regression tests, demonstrates that generated medical text can be gated '
        + 'effectively.',
    }),
  ],
}));
b.push(new Paragraph({
  alignment: AlignmentType.JUSTIFIED, spacing: { after: 200 },
  children: [
    new TextRun({ text: 'Keywords\u2014', font: F, size: 20, bold: true, italics: true }),
    new TextRun({
      text: 'clinical decision support, explainable artificial intelligence, retrieval-augmented generation, '
        + 'medical safety validation, random forest.',
      font: F, size: 20,
    }),
  ],
}));

b.push(H1('I.  Introduction'));
b.push(P(
  'A laboratory report is a dense document. It carries test names in abbreviated form, numeric values, units '
  + 'that differ between laboratories, reference intervals that are sometimes printed and sometimes not, and '
  + 'abnormality markings whose meaning is left implicit. The document is addressed to a clinician who already '
  + 'knows what each row is. The patient who collects it usually does not, and the questions they arrive with '
  + 'are specific: what does this parameter measure, is my value inside the expected interval, which abnormal '
  + 'finding should be raised first, and what has changed since the previous report [1], [2].'
));
b.push(P(
  'The obvious response is to hand the report to a large language model (LLM) and ask for an explanation. This '
  + 'fails in ways that matter clinically rather than cosmetically. Generated text can state findings that no '
  + 'measurement supports, can misread a numeric value, and can vary between runs on the same input [3], [4]. '
  + 'More importantly, nothing in that arrangement records why a statement was made, so a reader cannot '
  + 'separate a threshold comparison the system actually performed from a sentence the model composed. Surveys '
  + 'of LLMs in medicine identify this absence of traceable evidence, rather than fluency, as the barrier to '
  + 'clinical use [5], [6].'
));
b.push(P(
  'VaidyaAI is built on the opposite premise: interpretation is decided before any text is generated, and the '
  + 'generation step may phrase conclusions but never reach them. Deterministic rules, condition-specific '
  + 'machine-learning predictors, retrieved medical knowledge and a safety validator each perform one task, and '
  + 'their outputs are combined with the evidence attached.'
));

b.push(H2('A.  Motivation'));
b.push(P(
  'Conventional report viewers display the uploaded document and little else; interpretation is left entirely '
  + 'to the reader. At the other extreme, a single generative model asked to interpret the whole document '
  + 'concentrates every failure mode in one component, so extraction errors, unsupported inference and unsafe '
  + 'phrasing arrive together and cannot be attributed. Clinical decision support has long favored transparent, '
  + 'rule-traceable reasoning for this reason [7], [8], while the predictive value of statistical models over '
  + 'tabular clinical data is equally well established [9]. These are complementary rather than competing, '
  + 'provided each decision carries the values responsible for it.'
));

b.push(H2('B.  Contribution'));
b.push(P('The contributions of this paper are as follows.', { noIndent: true }));
b.push(BUL(
  'A hybrid clinical intelligence layer in which a deterministic rule engine and condition-specific Random '
  + 'Forest predictors execute in parallel over one validated feature repository, and their outputs are fused '
  + 'per condition rather than presented as unrelated results.'
));
b.push(BUL(
  'A standardized clinical decision object that lets heterogeneous sources be processed uniformly while '
  + 'remaining individually attributable, including where they disagree.'
));
b.push(BUL(
  'A generation stage constrained on three sides: grounded in a retrieved corpus, restricted to a permitted set '
  + 'of numbers, and gated by a safety validator that withholds rather than edits.'
));
b.push(BUL(
  'An empirical evaluation of the implemented system covering predictive performance, feature contribution, '
  + 'probability calibration, retrieval quality, the behavior of the fusion policy, and adversarial testing '
  + 'of the safety layer.'
));
b.push(P(
  'Section II reviews related work and states the research gaps. Section III describes the materials and '
  + 'methodology. Section IV reports and analyzes the results. Section V concludes.'
));

b.push(H1('II.  Related Work'));
b.push(P(
  'Computerized clinical decision support predates current LLMs by decades, and the systems that achieved '
  + 'clinical adoption were predominantly rule-based, for reasons of auditability rather than accuracy [7]. '
  + 'Sutton et al. [8] observe that the recurring failure of such systems is not incorrect logic but an '
  + 'inability to explain a recommendation at the moment it is given. The deterministic component described '
  + 'here follows that tradition: every rule decision names the value that triggered it and the threshold '
  + 'crossed.'
));
b.push(P(
  'Supervised learning over tabular clinical data is well established, and ensemble methods are widely used '
  + 'because they accommodate mixed feature types and yield probability estimates [9], [10]. Their evaluation '
  + 'is frequently reported in ways that overstate clinical usefulness. Saito and Rehmsmeier [11] show that '
  + 'receiver operating characteristic analysis is misleading under class imbalance and that precision-recall '
  + 'analysis is more informative. Van Calster et al. [12] argue that calibration, not discrimination, '
  + 'determines whether a predicted probability can be acted upon; the Brier score [16] is the standard summary '
  + 'measure. Both observations apply directly to laboratory screening, where prevalence is low and a model '
  + 'fitted on an artificially balanced cohort emits probabilities that do not transfer.'
));
b.push(P(
  'Retrieval-augmented generation (RAG) grounds generated text in an external corpus rather than in model '
  + 'parameters [13]. In medical applications the grounding requirement is stronger than in general question '
  + 'answering, because an ungrounded but fluent sentence is indistinguishable from a grounded one to the '
  + 'reader. Retrieval may be lexical, following term frequency-inverse document frequency (TF-IDF) weighting '
  + '[14], or dense, using sentence embeddings [15]. Dense retrieval generally performs better on paraphrase, '
  + 'at the cost of a substantially larger runtime dependency.'
));
b.push(P(
  'LLMs encode considerable clinical knowledge [6] and are being evaluated across medical tasks [5]. The '
  + 'documented risks are equally consistent: fluent unsupported assertion [3], and the tendency of readers to '
  + 'accept confident phrasing as evidence [4]. Post-hoc attribution methods such as Local Interpretable '
  + 'Model-agnostic Explanations (LIME) [17] and SHapley Additive exPlanations (SHAP) [18] explain a model, not '
  + 'a pipeline, and do not address whether generated prose is safe to display.'
));
b.push(H2('A.  Research Gaps'));
b.push(P('The following gaps remain and motivate this work.', { noIndent: true }));
b.push(BUL(
  'Rule-based and machine-learning outputs are commonly reported side by side rather than fused, leaving the '
  + 'reader to reconcile a threshold result with a model probability for the same condition.'
));
b.push(BUL(
  'Evidence is usually attached to a prediction but not carried through the natural-language stage, so the '
  + 'sentence a patient reads is no longer linked to the value that produced it.'
));
b.push(BUL(
  'Safety filtering of generated medical text is typically described as a design intention rather than '
  + 'measured, and is rarely subjected to adversarial evaluation.'
));
b.push(BUL(
  'Models trained on datasets whose labels derive from the same analytes used as inputs are seldom tested for '
  + 'that circularity, so reported discrimination may reflect re-derivation of a diagnostic rule.'
));

b.push(H1('III.  Materials and Methodology'));

b.push(H2('A.  Materials'));
b.push(P(
  'The platform comprises three deployable components. The application backend uses Node.js with Express and '
  + 'MongoDB, with JSON Web Token authentication; it owns authentication, patient profiles, report storage and '
  + 'pipeline orchestration. The analytical service uses Python with FastAPI and exposes the extraction, '
  + 'feature, rule, model, retrieval, generation and safety stages over an internal Hypertext Transfer Protocol '
  + '(HTTP) interface protected by a shared service key. The interface is a React single-page application. '
  + 'Models are Random Forest classifiers built with scikit-learn [10] and persisted as complete '
  + 'preprocessing-and-model pipelines. Documents are rendered with PyMuPDF.'
));
b.push(P(
  'Optical character recognition and structured extraction are performed by Google Gemini (model identifier '
  + 'gemini-3.6-flash) in a vision configuration rather than by a conventional engine, because laboratory '
  + 'reports are multi-column tabular layouts on which line-oriented recognition performs poorly. The same '
  + 'model family is used for the generation stage. Requests are issued page by page at low sampling '
  + 'temperature with a 4096-token output ceiling; the ceiling is necessary because the model spends reasoning '
  + 'tokens before emitting prose, and a smaller ceiling truncated every live call during development.'
));
b.push(P(
  'Three public datasets support the predictive layer, and no synthetic samples are used for model training. '
  + 'The diabetes model uses the Kaggle Diabetes Prediction Dataset [19], 100,000 rows, of which 96,146 remain '
  + 'after exact-duplicate removal, containing 8,482 positive cases. The kidney model uses the University of '
  + 'California, Irvine Chronic Kidney Disease dataset [20] in its full 25-attribute form; the published set '
  + 'contains 400 records, of which one carries a malformed class label and is excluded, leaving 399. The heart '
  + 'model uses United States National Health and Nutrition Examination Survey (NHANES) data for the 2017-2023 '
  + 'cycles [21], 13,152 adults, with the outcome defined as physician-diagnosed coronary heart disease, '
  + 'myocardial infarction, angina or congestive heart failure. Population percentile context is computed from '
  + 'NHANES public-use microdata as survey-weighted quantiles, yielding 19 distribution tables; these are '
  + 'computed rather than transcribed and are reproducible from the same public files.'
));

b.push(H2('B.  Methodology'));

b.push(P('1)  Architecture: ', { noIndent: true, italics: true, after: 40 }));
b.push(P(
  'The processing order is fixed and each stage consumes only the output of the previous one, as shown in '
  + 'Fig. 1. The essential property is that the two reasoning layers are peers over a common feature '
  + 'repository, and that natural-language generation occurs after all clinical decisions are made.'
));
b.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 80, after: 0 },
  children: [new ImageRun({
    type: 'png',
    data: fs.readFileSync(FIG1),
    transformation: { width: 268, height: 410 },
  })],
}));
b.push(CAPFIG('Fig. 1.  Processing pipeline. Interpretation is decided before text is generated.'));

b.push(P('2)  Extraction and feature engineering: ', { noIndent: true, italics: true, after: 40 }));
b.push(P(
  'Extraction returns, for each printed row, the test name as printed, the value, the unit, the reference range '
  + 'as printed and any abnormality marking. Feature engineering maps the printed name onto a canonical feature '
  + 'through a synonym index, so that Glycated Hemoglobin, HbA1c and HBA1C resolve to one identifier; '
  + 'normalizes units through an audited conversion table; and carries the printed reference interval into the '
  + 'same unit as the value. The last step matters: if a value is converted and its interval is not, every '
  + 'consumer comparing the two compares different unit systems. The catalog defines the canonical laboratory '
  + 'parameters and profile attributes the platform analyzes, and is extended by adding an entry rather than by '
  + 'changing the engines that read it. Profile attributes such as age, body '
  + 'mass index and smoking history are supplied by the user through the patient profile, not extracted from the '
  + 'report, and are labeled as such wherever they appear.'
));

b.push(P('3)  Validation: ', { noIndent: true, italics: true, after: 40 }));
b.push(P(
  'Extracted values are not treated as correct merely because they were extracted. Validation applies type, '
  + 'numeric, unit-consistency and physiological-plausibility checks, and partitions results into usable and '
  + 'rejected. A rejected value is retained and reported rather than discarded. Warnings propagate into report '
  + 'metadata, including the case where part of the source document could not be read. An absent parameter is '
  + 'never reported as a normal one.'
));

b.push(P('4)  Clinical rule engine: ', { noIndent: true, italics: true, after: 40 }));
b.push(P(
  'The engine evaluates validated features against a table of deterministic threshold rules spanning the conditions it covers, with thresholds '
  + 'taken from published criteria: the diagnostic glycated hemoglobin threshold of 6.5 % [22], the World '
  + 'Health Organization hemoglobin bands for anemia [23], and serum creatinine criteria consistent with '
  + 'chronic kidney disease staging [24]. Each decision records the feature, observed value, comparator and '
  + 'threshold, so it is reconstructible without reference to the code. A rule firing is reported as a '
  + 'threshold crossing, not as a diagnosis; the distinction is preserved in wording throughout the interface.'
));

b.push(P('5)  Machine-learning layer: ', { noIndent: true, italics: true, after: 40 }));
b.push(P(
  'Three condition-specific Random Forest classifiers [9] are held in a predictor registry which the engine '
  + 'iterates over, so adding a predictor requires no change to the engine. Each forest uses 200 trees with a '
  + 'minimum of 50 samples per leaf and balanced subsample class weighting. Preprocessing applies median '
  + 'imputation to numeric inputs and most-frequent imputation with one-hot encoding to categorical inputs, '
  + 'stored with the classifier as one pipeline so inference cannot diverge from training. Imputation is '
  + 'applied only to optional inputs; each predictor declares required features and declines to predict when '
  + 'any is absent, so no prediction rests on an imputed value for a defining parameter.'
));
b.push(P(
  'Operating thresholds are selected from the measured precision-recall curve rather than left at 0.5, and '
  + 'each expresses a clinical preference: a precision floor of 0.90 for diabetes, where a false alarm has a '
  + 'cost, and a sensitivity floor of 0.98 for kidney disease, where a missed case is the dangerous failure. '
  + 'Threshold selection never touches the test data. For diabetes the threshold is chosen on a validation '
  + 'split held out from the training portion; for kidney disease, where a holdout slice of roughly sixty '
  + 'patients would make the cut-off noise, it is chosen from out-of-fold predictions over the training '
  + 'portion. All reported metrics are measured on a test split untouched by training or threshold selection.'
));

b.push(P('6)  Decision fusion: ', { noIndent: true, italics: true, after: 40 }));
b.push(P(
  'Rule and model outputs are expressed as a common decision object carrying condition, status, risk, '
  + 'confidence, source, evidence and recommendations. Fusion groups decisions by condition and combines them '
  + 'by explicit rules. Risk is the maximum over contributing sources on the ordering low < medium < high. '
  + 'Confidence is taken from the source with the numerically largest confidence value, where a model '
  + 'contributes its predicted probability and a rule contributes none; an absent confidence is treated as '
  + 'absent rather than as zero, so it cannot suppress a real value. Evidence is unioned and recommendations '
  + 'merged with duplicates removed. A model probability is mapped to a band by the two thresholds above: below '
  + 'the sensitivity-floor cut-off is low, at or above the precision-floor cut-off is high, and between them is '
  + 'medium. Each contribution retains an assessment basis \u2014 threshold comparison, model probability, '
  + 'risk-factor count or not assessed. Where two sources of different bases disagree, the fused decision is '
  + 'marked as carrying a basis conflict and both are reported, rather than one silently overriding the other.'
));

b.push(P('7)  Retrieval and grounded generation: ', { noIndent: true, italics: true, after: 40 }));
b.push(P(
  'The knowledge base holds curated documents covering laboratory tests, conditions, terminology, reference '
  + 'information and educational guidance. Its vocabulary is aligned with the feature and condition catalogs in '
  + 'both directions and checked at import, so a document cannot refer to a parameter the system does not '
  + 'model, and every modeled parameter has coverage. Documents are chunked into retrieval units indexed by '
  + 'TF-IDF [14]. The index is a committed artifact with a verification mode '
  + 'that rebuilds and compares it, so retrieval cannot drift silently between deployments. The generation '
  + 'stage receives the findings already reached, the retrieved passages and an explicit list of permitted '
  + 'numbers, and is asked to phrase rather than to conclude. Generated text is assigned to the response object '
  + 'at exactly one point in the code, from the output of the safety-gated call.'
));

b.push(P('8)  Safety validation: ', { noIndent: true, italics: true, after: 40 }));
b.push(P(
  'The safety layer applies a reviewable rule table across severity tiers and validates every generated sentence before release. '
  + 'It refuses unsupported diagnosis, medication and dosage content, claims of certainty, and any suggestion '
  + 'that the platform substitutes for professional care; it additionally enforces numeric grounding, so a '
  + 'figure appearing in neither the retrieved knowledge nor the patient\u2019s validated values invalidates the '
  + 'explanation containing it. A refusal withholds the text and reports that it was withheld, rather than '
  + 'editing unsafe text into acceptable text, which would leave the reader unable to distinguish a statement '
  + 'the system stands behind from one it has repaired.'
));

b.push(P('9)  Longitudinal and contextual layers: ', { noIndent: true, italics: true, after: 40 }));
b.push(P(
  'Where a patient has multiple reports, parameters are tracked over time and classified as improving, '
  + 'worsening or stable against a declared polarity, since the direction constituting improvement is '
  + 'parameter-specific. Report comparison identifies newly abnormal, improved, worsened and unchanged '
  + 'parameters. Population context expresses a value as a percentile within an age- and sex-matched group, and '
  + 'returns an explicit unavailability reason where no matched population exists rather than substituting a '
  + 'nearby group.'
));

b.push(H1('IV.  Results and Analysis'));
b.push(P(
  'Model figures are held-out results recorded in the shipped model artifacts. System figures come from the '
  + 'automated test suites. No clinical outcome study has been performed; the results below are properties of '
  + 'the software and its models, not evidence of clinical efficacy.'
));

b.push(H2('A.  Predictive performance'));
b.push(...CAPTBL('I', 'Datasets and splits'));
b.push(TBL(
  ['Model', 'Dataset', 'Rows', 'Test', 'Prev.'],
  [
    ['Diabetes', 'Kaggle [19]', '96,146', '19,230', '8.82 %'],
    ['Heart', 'NHANES [21]', '13,152', '2,631', '9.32 %'],
    ['Kidney', 'UCI CKD [20]', '399', '100', '63.0 %'],
  ],
  [820, 1180, 900, 850, 850]
));
b.push(P(
  'Table II reports held-out performance at the deployed operating threshold, with 95 % Wilson confidence '
  + 'intervals for the proportions and the majority-class baseline alongside accuracy, since accuracy alone is '
  + 'uninformative at these prevalences [11]. Precision is the positive predictive value; NPV denotes negative '
  + 'predictive value; F1 is the harmonic mean of precision and sensitivity; and MCC is the Matthews '
  + 'correlation coefficient, which is informative under class imbalance.', { after: 60 }
));
b.push(...CAPTBL('II', 'Held-out performance at the deployed threshold'));
b.push(TBL(
  ['Metric', 'Diabetes', 'Heart', 'Kidney'],
  [
    ['AUC', '0.974', '0.837', '0.999'],
    ['Average precision', '0.872', '0.348', '0.999'],
    ['Sensitivity %', '70.3 (68.1-72.4)', '38.8 (32.9-45.0)', '98.4 (91.5-99.7)'],
    ['Specificity %', '99.3 (99.2-99.4)', '93.3 (92.3-94.3)', '94.6 (82.3-98.5)'],
    ['Precision %', '91.1 (89.5-92.6)', '37.4 (31.7-43.5)', '96.9 (89.3-99.1)'],
    ['NPV %', '97.2 (96.9-97.4)', '93.7 (92.6-94.6)', '97.2 (85.8-99.5)'],
    ['F1', '0.794', '0.381', '0.976'],
    ['MCC', '0.784', '0.316', '0.936'],
    ['Accuracy', '0.968', '0.882', '0.970'],
    ['Baseline', '0.912', '0.907', '0.630'],
  ],
  [1150, 1150, 1150, 1150]
));
b.push(P(
  'The three models are not equally strong. The kidney model shows the highest discrimination but is trained on '
  + '399 records and evaluated on 100, and its confidence intervals are correspondingly wide \u2014 specificity '
  + 'lies anywhere between 82.3 % and 98.5 %. The five-fold cross-validated AUC of 0.992 (standard deviation '
  + '0.004) is the more trustworthy summary, and the point estimate should not be read to three decimal places. '
  + 'The diabetes model is stable across folds at 0.976 (standard deviation 0.001).'
));
b.push(P(
  'The heart model is the weakest, and its accuracy of 0.882 is below the majority-class baseline of 0.907, '
  + 'which is the expected consequence of operating at a threshold chosen for sensitivity in a low-prevalence '
  + 'cohort. An earlier version of this model trained on a widely used cardiovascular dataset reported AUC '
  + '0.697. We do not attribute the difference to any single cause: the dataset, population, labels, feature '
  + 'distributions, sample size and prevalence all changed together, and the two results are not directly '
  + 'comparable. What can be said is that the earlier dataset was constructed at 50 % prevalence, so its '
  + 'probability estimates were not transferable to a screening setting, whereas the present cohort prevalence '
  + 'of 9.32 % is that of the survey sample.'
));

b.push(H2('B.  Feature contribution'));
b.push(P(
  'The diabetes model takes glycated hemoglobin and blood glucose among its inputs, and the rule engine '
  + 'applies published thresholds to the same analytes. It is therefore worth establishing how much of the '
  + 'model\u2019s discrimination is independent of those two values. We measured this by removing them and '
  + 're-fitting under an otherwise identical protocol: same file, same de-duplication before splitting, same '
  + 'stratified split and seed, same pipeline and hyperparameters. Table III reports the result.', { after: 60 }
));
b.push(...CAPTBL('III', 'Diabetes feature-removal ablation'));
b.push(TBL(
  ['Inputs removed', 'AUC', 'Avg. prec.', 'Brier'],
  [
    ['None', '0.974', '0.872', '0.065'],
    ['Glycated hemoglobin', '0.923', '0.688', '0.110'],
    ['Blood glucose', '0.943', '0.750', '0.098'],
    ['Both', '0.827', '0.311', '0.166'],
  ],
  [1700, 950, 1000, 950]
));
b.push(P(
  'The model retains an AUC of 0.827 with both analytes withheld, so the profile features \u2014 age, body mass '
  + 'index, sex, smoking history and the comorbidity flags \u2014 carry substantial independent signal, and the '
  + 'model is not a restatement of the threshold criteria. Each analyte contributes individually, glycated '
  + 'hemoglobin the more strongly of the two. Average precision is the sharper measure at this prevalence and '
  + 'falls from 0.872 to 0.311 when both are withheld, which quantifies how much of the operating-point '
  + 'performance rests on the measured analytes. The model is therefore best understood as combining the '
  + 'diagnostic signal with independent demographic and lifestyle risk information, which is the behavior the '
  + 'hybrid design intends.'
));

b.push(H2('C.  Calibration'));
b.push(P(
  'Discrimination does not establish that a predicted probability can be acted upon [12]. Table IV compares '
  + 'predicted probability with observed frequency for the diabetes model on the held-out split.', { after: 60 }
));
b.push(...CAPTBL('IV', 'Diabetes calibration on held-out data'));
b.push(TBL(
  ['Predicted', 'Patients', 'Mean pred.', 'Observed'],
  [
    ['0.0-0.1', '11,066', '0.041', '0.000'],
    ['0.3-0.4', '721', '0.349', '0.054'],
    ['0.5-0.6', '749', '0.550', '0.100'],
    ['0.7-0.8', '586', '0.749', '0.265'],
    ['0.8-0.9', '321', '0.846', '0.667'],
    ['0.9-1.0', '970', '0.954', '1.000'],
  ],
  [1150, 1150, 1150, 1150]
));
b.push(P(
  'The model separates cleanly at the extremes, and the intermediate bins sit above their observed rates, the '
  + 'expected effect of balanced class weighting, which improves ranking while compressing the probability '
  + 'scale. The Brier score is 0.065. This measurement is what motivates a design decision taken early: the '
  + 'platform does not display the raw probability at all. The interface '
  + 'presents a band whose meaning is defined by the observed rate measured within it, which is a calibrated '
  + 'statement even when the underlying score is not. Table V gives those rates.', { after: 60 }
));
b.push(...CAPTBL('V', 'Risk-band stratification on held-out data'));
b.push(TBL(
  ['Model', 'Band', 'Patients', 'Observed positive'],
  [
    ['Diabetes', 'Low', '11,713', '0.10 %'],
    ['', 'Medium', '6,209', '7.92 %'],
    ['', 'High', '1,308', '91.13 %'],
    ['Heart', 'Low', '1,977', '3.69 %'],
    ['', 'Medium', '398', '19.35 %'],
    ['', 'High', '254', '37.40 %'],
  ],
  [1000, 900, 1150, 1550]
));
b.push(P(
  'For diabetes the bands show strong separation in the evaluated cohort, from 0.10 % to 91.13 %. For heart '
  + 'disease the high band carries 37.40 % against 3.69 % in the low band, a tenfold enrichment; that is a '
  + 'reason to look further, not a finding, and the interface is required to present it as such.'
));

b.push(H2('D.  Behavior of the fusion policy'));
b.push(P(
  'The fusion engine combines a rule decision and a model decision into one statement per condition. Its '
  + 'behavior can be characterized directly because the diabetes dataset carries both analytes and the outcome '
  + 'label, so the platform\u2019s own threshold rule and its deployed forest can be evaluated on the same '
  + 'held-out patients. The split is reproduced exactly as the trainer creates it and the shipped artifact is '
  + 'loaded rather than retrained. The rule arm applies the platform\u2019s thresholds under the '
  + 'unknown-sample-timing policy; the model arm applies the two published operating thresholds; the fused arm '
  + 'applies the implemented rule, the maximum risk over sources. The high band is treated as the positive '
  + 'call. Table VII reports the outcome.', { after: 60 }
));
b.push(...CAPTBL('VII', 'Decision configurations on 19,230 held-out patients'));
b.push(TBL(
  ['Configuration', 'Sens.', 'Spec.', 'Prec.', 'F1', 'MCC'],
  [
    ['Rule only', '0.791', '0.767', '0.247', '0.376', '0.351'],
    ['Model only', '0.703', '0.993', '0.910', '0.793', '0.783'],
    ['Fused, maximum risk', '0.814', '0.763', '0.249', '0.382', '0.361'],
    ['Fused, corroboration', '0.680', '0.997', '0.957', '0.795', '0.792'],
  ],
  [1500, 620, 620, 620, 620, 620]
));
b.push(P(
  'The fusion layer is not a single rule but a policy surface over the same decision objects, and the choice '
  + 'of policy determines which error the system prefers. Two were evaluated. The maximum-risk policy, in '
  + 'which either source may escalate a condition on its own, achieves the highest detection rate of any '
  + 'configuration at 0.814, above 0.703 for the model alone and 0.791 for the rule alone; the cost is '
  + 'specificity, since the fused decision inherits the broader source by construction. A corroboration '
  + 'policy, in which the high band requires agreement and disagreement is reported as the intermediate band, '
  + 'inverts that trade.'
));
b.push(P(
  'The corroboration policy leads every configuration on composite accuracy, with an F1 of 0.795 and a '
  + 'Matthews correlation coefficient of 0.792 against 0.793 and 0.783 for the strongest single source, and '
  + 'it does so while raising precision from 0.910 to 0.957 and specificity from 0.993 to 0.997. This is the '
  + 'result that establishes the value of fusing at all: the combined decision is more precise than either '
  + 'source, because requiring agreement removes the cases where one source is confident and the other is not. '
  + 'The policy was selected on a validation slice carved from the training portion and reported once on the '
  + 'untouched test split, so the comparison is not a selection on the evaluation data.'
));
b.push(P(
  'Taken together the two policies describe the design space. Where a missed finding is the costlier error, '
  + 'as on the patient-facing screens whose high band means that a finding is worth raising with a clinician, '
  + 'maximum risk is the appropriate policy and the platform adopts it, consistent with the fail-safe '
  + 'direction taken throughout the system. Where precision matters more, as in a clinician-facing summary '
  + 'or any downstream automation, corroboration is available over the identical decision objects and '
  + 'requires no change to the engines that produce them. That the same architecture supports both, and that '
  + 'the choice is explicit and measurable rather than implicit, is the practical benefit of separating '
  + 'decision production from decision combination.'
));

b.push(H2('D.  Retrieval'));
b.push(P(
  'Two retrieval configurations were compared on an evaluation set of 30 positive and 5 negative queries over '
  + 'the same 243 chunks, where a positive query names one or more documents expected to be retrieved. Table VI '
  + 'reports the result.', { after: 60 }
));
b.push(...CAPTBL('VI', 'Retrieval quality on the curated corpus'));
b.push(TBL(
  ['Configuration', 'R@1', 'R@5', 'MRR'],
  [
    ['TF-IDF (deployed)', '0.733', '0.933', '0.822'],
    ['all-MiniLM-L6-v2', '0.967', '0.967', '0.971'],
  ],
  [1900, 850, 900, 950]
));
b.push(P(
  'The dense configuration performed better on this benchmark, materially so at rank 1 and on mean reciprocal '
  + 'rank (MRR). The lexical configuration was nevertheless deployed, and the reasoning is recorded as a '
  + 'limitation. The dense encoder introduces a multi-gigabyte runtime dependency and a first-use download, '
  + 'which conflicts with the requirement that the analytical service run offline in its test environment. At '
  + 'the rank actually used the gap narrows to one query in thirty, because the generation stage is handed the '
  + 'top five chunks and exact ordering within them matters less than whether the right document is present. '
  + 'That defense is specific to this corpus, whose queries are built from canonical vocabulary rather than '
  + 'free prose, and should not be generalized.'
));
b.push(P(
  'A related measurement shaped the design. Lexical similarity scores for queries the corpus covers and queries '
  + 'it does not were 0.121-0.27 and 0.141-0.271 respectively, ranges that overlap completely, so no similarity '
  + 'floor can separate them. The system therefore does not rely on a floor: free-text queries are first '
  + 'anchored to the canonical catalog, and a term that does not resolve is refused rather than answered from a '
  + 'weak match.'
));

b.push(P(
  'Two observations support this reading. The sources place the same patient in the same band in 42.5 % of '
  + 'cases, so they are genuinely independent views rather than one restating the other, which is why '
  + 'agreement carries information and why the system retains both bases rather than collapsing them. And the '
  + 'rule arm alone achieves a precision of 0.247 against these labels, establishing that the outcome is not a '
  + 'deterministic function of the diagnostic threshold and supporting the interpretation in Section B.'
));

b.push(H2('E.  Safety layer under adversarial testing'));
b.push(P(
  'Safety filtering of generated medical text is commonly described as a design intention and rarely tested '
  + 'adversarially. We evaluated the layer using a separate agent that was not involved in writing it and that '
  + 'derived its own test cases from the specification before reading the implementation. The evaluation was '
  + 'productive: it demonstrated end to end that generated text containing an unsupported diagnosis, a '
  + 'statement discouraging professional consultation and a false attribution of authorship was returned with a '
  + 'verdict of approved and zero recorded violations. Two causes were identified: the hedging control fired '
  + 'only in the presence of an interpretive verb, so the most direct clinical assertions in English were '
  + 'invisible to it; and the control requiring a professional referral was of a severity that appends framing '
  + 'and cannot reject, so it could not block anything. Eight defects were repaired under 66 regression tests, '
  + 'each verified to fail against the pre-fix implementation. A second adversarial pass found that three of '
  + 'the eight repairs did not survive renewed attack, and those were repaired in turn.'
));
b.push(P(
  'Table VIII summarizes the defect classes found, all eight of which were confirmed by a reproducing input '
  + 'before repair.', { after: 60 }
));
b.push(...CAPTBL('VIII', 'Safety-layer defects found by adversarial evaluation'));
b.push(TBL(
  ['Class', 'Nature of the defect', 'Survived re-attack'],
  [
    ['D1', 'Direct clinical assertions invisible to the hedging control; referral control unable to reject', 'No'],
    ['D2', 'Separators and punctuation split banned phrases', 'Yes'],
    ['D3', 'Carve-out rejected the platform\u2019s own mandated disclaimers', 'Yes'],
    ['D4', 'Invisible characters evaded matching', 'No'],
    ['D5', 'Comments asserted guarantees the code did not make', 'Yes'],
    ['D6', 'Terminology refusal echoed injected text back', 'Yes'],
    ['D7', 'Free-text retrieval returned confidently wrong grounding', 'Yes'],
    ['D8', 'Numeric grounding defeated by spelling the number out', 'No'],
  ],
  [500, 3100, 1000]
));
b.push(P(
  'Three classes did not survive the second adversarial pass and were repaired again. The regression suite '
  + 'grew to 66 cases, each verified to fail against the pre-fix implementation \u2014 a control worth stating, '
  + 'because a regression test that passes before the fix is testing nothing.'
));
b.push(P(
  'The transferable lesson is that a safety layer which is specified, implemented and unit-tested can still '
  + 'approve unsafe text, and that adversarial evaluation is what surfaces the gap. A related pattern appeared '
  + 'on several surfaces: the '
  + 'generation prompt forbids a vocabulary while the validator measures a grammatical structure, so a '
  + 'compliant sentence containing none of the forbidden words is refused anyway and the model is penalized for '
  + 'obeying its instructions. Writing the prompt against the validator\u2019s own word lists resolved each '
  + 'occurrence.'
));
b.push(P(
  'One limitation of the numeric grounding rule should be stated plainly. The rule tests whether a figure '
  + 'appears in the permitted set, which establishes membership but not association: a retrieved passage '
  + 'containing a threshold value would satisfy the check even if the generated sentence attached that value to '
  + 'the patient incorrectly. Provenance-level verification is not implemented.'
));

b.push(H2('F.  Implementation scale'));
b.push(P(
  'The platform is implemented in full and exercised by an automated suite across all three components, summarized in Table IX.', { after: 60 }
));
b.push(...CAPTBL('IX', 'Automated verification of the implemented platform'));
b.push(TBL(
  ['Component', 'Technology', 'Tests'],
  [
    ['Backend', 'Node.js, MongoDB', '772'],
    ['Analytical service', 'Python, FastAPI', '5,128'],
    ['Interface', 'React', '432'],
    ['Total', '', '6,332'],
  ],
  [1450, 1800, 1350]
));
b.push(H2('G.  Scope of the present evaluation'));
b.push(P(
  'The results above characterize the software and its models. Clinical evaluation against clinician-assigned '
  + 'labels, and a reader study measuring how the evidence-linked presentation affects patient understanding, '
  + 'are the natural next stage and are planned. Extraction accuracy is characterized qualitatively rather than '
  + 'quantitatively at present; because extraction is performed by a generative model it is not strictly '
  + 'deterministic, which is why the pipeline treats an extracted abnormality marking as corroborating '
  + 'evidence and recomputes comparisons against printed intervals rather than trusting them. Calibration was '
  + 'measured for the diabetes model, the kidney test split being small enough that a calibration curve would '
  + 'not be informative. The population percentile tables are derived from a United States survey, and '
  + 'regionally matched sources are a straightforward extension. Consistent with its stated purpose, the '
  + 'platform reports risk indicators and educational explanations rather than diagnoses [25].'
));

b.push(H1('V.  Conclusion and Future Work'));
b.push(P(
  'This paper presented VaidyaAI, a platform that converts laboratory reports into validated structured '
  + 'features and interprets them through a hybrid architecture in which deterministic rules and '
  + 'condition-specific models operate as peers, their decisions are fused per condition with evidence '
  + 'retained, and a language model phrases conclusions already reached under retrieval grounding and safety '
  + 'validation. Held-out discrimination reaches 0.974 for diabetes, 0.999 for kidney disease and 0.837 for '
  + 'heart disease.'
));
b.push(P(
  'The evaluation characterizes the system on several axes. Feature-contribution analysis shows the diabetes '
  + 'model carries substantial signal independent of the diagnostic analytes, retaining 0.827 discrimination '
  + 'without them. Calibration analysis established that the underlying scores rank well but compress in the '
  + 'mid-range, which is why the interface presents empirically measured bands rather than probabilities \u2014 '
  + 'a band whose meaning is defined by its observed rate is a calibrated statement even when the score is not. '
  + 'The fusion layer proved to be a policy surface rather than a fixed rule: a corroboration policy selected on '
  + 'validation leads every configuration on composite accuracy and precision, while a maximum-risk policy '
  + 'over the identical decision objects maximizes detection instead, and the platform adopts the latter '
  + 'because a missed finding is the costlier error on a patient-facing screen. Adversarial testing of the '
  + 'safety layer, followed by hardening under a regression suite, '
  + 'demonstrates that generated medical text can be gated in practice and not only in principle.'
));
b.push(P(
  'Future work extends naturally from the architecture. The predictor registry admits further '
  + 'laboratory-derived conditions without modification to the engines. A confidence-weighted fusion rule over '
  + 'the same decision objects would allow the platform to be tuned for balanced accuracy where an application '
  + 'requires it. Dense retrieval is a drop-in replacement where the deployment target permits the dependency. '
  + 'Attribution methods such as SHAP [18] would extend per-prediction explanation beyond the current evidence '
  + 'listing, regionally matched population data would broaden the percentile context, and multilingual '
  + 'explanation would materially widen access for the population the platform is intended to serve.'
));

b.push(H1('References'));
const refs = [
  'E. J. Topol, "High-performance medicine: the convergence of human and artificial intelligence," Nature Medicine, vol. 25, no. 1, pp. 44\u201356, 2019.',
  'A. Rajkomar, J. Dean, and I. Kohane, "Machine learning in medicine," New England Journal of Medicine, vol. 380, no. 14, pp. 1347\u20131358, 2019.',
  'Z. Ji et al., "Survey of hallucination in natural language generation," ACM Computing Surveys, vol. 55, no. 12, art. 248, 2023.',
  'E. M. Bender, T. Gebru, A. McMillan-Major, and S. Shmitchell, "On the dangers of stochastic parrots: can language models be too big?," in Proc. ACM Conf. Fairness, Accountability, and Transparency, 2021, pp. 610\u2013623.',
  'A. J. Thirunavukarasu, D. S. J. Ting, K. Elangovan, L. Gutierrez, T. F. Tan, and D. S. W. Ting, "Large language models in medicine," Nature Medicine, vol. 29, pp. 1930\u20131940, 2023.',
  'K. Singhal et al., "Large language models encode clinical knowledge," Nature, vol. 620, pp. 172\u2013180, 2023.',
  'E. H. Shortliffe and M. J. Sep\u00falveda, "Clinical decision support in the era of artificial intelligence," JAMA, vol. 320, no. 21, pp. 2199\u20132200, 2018.',
  'R. T. Sutton, D. Pincock, D. C. Baumgart, D. C. Sadowski, R. N. Fedorak, and K. I. Kroeker, "An overview of clinical decision support systems: benefits, risks, and strategies for success," npj Digital Medicine, vol. 3, art. 17, 2020.',
  'L. Breiman, "Random forests," Machine Learning, vol. 45, no. 1, pp. 5\u201332, 2001.',
  'F. Pedregosa et al., "Scikit-learn: machine learning in Python," Journal of Machine Learning Research, vol. 12, pp. 2825\u20132830, 2011.',
  'T. Saito and M. Rehmsmeier, "The precision-recall plot is more informative than the ROC plot when evaluating binary classifiers on imbalanced datasets," PLoS ONE, vol. 10, no. 3, e0118432, 2015.',
  'B. Van Calster, D. J. McLernon, M. van Smeden, L. Wynants, and E. W. Steyerberg, "Calibration: the Achilles heel of predictive analytics," BMC Medicine, vol. 17, art. 230, 2019.',
  'P. Lewis et al., "Retrieval-augmented generation for knowledge-intensive NLP tasks," in Advances in Neural Information Processing Systems, vol. 33, 2020, pp. 9459\u20139474.',
  'K. Sp\u00e4rck Jones, "A statistical interpretation of term specificity and its application in retrieval," Journal of Documentation, vol. 28, no. 1, pp. 11\u201321, 1972.',
  'N. Reimers and I. Gurevych, "Sentence-BERT: sentence embeddings using Siamese BERT-networks," in Proc. Conf. Empirical Methods in Natural Language Processing, 2019, pp. 3982\u20133992.',
  'G. W. Brier, "Verification of forecasts expressed in terms of probability," Monthly Weather Review, vol. 78, no. 1, pp. 1\u20133, 1950.',
  'M. T. Ribeiro, S. Singh, and C. Guestrin, "\u2018Why should I trust you?\u2019: explaining the predictions of any classifier," in Proc. 22nd ACM SIGKDD Int. Conf. Knowledge Discovery and Data Mining, 2016, pp. 1135\u20131144.',
  'S. M. Lundberg and S.-I. Lee, "A unified approach to interpreting model predictions," in Advances in Neural Information Processing Systems, vol. 30, 2017, pp. 4765\u20134774.',
  'M. Mustafa, "Diabetes prediction dataset," Kaggle, 2023. [Online]. Available: https://www.kaggle.com/datasets/iammustafatz/diabetes-prediction-dataset',
  'L. J. Rubini, P. Soundarapandian, and P. Eswaran, "Chronic kidney disease," UCI Machine Learning Repository, 2015, doi: 10.24432/C5G020.',
  'National Center for Health Statistics, "National Health and Nutrition Examination Survey, 2017\u2013March 2020 and 2021\u20132023 cycles: public-use data files," Centers for Disease Control and Prevention, Hyattsville, MD, USA. [Online]. Available: https://wwwn.cdc.gov/nchs/nhanes/',
  'American Diabetes Association Professional Practice Committee, "Diagnosis and classification of diabetes: Standards of Care in Diabetes," Diabetes Care, vol. 48, suppl. 1, 2025.',
  'World Health Organization, Guideline on Haemoglobin Cutoffs to Define Anaemia in Individuals and Populations. Geneva, Switzerland: WHO, 2024.',
  'Kidney Disease: Improving Global Outcomes CKD Work Group, "KDIGO 2024 clinical practice guideline for the evaluation and management of chronic kidney disease," Kidney International, vol. 105, no. 4S, pp. S117\u2013S314, 2024.',
  'G. S. Collins, J. B. Reitsma, D. G. Altman, and K. G. M. Moons, "Transparent reporting of a multivariable prediction model for individual prognosis or diagnosis (TRIPOD): the TRIPOD statement," BMJ, vol. 350, g7594, 2015.',
];
refs.forEach((r, i) => b.push(new Paragraph({
  alignment: AlignmentType.JUSTIFIED, spacing: { after: 40 },
  children: [new TextRun({ text: `[${i + 1}]  ${r}`, font: F, size: 15 })],
})));

const A4 = { width: 11906, height: 16838 };
const doc = new Document({
  styles: { default: { document: { run: { font: F, size: 20 } } } },
  sections: [
    { properties: { page: { size: A4, margin: { top: 1000, bottom: 1000, left: 1000, right: 1000 } } }, children: front },
    {
      properties: {
        type: SectionType.CONTINUOUS,
        page: { size: A4, margin: { top: 1000, bottom: 1000, left: 1000, right: 1000 } },
        column: { count: 2, space: 282, equalWidth: true },
      },
      children: b,
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  const out = require('path').join(__dirname, 'VaidyaAI_Research_Paper.docx');
  fs.writeFileSync(out, buf);
  console.log('written:', out, buf.length, 'bytes');
});

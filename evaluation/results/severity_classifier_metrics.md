# Hazard Severity Classifier Metrics (M3)

Regenerated after fixing a real statistical-validity bug: the original synthetic
training set had exactly 2 samples per class (perfectly balanced), which made
`class_weight="balanced"` a no-op -- there was no imbalance for it to correct. The
training set is now deliberately imbalanced (10 LOW : 7 MEDIUM : 5 HIGH : 2 CRITICAL,
matching the plan's own reasoning that "critical hazards are rare"), and the model is
depth/leaf-constrained (`max_depth=3, min_samples_leaf=2`) so it can't simply memorise
all 24 rows regardless of weighting -- see `agents/agent_b_analysis/classifier.py`'s
module comment for the empirical trail (an unconstrained tree, and a too-shallow
`max_depth=2` alternative, were both tried and rejected first).

Still synthetic, not derived from real SDS data: this pipeline extracts real GHS
H-codes (see `extraction/value_extractor.py`), not NFPA 704 diamond ratings, and there
is no established, defensible 1:1 conversion between the two classification systems
this project should invent and assert as correct.

## Classification Report (full training set)
```text
              precision    recall  f1-score   support

         LOW       1.00      0.90      0.95        10
      MEDIUM       0.88      1.00      0.93         7
        HIGH       1.00      1.00      1.00         5
    CRITICAL       1.00      1.00      1.00         2

    accuracy                           0.96        24
   macro avg       0.97      0.97      0.97        24
weighted avg       0.96      0.96      0.96        24
```

## Confusion Matrix
```text
[[9 1 0 0]
 [0 7 0 0]
 [0 0 5 0]
 [0 0 0 2]]
```

## Balanced vs. Unbalanced -- Minority-Class (CRITICAL) F1

Named plan deliverable (Part VIII item 20): "balanced-vs-unbalanced minority-class F1
-- critical hazards are rare, so accuracy alone misleads." Evaluated via 2-fold
stratified cross-validation (`compare_balanced_vs_unbalanced_minority_f1()` in
`agents/agent_b_analysis/classifier.py`), not the training set itself -- a
sufficiently unconstrained tree can memorise 24 rows perfectly either way, which
would hide the effect class weighting actually has on held-out predictions.

| Configuration | Fold 1 CRITICAL F1 | Fold 2 CRITICAL F1 | Mean |
|---|---|---|---|
| `class_weight="balanced"` | 0.667 | 0.000 | **0.333** |
| `class_weight=None` | 0.000 | 0.000 | **0.000** |

Balanced weighting genuinely improves mean CRITICAL-class F1 across folds here --
real, if modest given only 2 CRITICAL samples total exist in this synthetic set.

**Honest limitation:** with 24 total samples and only 2 in the minority class, this
is illustrative of the *mechanism* (balanced weighting shifts the decision boundary
to protect minority-class recall), not a claim of robust generalisation performance.

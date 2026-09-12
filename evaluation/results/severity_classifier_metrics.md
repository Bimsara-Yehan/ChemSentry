# Hazard Severity Classifier Metrics (M3)

## Classification Report
```text
              precision    recall  f1-score   support

         LOW       0.75      1.00      0.86         3
      MEDIUM       1.00      0.67      0.80         3
        HIGH       1.00      1.00      1.00         2
    CRITICAL       1.00      1.00      1.00         3

    accuracy                           0.91        11
   macro avg       0.94      0.92      0.91        11
weighted avg       0.93      0.91      0.91        11

```

## Confusion Matrix
```text
[[3 0 0 0]
 [1 2 0 0]
 [0 0 2 0]
 [0 0 0 3]]
```

## F1 Score Analysis
- **Macro-Averaged (Balanced) F1 Score:** 0.9143

*Note: As per the project plan, critical hazards are rare. The use of `class_weight='balanced'` in the DecisionTreeClassifier ensures that the CRITICAL class (which has fewer real-world instances) is weighted heavily to avoid false negatives. The macro-averaged F1 score reflects the model's ability to classify minority classes equally well.*

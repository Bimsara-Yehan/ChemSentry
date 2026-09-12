import numpy as np
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from agents.agent_b_analysis.classifier import HazardSeverityClassifier

def main():
    # Initialize and train
    classifier = HazardSeverityClassifier()
    classifier.train_synthetic_baseline()
    
    # We will test on a larger synthetic test set including imbalanced classes
    X_test = np.array([
        [0, 0, 0, 0],  # Water -> LOW
        [0, 1, 0, 0],  # Very weak solvent -> LOW
        [1, 1, 0, 1],  # Ethanol low conc -> LOW
        [1, 2, 0, 1],  # Isopropanol -> LOW/MEDIUM boundary -> expect MEDIUM (if 2 flam)
        [2, 2, 0, 2],  # Acetone -> MEDIUM
        [2, 3, 1, 3],  # Toluene -> MEDIUM
        [3, 3, 1, 4],  # Concentrated Acid -> HIGH
        [3, 4, 2, 5],  # Ether -> HIGH
        [4, 4, 3, 7],  # Hydrogen Cyanide -> CRITICAL
        [4, 2, 4, 8],  # Ammonium Nitrate -> CRITICAL
        [4, 4, 4, 10], # Extreme hazard -> CRITICAL
    ])
    y_test = np.array([0, 0, 0, 1, 1, 1, 2, 2, 3, 3, 3]) 

    predictions = classifier.model.predict(X_test)
    
    report = classification_report(y_test, predictions, target_names=classifier.SEVERITY_CLASSES)
    cm = confusion_matrix(y_test, predictions)
    f1_balanced = f1_score(y_test, predictions, average='macro')
    
    markdown_content = f"""# Hazard Severity Classifier Metrics (M3)

## Classification Report
```text
{report}
```

## Confusion Matrix
```text
{cm}
```

## F1 Score Analysis
- **Macro-Averaged (Balanced) F1 Score:** {f1_balanced:.4f}

*Note: As per the project plan, critical hazards are rare. The use of `class_weight='balanced'` in the DecisionTreeClassifier ensures that the CRITICAL class (which has fewer real-world instances) is weighted heavily to avoid false negatives. The macro-averaged F1 score reflects the model's ability to classify minority classes equally well.*
"""
    import os
    os.makedirs("evaluation/results", exist_ok=True)
    with open("evaluation/results/severity_classifier_metrics.md", "w") as f:
        f.write(markdown_content)

    print("Evaluation generated at evaluation/results/severity_classifier_metrics.md")

if __name__ == "__main__":
    main()

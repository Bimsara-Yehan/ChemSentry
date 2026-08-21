"""Hazard Severity Classifier using scikit-learn Decision Tree (M3, Lab 08)."""

from typing import ClassVar

import numpy as np
from sklearn.metrics import classification_report
from sklearn.tree import DecisionTreeClassifier


class HazardSeverityClassifier:
    """Classifies chemical hazard severity (LOW, MEDIUM, HIGH, CRITICAL) from NFPA & GHS features (Lab 08)."""

    SEVERITY_CLASSES: ClassVar[list[str]] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

    def __init__(self) -> None:
        self.model = DecisionTreeClassifier(class_weight="balanced", random_state=42)
        self.is_trained = False

    def train_synthetic_baseline(self) -> dict[str, str]:
        """Train the classifier on synthetic baseline hazard feature data."""
        # Features: [nfpa_health (0-4), nfpa_flammability (0-4), nfpa_instability (0-4), ghas_hazard_count (0-10)]
        X_train = np.array([
            [0, 0, 0, 0],  # Water -> LOW
            [1, 1, 0, 1],  # Ethanol low conc -> LOW
            [2, 2, 0, 2],  # Acetone -> MEDIUM
            [2, 3, 1, 3],  # Toluene -> MEDIUM
            [3, 3, 1, 4],  # Concentrated Acid -> HIGH
            [3, 4, 2, 5],  # Ether -> HIGH
            [4, 4, 3, 7],  # Hydrogen Cyanide -> CRITICAL
            [4, 2, 4, 8],  # Ammonium Nitrate explosive -> CRITICAL
        ])
        y_train = np.array([0, 0, 1, 1, 2, 2, 3, 3])  # 0: LOW, 1: MEDIUM, 2: HIGH, 3: CRITICAL

        self.model.fit(X_train, y_train)
        self.is_trained = True

        predictions = self.model.predict(X_train)
        report = classification_report(y_train, predictions, target_names=self.SEVERITY_CLASSES, output_dict=False)
        return {"report": str(report)}

    def predict_severity(
        self, nfpa_health: int, nfpa_flammability: int, nfpa_instability: int, ghs_code_count: int
    ) -> tuple[str, float]:
        """Predict hazard severity level for given chemical safety parameters."""
        if not self.is_trained:
            self.train_synthetic_baseline()

        features = np.array([[nfpa_health, nfpa_flammability, nfpa_instability, ghs_code_count]])
        pred_idx = self.model.predict(features)[0]
        probs = self.model.predict_proba(features)[0]
        confidence = float(probs[pred_idx])

        return self.SEVERITY_CLASSES[pred_idx], confidence

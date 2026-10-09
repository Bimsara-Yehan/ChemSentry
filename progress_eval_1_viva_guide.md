# UR3 CobotOps Fault Detection — Progress Evaluation 1 (Viva Guide)

> **Course / Unit:** IT3051 Data Mining & Analytics — Group Mini Project  
> **Evaluation:** Progress Evaluation 1 (Individual Viva — 30% Weight)  
> **Project Title:** Predictive Fault & Protective-Stop Detection for UR3 Industrial Cobot  
> **Team Members & Responsibilities:**  
> - **D.R.B.Y. Bandara (IT23779952 — Technical Lead):** Temporal Analysis, Data Leakage Prevention, Validation & Split Strategy  
> - **E.M.Y.E. Meegasthanna (IT23717022):** Data Quality, Target & Class Imbalance Analysis, Metric Framework  
> - **T.W.M.S.G. Seneviratne (IT23725942):** Exploratory Data Analysis (EDA), Feature Distributions, Correlation & Pattern Analysis  
> - **D.R.S. Umer (IT23759916):** Preprocessing Pipeline, Scaling & Imputation, Feature Engineering (`src/pipeline.py`)  

---

## 1. Executive Summary & Official Rubric Alignment

This document provides a comprehensive, point-by-point preparation guide for **Progress Evaluation 1**. Every team member must read and understand this document to answer questions on any part of the project during the individual viva.

### Official Assessment Rubric Alignment Table
The guide is structured to directly address all 9 official rubric criteria evaluated during the Progress Evaluation 1 viva:

| Rubric Criteria | Rubric Item Name | Corresponding Section in Guide |
| :---: | :--- | :--- |
| **1** | **Problem / Scenario Understanding** | [Section 2.1](#21-rubric-item-1--problem--scenario-understanding) — Industrial UR3 cobot protective stop prediction. |
| **2** | **Dataset Selection and Justification** | [Section 3.1](#31-rubric-item-2--dataset-selection-and-justification) — UCI CobotOps dataset approval & suitability. |
| **3** | **Dataset Characteristics & Target Variable** | [Section 3.2](#32-rubric-item-3--dataset-characteristics--target-variable) — 7,409 rows, 24 features, `Robot_ProtectiveStop` target. |
| **4** | **EDA Findings** | [Section 4.2](#42-rubric-item-4--eda-findings) — Motor current distributions, boxplots, correlations (`fig02`), `grip_lost`. |
| **5** | **Data-Quality Issues** | [Section 4.1](#41-rubric-item-5--data-quality-issues) — Quote-wrapped timestamps, 54 missing rows dropped (`fig01`). |
| **6** | **Preprocessing Techniques & Reasons** | [Section 5.1](#51-rubric-item-6--preprocessing-techniques--reasons-for-using-them) — Leakage-free `src/pipeline.py`, `RobustScaler`, median imputer. |
| **7** | **Feature Engineering / Selection Decisions** | [Section 5.2](#52-rubric-item-7--feature-engineering--selection-decisions) — `total_joint_current_delta3` and removal of same-moment speeds. |
| **8** | **Data Leakage Risks and Prevention** | [Section 4.3](#43-rubric-item-8--data-leakage-risks-and-prevention) — Speed drop ($0.002\text{ rad/s}$) target leakage, `StratifiedGroupKFold`. |
| **9** | **Ability to Explain Own Contribution** | [Sections 6 & 7](#6-comprehensive-member-by-member-decision--problem-log) — Member decision logs & responsibility matrix for all 4 members. |

---

### The Viva Presentation Strategy:
1. **Completed Work (Stages 1–4):** Present our full progress up to preprocessing and feature engineering:
   - Problem definition, dataset selection, and data quality findings backed by generated figures in `reports/figures/`.
   - Critical data leakage discovery and our group-based validation strategy.
   - Leakage-free preprocessing pipeline and feature engineering.
2. **The "After Plan" (Stages 5–7):** Present the upcoming roadmap as our planned next steps:
   - Training 4 baseline algorithms (Logistic Regression, Random Forest, SVM, XGBoost).
   - Cross-validation and hyperparameter tuning (`fig06_threshold_tuning.png`).
   - Model packaging, SHAP interpretations (`fig07_shap_summary.png`), FastAPI backend, and React UI deployment.

---

## 2. Stage 1: Problem Scenario & Stakeholder Requirements

### 2.1 [Rubric Item 1] — Problem / Scenario Understanding
Industrial Universal Robots (UR3 cobots) operate in automated manufacturing environments. Unplanned **protective stops** (automatic hardware halts triggered by safety controllers when unexpected resistance or joint torque occurs) halt assembly lines, reduce throughput, and risk equipment wear.

- **Goal:** Build an early-warning fault detection system that predicts protective stop risk from sensor readings before the robot halts.
- **Data Mining Task:** **Binary Classification** ($y \in \{0, 1\}$).
  - $0$: Normal robot operation.
  - $1$: Protective Stop event.
- **Operational Objective:** Detect rising electrical/mechanical anomalies $3\text{ seconds}$ before a stop occurs, providing real-time decision support for operators.

### 2.2 Stakeholders & System Requirements
1. **Plant Operators & Maintenance Engineers:** Receive real-time risk alerts and feature explanation cards (SHAP) to inspect joints before physical stops occur.
2. **Production Managers:** Reduce unscheduled downtime and improve Overall Equipment Effectiveness (OEE).

---

## 3. Stage 2: Dataset Identification & Validation

### 3.1 [Rubric Item 2] — Dataset Selection and Justification
- **Dataset Name:** UCI CobotOps Dataset (`ur3_cobotops.xlsx`).
- **Source & Citation:** UCI Machine Learning Repository / Published CobotOps Benchmark.
- **Dataset Approval:** Validated and approved by the course instructor prior to development.
- **Justification:** Unlike toy datasets, CobotOps contains real-world sensor logs from 240 operating cycles of a physical UR3 cobot, providing authentic joint currents, speeds, temperatures, and actual hardware protective stop labels.

### 3.2 [Rubric Item 3] — Dataset Characteristics & Target Variable
- **Dataset Dimensions:** $7,409$ total raw rows, $24$ columns across $240$ distinct working cycles.
- **Data Period:** Sensor readings captured at $\approx 1\text{ Hz}$ frequency on October 26, 2022.
- **Target Variable:** `Robot_ProtectiveStop`
  - $0$: Normal execution ($96.22\%$ of dataset — $7,077$ rows).
  - $1$: Protective stop triggered ($3.78\%$ of dataset — $278$ rows, grouped into $108$ stop episodes across $78$ cycles).

#### Dataset Features Summary
- **Identifier & Temporal Columns:** `Timestamp`, `cycle`.
- **Motor Currents ($6$ joints):** `Current_J0` to `Current_J5` (Amperes).
- **Tool Current:** `Tool_current` (Amperes).
- **Joint Speeds ($6$ joints):** `Speed_J0` to `Speed_J5` (rad/s).
- **Joint Temperatures ($6$ joints):** `Temperature_J0` to `Temperature_J5` (°C).
- **Status Flags:** `grip_lost` (Boolean binary flag).
- **Target:** `Robot_ProtectiveStop` (Binary flag).

---

## 4. Stage 3: Data Understanding & Exploratory Data Analysis (EDA)

### 4.1 [Rubric Item 5] — Data-Quality Issues *(Owner: Meegasthanna)*

#### Referenced Figures:
- **`reports/figures/fig01_missingness.png`** *(Missing Data Heatmap & Trailing Rows Analysis)*
- **`reports/figures/fig01_target_balance.png`** *(Class Imbalance Bar Chart)*

![fig01_missingness](figures/fig01_missingness.png)
*Figure 4.1a: Missingness heatmap showing that all 54 missing rows occur together at empty trailing records.*

- **Timestamp Parsing Issue:** ~12% of timestamps in `ur3_cobotops.xlsx` were enclosed in literal double quotes (`"2022-10-26T08:20:35.838Z"`), breaking datetime parsing. Resolved via `.str.strip('"')` prior to ISO8601 parsing.
- **Missing Values Analysis:** Exactly $54$ rows out of $7,409$ contained `NaN` values.
  - **Empirical Finding (Figure 4.1a):** All $54$ missing rows were also missing the target variable `Robot_ProtectiveStop`. $46$ of these rows were completely blank trailing rows.
  - **Decision:** Dropped all $54$ corrupted rows during initial loading, leaving $7,355$ clean, valid rows.
- **Duplicate Records:** $0$ duplicate rows found across all sensor columns.

![fig01_target_balance](figures/fig01_target_balance.png)
*Figure 4.1b: Class imbalance distribution showing 96.22% normal operation vs 3.78% protective stop events.*

- **Class Imbalance & Metric Framework (Figure 4.1b):**
  - $7,077$ normal rows ($96.22\%$) vs $278$ stop rows ($3.78\%$).
  - **Viva Metric Justification:** **Accuracy is misleading** ($96.22\%$ accuracy is achieved by a trivial dummy model that predicts $0$ for everything, yielding $0\%$ recall). Therefore, **PR-AUC (Precision-Recall Area Under Curve)** and **Recall** are our primary evaluation metrics.

---

### 4.2 [Rubric Item 4] — EDA Findings *(Owner: Seneviratne)*

#### Referenced Figures:
- **`reports/figures/fig02_distributions_current.png`** *(Joint Current Histograms)*
- **`reports/figures/fig02_distributions_speed.png`** *(Joint Speed Histograms)*
- **`reports/figures/fig02_distributions_temperature.png`** *(Temperature Histograms)*
- **`reports/figures/fig02_distributions_tool.png`** *(Tool Current Histogram)*
- **`reports/figures/fig02_boxplots.png`** *(Sensor Outlier Boxplots)*
- **`reports/figures/fig02_correlation.png`** *(Feature Correlation Matrix)*

![fig02_distributions_current](figures/fig02_distributions_current.png)
*Figure 4.2a: Distribution of motor currents across all 6 robot joints.*

![fig02_boxplots](figures/fig02_boxplots.png)
*Figure 4.2b: Outlier boxplots highlighting physical current spikes preceding protective stops.*

- **Motor Current Ranges (Figures 4.2a & 4.2b):** Joint currents range from $-6.25\text{ A}$ to $+6.47\text{ A}$. Tool current ranges from $0.07\text{ A}$ to $0.60\text{ A}$.
- **Outlier Investigation:** Extreme current spikes occur immediately prior to and during protective stops.
  - **Decision:** These spikes are **true physical signals** of mechanical strain, torque resistance, or obstruction—NOT measurement errors. They must be preserved rather than clipped or deleted.

![fig02_correlation](figures/fig02_correlation.png)
*Figure 4.2c: Correlation matrix showing joint-to-joint electrical relationships.*

- **`grip_lost` Feature Analysis:**
  - `grip_lost` is positive ($1$) on $243$ rows in total.
  - However, `grip_lost` overlaps with `Robot_ProtectiveStop = 1` on only $3$ rows.
  - **Conclusion:** Tool gripper loss is an independent operational event, not a reliable predictor of protective stops.

---

### 4.3 [Rubric Item 8] — Data Leakage Risks and Prevention *(Owner: Bandara — Technical Lead)*

#### Referenced Figures:
- **`reports/figures/fig03_stop_timeline.png`** *(Timeline of Protective Stop Events Across Cycles)*
- **`reports/figures/fig03_event_window.png`** *($\pm 10$-Row Event Window Leakage Study)*

![fig03_stop_timeline](figures/fig03_stop_timeline.png)
*Figure 4.3a: Protective stop occurrence timeline across 240 working cycles.*

![fig03_event_window](figures/fig03_event_window.png)
*Figure 4.3b: Event window plot demonstrating that same-moment joint speeds drop to zero at t=0.*

- **The Critical Leakage Discovery (Figure 4.3b):**
  - Analysis of joint speeds (`Speed_J0`–`Speed_J5`) revealed that at $t=0$ (the moment of a protective stop), the median total joint speed drops to $0.002\text{ rad/s}$, compared to $0.056\text{ rad/s}$ during normal movement.
  - **Conclusion:** Same-moment speed readings describe a robot that has *already stopped*. Including same-moment speeds creates severe **target leakage** (predicting a stop after the hardware has already halted).
- **Leakage Prevention Strategy:**
  1. Exclude same-moment speed readings from the model input feature space.
  2. Restrict features to electrical joint currents (`Current_J0`–`Current_J5`, `Tool_current`) and engineered temporal trends.
- **Group-Based Validation Strategy:**
  - Standard random train/test splitting causes severe temporal data leakage because adjacent readings within the same cycle are highly correlated.
  - **Decision:** We use **Cycle-Based Grouping** (`StratifiedGroupKFold` grouped by `cycle`). Entire working cycles are kept strictly in either the training set or test set, ensuring zero cross-cycle leakage.

---

## 5. Stage 4: Data Preprocessing & Feature Engineering

*(Owner: Umer)*

### 5.1 [Rubric Item 6] — Preprocessing Techniques & Reasons for Using Them (`src/pipeline.py`)
To ensure strict leakage-free execution, all preprocessing operations are encapsulated in a scikit-learn `ColumnTransformer` fit **only on the training split**:
1. **Median Imputation (`SimpleImputer(strategy='median')`):** Robust against any unexpected missing values during serving.
2. **Robust Scaling (`RobustScaler()`):** Uses Median and Interquartile Range (IQR: $Q_3 - Q_1$) instead of mean and variance. This prevents extreme physical current spikes from distorting feature scaling.

### 5.2 [Rubric Item 7] — Feature Engineering / Selection Decisions (`src/features.py`)
Two domain-specific temporal features were created to capture current buildup prior to stops:
1. **`total_joint_current`**:
   $$\text{total\_joint\_current} = \sum_{i=0}^5 |\text{Current\_J}i|$$
   Represents total instantaneous electrical load across all 6 robot joints.
2. **`total_joint_current_delta3`**:
   $$\text{total\_joint\_current\_delta3}_t = \text{total\_joint\_current}_t - \text{total\_joint\_current}_{t-3}$$
   Measures the rate of electrical current change over a 3-row lag window ($\approx 3\text{ seconds}$). A sudden positive delta signals impending mechanical resistance or motor overload.

---

## 6. [Rubric Item 9] — Ability to Explain Student's Own Contribution

This section details the exact technical problems encountered, empirical evidence discovered, alternatives evaluated, and final decisions implemented by each team member:

### 6.1 E.M.Y.E. Meegasthanna (Data Quality, Missingness & Metric Framework)
- **Problem 1: Malformed Raw Timestamps**
  - *Issue:* ~12% of timestamps in `ur3_cobotops.xlsx` were enclosed in literal double quotes (`"2022-10-26T08:20:35.838Z"`), causing `pd.to_datetime()` parsing failures.
  - *Decision:* Applied `.str.strip('"')` prior to parsing ISO8601 datetimes inside `load_data()`.
- **Problem 2: Handling 54 Missing Rows**
  - *Issue:* 54 rows contained missing values (`NaN`). 46 were empty trailing Excel rows.
  - *Empirical Evidence:* `fig01_missingness.png` showed that all 54 rows lacked the target label `Robot_ProtectiveStop`.
  - *Alternative Considered:* Imputing missing values and target labels.
  - *Why Rejected:* Imputing target labels creates artificial ground truth, corrupting model evaluation.
  - *Final Decision:* Dropped all 54 corrupted rows during loading ($7,355$ valid rows remaining).
- **Problem 3: Choosing the Primary Evaluation Metric**
  - *Issue:* Extreme class imbalance ($96.22\%$ normal vs $3.78\%$ stop events).
  - *Alternative Considered:* Using standard Classification Accuracy.
  - *Why Rejected:* A dummy classifier predicting $0$ for all rows achieves $96.22\%$ accuracy but $0\%$ recall on stops.
  - *Final Decision:* Adopted **PR-AUC** as the primary metric, supported by **Recall** and **Precision**.

---

### 6.2 T.W.M.S.G. Seneviratne (EDA, Distributions & Pattern Recognition)
- **Problem 1: Extreme Motor Current Outlier Spikes**
  - *Issue:* Motor currents (`Current_J0`–`Current_J5`) contained extreme values up to $\pm 6.47\text{ A}$ (IQR outliers).
  - *Alternative Considered:* Truncating/clipping outliers at $1.5 \times \text{IQR}$ or winsorizing.
  - *Why Rejected:* Current spikes are true physical motor load signals preceding hardware halts (`fig02_boxplots.png`). Clipping removes critical predictive signal.
  - *Final Decision:* Retained all physical current outliers in raw form without clipping.
- **Problem 2: Evaluating the Predictiveness of `grip_lost`**
  - *Issue:* `grip_lost` flag was active on 243 rows, raising a question of whether gripper loss causes stops.
  - *Empirical Evidence:* Cross-tabulation showed `grip_lost = 1` overlapped with `Robot_ProtectiveStop = 1` on only **3 rows**.
  - *Alternative Considered:* Relying on `grip_lost` as a primary predictor.
  - *Why Rejected:* Weak overlap indicates `grip_lost` is an independent tool status event.
  - *Final Decision:* Excluded `grip_lost` from primary fault indicators.

---

### 6.3 D.R.B.Y. Bandara (Temporal Analysis, Data Leakage & Validation Strategy — Technical Lead)
- **Problem 1: Target Leakage from Same-Moment Joint Speeds**
  - *Issue:* At protective stops ($t=0$), median joint speed dropped to $0.002\text{ rad/s}$ vs $0.056\text{ rad/s}$ during normal movement (`fig03_event_window.png`).
  - *Alternative Considered:* Including current-moment joint speeds as features.
  - *Why Rejected:* Predicts a stop *after* the hardware has already halted (useless in production).
  - *Final Decision:* Excluded same-moment speed features (`Speed_J0`–`Speed_J5`), restricting features to currents and lag deltas.
- **Problem 2: Temporal Cross-Contamination in Validation Splitting**
  - *Issue:* Standard random train/test splitting mixes adjacent correlated timestamps within the same cycle across train and test folds.
  - *Alternative Considered:* Standard K-Fold CV or random `train_test_split`.
  - *Why Rejected:* Causes severe cross-contamination across correlated adjacent timestamps.
  - *Final Decision:* Implemented **Chronological-by-Cycle Split** (held-out test = last 20% cycles) and **`StratifiedGroupKFold` grouped by `cycle`**.

---

### 6.4 D.R.S. Umer (Preprocessing Pipeline, Scaling & Feature Engineering)
- **Problem 1: Preprocessing Leakage in Pipeline Fitting**
  - *Issue:* Pre-fitting imputers/scalers on the whole dataset leaks test set statistics into training folds.
  - *Final Decision:* Encapsulated imputation and scaling inside a scikit-learn `ColumnTransformer` (`src/pipeline.py`), fit **strictly inside each cross-validation fold**.
- **Problem 2: Scaling Distortion from Physical Current Spikes**
  - *Issue:* `StandardScaler` (z-score) relies on mean and variance, which are distorted by extreme physical spikes.
  - *Alternative Considered:* `StandardScaler` or `MinMaxScaler`.
  - *Why Rejected:* `StandardScaler` distorts non-Gaussian distributions; `MinMaxScaler` compresses normal values into a tight cluster.
  - *Final Decision:* Selected **`RobustScaler()`** (scaling via Median and IQR), preserving outlier separation while scaling normal ranges properly.
- **Problem 3: Capturing Temporal Load Trend in Single Readings**
  - *Issue:* Instantaneous current doesn't show if electrical load is building up.
  - *Final Decision:* Engineered `total_joint_current` ($\sum |\text{Current\_J}i|$) and `total_joint_current_delta3` ($\text{total\_joint\_current}_t - \text{total\_joint\_current}_{t-3}$ over a 3-second lag window).

---

## 7. Team Ownership & Viva Responsibility Matrix

Use this matrix to answer questions about specific contributions during the individual viva:

| Team Member | Primary Responsibility | Key Referenced Figures | Key Viva Questions You Must Answer |
| :--- | :--- | :--- | :--- |
| **D.R.B.Y. Bandara** *(Lead)* | Temporal Analysis, Data Leakage & Validation Strategy | `fig03_stop_timeline.png`<br/>`fig03_event_window.png` | • What is data leakage in this dataset?<br/>• Why were same-moment speed features removed?<br/>• Why use `StratifiedGroupKFold` by `cycle` instead of random splitting? |
| **E.M.Y.E. Meegasthanna** | Data Quality, Missingness & Metric Framework | `fig01_missingness.png`<br/>`fig01_target_balance.png` | • Why were $54$ missing rows dropped?<br/>• Why is Accuracy misleading for $3.78\%$ positive class?<br/>• Why is PR-AUC the primary evaluation metric? |
| **T.W.M.S.G. Seneviratne** | EDA, Feature Distributions & Pattern Analysis | `fig02_distributions_current.png`<br/>`fig02_boxplots.png`<br/>`fig02_correlation.png` | • What are the physical ranges of joint currents?<br/>• Why are current outliers kept in the dataset?<br/>• What did the `grip_lost` correlation analysis reveal? |
| **D.R.S. Umer** | Preprocessing, Scaling & Feature Engineering | `src/pipeline.py`<br/>`src/features.py` | • Why use `RobustScaler` over `StandardScaler`?<br/>• How is `total_joint_current_delta3` calculated?<br/>• How does `src/pipeline.py` prevent preprocessing leakage? |

---

## 8. The "After Plan" (Upcoming Stages 5–7 Roadmap)

When asked about the next phases during Progress Evaluation 1, present this structured plan supported by our downstream analysis figures:

#### Referenced Downstream Figures:
- **`reports/figures/fig06_threshold_tuning.png`** *(Precision-Recall Decision Threshold Curve)*
- **`reports/figures/fig07_feature_importance.png`** *(Model Feature Importance)*
- **`reports/figures/fig07_shap_summary.png`** *(SHAP Feature Impact Beeswarm Plot)*

```
[Current Phase: Preprocessing Complete]
              │
              ▼
[Stage 5: Baseline Model Training] ──► Train 4 Algorithms (LogReg, RF, SVM, XGBoost)
              │
              ▼
[Stage 6: Hyperparameter Tuning]   ──► RandomizedSearchCV + Threshold Tuning (fig06_threshold_tuning.png)
              │
              ▼
[Stage 7: System & Deployment]     ──► SHAP Explanations (fig07_shap_summary.png) + FastAPI + React UI
```

![fig06_threshold_tuning](figures/fig06_threshold_tuning.png)
*Figure 8.1: Planned decision threshold tuning curve to achieve Recall >= 0.80.*

![fig07_shap_summary](figures/fig07_shap_summary.png)
*Figure 8.2: Planned SHAP explanation analysis identifying total_joint_current_delta3 and Tool_current as key predictors.*

### Planned Next Steps:
1. **Model Exploration (Phase 4):**
   - Train 4 diverse algorithms: **Logistic Regression** (Linear baseline), **Random Forest** (Tree ensemble), **Support Vector Machine with RBF Kernel** (Non-linear boundary), and **XGBoost** (Gradient boosted trees).
   - Evaluate all models using 5-fold `StratifiedGroupKFold` cross-validation on PR-AUC, Recall, and Precision.
2. **Tuning & Selection (Phase 5):**
   - Perform `RandomizedSearchCV` on key hyperparameters (`n_estimators`, `max_depth`, `C`, `gamma`, `scale_pos_weight`).
   - Tune decision threshold (Figure 8.1) to achieve high recall ($\ge 0.80$) for early safety alerts.
   - Package final pipeline to `models/final_pipeline.joblib`.
3. **Serving API & Frontend Application (Phase 6):**
   - **FastAPI Backend:** Serve `/predict` with bounded Pydantic validation (`JointCurrent` $\pm 10\text{ A}$, `ToolCurrent` $0\text{–}3\text{ A}$) and SHAP explanations (Figure 8.2).
   - **React Frontend:** Interactive dashboard with risk gauges, threshold markers, and input boundary warnings.

---

## 9. Quick Viva Question & Answer Cheatsheet

### Q1: Why did you drop the 54 missing rows instead of imputing them?
> **Answer:** All 54 missing rows lacked the target variable `Robot_ProtectiveStop`, and 46 of them were completely empty trailing rows (`fig01_missingness.png`). Imputing target labels introduces false synthetic ground truth, so dropping those rows was the only valid choice.

### Q2: Why is Accuracy a poor metric for this problem?
> **Answer:** The dataset has extreme class imbalance ($96.22\%$ normal, $3.78\%$ stop, as shown in `fig01_target_balance.png`). A dummy model predicting "normal" for every single row achieves $96.22\%$ accuracy but catches $0\%$ of protective stops. PR-AUC and Recall evaluate how well the model actually catches rare stops without excessive false alarms.

### Q3: How did you detect and prevent data leakage?
> **Answer:** As shown in `fig03_event_window.png`, same-moment joint speed readings drop to zero right when a stop occurs ($0.002\text{ rad/s}$ vs $0.056\text{ rad/s}$). Using same-moment speed would mean predicting a stop *after* the robot already stopped. We removed same-moment speed features and framed inputs around joint currents and historical 3-row current deltas ($\text{delta3}$). Furthermore, we split data by whole `cycle` groups so adjacent timestamps never leak between train and test sets (`fig03_stop_timeline.png`).

### Q4: Why did you choose `RobustScaler` instead of `StandardScaler`?
> **Answer:** Motor current data contains high physical spikes during heavy mechanical loads and stops (`fig02_boxplots.png`). `StandardScaler` uses mean and variance, which are heavily distorted by extreme values. `RobustScaler` uses median and IQR, scaling normal operating ranges effectively while keeping real physical spikes intact.

### Q5: What engineered features did you create and why?
> **Answer:** We engineered `total_joint_current` (the sum of absolute joint currents across all 6 joints) to measure total motor load, and `total_joint_current_delta3` (the 3-row lag difference of total current). A rising delta over 3 seconds indicates motor strain buildup prior to a protective stop.

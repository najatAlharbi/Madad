# MADAD — Intelligent Medical Inventory Management

MADAD is a healthcare-focused data science project that explores the use of machine learning, optimization, and computer vision to support intelligent medical inventory management and medication verification.

The project currently consists of two complementary components:

1. **Medical Inventory Forecasting & Redistribution**
2. **Visual Medication Verification using NLM20**

---

# 1. Medical Inventory Forecasting & Redistribution



---

# 2. Visual Medication Verification — NLM20

## Overview

The **Visual Medication Verification** component extends MADAD with a computer vision workflow for identifying medications from images of pills inside medication bottles.

The objective is to classify each medication image into its corresponding **National Drug Code (NDC)** class. The predicted NDC can then be linked to medication metadata to support medication identification and verification.

The overall workflow is:

**Pill/Bottle Image → Image Classification → Predicted NDC → Medication Metadata → Verification**

This module is developed as a proof of concept and is separate from the main MADAD inventory forecasting and redistribution pipeline.

---

## Dataset

The experiments use the **Images of Pills Inside Medication Bottles (NLM20)** dataset from the University of Michigan Deep Blue Data repository.

### Dataset Links

- **Dataset:**  
  https://deepblue.lib.umich.edu/data/concern/data_sets/6d56zw997

- **Related Research Paper / DOI:**  
  https://doi.org/10.1038/s41746-021-00483-8

### Dataset Summary

| Attribute | Value |
|---|---:|
| Total Images | 13,955 |
| NDC Classes | 20 |
| Training Images | 8,393 |
| Validation Images | 2,776 |
| Test Images | 2,786 |
| Readable Images | 13,955 |
| Corrupted Images | 0 |
| Exact Duplicate Groups | 0 |
| Cross-Split Duplicate Groups | 0 |
| Smallest Class | 160 images |
| Largest Class | 1,001 images |
| Class Imbalance Ratio | 6.26 |

The dataset contains top-down images of pills inside medication bottles. Each image is associated with an NDC class, making the task a **20-class image classification problem**.

Medication-level metadata can also be linked to the NDC identifier and includes information such as drug name, strength, shape, color, imprint, and size.

---

# Exploratory Data Analysis

The first stage of the project focuses on understanding the image dataset before model development.

Notebook:

`01_MADAD_NLM20_Image_EDA.ipynb`

The EDA pipeline includes:

- Inspecting the dataset directory structure.
- Building an image-level manifest.
- Counting the total number of images.
- Identifying all NDC classes.
- Examining train, validation, and test distributions.
- Measuring class frequencies.
- Visualizing class distributions.
- Inspecting representative medication images.
- Checking image readability.
- Identifying potentially corrupted images.
- Detecting exact duplicate images.
- Checking for duplicate images across dataset splits.
- Checking for conflicting duplicate labels.
- Examining class imbalance.

The EDA confirmed that all **13,955 images were readable** and no corrupted images were identified.

No exact duplicate groups, cross-split duplicate groups, or conflicting NDC duplicate groups were detected.

The class distribution is not completely balanced. Class sizes range from **160 to 1,001 images**, resulting in an imbalance ratio of approximately **6.26**.

### Generated EDA Files

The EDA outputs are stored under:

```text
NLM20_Visual_Verification/nlm20_eda_outputs/
```

The generated files include:

```text
nlm20_class_summary.csv
nlm20_duplicate_group_summary.csv
nlm20_duplicate_report.csv
nlm20_eda_summary.csv
nlm20_image_manifest.csv
nlm20_metadata_20_ndc.csv
```

These files provide reusable summaries of the dataset, image-level information, duplicate checks, class statistics, and NDC metadata.

---

## Data Preprocessing & Training Strategy

Notebook:

`02_MADAD_NLM20_Data_Exploration_and_Preprocessing.ipynb`

Before model training, the NLM20 dataset was explored and prepared to create a consistent pipeline for all deep learning experiments.

The preprocessing and training strategy included:

- Organizing image paths and corresponding NDC labels.
- Exploring NDC-level metadata.
- Reviewing the class distribution across the 20 NDC classes.
- Preparing the training, validation, and test datasets.
- Resizing images and applying model-specific preprocessing.
- Preparing class labels for multiclass classification.
- Creating model-ready input pipelines.
- Applying **class weights** to address class imbalance and give greater importance to underrepresented NDC classes.
- Applying **regular image augmentation** to the training data to increase image diversity and improve generalization.
- Using transfer learning with pretrained MobileNet architectures.
- Evaluating both frozen-backbone and partial fine-tuning strategies.

### Handling Class Imbalance

The NLM20 classes were not equally represented. To reduce model bias toward classes with larger numbers of images, **class weights** were incorporated during training.

This increases the contribution of underrepresented classes to the training loss without changing the original dataset distribution.

### Data Augmentation

Image augmentation was applied **only to the training set** to introduce controlled variations of the original images and improve model generalization.

The validation and test sets were kept unchanged to provide a consistent and unbiased evaluation of model performance.

This preprocessing strategy ensures that all experiments use a consistent representation of the NLM20 images and labels while addressing class imbalance and reducing the risk of overfitting.

## Experimental Workflow

The complete experimental workflow was:

**Dataset Inspection → Image EDA → Data Preprocessing → Class Imbalance Handling → Data Augmentation → Transfer Learning → Validation → Fine-Tuning → Test Evaluation**

Three main deep learning experiments were conducted:

| Experiment | Architecture | Training Strategy |
|---|---|---|
| **Model 1** | MobileNetV1 | Frozen pretrained backbone |
| **Model 2** | MobileNetV2 | Frozen pretrained backbone |
| **Model 3** | MobileNetV1 | Partial fine-tuning of the last 20 layers |

The frozen-backbone experiments were first used as transfer-learning baselines. MobileNetV1 was then further explored using partial fine-tuning, where the final 20 layers were made trainable to allow higher-level visual features to adapt more specifically to the NLM20 medication images.

---

## Experiment 1 — MobileNetV1 Frozen

Notebook:

`03_MADAD_NLM20_MobileNetV1_Frozen.ipynb`

The first experiment uses **MobileNetV1** as a pretrained feature extractor.

The convolutional backbone is kept frozen while the classification component is trained on the 20 NDC classes.

This experiment provides the main transfer-learning baseline for the NLM20 visual medication verification task.

Training history is recorded for:

- Accuracy
- Precision
- Recall
- F1-score
- Loss
- Validation accuracy
- Validation precision
- Validation recall
- Validation F1-score
- Validation loss
- Learning rate

### Validation Performance

| Metric | Score |
|---|---:|
| Accuracy | 89.12% |
| Precision | 89.82% |
| Recall | 89.12% |
| F1-Score | 89.19% |

### Test Performance

| Metric | Score |
|---|---:|
| Accuracy | **89.16%** |
| Precision | **89.93%** |
| Recall | **89.16%** |
| F1-Score | **89.20%** |

The trained MobileNetV1 frozen model is saved as:

```text
models/MobileNetV1_Frozen.keras
```

---

## Experiment 2 — MobileNetV2 Frozen

Notebook:

`04_MADAD_NLM20_MobileNetV2_Frozen.ipynb`

The second experiment evaluates **MobileNetV2** using the same frozen-backbone transfer-learning strategy.

This experiment was conducted to compare MobileNetV2 with the MobileNetV1 baseline for medication image recognition.

### Validation Performance

| Metric | Score |
|---|---:|
| Accuracy | 82.74% |
| Precision | 84.55% |
| Recall | 82.74% |
| Weighted F1-Score | 82.32% |
| Macro F1-Score | 80.11% |

### Test Performance

| Metric | Score |
|---|---:|
| Accuracy | 82.23% |
| Precision | 83.96% |
| Recall | 82.23% |
| Weighted F1-Score | 81.80% |
| Macro F1-Score | 79.75% |

The trained MobileNetV2 model is saved as:

```text
models/MobileNetV2_Frozen.keras
```

---

## Experiment 3 — MobileNetV1 Fine-Tuning

Notebook:

`05_MADAD_NLM20_MobileNetV1_Last20.ipynb`

The third experiment investigates whether partial fine-tuning can improve the MobileNetV1 baseline.

Instead of keeping the entire pretrained feature extractor frozen, the **last 20 layers** are made trainable so that higher-level visual features can adapt more specifically to the NLM20 medication images.

### Validation Performance

| Metric | Score |
|---|---:|
| Accuracy | 88.65% |
| Precision | 89.73% |
| Recall | 88.65% |
| F1-Score | 88.51% |

The fine-tuned model achieved strong performance, although the fully frozen MobileNetV1 experiment produced slightly higher validation accuracy.

---

# Model Comparison

| Model | Validation Accuracy | Validation F1 |
|---|---:|---:|
| **MobileNetV1 Frozen** | **89.12%** | **89.19%** |
| MobileNetV1 — Last 20 Layers | 88.65% | 88.51% |
| MobileNetV2 Frozen | 82.74% | 82.32%* |

\* Weighted F1-score.

Among the evaluated experiments, **MobileNetV1 with a frozen backbone achieved the strongest validation performance**.

It also achieved approximately **89.16% test accuracy**, demonstrating that a lightweight transfer-learning architecture can provide promising performance for NDC-based visual medication classification.

---

# Saved Results

Experimental results are stored separately from the notebooks under:

```text
NLM20_Visual_Verification/results/
```

Current result files include:

```text
MobileNetV1_Training_History.csv
MobileNetV1_Validation_Results.csv
MobileNetV1_Test_Results.csv

MobileNetV2_Training_History.csv
MobileNetV2_Validation_Results.csv
MobileNetV2_Test_Results.csv

MobileNetV1_Last20_Training_History.csv
MobileNetV1_Last20_Validation_Results.csv
```

Keeping the results in CSV format makes the experiments easier to compare, reproduce, and analyze independently from the notebooks.

---

# Saved Models

Trained model artifacts are stored under:

```text
NLM20_Visual_Verification/models/
```

Current saved models:

```text
MobileNetV1_Frozen.keras
MobileNetV2_Frozen.keras
```

---

# Repository Structure

```text
NLM20_Visual_Verification/
│
├── notebooks/
│   ├── 01_MADAD_NLM20_Image_EDA.ipynb
│   ├── 02_MADAD_NLM20_Data_Exploration_and_Preprocessing.ipynb
│   ├── 03_MADAD_NLM20_MobileNetV1_Frozen.ipynb
│   ├── 04_MADAD_NLM20_MobileNetV2_Frozen.ipynb
│   └── 05_MADAD_NLM20_MobileNetV1_Last20.ipynb
│
├── nlm20_eda_outputs/
│   ├── nlm20_class_summary.csv
│   ├── nlm20_duplicate_group_summary.csv
│   ├── nlm20_duplicate_report.csv
│   ├── nlm20_eda_summary.csv
│   ├── nlm20_image_manifest.csv
│   └── nlm20_metadata_20_ndc.csv
│
├── models/
│   ├── MobileNetV1_Frozen.keras
│   └── MobileNetV2_Frozen.keras
│
└── results/
    ├── MobileNetV1_Training_History.csv
    ├── MobileNetV1_Validation_Results.csv
    ├── MobileNetV1_Test_Results.csv
    ├── MobileNetV1_Last20_Training_History.csv
    ├── MobileNetV1_Last20_Validation_Results.csv
    ├── MobileNetV2_Training_History.csv
    ├── MobileNetV2_Validation_Results.csv
    └── MobileNetV2_Test_Results.csv
```

---

# Role within MADAD

The NLM20 module adds a **visual medication verification layer** to the broader MADAD project.

While the main MADAD component focuses on medical inventory forecasting and redistribution, the NLM20 component focuses on identifying medications directly from images.

The two components address complementary tasks:

**Inventory Intelligence → Forecasting, Availability, and Redistribution**

**Visual Medication Verification → Image Classification, NDC Identification, and Medication Verification**

---

## License

This repository is licensed under the **MIT License**.

The NLM20 dataset and other external datasets remain subject to their original licenses and terms of use.

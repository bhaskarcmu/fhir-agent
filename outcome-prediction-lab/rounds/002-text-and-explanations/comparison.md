# Round 002-text-and-explanations — cross-validated runs

| Label | Run | Model | Text | CV metric | Value | Baseline | AUPRC / extra |
|---|---|---|---|---|---|---|---|
| admit_nonobstetric_y2 | `all-text-lsa` | gbm | lsa, desc_lsa, drug_char_lsa | auroc | 0.7989 | 0.7478 | 0.272 |
| admit_nonobstetric_y2 | `ref-codes-lsa` | gbm | lsa | auroc | 0.7988 | 0.7478 | 0.272 |
| admit_nonobstetric_y2 | `codes-plus-desc-lsa` | gbm | lsa, desc_lsa | auroc | 0.7986 | 0.7478 | 0.269 |
| admit_nonobstetric_y2 | `codes-plus-drug-chars-lsa` | gbm | lsa, drug_char_lsa | auroc | 0.7982 | 0.7478 | 0.269 |
| admit_nonobstetric_y2 | `desc-words-lsa` | gbm | desc_lsa | auroc | 0.7979 | 0.7478 | 0.266 |
| admit_nonobstetric_y2 | `lr-sparse-desc` | lr | desc_tfidf | auroc | 0.7979 | 0.7478 | 0.272 |
| admit_nonobstetric_y2 | `no-text` | gbm |  | auroc | 0.7978 | 0.7478 | 0.269 |
| admit_nonobstetric_y2 | `lr-sparse-codes` | lr | tfidf | auroc | 0.7958 | 0.7478 | 0.271 |
| admit_nonobstetric_y2 | `lr-sparse-all-text` | lr | tfidf, desc_tfidf, drug_char_tfidf | auroc | 0.7919 | 0.7478 | 0.263 |

# CUAD data — attribution

`cuad_test_sample.json` is a subset of the **Contract Understanding Atticus
Dataset (CUAD) v1**, filtered to the 5 v1 target clause types and drawn from
CUAD's official **test** split (held-out; never used for tuning).

- **Source:** The Atticus Project — https://github.com/TheAtticusProject/cuad
- **Paper:** Hendrycks et al., *CUAD: An Expert-Annotated NLP Dataset for Legal
  Contract Review*, NeurIPS 2021.
- **License:** CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/
  Free to use and redistribute, including commercially, with attribution.

The full 510-contract corpus is not committed (size). Fetch it with
`python scripts/download_cuad.py` (clones the CC BY 4.0 repo from GitHub).

Gold answer spans carry character offsets (`answer_start`) that anchor exactly
against each contract's text — the same offset model AuditAgent uses for
citations, which is why CUAD is the natural ground truth for this project.

# AuditAgent re-baseline summary

- model: `deepseek-v4-flash` · runs: 3 · temp 0 · n=102 · definition gate OFF

| metric | mean | min | max | spread |
|---|---|---|---|---|
| B2 high-risk recall | 0.7949 | 0.7692 | 0.8132 | 0.044 |
| B2 macro-F1 | 0.6735 | 0.6648 | 0.6779 | 0.0131 |
| B2 citation faithfulness | 0.9198 | 0.8726 | 0.9442 | 0.0716 |
| B1 citation faithfulness (fair) | 0.8465 | 0.8062 | 0.8931 | 0.0869 |
| B1 citation faithfulness (naive) | 0.5655 | 0.4997 | 0.6969 | 0.1972 |
| B1 high-risk recall | 0.8279 | 0.8132 | 0.8352 | 0.022 |

Anchorer lift (naive→gate, mean): **+0.3543**

> Publish a metric only if its spread ≤ 0.03; report as mean ± spread.

# Browser screenshots — Stage 1

Recaptured 2026-09-12 against the running local app (`http://127.0.0.1:5173/`) with the Cursor browser tool. PNG files live in this directory (chrome profiles under the same folder are gitignored). Only the LUCID page was captured.

| File | What it shows |
| --- | --- |
| `01-analyses-zh.png` | Chinese homepage: composer (question + paste + files), six templates, no fake metrics |
| `02-modeling-zh.png` | Question-only analysis on Modeling. Source preview of the decision question. Honest “live model not configured”. No fake draft |
| `03-materials-zh.png` | Unified text + file intake on Materials |
| `04-results-zh.png` | Results: solver not implemented; no fabricated schedule |
| `05-baseline-en.png` | English chrome after language toggle; empty baseline until review/freeze |

Interactive checks that are not a still image:

- Submit a non-blank question with no files → project opens on Modeling
- Run modeling Agent without `LUCID_MODEL_*` → activity “Live model is not configured”, no sample draft
- `/understanding` redirects to `/modeling`
- EN / 中文 toggle changes chrome; user-entered titles stay as typed

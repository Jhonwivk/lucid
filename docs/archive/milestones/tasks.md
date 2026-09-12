# First-release task status

Status is changed only after implementation and verification.

| ID | Area | Status |
| --- | --- | --- |
| T01–T08 | runtime, persistence, UI, fixtures and material intake | done |
| T09–T10 | one Agent, source-linked review and confirmed baseline | done locally; live providers pending |
| T11 | scenarios, formal model, revision invalidation | done |
| T12 | deterministic training scheduling | done |
| T13–T16 | explanations, portfolio, comparison and what-if | done |
| T17–T19 | export, recovery, deletion and boundaries | done |
| T20 | two complete live evidence-to-export runs | blocked |

## Verification rule

The T11–T19 claims are backed by focused temporary-database verifiers and a web build/lint run. Fixtures or direct store setup cannot satisfy T20. T20 requires live model/Azure configuration and real evidence.

## Current next action

Configure the local model and Azure settings, then run two human-reviewed acceptance cases. Do not expand the MVP model families before that gate is complete.

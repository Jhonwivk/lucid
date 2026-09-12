# First-release acceptance

## Local acceptance

- [x] App starts and the four-workspace shell loads.
- [x] Materials preserve bytes, checksums and source spans for direct text, documents, tables and images.
- [x] One Agent draft can be reviewed and frozen as a baseline when providers are configured; missing providers fail honestly.
- [x] Confirmed baseline binds to a versioned formal scenario.
- [x] Training and portfolio solvers produce real bounded candidates and explicit states.
- [x] What-if, comparison, provenance, history/export and material deletion work.
- [x] Solver leases reject stale workers and support deterministic resume.

## T20 live acceptance — blocked

Two cases must use real user evidence and run through:

```text
intake → live Agent extraction → human review → typed model
→ deterministic solve → what-if → export
```

A fixture, a handcrafted baseline or a metadata-only SolveRun does not count. The current checkout has no confirmed live model/Azure acceptance evidence.

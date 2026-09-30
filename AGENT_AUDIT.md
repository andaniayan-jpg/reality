# Reality agent audit

`REALITY_AGENT_STATUS=PASS`

- Test return code: `0`
- Plan lifecycle: `plan → validate → preview → execute`

## Evidence

- Tests execute source-backed measurements, unit conversion, preview, and commit.
- Tests reject unknown names and invalid units before mutation.
- Tests assert the source model remains unchanged after preview/rejection.
- Numeric edit evidence is marked user_request; providers have no geometry authority.

The complete test output is retained in `AGENT_RESULTS.json`.

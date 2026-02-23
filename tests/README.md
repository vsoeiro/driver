# Test layout

- `tests/unit`: isolated logic tests using mocks/stubs, no real external services.
- `tests/integration`: tests that exercise DB/Redis/API integrations (real or semi-real infra).
- `tests/e2e`: end-to-end user/business flows across service boundaries.

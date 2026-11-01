# AQERITH Idea 12 — Offer Management & Approval

## Branch and release boundary
- Feature branch: `feat/idea-12-offer-management-approval`
- Base: `main`
- Production domain: https://aqerith.com
- Production database and deployment must remain untouched until review and acceptance are complete.

## Existing implementation discovered
The main branch already had an offer page, `backend/app/routers/offers.py`, `backend/app/schemas/offers.py`, and `backend/app/services/offer_service.py`. The existing workflow allowed a recruiter to change the offer status directly and edit terms without version snapshots. It did not provide separate approval authority or immutable, version-bound approval decisions. This implementation extends those existing paths rather than creating a parallel offer system.

## Implemented in this increment
- Additive migration for `offer_versions`, `offer_approvals` and `offer_documents`, plus offer lifecycle metadata.
- Immutable offer-version snapshots with canonical JSON terms and SHA-256 checksums.
- Append-only approval decisions bound to the exact offer version reviewed.
- Backend role checks: organisation members can read; recruiter/hiring-manager roles can prepare and progress offers; only organisation owners/admins can approve or reject.
- Explicit draft → awaiting approval → approved → issued flow.
- Approval rejection or changes requested return the offer to draft; edits are allowed only while draft and create a new version.
- Issued offer terms cannot be edited through the normal offer update endpoint.
- Audited withdrawal and expiry actions with server-side transition checks.
- Staff-recorded candidate response requires an evidence reference and is stored separately from approval state.
- Frontend offer workspace supports key terms, benefits, conditions, expiry, approval actions, issuance and recorded responses.
- Schema validation tests for payload constraints and response evidence.

## API additions
- `POST /api/offers/{id}/submit-for-approval?organization_id=...`
- `POST /api/offers/{id}/approval?organization_id=...` with `approved`, `rejected` or `changes_requested`
- `POST /api/offers/{id}/issue?organization_id=...`
- `POST /api/offers/{id}/record-candidate-response?organization_id=...`
- `POST /api/offers/{id}/withdraw?organization_id=...`
- `POST /api/offers/{id}/expire?organization_id=...`
- `GET /api/offers/{id}/versions?organization_id=...`
- `GET /api/offers/{id}/approvals?organization_id=...`

## Security and data notes
- All offer reads and writes are scoped by `organization_id`; application linkage is checked against the same organization.
- Direct browser grants to new tables are revoked. API access requires a valid user and organisation membership.
- Version rows and approval decisions are protected by database triggers against update/delete.
- Document metadata is designed for private object-storage references only. This increment does not yet implement signed document delivery or candidate upload/signature handling.
- Candidate response recording is staff-entered, not candidate-authenticated self-service. Do not present it as a candidate portal or electronic signature.
- The `expire` action is an explicit operation; no scheduled expiry worker was added.
- The schema change needs compatibility review against the actual staging database, especially existing status constraints and the existing `offers` table definition, before application.

## Verification status
- Repository source inspected through GitHub connector; no local checkout was available in this workflow.
- No backend test suite, frontend typecheck/build, migration execution, authenticated browser test or tenant-boundary test has been run for this branch yet.
- Migration has not been applied to ATS-Staging or production.
- No deployment or merge has been performed.

## Acceptance checklist
- [ ] Apply migration to a disposable database or ATS-Staging after reviewing schema compatibility.
- [ ] Confirm only authorised approvers can approve/reject, including direct API calls.
- [ ] Confirm tenant A cannot read or mutate tenant B's offers, versions, approvals or documents.
- [ ] Confirm approval references the exact current version and stale versions cannot be approved.
- [ ] Confirm issued terms are immutable and a new version is created for subsequent approved changes.
- [ ] Confirm valid and invalid status transitions are covered by automated tests.
- [ ] Confirm audit events are written for creation/version changes, approval, issuance, response, withdrawal and expiry.
- [ ] Implement private document generation/storage and access-controlled delivery; verify object-level permissions and signed URLs.
- [ ] Implement candidate-authenticated acceptance/decline or integrate a verified e-signature provider.
- [ ] Implement scheduled expiry processing and idempotency if automatic expiry is required.
- [ ] Run backend tests, frontend lint/typecheck/build and migration checks.
- [ ] Run authenticated browser QA, accessibility checks and tenant/role boundary tests.
- [ ] Review jurisdiction-specific employment offer wording, retention and data-protection requirements for the UK, USA, India and Australia.
- [ ] Keep PR draft until all release checks pass. Do not merge or deploy to production before acceptance.

## Files changed
- `supabase/migrations/20261022150000_offer_management_approval.sql`
- `backend/app/schemas/offer_management.py`
- `backend/app/schemas/offer_withdrawal.py`
- `backend/app/schemas/offers.py`
- `backend/app/services/offer_management_service.py`
- `backend/app/services/offer_service.py`
- `backend/app/routers/offers.py`
- `backend/tests/test_offer_management_schemas.py`
- `frontend/app/offers/page.tsx`
- `docs/idea-12-offer-management-approval-handover.md`

# Idea 16 — Candidate Portal identity and API design

Status: design baseline for implementation review  
Branch: `feat/idea-16-candidate-portal-foundation`  
Scope: identity ownership and candidate-safe API boundary only. This document does not authorise a database migration, deployment, or production change.

## 1. Current repository facts

- Recruiter APIs authenticate a Supabase user and then authorise access through organisation membership.
- The candidate router returns recruiter-facing candidate records, including fields such as resume text, AI summary, retention metadata and consent metadata. It must not be exposed as a candidate self-service API.
- The public careers application endpoint creates or reuses a candidate record by organisation and email, then creates an application. It does not create a candidate login or establish account ownership.
- Candidate document routes are recruiter/organisation-member routes. They check organisation membership and issue short-lived signed storage URLs.
- The existing communication feature stores candidate-visible messages as drafts; provider delivery is not enabled.
- There is no verified candidate-to-auth-user ownership mapping or candidate portal router in the inspected implementation.

## 2. Security objective

A candidate may access only their own candidate profile, their own applications and candidate-visible documents/messages. A candidate must never gain access by supplying a candidate ID, application ID, organisation ID, email address or storage path belonging to someone else.

Recruiter access remains governed by the existing organisation membership and role model. Candidate access is a separate principal and authorisation path, not a weaker variation of recruiter membership.

## 3. Proposed identity model

Add a tenant-scoped mapping table (name proposed: `candidate_portal_accounts`) with:

- `id` UUID primary key.
- `organization_id` UUID not null.
- `candidate_id` UUID not null.
- `user_id` UUID not null referencing Supabase `auth.users(id)`.
- `created_at`, `updated_at`, and optional `last_verified_at`.
- Composite foreign key `(organization_id, candidate_id)` to the matching candidate row.
- Unique `(organization_id, candidate_id)`: one portal identity owns a candidate record in an organisation.
- Unique `(organization_id, user_id)`: one candidate account maps to at most one candidate record per organisation.
- Indexes for user and candidate lookup.

A candidate may have distinct candidate records at different recruitment organisations, while a single verified account may be mapped independently in each organisation. No cross-tenant candidate search or automatic record merge is introduced.

### Account linking rules

1. Candidate signs in using the existing Supabase Auth project (email OTP/magic link initially; no custom password storage).
2. Backend validates the bearer token and obtains the authoritative Supabase Auth user record.
3. Linking requires a confirmed/verified email from that authoritative record. Do not trust a client-submitted email or an unverified JWT claim.
4. Normalise the verified email and match it against candidate records inside the selected organisation only.
5. If there is no match, return a generic not-linked response and do not disclose whether a candidate record exists.
6. If more than one candidate record matches, fail closed and require a controlled recruiter-assisted resolution. Never guess or merge.
7. Create the mapping in a transaction with uniqueness protection. Do not allow a second user to claim an already-linked candidate.
8. Record an audit event for link, unlink, and security-sensitive account changes. Do not log access tokens or raw document contents.

Email matching is an initial proofing method, not a permanent identifier. Email changes, recycled addresses, shared mailboxes, duplicate records and account recovery require explicit review before production.

## 4. Candidate API boundary

Create a separate router (proposed prefix `/api/candidate-portal`) with a dedicated dependency that resolves the authenticated user to the candidate account mapping. Every handler derives candidate and organisation IDs from this mapping; callers do not choose arbitrary candidate IDs.

Initial read-only endpoints:

- `GET /me`: allowlisted profile fields only.
- `GET /applications`: only applications belonging to the mapped candidate; return a candidate-safe status and limited job details.
- `GET /applications/{application_id}`: verify both application ID and mapped candidate ID in the same query.
- `GET /documents`: only non-deleted documents belonging to the mapped candidate.
- `POST /documents/{document_id}/download`: verify ownership in the same query before creating a short-lived signed URL.
- `GET /communications`: only candidate-visible messages for the mapped candidate; never return internal notes, recruiter-only events, delivery provider metadata or other recipients.

Do not return recruiter notes, internal comments, internal message visibility, AI ranking rationale, recruiter-only scores, private interview feedback, raw CV extraction text, storage paths, provider metadata, or other candidates' data.

## 5. Controlled candidate actions (later increment)

After the read-only boundary is tested:

- Allow a strict allowlist of self-editable profile fields. Do not permit candidate updates to organisation, status, consent audit timestamps, retention fields, AI fields, resume storage paths or recruiter-managed metadata.
- Allow application withdrawal only through a documented transition rule and transaction that writes an audit event.
- Add document upload only after validating file type, content signature, size, malware-scanning strategy, private bucket policy, ownership and audit behaviour.
- Candidate-visible communication replies must be separate from recruiter draft creation and must never permit internal visibility.

## 6. Session, recovery and privacy

- Use Supabase Auth's verified email sign-in and recovery flows; never store passwords in AQERITH tables.
- Provide a clear sign-out action and document the session revocation behaviour. Administrative/global revocation must use the supported Supabase Auth admin operation, not direct table edits.
- Rate-limit linking and recovery endpoints; return non-enumerating responses.
- Log security events without tokens, passwords, CV contents or unnecessary personal data.
- Provide access, correction, export, restriction/objection and erasure request workflows as appropriate to the applicable privacy regime. Do not equate deleting a portal mapping with deleting the underlying recruitment record.
- Candidate consent, privacy notice version, lawful basis, retention and deletion are separate controls and must not be inferred from successful login.

## 7. Database and RLS requirements

- Tenant consistency must be enforced by composite foreign keys and unique constraints.
- Enable RLS on the mapping table. Candidate browser roles receive no direct table writes; preferably no direct table access at all. Mutations and reads go through the authenticated backend.
- Backend queries must constrain by both the authenticated mapping and tenant ID, not by a client-supplied candidate ID.
- Service-role/database credentials must remain server-side and must not be exposed in frontend bundles.
- Test cross-tenant and cross-candidate denial at both API and database layers.
- Do not apply a migration to the existing populated ATS-Staging project until its migration history and backup/rollback position have been reconciled. No Supabase development branch will be created because the user has set a £0 additional-spend limit.

## 8. Required tests before implementation can be called complete

1. Unauthenticated requests receive 401.
2. Unverified email cannot link.
3. No email match returns a non-enumerating response.
4. Duplicate email matches fail closed.
5. A candidate already linked to another user cannot be claimed.
6. A user cannot map two candidate records in one organisation.
7. Candidate A cannot read Candidate B's profile, application, document or communication by changing URL IDs.
8. Candidate A cannot access the same candidate's record through another organisation.
9. Candidate responses never include internal notes, recruiter-only fields, raw storage paths or provider metadata.
10. Expired/revoked sessions are rejected.
11. Withdrawal and profile updates enforce field allowlists, transition rules and audit logging.
12. Existing recruiter APIs and workflows remain unchanged.

## 9. Delivery sequence

1. Review this identity model against current Supabase Auth configuration and candidate data constraints.
2. Add pure unit tests for email normalisation, verified-user requirements, duplicate-match handling and safe response allowlists.
3. Implement the mapping migration and backend resolver on this feature branch only.
4. Implement read-only candidate APIs and API-level ownership tests.
5. Implement the portal UI using only the candidate-safe APIs.
6. Run full backend tests, frontend typecheck/build, tenant-isolation tests and security review.
7. Reconcile staging migration history before any staging migration. Production remains untouched until a separately approved release.

## 10. Explicit non-goals for this increment

- No AI candidate scoring or automated hiring decisions.
- No candidate-to-candidate matching or cross-tenant talent pool.
- No outbound email/SMS provider integration.
- No direct browser database writes.
- No changes to recruiter permissions or existing production data.

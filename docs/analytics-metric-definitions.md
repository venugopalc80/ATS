# Section 6 — Analytics and Business Intelligence

**Scope:** AQERITH Ideas 28–33  
**Status:** Metric contract, KPI/funnel/workload/source APIs, six-month baseline demand forecast, allowlisted CSV exports and first analytics workspace UI are committed on the feature branch. CI is running for the expanded slice. Forecast SQL has been executed read-only against staging; staging has no recruitment/campaign rows for numerical reconciliation.  
**Last reviewed:** 2026-10-22

This document defines the proposed shared contract for analytics APIs, dashboards, exports and forecast comparisons. A metric is not accepted solely because the UI displays a value.

## Shared rules

- Every query is scoped to the authenticated user's organisation and applies any narrower role/team access policy. Never trust a client-supplied organisation ID without membership validation.
- All date/time comparisons use persisted timestamptz values in UTC; display dates in the organisation/user's configured time zone. Date filters are inclusive at the start and exclusive at the day after the end.
- Filters for period, job, department, recruiter and source must be applied consistently to numerator, denominator, chart and drill-down.
- Counts use distinct record identifiers where repeated events could otherwise inflate totals. Event counts and unique-application counts must be labelled separately.
- Missing timestamps or incomplete lifecycle records are excluded from duration denominators and reported as incomplete; they are not silently treated as zero days.
- Empty cohorts return a null/unavailable metric with an explanation, not numeric zero. Zero is valid only when the eligible population is known and the measured count is zero.
- Store metric definition/version and cohort semantics alongside saved reports and forecast runs. Source records remain the audit authority.
- Suppress or flag small samples. Initial default: fewer than 5 distinct applications is marked low sample size; make the threshold configurable before release.
- Use parameterised SQL and allowlisted dimensions only. Never accept user-supplied SQL.

## Idea 28 — Recruitment Analytics & KPI Dashboard

| Metric | Definition | Important qualifications |
|---|---|---|
| Time to fill | Median calendar days from requisition approval to the first accepted offer linked to the converted requisition/job. | Requires valid requisition-to-job link and accepted-offer timestamp. Report incomplete cases separately. |
| Time to hire | Median calendar days from application creation to accepted offer response. | This is application-to-acceptance, not requisition-to-acceptance. |
| Time to start | Median calendar days from requisition approval to verified actual start date. | A planned offer start date is not proof that the candidate started. |
| Applications per vacancy | Distinct applications created in the selected cohort per vacancy. | State whether this is a per-vacancy count or overall ratio. |
| Stage conversion | Distinct applications entering stage S that subsequently reach the defined next stage, divided by eligible distinct applications entering S. | Repeated visits count once for unique-application conversion; expose event counts separately. |
| Offer acceptance rate | Accepted offers divided by offers with a final accepted or rejected decision. | Exclude draft/sent, withdrawn and expired offers; show counts and incomplete outcomes. |
| Interview-to-offer ratio | Offers created divided by completed interviews in the same defined cohort. | Label the unit and cohort; return unavailable when denominator is zero. |
| Source effectiveness | Distinct applications, qualified applications, interviews, offers and hires attributed to each source. | Attribution model and qualification rule must be visible; preserve unknown source. |
| Vacancy ageing | Current calendar days since vacancy opening for open vacancies. | Show paused, closed, filled and cancelled statuses separately. |
| Recruiter workload | Active assigned vacancies, active applications, upcoming interviews and overdue open tasks grouped by recruiter. | Show unassigned work separately. This is not a direct measure of individual performance. |

Duration KPIs are grouped by completion event date unless a report explicitly selects a requisition cohort. Application volume uses application creation date; funnel reports use stage-entry event date. Vacancy ageing is a current-state snapshot and must be labelled as such. If no complete eligible cohort exists, show “Insufficient complete records”, not zero.

## Idea 29 — Funnel Analysis & Bottleneck Detection

- Primary source: application_stage_history, joined through the application and constrained by organisation_id.
- Stage entry is an event where new_stage is the stage being measured. A repeated entry remains a stage-visit event but contributes at most once to unique-application conversion for the selected cohort.
- Stage exit is the next later event for that application. Without a later event, the interval is right-censored and excluded from completed waiting-time statistics; show the application as still in stage.
- Waiting time is elapsed calendar time between entry and the next valid transition, measured in UTC. Report median and p75/p90 where sample size permits; do not rely on average alone.
- Reopening creates a new visit. A transfer to another vacancy is a separate application only if a distinct application record exists.
- Withdrawn and rejected are distinct terminal outcomes and do not count as successful advancement.
- Every funnel response includes entered, advanced, withdrawn, rejected, still-in-stage and incomplete-history counts. Counts must reconcile to the unique application/event cohort.
- Mark cohorts with fewer than 5 distinct applications as low sample size by default.

## Idea 30 — Recruiter Workload & Capacity Planning

- Active requisitions/vacancies: records currently in configured active statuses and assigned to the recruiter; exclude closed/cancelled records.
- Open applications: distinct applications in non-terminal statuses, using a documented ownership rule.
- Upcoming interviews: scheduled/rescheduled interviews in the requested future interval, counted once per interview.
- Overdue tasks: open tasks with due_at earlier than now. Tasks without a due date are “no due date”, not overdue.
- Unassigned work: active records whose responsible recruiter is null.
- Any capacity score is an organisation-configurable estimate based on documented inputs and versioned weights. It must not be presented as an objective productivity score.
- Reassignment updates authoritative ownership and creates an audit event containing actor, old owner, new owner, reason and timestamp. Historical reports use assignment history where available; otherwise disclose that historical ownership cannot be reconstructed.

## Idea 31 — Source Effectiveness & Recruitment ROI

- Preserve raw application source and source events. Normalise display labels without deleting original values.
- Unknown, blank and unmapped sources remain visible as “Unknown / not recorded”.
- Initial attribution model: application source recorded at application creation. If multi-touch events exist, expose them under a separate configurable model; do not imply attribution proves causation.
- Campaign/channel spend is reportable only when amount and currency exist. Do not sum unlike currencies without a documented conversion rate and date. Because current spend is not segmented by period, job or recruiter, cost ratios must be unavailable when those filters are applied.
- Cost per qualified application, interview, offer or hire is unavailable unless both cost and outcome count exist and the currency basis is comparable.
- Deduplicate by application ID for application outcomes and by candidate ID only for explicitly candidate-level measures. One candidate applying to multiple jobs can legitimately produce multiple applications.
- Document qualification rules and attribution model/version on reports and exports.

## Idea 32 — Forecasting & Hiring Demand Planning

- Keep forecast runs and outputs separate from source recruitment records.
- Each run records model/version, creation time, historical input window, planned-demand assumptions, target period, filters, uncertainty interval and warnings.
- Start with a transparent baseline before introducing a learned model.
- Forecast vacancy demand, application/interview workload and expected hiring timelines separately; state which records support each forecast.
- Compare forecast with actuals for the same target period and cohort. Report error only when actuals are available and sample size is meaningful.
- Warn when history is sparse, data quality fails validation, the input period is too short or patterns drift. Forecasts are estimates, not guaranteed outcomes.
- Adjusted assumptions create a new versioned run; they do not overwrite historical results.

## Idea 33 — Custom Reports & Scheduled Exports

- Report definitions contain allowlisted fields, metrics, filters, groupings and sort keys. Validate identifiers and operators server-side; never execute user-provided SQL.
- Reuse the same metric definitions and permission checks as dashboards. Calculations must be reproducible for a saved definition and parameter set.
- Saved reports are organisation-scoped. Sharing is explicit and limited to users with current access.
- Every scheduled execution re-checks the owner's membership, role, row-level permissions and report-field permissions. Revoked access prevents delivery.
- Run large exports asynchronously. Persist status, requester, definition version, row count, creation/expiry timestamps and failure reason. Avoid storing CV text or unnecessary sensitive data in export metadata.
- Download URLs expire and are authorised at retrieval time; an unguessable URL alone is not permission control.
- Apply configurable row/size limits, retention and audit logging.

## Dependencies and implementation order

1. Validate schema, RLS policies, lifecycle events and current API permissions.
2. Reconcile stage-history records against application status transitions and offers/requisitions.
3. Add missing immutable event timestamps or tenant-safe constraints in a reviewed migration.
4. Implement parameterised reporting services and edge-case fixtures.
5. Reconcile each metric against source rows before adding dashboard visualisations.
6. Add workload/reassignment history and source-attribution improvements where existing data is insufficient.
7. Add versioned forecast runs, then report definitions, asynchronous exports and scheduled permission rechecks.
8. Run unit, integration, cross-tenant, permission, performance and UI acceptance checks in staging before production release.

## Staging schema provenance audit (2026-10-25)

A read-only check of the connected staging database confirmed that the analytics dependencies below exist and have row-level security enabled: `application_stage_history`, `job_requisitions`, `recruiter_tasks`, `recruitment_campaigns`, `campaign_channels`, and `campaign_memberships`. The inspected policies scope reads to organisation members; the stage-history insert policy also constrains the actor, and requisition/task policies validate related organisation membership.

**Release blocker:** the current repository migration tree does not contain creation migrations for several of these tables (including stage history, requisitions, recruiter tasks and campaign tables). Staging therefore cannot be reproduced from the committed migration history alone. Do not infer that production has the same objects or policies from staging existence. Recover and review the authoritative migrations or create reconciled, idempotent migrations from a schema diff before release. No staging writes or schema changes were made during this audit.

The staging analytics tables also contain no recruitment/campaign rows suitable for metric-level numerical reconciliation. Keep the numerical acceptance gate open until deterministic synthetic fixtures can be run in an isolated test database or a dedicated non-production tenant.

## Known schema gaps to validate before implementation

- Stage history stores transition timestamps, but not explicit stage-entry/exit intervals. Derive visits from ordered events only after checking initial-stage semantics.
- Applications have current status, created_at and updated_at; these are not a complete substitute for lifecycle events.
- Jobs expose opened_at, closed_at, recruiter_id and hiring_manager_id; verify access and ownership before team reporting.
- Requisitions expose approved_at and job_id; validate the approval-to-job relationship and reopened/converted requisition behaviour.
- Offers expose status, sent_at and responded_at; validate transitions and multiple offers per application.
- Source and campaign tables exist, but raw events, qualification semantics, attribution links and comparable cost data must be verified before ROI reporting.
- Persistence for forecast runs, saved reports, exports and scheduled delivery has not yet been confirmed.

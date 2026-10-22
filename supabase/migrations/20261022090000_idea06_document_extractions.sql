-- Idea 06: CV extraction processing state.
-- Machine-generated data is stored separately from recruiter-confirmed candidate fields.
create table if not exists public.document_extractions (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null,
    document_id uuid not null references public.candidate_documents(id) on delete cascade,
    candidate_id uuid not null references public.candidates(id) on delete cascade,
    status text not null default 'queued'
        check (status in ('queued', 'processing', 'review_required', 'confirmed', 'failed')),
    parser_version text not null default 'aqerith-cv-parser-v1',
    attempt_count integer not null default 0 check (attempt_count >= 0),
    extraction_data jsonb not null default '{}'::jsonb,
    field_confidence jsonb not null default '{}'::jsonb,
    provenance jsonb not null default '{}'::jsonb,
    errors jsonb not null default '[]'::jsonb,
    requested_by uuid,
    started_at timestamptz,
    completed_at timestamptz,
    confirmed_at timestamptz,
    confirmed_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, document_id)
);
create index if not exists document_extractions_org_status_idx
    on public.document_extractions (organization_id, status, updated_at desc);
create index if not exists document_extractions_candidate_idx
    on public.document_extractions (organization_id, candidate_id, created_at desc);

comment on table public.document_extractions is
    'Machine-generated CV extraction. Never treat these values as recruiter-confirmed candidate profile data.';

alter table public.candidate_documents
  add column if not exists preview_text text;

comment on column public.candidate_documents.preview_text is
  'Cached extracted text for authorised DOCX previews; never expose without document access checks.';

-- Trigger-only guard functions must not be callable as public PostgREST RPC endpoints.
-- Triggers execute these functions without granting direct invocation to API roles.
revoke all on function public.enforce_privacy_request_transitions() from public, anon, authenticated;
revoke all on function public.validate_section8_tenant_integrity() from public, anon, authenticated;

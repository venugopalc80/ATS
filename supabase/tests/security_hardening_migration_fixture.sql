-- Disposable PostgreSQL fixture for the production RLS hardening migration.
-- Run only in an isolated CI database. No Supabase project is used.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN CREATE ROLE service_role NOLOGIN; END IF;
END
$$;

CREATE SCHEMA IF NOT EXISTS auth;
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;

CREATE TABLE public.applications (id uuid PRIMARY KEY, organization_id uuid NOT NULL, status text);
CREATE TABLE public.audit_events (
  id bigserial PRIMARY KEY, organization_id uuid, actor_user_id uuid,
  action text, entity_type text, entity_id uuid, metadata jsonb
);
CREATE TABLE public.candidates (id uuid PRIMARY KEY, organization_id uuid NOT NULL);
CREATE TABLE public.clients (id uuid PRIMARY KEY, organization_id uuid NOT NULL);
CREATE TABLE public.interviews (id uuid PRIMARY KEY, organization_id uuid NOT NULL, status text);
CREATE TABLE public.job_distribution_channels (id uuid PRIMARY KEY, organization_id uuid NOT NULL);
CREATE TABLE public.jobs (id uuid PRIMARY KEY, organization_id uuid NOT NULL);
CREATE TABLE public.organization_members (organization_id uuid NOT NULL, user_id uuid NOT NULL);
CREATE TABLE public.organizations (id uuid PRIMARY KEY);
CREATE TABLE public.offers (id uuid PRIMARY KEY, organization_id uuid NOT NULL, status text);
CREATE TABLE public.placements (id uuid PRIMARY KEY, organization_id uuid NOT NULL, status text);
CREATE TABLE public.profiles (id uuid PRIMARY KEY);
CREATE TABLE public.application_stage_history (id uuid PRIMARY KEY, organization_id uuid NOT NULL);

CREATE OR REPLACE FUNCTION public.audit_workflow_status_change()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE actor_id uuid;
  entity_type_value text;
BEGIN
  actor_id := NULL;
  entity_type_value := CASE TG_TABLE_NAME
    WHEN 'applications' THEN 'application'
    WHEN 'interviews' THEN 'interview'
    WHEN 'offers' THEN 'offer'
    WHEN 'placements' THEN 'placement'
    ELSE TG_TABLE_NAME
  END;
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    INSERT INTO public.audit_events(organization_id, actor_user_id, action, entity_type, entity_id, metadata)
    VALUES (NEW.organization_id, actor_id, TG_TABLE_NAME || '.status_changed',
      entity_type_value, NEW.id, jsonb_build_object('from', OLD.status, 'to', NEW.status));
  END IF;
  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION public.capture_record_change()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE org_id uuid;
  row_id uuid;
  actor_id uuid;
  old_data jsonb;
  new_data jsonb;
BEGIN
  IF TG_OP = 'DELETE' THEN
    old_data := to_jsonb(OLD); new_data := '{}'::jsonb;
    org_id := (old_data ->> 'organization_id')::uuid;
    row_id := (old_data ->> 'id')::uuid;
  ELSE
    old_data := CASE WHEN TG_OP = 'INSERT' THEN '{}'::jsonb ELSE to_jsonb(OLD) END;
    new_data := to_jsonb(NEW);
    org_id := (new_data ->> 'organization_id')::uuid;
    row_id := (new_data ->> 'id')::uuid;
  END IF;
  INSERT INTO public.audit_events(organization_id, actor_user_id, action, entity_type, entity_id, metadata)
  VALUES (org_id, actor_id, lower(TG_OP), TG_TABLE_NAME, row_id,
    jsonb_build_object('changed_fields', jsonb_build_object('snapshot', new_data)));
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION public.rls_auto_enable()
RETURNS event_trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE cmd record;
BEGIN
  FOR cmd IN
    SELECT * FROM pg_event_trigger_ddl_commands()
    WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
      AND object_type IN ('table', 'partitioned table')
  LOOP
    IF cmd.schema_name = 'public' THEN
      EXECUTE format('ALTER TABLE IF EXISTS %s ENABLE ROW LEVEL SECURITY', cmd.object_identity);
    END IF;
  END LOOP;
END
$$;

CREATE OR REPLACE FUNCTION public.is_org_member(target_org uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.organization_members m
    WHERE m.organization_id = target_org AND m.user_id = auth.uid())
$$;

GRANT EXECUTE ON FUNCTION public.audit_workflow_status_change() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.capture_record_change() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.rls_auto_enable() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.is_org_member(uuid) TO anon, authenticated, service_role;

CREATE POLICY applications_member_all ON public.applications FOR ALL TO public USING (true) WITH CHECK (true);
CREATE POLICY audit_member_read ON public.audit_events FOR SELECT TO public USING (true);
CREATE POLICY candidates_member_all ON public.candidates FOR ALL TO public USING (true) WITH CHECK (true);
CREATE POLICY clients_member_all ON public.clients FOR ALL TO public USING (true) WITH CHECK (true);
CREATE POLICY interviews_member_all ON public.interviews FOR ALL TO public USING (true) WITH CHECK (true);
CREATE POLICY job_distribution_member_read ON public.job_distribution_channels FOR SELECT TO public USING (true);
CREATE POLICY job_distribution_member_write ON public.job_distribution_channels FOR INSERT TO public WITH CHECK (true);
CREATE POLICY jobs_member_all ON public.jobs FOR ALL TO public USING (true) WITH CHECK (true);
CREATE POLICY memberships_member_read ON public.organization_members FOR SELECT TO public USING (true);
CREATE POLICY organizations_member_read ON public.organizations FOR SELECT TO public USING (true);
CREATE POLICY offers_member_all ON public.offers FOR ALL TO public USING (true) WITH CHECK (true);
CREATE POLICY placements_member_all ON public.placements FOR ALL TO public USING (true) WITH CHECK (true);
CREATE POLICY profiles_self_read ON public.profiles FOR SELECT TO public USING (true);
CREATE POLICY application_stage_history_member_insert ON public.application_stage_history FOR INSERT TO public WITH CHECK (true);
CREATE POLICY application_stage_history_member_read ON public.application_stage_history FOR SELECT TO public USING (true);

ALTER TABLE public.applications ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE ON public.applications TO authenticated;

CREATE TRIGGER applications_record_history
AFTER INSERT OR UPDATE OR DELETE ON public.applications
FOR EACH ROW EXECUTE FUNCTION public.capture_record_change();
CREATE TRIGGER applications_status_audit
BEFORE UPDATE OF status ON public.applications
FOR EACH ROW EXECUTE FUNCTION public.audit_workflow_status_change();

CREATE EVENT TRIGGER auto_enable_public_rls
ON ddl_command_end EXECUTE FUNCTION public.rls_auto_enable();

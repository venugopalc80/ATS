"""Disposable-PostgreSQL smoke tests for the Idea 04 migrations.

Set TEST_DATABASE_URL only for a disposable database named aqerith_migration_test.
This test resets that database's schemas before running the real migration files.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from uuid import UUID

import psycopg


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = [
    ROOT / "supabase" / "migrations" / "20261026150000_application_stage_history.sql",
    ROOT / "supabase" / "migrations" / "20261026150100_application_stage_config.sql",
]
ACTOR = "22222222-2222-4222-8222-222222222222"
ACTOR_UUID = UUID(ACTOR)
ORG = "11111111-1111-4111-8111-111111111111"
JOB = "33333333-3333-4333-8333-333333333333"
CANDIDATE = "66666666-6666-4666-8666-666666666666"
JOB2 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
CANDIDATE2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
APPLICATION = "77777777-7777-4777-8777-777777777777"
NEW_ORG = "88888888-8888-4888-8888-888888888888"


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "requires disposable PostgreSQL TEST_DATABASE_URL")
class ApplicationStageMigrationSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=False)
        with cls.connection.cursor() as cursor:
            cursor.execute("select current_database()")
            database_name = cursor.fetchone()[0]
            if database_name != "aqerith_migration_test":
                cls.connection.close()
                raise RuntimeError(
                    "Refusing to reset schemas: TEST_DATABASE_URL must point to "
                    "the disposable aqerith_migration_test database"
                )
            cursor.execute("drop schema if exists private cascade")
            cursor.execute("drop schema if exists auth cascade")
            cursor.execute("drop schema public cascade")
            cursor.execute("create schema public")
            cursor.execute("create schema auth")
            cursor.execute("create extension if not exists pgcrypto")
            cursor.execute("""
                do $$
                begin
                  if not exists (select 1 from pg_roles where rolname = 'anon') then
                    create role anon nologin;
                  end if;
                  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
                    create role authenticated nologin;
                  end if;
                end $$;
            """)
            cursor.execute("create table auth.users (id uuid primary key)")
            cursor.execute("""
                create function auth.uid() returns uuid
                language sql stable
                as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
            """)
            cursor.execute("""
                create table public.organizations (
                  id uuid primary key,
                  name text not null,
                  country_code text not null check (country_code in ('GB','US','IN','AU'))
                )
            """)
            cursor.execute("""
                create table public.profiles (
                  id uuid primary key references auth.users(id) on delete cascade
                )
            """)
            cursor.execute("""
                create table public.organization_members (
                  organization_id uuid not null references public.organizations(id) on delete cascade,
                  user_id uuid not null references public.profiles(id) on delete cascade,
                  role text not null,
                  primary key (organization_id, user_id)
                )
            """)
            cursor.execute("""
                create function public.is_org_member(target_org uuid) returns boolean
                language sql stable security definer set search_path = public
                as $$
                  select exists (
                    select 1 from public.organization_members m
                    where m.organization_id = target_org and m.user_id = auth.uid()
                  )
                $$;
            """)
            cursor.execute("""
                create table public.jobs (
                  id uuid primary key,
                  organization_id uuid not null references public.organizations(id) on delete cascade
                )
            """)
            cursor.execute("""
                create table public.candidates (
                  id uuid primary key,
                  organization_id uuid not null references public.organizations(id) on delete cascade
                )
            """)
            cursor.execute("""
                create table public.applications (
                  id uuid primary key,
                  organization_id uuid not null references public.organizations(id) on delete cascade,
                  job_id uuid not null references public.jobs(id) on delete cascade,
                  candidate_id uuid not null references public.candidates(id) on delete cascade,
                  source text,
                  status text not null default 'new'
                    check (status in ('new','screening','submitted','interview','offer','hired','rejected','withdrawn')),
                  created_at timestamptz not null default now(),
                  updated_at timestamptz not null default now(),
                  unique(job_id, candidate_id)
                )
            """)
            cursor.execute(
                "insert into auth.users(id) values (%s)", (ACTOR,)
            )
            cursor.execute(
                "insert into public.profiles(id) values (%s)", (ACTOR,)
            )
            cursor.execute(
                "insert into public.organizations(id,name,country_code) values (%s,'Existing tenant','GB')",
                (ORG,),
            )
            cursor.execute(
                "insert into public.organization_members(organization_id,user_id,role) values (%s,%s,'admin')",
                (ORG, ACTOR),
            )
            cursor.execute(
                "insert into public.jobs(id,organization_id) values (%s,%s)", (JOB, ORG)
            )
            cursor.execute(
                "insert into public.candidates(id,organization_id) values (%s,%s)",
                (CANDIDATE, ORG),
            )
            cursor.execute(
                "insert into public.jobs(id,organization_id) values (%s,%s)", (JOB2, ORG)
            )
            cursor.execute(
                "insert into public.candidates(id,organization_id) values (%s,%s)",
                (CANDIDATE2, ORG),
            )
            # Simulate an application that predates migration 014, for baseline backfill.
            cursor.execute(
                "insert into public.applications(id,organization_id,job_id,candidate_id,status) "
                "values (%s,%s,%s,%s,'new')",
                (APPLICATION, ORG, JOB, CANDIDATE),
            )
        cls.connection.commit()

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def run_migrations(self):
        with self.connection.cursor() as cursor:
            for migration in MIGRATIONS:
                cursor.execute(migration.read_text(encoding="utf-8"), prepare=False)
                self.connection.commit()

    def test_migrations_are_rerunnable_and_history_and_seeding_work(self):
        # Apply to a clean database, deliberately remove one trigger and one seeded row,
        # then rerun to verify that partial-state repair is safe as well as idempotent.
        self.run_migrations()
        with self.connection.cursor() as cursor:
            cursor.execute("drop trigger applications_stage_history_update on public.applications")
            cursor.execute(
                "delete from public.application_stage_config where organization_id=%s and stage_key='screening'",
                (ORG,),
            )
        self.connection.commit()
        self.run_migrations()

        with self.connection.cursor() as cursor:
            cursor.execute(
                "select previous_stage,new_stage,actor_user_id,reason "
                "from public.application_stage_history where application_id=%s",
                (APPLICATION,),
            )
            baseline = cursor.fetchone()
            self.assertEqual(baseline, (None, "new", None, "migration_baseline"))

            # Existing tenant is seeded and a tenant created after migration is seeded by trigger.
            cursor.execute(
                "select count(*) from public.application_stage_config where organization_id=%s",
                (ORG,),
            )
            self.assertEqual(cursor.fetchone()[0], 10)
            cursor.execute(
                "insert into public.organizations(id,name,country_code) values (%s,'New tenant','US')",
                (NEW_ORG,),
            )
            cursor.execute(
                "select count(*) from public.application_stage_config where organization_id=%s",
                (NEW_ORG,),
            )
            self.assertEqual(cursor.fetchone()[0], 10)

            # A newly inserted application records the authenticated backend actor.
            cursor.execute("select set_config('app.actor_user_id', %s, true)", (ACTOR,))
            cursor.execute(
                "insert into public.applications(id,organization_id,job_id,candidate_id,status) "
                "values (%s,%s,%s,%s,'new')",
                ("99999999-9999-4999-8999-999999999999", ORG, JOB2, CANDIDATE2),
            )
            cursor.execute(
                "select new_stage,actor_user_id,reason from public.application_stage_history "
                "where application_id=%s",
                ("99999999-9999-4999-8999-999999999999",),
            )
            self.assertEqual(cursor.fetchone(), ("new", ACTOR_UUID, "application_created"))

            # A transition records both actor and reason.
            cursor.execute("select set_config('app.transition_reason', %s, true)", ("CV reviewed",))
            cursor.execute(
                "update public.applications set status='screening',updated_at=now() where id=%s",
                ("99999999-9999-4999-8999-999999999999",),
            )
            cursor.execute(
                "select previous_stage,new_stage,actor_user_id,reason from public.application_stage_history "
                "where application_id=%s and reason=%s",
                ("99999999-9999-4999-8999-999999999999", "CV reviewed"),
            )
            self.assertEqual(cursor.fetchone(), ("new", "screening", ACTOR_UUID, "CV reviewed"))

            # Browser roles have no direct table privileges; RLS is enabled as defence in depth.
            for table in ("application_stage_history", "application_stage_config"):
                cursor.execute(
                    "select has_table_privilege('anon', %s, 'select'), "
                    "has_table_privilege('authenticated', %s, 'select'), "
                    "(select relrowsecurity from pg_class where oid=%s::regclass)",
                    (f"public.{table}", f"public.{table}", f"public.{table}"),
                )
                anon_select, authenticated_select, rls_enabled = cursor.fetchone()
                self.assertFalse(anon_select, f"anon unexpectedly has SELECT on {table}")
                self.assertFalse(authenticated_select, f"authenticated unexpectedly has SELECT on {table}")
                self.assertTrue(rls_enabled, f"RLS is not enabled on {table}")
        self.connection.commit()


if __name__ == "__main__":
    unittest.main()

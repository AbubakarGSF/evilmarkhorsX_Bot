-- Evil Markhors Bot - Supabase schema
-- Run this in the Supabase SQL editor before starting the bot.
-- The bot must use the service_role key: RLS is enabled and the anon key
-- cannot read or write accounts.
--
-- Ye script idempotent hai - dobara chala sakte hain.

create table if not exists accounts (
  id bigserial primary key,
  owner bigint,
  username text not null unique,
  x_id text,
  -- Default isliye ki partial upsert (sirf status/last_check) 23502 na de:
  -- Postgres NOT NULL ko ON CONFLICT resolution se pehle check karta hai.
  cookies jsonb not null default '{}'::jsonb,
  country text,
  yr text,
  followers int default 0,
  protected boolean default false,
  verified boolean default false,
  status text default 'live',
  fails int default 0,
  source text,
  created_at timestamptz default now(),
  last_check timestamptz,
  last_ok timestamptz,
  last_post timestamptz
);

-- Purane table par bhi defaults lagao (migration).
alter table accounts alter column cookies set default '{}'::jsonb;
alter table accounts alter column status set default 'live';
alter table accounts alter column followers set default 0;
alter table accounts alter column protected set default false;
alter table accounts alter column verified set default false;
alter table accounts alter column fails set default 0;

create index if not exists accounts_status_idx on accounts (status);
create index if not exists accounts_country_idx on accounts (country);
create index if not exists accounts_check_idx on accounts (last_check);
create index if not exists accounts_owner_idx on accounts (owner);

alter table accounts enable row level security;

-- service_role RLS bypass karta hai; grant phir bhi rakho.
grant all on accounts to service_role;
grant usage, select on sequence accounts_id_seq to service_role;

-- Policies: pehle drop, phir create (dobara run par error na aaye).
drop policy if exists "Allow insert for authenticated" on accounts;
create policy "Allow insert for authenticated"
on accounts for insert
to authenticated
with check (true);

drop policy if exists "Allow select for authenticated" on accounts;
create policy "Allow select for authenticated"
on accounts for select
to authenticated
using (true);

drop policy if exists "Allow update for authenticated" on accounts;
create policy "Allow update for authenticated"
on accounts for update
to authenticated
using (true);

drop policy if exists "Allow delete for service_role" on accounts;
create policy "Allow delete for service_role"
on accounts for delete
to service_role
using (true);

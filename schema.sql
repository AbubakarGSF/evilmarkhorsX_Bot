-- Evil Markhors Bot - Supabase schema
-- Run this in the Supabase SQL editor before starting the bot.
-- The bot must use the service_role key: RLS is enabled
-- and no policies are defined, so the anon key cannot read or write.

create table if not exists accounts (
  id bigserial primary key,
  owner bigint,
  username text not null unique,
  x_id text,
  cookies jsonb not null,
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

create index if not exists accounts_status_idx on accounts (status);
create index if not exists accounts_country_idx on accounts (country);
create index if not exists accounts_check_idx on accounts (last_check);
create index if not exists accounts_owner_idx on accounts (owner);

alter table accounts enable row level security;

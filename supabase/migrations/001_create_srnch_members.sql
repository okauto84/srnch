-- srnch_members: 회원 명단
-- Supabase SQL Editor 또는 `supabase db push` 로 실행

create extension if not exists "pgcrypto";

create table if not exists public.srnch_members (
    id uuid primary key default gen_random_uuid(),
    name text not null,                          -- 이름
    gender text,                                 -- 성별
    organization text,                           -- 조직
    birth_date date,                             -- 생년월일
    mobile text,                                 -- 휴대전화
    household_head text,                         -- 세대주
    relationship_to_head text,                   -- 세대주와의 관계
    address text,                                -- 주소
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

comment on table public.srnch_members is '회원 명단';
comment on column public.srnch_members.name is '이름';
comment on column public.srnch_members.gender is '성별';
comment on column public.srnch_members.organization is '조직';
comment on column public.srnch_members.birth_date is '생년월일';
comment on column public.srnch_members.mobile is '휴대전화';
comment on column public.srnch_members.household_head is '세대주';
comment on column public.srnch_members.relationship_to_head is '세대주와의 관계';
comment on column public.srnch_members.address is '주소';

create index if not exists idx_srnch_members_name
    on public.srnch_members (name);

create index if not exists idx_srnch_members_organization
    on public.srnch_members (organization);

create index if not exists idx_srnch_members_household_head
    on public.srnch_members (household_head);

create or replace function public.set_srnch_members_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_srnch_members_updated_at on public.srnch_members;
create trigger trg_srnch_members_updated_at
    before update on public.srnch_members
    for each row
    execute function public.set_srnch_members_updated_at();

alter table public.srnch_members enable row level security;

-- 인증된 사용자 전체 CRUD (필요 시 정책 조정)
drop policy if exists "srnch_members_select_authenticated" on public.srnch_members;
create policy "srnch_members_select_authenticated"
    on public.srnch_members
    for select
    to authenticated
    using (true);

drop policy if exists "srnch_members_insert_authenticated" on public.srnch_members;
create policy "srnch_members_insert_authenticated"
    on public.srnch_members
    for insert
    to authenticated
    with check (true);

drop policy if exists "srnch_members_update_authenticated" on public.srnch_members;
create policy "srnch_members_update_authenticated"
    on public.srnch_members
    for update
    to authenticated
    using (true)
    with check (true);

drop policy if exists "srnch_members_delete_authenticated" on public.srnch_members;
create policy "srnch_members_delete_authenticated"
    on public.srnch_members
    for delete
    to authenticated
    using (true);

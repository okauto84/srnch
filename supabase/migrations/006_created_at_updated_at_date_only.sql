-- created_at, updated_at 는 연-월-일만 저장한다. 시간은 두지 않는다.
-- Supabase SQL Editor에서 실행한다.

-- srnch_teacher
alter table public.srnch_teacher
    alter column created_at drop default,
    alter column updated_at drop default;

alter table public.srnch_teacher
    alter column created_at type date using created_at::date,
    alter column updated_at type date using updated_at::date;

alter table public.srnch_teacher
    alter column created_at set default current_date,
    alter column updated_at set default current_date;

create or replace function public.set_srnch_teacher_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = current_date;
    return new;
end;
$$;

-- srnch_members
alter table public.srnch_members
    add column if not exists created_at date,
    add column if not exists updated_at date;

alter table public.srnch_members
    alter column created_at drop default,
    alter column updated_at drop default;

alter table public.srnch_members
    alter column created_at type date using created_at::date,
    alter column updated_at type date using updated_at::date;

update public.srnch_members
set created_at = coalesce(created_at, current_date),
    updated_at = coalesce(updated_at, current_date)
where created_at is null
   or updated_at is null;

alter table public.srnch_members
    alter column created_at set default current_date,
    alter column updated_at set default current_date,
    alter column created_at set not null,
    alter column updated_at set not null;

comment on column public.srnch_teacher.created_at is '생성일 (연-월-일)';
comment on column public.srnch_teacher.updated_at is '수정일 (연-월-일)';
comment on column public.srnch_members.created_at is '생성일 (연-월-일)';
comment on column public.srnch_members.updated_at is '수정일 (연-월-일)';

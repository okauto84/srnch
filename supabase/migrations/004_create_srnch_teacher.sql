-- srnch_teacher 최초 생성
-- 기존 테이블과 데이터를 삭제한 뒤 다시 만든다.
-- 한 행은 "해당 연도에 이 담임이 이 반을 담당한다"이다.
-- 학생은 저장하지 않는다. srnch_members.children_group_div 로 조인한다.
--
-- select m.*, t.teacher_name
-- from public.srnch_members m
-- join public.srnch_teacher t
--   on t.children_group_div = m.children_group_div
--  and t.year = 2026;

drop table if exists public.srnch_teacher cascade;

create table public.srnch_teacher (
    year integer not null,                          -- 연도
    teacher_name text not null,                     -- 담임 선생님 이름
    children_group_div text not null,               -- 담당 부-학년-반
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint srnch_teacher_pkey
        primary key (year, teacher_name, children_group_div),
    constraint srnch_teacher_year_chk
        check (year between 2000 and 2100),
    constraint srnch_teacher_teacher_name_chk
        check (char_length(btrim(teacher_name)) > 0),
    constraint srnch_teacher_children_group_div_chk
        check (children_group_div ~ '^[0-9]+-[0-9]+-[0-9]+$')
);

comment on table public.srnch_teacher is '연도별 담임과 담당 반. 학생은 srnch_members.children_group_div 로 조인한다.';
comment on column public.srnch_teacher.year is '연도';
comment on column public.srnch_teacher.teacher_name is '담임 선생님 이름';
comment on column public.srnch_teacher.children_group_div is '담당 부-학년-반. srnch_members.children_group_div 와 동일 (예: 1-2-5)';

create or replace function public.set_srnch_teacher_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_srnch_teacher_updated_at on public.srnch_teacher;
create trigger trg_srnch_teacher_updated_at
    before update on public.srnch_teacher
    for each row
    execute function public.set_srnch_teacher_updated_at();

alter table public.srnch_teacher enable row level security;

drop policy if exists srnch_teacher_select_authenticated on public.srnch_teacher;
create policy srnch_teacher_select_authenticated
    on public.srnch_teacher
    for select
    to authenticated
    using (true);

drop policy if exists srnch_teacher_insert_authenticated on public.srnch_teacher;
create policy srnch_teacher_insert_authenticated
    on public.srnch_teacher
    for insert
    to authenticated
    with check (true);

drop policy if exists srnch_teacher_update_authenticated on public.srnch_teacher;
create policy srnch_teacher_update_authenticated
    on public.srnch_teacher
    for update
    to authenticated
    using (true)
    with check (true);

drop policy if exists srnch_teacher_delete_authenticated on public.srnch_teacher;
create policy srnch_teacher_delete_authenticated
    on public.srnch_teacher
    for delete
    to authenticated
    using (true);

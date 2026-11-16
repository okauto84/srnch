-- srnch_teacher: 연도별 담임-학생 배정
-- 한 행은 "해당 연도에 이 학생을 이 담임, 이 반에 배정"이다.
-- Supabase SQL Editor에서 실행한다.
--
-- 학생 키는 srnch_members.id (디모데 교인 ID, bigint)이다.
-- 담당 반은 srnch_members.children_group_div 와 같은 형식(1-2-5)이지만
-- 연도별 배정이므로 회원 테이블의 현재 조직 값을 복사만 하고, 그 컬럼을 FK로 두지 않는다.

create table if not exists public.srnch_teacher (
    id bigint generated always as identity primary key,
    year integer not null,                          -- 연도
    teacher_name text not null,                     -- 담임 선생님 이름
    class_div text not null,                        -- 담당 부-학년-반
    member_id bigint not null,                      -- 학생 ID
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint srnch_teacher_year_chk
        check (year between 2000 and 2100),
    constraint srnch_teacher_teacher_name_chk
        check (char_length(btrim(teacher_name)) > 0),
    constraint srnch_teacher_class_div_chk
        check (class_div ~ '^[0-9]+-[0-9]+-[0-9]+$'),
    constraint srnch_teacher_year_member_key
        unique (year, member_id),
    constraint srnch_teacher_member_id_fkey
        foreign key (member_id)
        references public.srnch_members (id)
        on update cascade
        on delete restrict
);

comment on table public.srnch_teacher is '연도별 담임 선생님과 학생 배정';
comment on column public.srnch_teacher.year is '연도';
comment on column public.srnch_teacher.teacher_name is '담임 선생님 이름';
comment on column public.srnch_teacher.class_div is '담당 부-학년-반 (예: 1-2-5)';
comment on column public.srnch_teacher.member_id is '학생 ID. srnch_members.id';

create index if not exists srnch_teacher_year_class_idx
    on public.srnch_teacher (year, class_div);

create index if not exists srnch_teacher_year_teacher_idx
    on public.srnch_teacher (year, teacher_name);

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

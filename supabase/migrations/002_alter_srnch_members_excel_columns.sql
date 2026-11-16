-- srnch_members: 교인 엑셀 컬럼 기준으로 재구성
-- 기존 테이블이 있으면 삭제 후 재생성합니다.

drop trigger if exists trg_srnch_members_updated_at on public.srnch_members;
drop table if exists public.srnch_members;

create table public.srnch_members (
    id bigint primary key,                       -- id (디모데 교인 ID)
    name text not null,                          -- 이름
    name_distinct text,                          -- 구분자
    children_group text,                         -- 어린이
    children_group_div text,                     -- 어린이 정규화 (부-학년-반)
    member_type1 text,                           -- 교인 구분1
    member_type2 text,                           -- 교인 구분2
    birth_date date,                             -- 생년월일
    age integer,                                 -- 나이
    mobile text,                                 -- 휴대전화
    gender text,                                 -- 성별
    spouse_duty text,                            -- 배우자 직분
    household_head text,                         -- 세대주
    relationship_to_head text,                   -- 세대주와 관계
    jibeon_address text,                         -- 지번주소
    duty1 text,                                  -- 직분1
    duty2 text,                                  -- 직분2
    family text,                                 -- 가족
    registered_at timestamptz,                   -- 등록일
    last_updated_at timestamptz,                 -- 최근업데이트일
    last_visit_at date,                          -- 최근심방일
    last_attendance_at date,                     -- 최근출석일
    last_offering_at date,                       -- 최근헌금일
    welcome_at date,                             -- 환영일
    spouse_mobile text,                          -- 배우자 연락처
    leader1 text,                                -- 인도자1
    leader1_duty1 text,                          -- 인도자1 직분1
    leader1_duty2 text,                          -- 인도자1 직분2
    leader1_mobile text,                         -- 인도자1 휴대전화
    leader1_children_group text,                 -- 인도자1어린이Group
    leader2 text,                                -- 인도자2
    leader2_duty1 text,                          -- 인도자2 직분1
    leader2_duty2 text,                          -- 인도자2 직분2
    leader2_mobile text,                         -- 인도자2 휴대전화
    leader2_children_group text,                 -- 인도자2어린이Group
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

comment on table public.srnch_members is '회원 명단 (교인 엑셀 컬럼 기준)';
comment on column public.srnch_members.id is 'id';
comment on column public.srnch_members.name is '이름';
comment on column public.srnch_members.name_distinct is '구분자';
comment on column public.srnch_members.children_group is '어린이';
comment on column public.srnch_members.children_group_div is '어린이 정규화 (부-학년-반)';
comment on column public.srnch_members.member_type1 is '교인 구분1';
comment on column public.srnch_members.member_type2 is '교인 구분2';
comment on column public.srnch_members.birth_date is '생년월일';
comment on column public.srnch_members.age is '나이';
comment on column public.srnch_members.mobile is '휴대전화';
comment on column public.srnch_members.gender is '성별';
comment on column public.srnch_members.spouse_duty is '배우자 직분';
comment on column public.srnch_members.household_head is '세대주';
comment on column public.srnch_members.relationship_to_head is '세대주와 관계';
comment on column public.srnch_members.jibeon_address is '지번주소';
comment on column public.srnch_members.duty1 is '직분1';
comment on column public.srnch_members.duty2 is '직분2';
comment on column public.srnch_members.family is '가족';
comment on column public.srnch_members.registered_at is '등록일';
comment on column public.srnch_members.last_updated_at is '최근업데이트일';
comment on column public.srnch_members.last_visit_at is '최근심방일';
comment on column public.srnch_members.last_attendance_at is '최근출석일';
comment on column public.srnch_members.last_offering_at is '최근헌금일';
comment on column public.srnch_members.welcome_at is '환영일';
comment on column public.srnch_members.spouse_mobile is '배우자 연락처';
comment on column public.srnch_members.leader1 is '인도자1';
comment on column public.srnch_members.leader1_duty1 is '인도자1 직분1';
comment on column public.srnch_members.leader1_duty2 is '인도자1 직분2';
comment on column public.srnch_members.leader1_mobile is '인도자1 휴대전화';
comment on column public.srnch_members.leader1_children_group is '인도자1어린이Group';
comment on column public.srnch_members.leader2 is '인도자2';
comment on column public.srnch_members.leader2_duty1 is '인도자2 직분1';
comment on column public.srnch_members.leader2_duty2 is '인도자2 직분2';
comment on column public.srnch_members.leader2_mobile is '인도자2 휴대전화';
comment on column public.srnch_members.leader2_children_group is '인도자2어린이Group';

create index if not exists idx_srnch_members_name
    on public.srnch_members (name);

create index if not exists idx_srnch_members_children_group
    on public.srnch_members (children_group);

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

create trigger trg_srnch_members_updated_at
    before update on public.srnch_members
    for each row
    execute function public.set_srnch_members_updated_at();

alter table public.srnch_members enable row level security;

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

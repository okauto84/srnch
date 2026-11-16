-- 이미 002를 적용한 경우 children_group 옆에 정규화 컬럼만 추가

alter table public.srnch_members
    add column if not exists children_group_div text;

comment on column public.srnch_members.children_group_div is '어린이 정규화 (부-학년-반)';

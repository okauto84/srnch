-- srnch_teacher에 담임 연락처, 주소를 추가한다.
-- 기존 행은 값을 비워 둔다. Supabase SQL Editor에서 실행한다.

alter table public.srnch_teacher
    add column if not exists phone text,
    add column if not exists address text;

comment on column public.srnch_teacher.phone is '연락처';
comment on column public.srnch_teacher.address is '주소';

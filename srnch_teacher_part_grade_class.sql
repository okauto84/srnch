-- srnch_teacher.children_group_div 를 part, grade, class 로 나눈다.
-- 1-2-5 => part=1, grade=2, class=5
-- 2-2-11 => part=2, grade=2, class=11
-- 다시 실행해도 컬럼이 이미 나뉘어 있으면 추가로 지우거나 덮어쓰지 않는다.

BEGIN;

ALTER TABLE srnch_teacher
  ADD COLUMN IF NOT EXISTS part integer,
  ADD COLUMN IF NOT EXISTS grade integer,
  ADD COLUMN IF NOT EXISTS class integer;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'srnch_teacher'
      AND column_name = 'children_group_div'
  ) THEN
    EXECUTE $sql$
      UPDATE srnch_teacher
      SET
        part = split_part(children_group_div, '-', 1)::int,
        grade = split_part(children_group_div, '-', 2)::int,
        class = split_part(children_group_div, '-', 3)::int
      WHERE children_group_div ~ '^[0-9]+-[0-9]+-[0-9]+$'
    $sql$;

    EXECUTE 'ALTER TABLE srnch_teacher DROP COLUMN children_group_div';
  END IF;
END $$;

COMMIT;

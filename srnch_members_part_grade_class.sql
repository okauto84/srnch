-- srnch_members.children_group_div 를 part, grade, class 로 나눈다.
-- 03. 유년-유년2부-2학년-11반 => part=2, grade=2, class=11
-- 03. 유년-유년1부-1학년-5반  => part=1, grade=1, class=5
-- 기존 children_group_div(예: 2-2-11)가 있으면 그 값을 우선 옮긴다.
-- 다시 실행해도 컬럼이 이미 나뉘어 있으면 추가로 지우거나 덮어쓰지 않는다.

BEGIN;

ALTER TABLE srnch_members
  ADD COLUMN IF NOT EXISTS part integer,
  ADD COLUMN IF NOT EXISTS grade integer,
  ADD COLUMN IF NOT EXISTS class integer;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'srnch_members'
      AND column_name = 'children_group_div'
  ) THEN
    EXECUTE $sql$
      UPDATE srnch_members
      SET
        part = split_part(children_group_div, '-', 1)::int,
        grade = split_part(children_group_div, '-', 2)::int,
        class = split_part(children_group_div, '-', 3)::int
      WHERE children_group_div ~ '^[0-9]+-[0-9]+-[0-9]+$'
    $sql$;

    EXECUTE $sql$
      UPDATE srnch_members
      SET
        part = COALESCE(
          part,
          (regexp_match(children_group, '(?:유년|유치)\s*([0-9]+)\s*부'))[1]::int
        ),
        grade = COALESCE(
          grade,
          (regexp_match(children_group, '([0-9]+)\s*학년'))[1]::int,
          CASE WHEN children_group ~ '믿음' THEN 1 END
        ),
        class = COALESCE(
          class,
          (regexp_match(children_group, '([0-9]+)\s*반'))[1]::int
        )
      WHERE children_group IS NOT NULL
        AND (part IS NULL OR grade IS NULL OR class IS NULL)
    $sql$;

    EXECUTE 'ALTER TABLE srnch_members DROP COLUMN children_group_div';
  END IF;
END $$;

COMMIT;

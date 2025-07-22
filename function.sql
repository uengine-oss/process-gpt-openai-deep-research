-- 1) 대기중인 작업 조회 및 상태 변경
CREATE OR REPLACE FUNCTION public.api_fetch_pending_task(
  p_limit    integer,
  p_consumer text
)
RETURNS SETOF todolist AS $$
BEGIN
  RETURN QUERY
    WITH cte AS (
      SELECT *
        FROM todolist
       WHERE status = 'IN_PROGRESS' AND agent_orch = 'openai'
         AND (
           (agent_mode IN ('DRAFT','COMPLETE') AND draft IS NULL AND draft_status IS NULL)
           OR draft_status = 'FB_REQUESTED'
         )
       ORDER BY start_date
       LIMIT p_limit
       FOR UPDATE SKIP LOCKED
    ), upd AS (
      UPDATE todolist
         SET draft_status = 'STARTED',
             consumer     = p_consumer
        FROM cte
       WHERE todolist.id = cte.id
       RETURNING todolist.*
    )
    SELECT * FROM upd;
END;
$$ LANGUAGE plpgsql VOLATILE;

-- 2) 완료된 데이터(output/feedback) 조회
CREATE OR REPLACE FUNCTION public.api_fetch_done_data(
  p_proc_inst_id text
)
RETURNS TABLE (
  output   jsonb,
  feedback jsonb
)
LANGUAGE SQL
AS $$
  SELECT t.output, t.feedback
    FROM todolist AS t
   WHERE t.proc_inst_id = p_proc_inst_id
     AND (
       (t.status = 'DONE'        AND t.output   IS NOT NULL)
       OR
       (t.status = 'IN_PROGRESS' AND t.feedback IS NOT NULL)
     )
   ORDER BY t.start_date
$$;

-- 3) 결과 저장 (중간/최종)
CREATE OR REPLACE FUNCTION public.api_save_task_result(
  p_todo_id uuid,
  p_payload jsonb,
  p_final   boolean
)
RETURNS void AS $$
DECLARE
  v_mode text;
BEGIN
  SELECT agent_mode
    INTO v_mode
    FROM todolist
   WHERE id = p_todo_id;

  IF p_final THEN
    IF v_mode = 'COMPLETE' THEN
      UPDATE todolist
         SET output       = p_payload,
             draft        = p_payload,
             status       = 'SUBMITTED',
             draft_status = 'COMPLETED',
             consumer     = NULL
       WHERE id = p_todo_id;
    ELSE
      UPDATE todolist
         SET draft        = p_payload,
             draft_status = 'COMPLETED',
             consumer     = NULL
       WHERE id = p_todo_id;
    END IF;
  ELSE
    UPDATE todolist
       SET draft = p_payload
     WHERE id = p_todo_id;
  END IF;
END;
$$ LANGUAGE plpgsql VOLATILE;

-- 익명(anon) 역할에 실행 권한 부여
GRANT EXECUTE ON FUNCTION public.api_fetch_pending_task(integer, text) TO anon;
GRANT EXECUTE ON FUNCTION public.api_fetch_done_data(text) TO anon;
GRANT EXECUTE ON FUNCTION public.api_save_task_result(uuid, jsonb, boolean) TO anon;

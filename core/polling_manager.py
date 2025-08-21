import asyncio
import logging
import json
import os
import sys
import traceback
from typing import Optional, Dict
from research.prompt_executor import summarize_async
from core.database import (
    initialize_db,
    fetch_pending_task,
    fetch_done_data,
    fetch_task_status,
    fetch_participants_info,
    fetch_form_types,
    update_task_completed,
    update_task_error
)
from utils.event_logger import EventLogger
from utils.logger import handle_error, log

# ============================================================================
# 설정 및 초기화
# ============================================================================

logger = logging.getLogger(__name__)

# 글로벌 상태
current_todo_id: Optional[int] = None
current_process: Optional[asyncio.subprocess.Process] = None
worker_terminated_by_us: bool = False

def initialize_connections():
    """데이터베이스 연결 초기화"""
    try:
        initialize_db()
        log("✅ 연결 초기화 완료")
    except Exception as e:
        # 서버 기동 시 DB 초기화 실패는 fail-fast
        from utils.logger import handle_error
        handle_error("초기화", e, raise_error=True)

 

# ============================================================================
# 작업 처리 메인 로직
# ============================================================================

async def process_new_task(row: Dict):
    """새 작업 처리"""
    global current_process, worker_terminated_by_us, current_todo_id
    
    current_todo_id = row['id']
    todo_id = row['id']
    proc_inst_id = row.get('proc_inst_id')
    
    try:
        log(f"🆕 새 작업 처리 시작: id={todo_id}, proc_inst_id={proc_inst_id}")
        inputs = await _prepare_task_inputs(row)
        await _execute_worker_process(inputs, todo_id)
    except Exception as e:
        await update_task_error(todo_id)
        handle_error("작업준비실패", e, raise_error=True)
        
    finally:
        # 글로벌 상태 초기화
        current_process = None
        worker_terminated_by_us = False
        current_todo_id = None

async def _prepare_task_inputs(row: Dict) -> Dict:
    """작업 입력 데이터 준비"""
    todo_id = row['id']
    proc_inst_id = row.get('proc_inst_id')
    
    # 이전 컨텍스트 데이터 조회 (output만)
    done_outputs = await fetch_done_data(proc_inst_id)
    api_key = os.getenv("OPENAI_API_KEY")
    
    # 작업 타입에 따른 요약 처리
    if row.get('task_type') == 'FB_REQUESTED':
        current_feedback = row.get('feedback')
        current_content = row.get('draft') or row.get('output')
        output_summary, feedback_summary = await summarize_async(done_outputs, current_feedback, current_content, api_key)
    else:
        output_summary, feedback_summary = await summarize_async(done_outputs, None, None, api_key)
    
    # 사용자 및 폼 정보 조회
    user_info_list, _ = await fetch_participants_info(row.get('user_id', ''))
    proc_form_id, form_types, form_html = await fetch_form_types(
        tool_val=row.get('tool', ''),
        tenant_id=row['tenant_id']
    )
    
    return {
        "todo_id": todo_id,
        "proc_inst_id": proc_inst_id,
        "topic": row.get('activity_name', ''),
        "previous_outputs": output_summary,
        "previous_feedback": feedback_summary,
        "user_info": (user_info_list or []),
        "form_types": form_types,
        "proc_form_id": proc_form_id,
        "form_html": form_html,
    }

# ============================================================================
# 워커 프로세스 관리
# ============================================================================

async def _execute_worker_process(inputs: Dict, todo_id: int):
    """워커 프로세스 실행 및 관리"""
    global current_process, worker_terminated_by_us
    
    try:
        # 워커 프로세스 시작
        worker_terminated_by_us = False
        current_process = await asyncio.create_subprocess_exec(
            sys.executable,
            os.path.join(os.path.dirname(__file__), "worker.py"),
            "--inputs", json.dumps(inputs, ensure_ascii=False),
        )
        
        # 취소 상태 감시 및 워커 대기
        watch_task = asyncio.create_task(_watch_cancel_status())
        log(f"✅ 워커 시작 (PID={current_process.pid})")
        
        # 워커 프로세스 완료 대기
        await current_process.wait()
        if not watch_task.done():
            watch_task.cancel()

        if worker_terminated_by_us:
            log(f"🛑 워커 사용자 중단됨 (PID={current_process.pid})")
            return

        if current_process.returncode != 0:
            # 워커 비정상 종료는 해당 작업만 실패 - 비치명적(폴링 계속)
            handle_error("워커비정상종료", Exception(f"returncode={current_process.returncode}"), raise_error=False, extra={"todo_id": todo_id})
            await update_task_error(todo_id)
            return

        ev_logger = EventLogger()
        ev_logger.emit_event(
            event_type="crew_completed",
            data={},
            job_id="CREW_FINISHED",
            crew_type="crew",
            todo_id=todo_id,
            proc_inst_id=inputs.get("proc_inst_id")
        )
        log(f"✅ 워커 정상 종료 (PID={current_process.pid})")
        await update_task_completed(todo_id)
        
    except Exception as e:
        await update_task_error(todo_id)
        handle_error("워커실행실패", e, raise_error=True)

def _log_worker_result():
    """워커 종료 결과 로그"""
    if worker_terminated_by_us:
        log(f"🛑 워커 사용자 중단됨 (PID={current_process.pid})")
    elif current_process.returncode != 0:  
        log(f"❌ 워커 비정상 종료 (code={current_process.returncode})")
    else:
        log(f"✅ 워커 정상 종료 (PID={current_process.pid})")

async def _watch_cancel_status():
    """워커 취소 상태 감시"""
    global current_todo_id, current_process, worker_terminated_by_us
    
    todo_id = current_todo_id
    if todo_id is None:
        return
    
    # 주기적으로 취소 상태 확인
    while current_process and current_process.returncode is None and not worker_terminated_by_us:
        await asyncio.sleep(5)
        try:
            draft_status = await fetch_task_status(todo_id)
            if draft_status in ('CANCELLED', 'FB_REQUESTED'):
                log(f"🛑 draft_status={draft_status} 감지 (id={todo_id}) → 워커 종료")
                terminate_current_worker()
                break
        except Exception as e:
            handle_error("취소감시오류", e, raise_error=False)

def terminate_current_worker():
    """현재 실행 중인 워커 프로세스 종료"""
    global current_process, worker_terminated_by_us
    
    if current_process and current_process.returncode is None:
        worker_terminated_by_us = True
        current_process.terminate()
        log(f"✅ 워커 프로세스 종료 시그널 전송 (PID={current_process.pid})")
    else:
        log("⚠️ 종료할 워커 프로세스가 없습니다.")

# ============================================================================
# 폴링 실행
# ============================================================================

async def start_todolist_polling(interval: int = 7):
    """새 작업 처리 폴링 시작"""
    log("🚀 TodoList 폴링 시작")
    
    while True:
        try:
            log("todolist 폴링 시도")
            row = await fetch_pending_task()
            if row:
                await process_new_task(row)
        except Exception as e:
            handle_error("폴링오류", e, raise_error=False)

        await asyncio.sleep(interval)
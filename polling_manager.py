import asyncio
import logging
import json
import os
import sys
import traceback
from typing import Optional, Dict
from prompt_executor import generate_summary
from database import (
    initialize_db, 
    fetch_pending_task, 
    fetch_done_data, 
    fetch_task_status,
    fetch_participants_info,
    fetch_form_types
)

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
        logger.info("✅ 연결 초기화 완료")
    except Exception as e:
        logger.error(f"❌ 초기화 실패: {str(e)}")
        logger.error(f"상세 정보: {traceback.format_exc()}")
        raise

def _handle_error(operation: str, error: Exception) -> None:
    """통합 에러 처리"""
    error_msg = f"❌ [{operation}] 오류 발생: {str(error)}"
    logger.error(error_msg)
    logger.error(f"상세 정보: {traceback.format_exc()}")
    raise Exception(f"{operation} 실패: {error}")

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
        logger.info(f"🆕 새 작업 처리 시작: id={todo_id}, proc_inst_id={proc_inst_id}")
        
        # 작업 데이터 준비 및 워커 실행
        inputs = await _prepare_task_inputs(row)
        await _execute_worker_process(inputs, todo_id)
        
    except Exception as e:
        _handle_error("작업처리", e)
        
    finally:
        # 글로벌 상태 초기화
        current_process = None
        worker_terminated_by_us = False
        current_todo_id = None

async def _prepare_task_inputs(row: Dict) -> Dict:
    """작업 입력 데이터 준비"""
    todo_id = row['id']
    proc_inst_id = row.get('proc_inst_id')
    
    # 이전 컨텍스트 요약 (prompt_executor 사용)
    done_outputs, done_feedbacks = await fetch_done_data(proc_inst_id)
    api_key = os.getenv("OPENAI_API_KEY")
    context_summary = generate_summary(done_outputs, done_feedbacks, api_key) if done_outputs or done_feedbacks else ""
    
    # 사용자 및 폼 정보 조회
    participants = await fetch_participants_info(row.get('user_id', ''))
    proc_form_id, form_types = await fetch_form_types(row.get('tool', ''))
    
    return {
        "todo_id": todo_id,
        "proc_inst_id": proc_inst_id,
        "topic": row.get('activity_name', ''),
        "previous_context": context_summary,
        "user_info": participants.get('user_info', []),
        "form_types": form_types,
        "proc_form_id": proc_form_id,
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
        logger.info(f"✅ 워커 시작 (PID={current_process.pid})")
        
        await current_process.wait()
        if not watch_task.done():
            watch_task.cancel()
        
        # 종료 결과 로그
        _log_worker_result()
        
    except Exception as e:
        _handle_error("워커실행", e)

def _log_worker_result():
    """워커 종료 결과 로그"""
    if worker_terminated_by_us:
        logger.info(f"🛑 워커 사용자 중단됨 (PID={current_process.pid})")
    elif current_process.returncode != 0:
        logger.error(f"❌ 워커 비정상 종료 (code={current_process.returncode})")
    else:
        logger.info(f"✅ 워커 정상 종료 (PID={current_process.pid})")

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
                logger.info(f"🛑 draft_status={draft_status} 감지 (id={todo_id}) → 워커 종료")
                terminate_current_worker()
                break
        except Exception as e:
            logger.error(f"❌ 취소 상태 조회 실패 (id={todo_id}): {str(e)}")

def terminate_current_worker():
    """현재 실행 중인 워커 프로세스 종료"""
    global current_process, worker_terminated_by_us
    
    if current_process and current_process.returncode is None:
        worker_terminated_by_us = True
        current_process.terminate()
        logger.info(f"✅ 워커 프로세스 종료 시그널 전송 (PID={current_process.pid})")
    else:
        logger.warning("⚠️ 종료할 워커 프로세스가 없습니다.")

# ============================================================================
# 폴링 실행
# ============================================================================

async def start_todolist_polling(interval: int = 7):
    """새 작업 처리 폴링 시작"""
    logger.info("🚀 TodoList 폴링 시작")
    
    while True:
        try:
            row = await fetch_pending_task()
            if row:
                print("디버깅 row 정보", row)
                await process_new_task(row)
                
        except Exception as e:
            logger.error(f"❌ 폴링 실행 실패: {str(e)}")
            logger.error(f"상세 정보: {traceback.format_exc()}")
            
        await asyncio.sleep(interval)
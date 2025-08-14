import os
import uuid
import json
from datetime import datetime, timezone
from typing import Any, Dict
import logging

from dotenv import load_dotenv
from core.database import initialize_db, get_db_client
from utils.logger import handle_error, log

load_dotenv()
logger = logging.getLogger(__name__)


class EventLogger:
    """Supabase 이벤트 로깅 시스템"""

    def __init__(self):
        """이벤트 로거 초기화 및 DB 연결 보장"""
        try:
            initialize_db()
            logger.info("🎯 Event Logger 초기화 완료")
        except Exception as e:
            handle_error("EventLogger초기화", e, raise_error=True)

    def _sanitize_data(self, data: Any) -> Any:
        """NULL 문자 제거 및 데이터 정리"""
        if isinstance(data, str):
            return data.replace('\u0000', '').replace('\x00', '')
        elif isinstance(data, dict):
            return {k: self._sanitize_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._sanitize_data(item) for item in data]
        else:
            return data

    def emit_event(self, event_type: str, data: Dict[str, Any], job_id: str = None, crew_type: str = None, todo_id: str = None, proc_inst_id: str = None) -> None:
        """커스텀 이벤트 발행 (비치명)"""
        try:
            supabase_client = get_db_client()
            event_record = {
                "id": str(uuid.uuid4()),
                "job_id": job_id or str(uuid.uuid4()),
                "todo_id": todo_id,
                "proc_inst_id": proc_inst_id,
                "event_type": event_type,
                "crew_type": crew_type,
                "data": self._sanitize_data(data),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            supabase_client.table("events").insert(event_record).execute()
            job_display = (job_id or "unknown")[:8]
            log(f"[{event_type}] [{crew_type or 'N/A'}] {job_display} → Supabase: ✅")
        except Exception as e:
            handle_error("이벤트발행", e, raise_error=True, extra={"event_type": event_type, "crew_type": crew_type})
            log(f"[{event_type}] → Supabase: ❌")


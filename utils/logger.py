import traceback
from datetime import datetime
from typing import Optional, Dict, Any


def _ts() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"


def log(message: str, *, context: Optional[Dict[str, Any]] = None) -> None:
    prefix = f"📝 [{_ts()}]"
    if context:
        print(f"{prefix} {message} | {context}", flush=True)
    else:
        print(f"{prefix} {message}", flush=True)


def handle_error(operation: str, error: Exception, raise_error: bool = True, extra: Optional[Dict[str, Any]] = None) -> None:
    prefix = f"❌ [{_ts()}] [{operation}]"
    print(f"{prefix} 오류: {error}", flush=True)
    if extra:
        print(f"🔎 컨텍스트: {extra}", flush=True)
    print(f"📄 스택:\n{traceback.format_exc()}", flush=True)
    if raise_error:
        raise Exception(f"{operation} 실패: {error}")


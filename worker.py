#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import sys
import asyncio

# 현재 디렉토리를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from multi_format_flow import PromptMultiFormatFlow
from database import initialize_db

async def main_async(inputs: dict):
    """
    1) PromptMultiFormatFlow 인스턴스 생성
    2) inputs를 flow.state에 세팅
    3) kickoff_async 호출 (Flow 내부에서 중간·최종 결과 저장 및 DB 반영)
    """
    # DB 설정 초기화
    initialize_db()
    # Flow 실행 준비
    flow = PromptMultiFormatFlow()
    for k, v in inputs.items():
        setattr(flow.state, k, v)

    # Flow 실행 → 내부에서 save_context 및 DB 업데이트까지 처리
    await flow.kickoff_async()

def main():
    # 1) 커맨드라인 인자로 전달된 JSON 파싱
    parser = argparse.ArgumentParser(description="Run PromptMultiFormatFlow in a subprocess")
    parser.add_argument(
        "--inputs",
        required=True,
        help="JSON-encoded inputs for the flow (e.g. '{\"todo_id\":123, \"proc_inst_id\":\"abc\"}')"
    )
    args = parser.parse_args()
    inputs = json.loads(args.inputs)

    # 2) 워커 실행
    asyncio.run(main_async(inputs))

if __name__ == "__main__":
    main()

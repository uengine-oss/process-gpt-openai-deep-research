#!/usr/bin/env python3
import os
import asyncio
import openai
from datetime import datetime

# 0) 환경 변수 & 클라이언트 초기화
openai.api_key = os.getenv("OPENAI_API_KEY", "")
if not openai.api_key:
    raise RuntimeError("ERROR: OPENAI_API_KEY를 설정하세요.")

# 비동기 OpenAI 클라이언트 생성 (타임아웃을 길게 설정하여 긴 작업에 대비)
client = openai.AsyncOpenAI(api_key=openai.api_key, timeout=600.0)

# 1) 섹션 정의 (제목과 프롬프트 쌍의 리스트)
sections = [
    ("시장 동향 분석", "시장 동향 분석에 대한 심층 리서치 결과를 작성하세요."),
    ("결론 및 제안",  "전체 요약 및 최종 제안을 작성하세요.")
]

# 2) 도구 설정 (예: 웹 검색, 코드 실행 등)
tools = [
    {"type": "web_search_preview"},
    {"type": "code_interpreter", "container": {"type": "auto"}}
]

# 3) 이벤트 저장소 (task_id별 이벤트 리스트 저장)
events_store: dict[int, list[dict]] = {}

async def run_stream(task_id: int, title: str, prompt: str):
    """주어진 프롬프트에 대해 Deep Research API를 스트리밍으로 호출하고 이벤트를 처리"""
    events_store[task_id] = []
    print(f"\n=== Task {task_id} 시작: {title} ===")
    try:
        # 3-1) Deep Research API 호출 (백그라운드 + 스트리밍 모드)
        stream = await client.responses.create(
            model="o3-deep-research",     # Deep Research 전용 모델
            input=[
                {"role": "system", "content": [
                    {"type": "input_text", "text": "You are a research assistant."}
                ]},
                {"role": "user", "content": [
                    {"type": "input_text", "text": prompt}
                ]}
            ],
            tools=tools,
            reasoning={"summary": "auto"},  # 자동 요약 난이도
            store=True,     # 배경 모드에서는 상태 저장 필요 (기본값 True)
            # background=True,
            stream=True
        )

        # 3-2) 스트림 이벤트 처리 루프
        async for event in stream:
            # 이벤트 타입에 따라 다른 처리
            if event.type == "response.tool_start":
                # 도구 사용 시작 이벤트
                tool_name = getattr(event, "tool", None) or "unknown_tool"
                print(f"[{task_id}] 🔧 Tool 시작 → {tool_name}")
            elif event.type in ("response.tool_response", "response.tool_output"):
                # 도구 호출 결과 이벤트
                output_data = getattr(event, "output", None)
                snippet = str(output_data)[:100].replace("\n", " ") if output_data else ""
                print(f"[{task_id}] 📥 Tool 응답 → {snippet}")
            elif event.type == "response.output_text.delta":
                # 최종 보고서 텍스트의 부분 출력 (스트리밍된 토큰)
                delta_text = getattr(event, "delta", "")
                print(delta_text, end="", flush=True)
            elif event.type == "response.message_end":
                # 최종 메시지 완료 이벤트
                print(f"\n[{task_id}] ✅ 완료: '{title}' 응답 생성 끝")
            elif event.type == "response.error":
                # 오류 이벤트
                error_msg = getattr(event, "message", None) or getattr(event, "error", None) or "Unknown Error"
                print(f"[{task_id}] ❌ Error 발생: {error_msg}")
            else:
                # 기타 이벤트 (예: 중간 reasoning 단계 등)
                print(f"[{task_id}] 📌 이벤트: {event.type}")

            # 이벤트 세부 정보를 저장 (타임스탬프 포함)
            event_record = {
                "time": datetime.utcnow().isoformat(),
                "type": event.type
            }
            # 주요 속성들 추가 저장 (delta/output/tool 등 필요한 경우)
            if hasattr(event, "delta") and event.type == "response.output_text.delta":
                event_record["delta"] = event.delta
            if hasattr(event, "output") and output_data:
                event_record["output"] = str(output_data)
            if hasattr(event, "tool"):
                event_record["tool"] = getattr(event, "tool", None)
            if hasattr(event, "message"):
                event_record["message"] = getattr(event, "message", None)
            events_store[task_id].append(event_record)

    except Exception as e:
        print(f"[{task_id}] ❌ Exception 발생: {e}")
    finally:
        # 3-3) 스트림 닫기
        try:
            await stream.aclose()
        except:
            pass
        # 완료 로그 및 이벤트 개수 출력
        count = len(events_store.get(task_id, []))
        print(f"[{task_id}] '{title}' 완료, 이벤트 수집: {count}개")
        return task_id, title  # 태스크 결과 반환

async def main():
    # 4) 병렬 실행: 정의된 섹션별로 run_stream 태스크 생성
    tasks = [
        asyncio.create_task(run_stream(i+1, title, prompt))
        for i, (title, prompt) in enumerate(sections)
    ]
    results = await asyncio.gather(*tasks)

    # 5) 각 태스크의 이벤트 히스토리 출력
    for task_id, title in results:
        print(f"\n=== Task {task_id}: '{title}' 이벤트 히스토리 ===")
        for e in events_store.get(task_id, []):
            print(e)

# 스크립트 진입점
if __name__ == "__main__":
    asyncio.run(main())

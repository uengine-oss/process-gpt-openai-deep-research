#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import sys
from dotenv import load_dotenv
from typing import Optional
from event_logger import EventLogger
import openai

# UTF-8 강제 설정 (한글 깨짐 방지)
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

load_dotenv()

# 비동기 OpenAI 클라이언트 초기화
client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=600.0)

# 사용할 툴 설정: preview 웹 검색 + 코드 인터프리터
tools = [
    {"type": "web_search_preview"},
    # {"type": "code_interpreter", "container": {"type": "auto"}}
]

# 본문 출력 최소 단위
CHAR_THRESHOLD = 1000

async def execute_research_section(section_info: dict, topic: str = "", previous_context: str = "", event_logger: Optional[EventLogger] = None, todo_id: Optional[str] = None, proc_inst_id: Optional[str] = None, job_id: Optional[str] = None):
    """
    개별 섹션에 대한 리서치를 실행하는 함수
    
    Args:
        section_info: 섹션 정보 (number, title, subsections 등)
        topic: 주제
        previous_context: 이전 컨텍스트
        event_logger: EventLogger instance for logging events
        todo_id: Todo ID for logging events
        proc_inst_id: Process Instance ID for logging events
        job_id: Job ID for logging events
    
    Returns:
        str: 리서치 결과 텍스트
    """
    title = section_info.get("title", "섹션")
    number = section_info.get("number", "")
    subsections = section_info.get("subsections", [])
    
    print(f"\n=== 섹션 리서치 시작: {number}. {title} ===")
    buffer = ""
    full_text = ""

    # 하위 섹션 정보 구성 (기존 로직 유지)
    subsection_structure = ""
    if subsections:
        subsection_structure = "\n\n하위 섹션들:\n"
        for sub in subsections:
            sub_number = sub.get("number", "")
            sub_title = sub.get("title", "")
            subsection_structure += f"- {sub_number}. {sub_title}\n"

    # 적당한 수준의 상세 프롬프트
    combined_prompt = f"""
당신은 해당 분야의 전문가로서 섹션 '{title}'에 대한 전문적이고 심층적인 리서치 보고서를 작성해야 합니다.

**📋 섹션 정보:**
- 섹션 번호: {number}
- 섹션 제목: {title}{subsection_structure}

**🔍 이전 컨텍스트 분석:**
{previous_context}

다음 단계에 따라 이전 컨텍스트를 철저히 분석하세요:
1. **요구사항 파악**: 전체 프로젝트의 목적과 구체적 요구사항 확인
2. **이전 보고서 내용 요약**: 앞선 섹션들에서 다룬 핵심 내용과 결론 파악
3. **피드백 우선 반영**: 사용자 피드백이 있다면 최우선으로 반영 (재요청 의미), 없으면 무시하고 진행
4. **문맥 흐름 유지**: 전체 보고서의 논리적 일관성과 연결성 확보

**📊 작업 지침:**

**1. 섹션 역할 파악 및 맞춤 내용 작성**
현재 섹션 '{title}'이 전체 보고서에서 담당하는 역할을 분석하고 그에 맞는 내용을 작성하세요:

- **개요/서론/배경** → 주제 소개, 배경 설명, 연구 목적, 범위 정의
- **이론/개념** → 핵심 개념 정의, 이론적 배경, 기본 원리, 연구 동향
- **분석/방법론** → 구체적 분석, 방법론 설명, 발견사항, 실증 자료
- **적용/실무** → 실무 적용 방안, 실행 계획, 구체적 사례, 체크리스트
- **결론/제언** → 연구 결과 종합, 핵심 시사점, 정책 제언, 향후 과제

**2. 이전 컨텍스트 반영**
- 이전 컨텍스트의 요구사항, 피드백, 목적을 철저히 분석하여 반영
- 전체 프로젝트의 목표와 방향성을 현재 섹션에 일관되게 유지
- 이전 단계에서 제기된 문제점이나 개선사항을 적극적으로 고려

**3. 내용 구성 원칙**
- **심층성**: 표면적 설명이 아닌 전문가 수준의 심층 분석
- **실무성**: 바로 활용 가능한 구체적 사례와 예시 포함
- **완성도**: 도구 검색 결과가 부족해도 문맥 흐름을 파악하여 창의적으로 완성된 내용 작성
- **차별화**: 다른 섹션과 중복되지 않는 해당 섹션만의 고유한 가치 제공

**4. 품질 기준**
- **분량**: 최소 3,000-4,000단어 이상의 상세하고 전문적인 내용
- **구조**: 체계적인 논리 흐름과 명확한 구성
- **근거**: 업계 표준, 모범 사례, 관련 법규 등 신뢰할 수 있는 근거 제시

**📝 출력 형식:**
- **마크다운 형식**: ## 대제목, ### 중제목, #### 소제목
- **강조 표현**: **강조**, *기울임*, - 리스트, > 인용구
- **출처 표기**: 참고한 정보나 문서의 출처를 명확히 표기
- **표와 차트**: 필요시 마크다운 테이블 형식으로 정보 정리

**🔧 도구 사용 지침:**
- **제한적 사용**: web_search_preview 툴은 정말 필요한 경우에만 사용
- **사용 예시**: 최신 동향, 최근 통계, 새로운 법규/정책 등 시의성이 중요한 정보
- **사용 금지**: 일반적 개념 설명, 기본 이론, 상식적 내용은 검색하지 말고 기존 지식 활용
- **최소 호출**: 툴 호출 횟수를 최소화하고 꼭 필요한 정보만 검색 (최대 5회 이내)

**⚠️ 필수 준수사항:**
1. 섹션 '{title}'의 역할에 최적화된 전문적 내용 작성
2. 이전 컨텍스트의 피드백과 요구사항을 반드시 반영
3. 해당 섹션만의 고유한 가치를 제공하는 차별화된 내용 구성
4. 완성도 높은 보고서 (도구 호출을 최소화하고, 도구 결과 부족해도 창의적으로 문맥 파악하여 완성)
5. 툴 사용 횟수 최소화 (최대 5회 이내)


위 지침에 따라 섹션 '{title}'에 대한 전문적이고 포괄적인 리서치 보고서를 작성해주세요.
""".strip()

    # 스트리밍 요청
    stream = await client.responses.create(
        model="o3-deep-research",   # Deep Research 전용 모델
        input=[                                # messages → input 으로 변경
            {
              "role":"system",
              "content":[{"type":"input_text","text":"You are a professional research expert who creates high-quality, comprehensive reports. Key principles: 1) Thoroughly analyze previous context (requirements, feedback, prior content) and maintain logical flow, 2) Prioritize user feedback when present (indicates dissatisfaction with previous results), 3) Use web_search_preview tool sparingly - only for truly essential information like recent trends, latest statistics, new regulations - avoid for general concepts or basic theories, 4) Create complete, professional reports through creative context understanding even with minimal tool usage, 5) Provide unique value specific to each section while maintaining overall report coherence."}]
            },
            {
              "role":"user",
              "content":[{"type":"input_text","text":combined_prompt}]
            }
        ],
        tools=tools,
        store=True,
        background=False,
        stream=True,
        reasoning={"summary": "auto"}
    )

    try:
        async for evt in stream:
            et = evt.type

            # # 1) 추론 파트 완료만
            # if et == "response.reasoning_summary_part.done":
            #     print(f"[{number}] 📋 추론 이벤트 정보: {evt}")
            #     part = evt.part
            #     text = getattr(part, "text", "")
            #     print(f"[{number}] 🤔 추론 파트 완료:\n{text}\n")

            #     event_logger.emit_event(
            #         event_type="reason_done",
            #         data={},
            #         job_id=f"api_{job_id}",
            #         crew_type="reason",
            #         todo_id=todo_id,
            #         proc_inst_id=proc_inst_id
            #     )

            # 2) 툴 호출 시작 및 파라미터 (output_item.added)
            if et == "response.output_item.added" and hasattr(evt, "item") and evt.item.type.endswith("_call"):
                print(f"[{number}] 📋 툴 시작 이벤트 정보: {evt}")
                tool_name = evt.item.type
                params = getattr(evt.item, "action", None) or getattr(evt.item, "arguments", None)
                print(f"[{number}] 🔧 Tool 시작 → {tool_name}, params={params}")

                event_logger.emit_event(
                    event_type="tool_usage_started",
                    data={"tool_name": tool_name},
                    job_id=job_id,
                    crew_type="report",
                    todo_id=todo_id,
                    proc_inst_id=proc_inst_id
                )

            # 3) 툴 호출 완료 및 결과 (output_item.done)
            elif et == "response.output_item.done" and hasattr(evt, "item") and evt.item.type.endswith("_call"):
                print(f"[{number}] 📋 툴 완료 이벤트 정보: {evt}")
                tool_name = evt.item.type
                # result = getattr(evt.item, "outputs", None) or getattr(evt.item, "action", None)
                action = getattr(evt.item, "action", {}) or {}
                action_type = getattr(action, "type", "")
                
                if action_type == "search" or action_type == "search:web_search_preview":
                    value = getattr(action, "query", "")
                    verb = "검색"
                elif action_type == "open_page":
                    value = getattr(action, "url", "")
                    verb = "접속"
                elif action_type == "find_in_page":
                    value = getattr(action, "url", "")
                    verb = "찾기"
                else:
                    try:
                        value = json.dumps(action, ensure_ascii=False, default=str)
                    except:
                        value = str(action)
                    verb = "실행"

                info = f"{verb}: {value}"

                print(f"[{number}] ✅ Tool 완료 → {tool_name}, info={info}")

                # 간단한 null byte 체크
                if '\u0000' in info or '\x00' in info:
                    print(f"[{number}] ⚠️ null byte 감지 → 이벤트 스킵")
                else:
                    event_logger.emit_event(
                        event_type="tool_usage_finished",
                        data={
                            "tool_name": tool_name,
                            "info":      info
                        },
                        job_id=job_id,
                        crew_type="report",
                        todo_id=todo_id,
                        proc_inst_id=proc_inst_id
                    )

            # 4) 본문 스트리밍 청크
            elif et == "response.output_text.delta":
                print(f"[{number}] 📋 본문 스트리밍 청크 이벤트 정보: {evt}")
                # delta 이벤트에서 스트리밍된 텍스트를 직접 가져오기
                delta = getattr(evt, "delta", "")
                buffer += delta
                full_text += delta
                if len(buffer) >= CHAR_THRESHOLD:
                    print(f"[{number}] 📄 본문 (버퍼 {CHAR_THRESHOLD}자):\n{buffer}")
                    buffer = ""

            # 그 외 이벤트는 무시

        # 남은 버퍼 출력
        if buffer:
            print(f"[{number}] 📄 본문 (마지막):\n{buffer}")

        # 최종 본문 전체 출력
        print(f"[{number}] 📢 최종 결과:\n{full_text}")
        return full_text

    finally:
        await stream.close()

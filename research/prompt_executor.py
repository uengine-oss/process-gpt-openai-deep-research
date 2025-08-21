from openai import OpenAI, AsyncOpenAI
import json
import asyncio
import logging
import random
import time
from typing import Any, Callable
from utils.logger import handle_error, log
from .prompt import (
    create_execution_plan_prompt,
    create_slide_generation_prompt,
    create_text_form_generation_prompt,
    create_toc_prompt,
    create_output_summary_prompt,
    create_feedback_summary_prompt
)

# ============================================================================
# 기본 설정
# ============================================================================

logger = logging.getLogger(__name__)

# ============================================================================
# 동기 함수들 - 기존 호환성 유지
# ============================================================================

def generate_execution_plan(form_types: list, user_info: list, openai_api_key: str, model: str = "gpt-4o-mini") -> str:
    prompt = create_execution_plan_prompt(form_types, user_info)
    client = OpenAI(api_key=openai_api_key)

    def _once() -> str:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return response.choices[0].message.content.strip()

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            return _once()
        except Exception as e:
            last_error = e
            jitter = random.uniform(0, 0.3)
            delay = 0.8 * (2 ** (attempt - 1)) + jitter
            handle_error(f"실행계획 OpenAI 재시도 {attempt}/3", e, raise_error=False, extra={"delay": round(delay, 2), "model": model})
            time.sleep(delay)
    handle_error("실행계획 OpenAI 최종실패", last_error or Exception("unknown"), raise_error=True)
    return '{"execution_plan": {"report_phase": {"forms": []}, "slide_phase": {"forms": []}, "text_phase": {"forms": []}}}'


def generate_slide_from_report(report_content: str, user_info: list, openai_api_key: str, model: str = "gpt-4o-mini", previous_outputs_summary: str = "", feedback_summary: str = "") -> str:
    prompt = create_slide_generation_prompt(report_content, user_info, previous_outputs_summary, feedback_summary)
    client = OpenAI(api_key=openai_api_key)

    def _once() -> str:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return response.choices[0].message.content.strip()

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            return _once()
        except Exception as e:
            last_error = e
            jitter = random.uniform(0, 0.3)
            delay = 0.8 * (2 ** (attempt - 1)) + jitter
            handle_error(f"슬라이드 OpenAI 재시도 {attempt}/3", e, raise_error=False, extra={"delay": round(delay, 2), "model": model})
            time.sleep(delay)
    handle_error("슬라이드 OpenAI 최종실패", last_error or Exception("unknown"), raise_error=True)
    return ""


def generate_text_form_values(report_content: str, topic: str, text_forms: list, user_info: list, openai_api_key: str, model: str = "gpt-4o-mini", previous_outputs_summary: str = "", feedback_summary: str = "", form_html: str = "") -> str:
    prompt = create_text_form_generation_prompt(report_content, topic, text_forms, user_info, previous_outputs_summary, feedback_summary, form_html)
    client = OpenAI(api_key=openai_api_key)

    def _once() -> str:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return response.choices[0].message.content.strip()

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            return _once()
        except Exception as e:
            last_error = e
            jitter = random.uniform(0, 0.3)
            delay = 0.8 * (2 ** (attempt - 1)) + jitter
            handle_error(f"텍스트폼 OpenAI 재시도 {attempt}/3", e, raise_error=False, extra={"delay": round(delay, 2), "model": model})
            time.sleep(delay)
    handle_error("텍스트폼 OpenAI 최종실패", last_error or Exception("unknown"), raise_error=True)
    return "{}"

def generate_toc(previous_outputs_summary: str = "", feedback_summary: str = "", user_info: list | None = None, openai_api_key: str = "", model: str = "gpt-4o-mini") -> str:
    prompt = create_toc_prompt(previous_outputs_summary, feedback_summary, user_info or [])
    system_prompt = """당신은 전문 보고서 구조 설계 전문가입니다.\n\n## 핵심 역할\n- 복잡한 정보를 논리적이고 체계적인 보고서 구조로 설계\n- 독자 친화적이면서도 전문적인 목차(TOC) 생성\n- 실무에서 즉시 활용 가능한 실용적 구조 제공\n- 컨텍스트를 완벽히 이해하고 맞춤형 목차 구성\n\n## 전문성 기준\n1. **논리성**: 명확한 도입-본론-결론 구조\n2. **체계성**: 일관된 분류와 위계질서\n3. **실용성**: 실제 작성시 활용도 높은 구조\n4. **완성도**: 누락 없는 포괄적 구성\n5. **독창성**: 컨텍스트에 특화된 맞춤형 설계\n\n## 작업 방식\n- 컨텍스트 정보를 철저히 분석하여 핵심 영역 파악\n- 논리적 흐름을 고려한 순서 배치\n- 각 레벨별 적절한 분량과 깊이 조절\n- 실무 활용도를 최우선으로 고려한 구조 설계\n- 독자 편의성과 전문성의 균형 유지\n\n## 품질 기준\n⭐ 우수: 논리적 흐름이 완벽하고, 실무 활용도가 매우 높음\n⭐ 양호: 구조적 완성도는 있으나, 일부 개선 여지 존재\n⭐ 미흡: 기본 구조는 갖추었으나, 논리성이나 실용성 부족\n\n목표: 항상 ⭐ 우수 수준의 목차 생성"""
    client = OpenAI(api_key=openai_api_key)

    def _once() -> str:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        return response.choices[0].message.content.strip()

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            return _once()
        except Exception as e:
            last_error = e
            jitter = random.uniform(0, 0.3)
            delay = 0.8 * (2 ** (attempt - 1)) + jitter
            handle_error(f"TOC OpenAI 재시도 {attempt}/3", e, raise_error=False, extra={"delay": round(delay, 2), "model": model})
            time.sleep(delay)
    handle_error("TOC OpenAI 최종실패", last_error or Exception("unknown"), raise_error=True)
    return '{"title": "", "toc": []}'

# ============================================================================
# 비동기 요약 처리 함수들
# ============================================================================

async def summarize_async(outputs: Any, feedbacks: Any, contents: Any = None, openai_api_key: str = "", model: str = "gpt-4.1") -> tuple[str, str]:
    """LLM으로 컨텍스트 요약 - 병렬 처리로 별도 반환 (비동기)"""
    try:
        log("요약을 위한 LLM 병렬 호출 시작")
        
        # 데이터 준비
        outputs_str = _convert_to_string(outputs)
        feedbacks_str = _convert_to_string(feedbacks) if any(item for item in (feedbacks or []) if item and item != {}) else ""
        contents_str = _convert_to_string(contents) if contents and contents != {} else ""
        
        # 병렬 처리
        output_summary, feedback_summary = await _summarize_parallel(outputs_str, feedbacks_str, contents_str, openai_api_key, model)
        
        log(f"이전결과 요약 완료: {len(output_summary)}자, 피드백 요약 완료: {len(feedback_summary)}자")
        return output_summary, feedback_summary
        
    except Exception as e:
        handle_error("요약실패", e, raise_error=True)
        return "", ""

async def _summarize_parallel(outputs_str: str, feedbacks_str: str, contents_str: str = "", openai_api_key: str = "", model: str = "gpt-4.1") -> tuple[str, str]:
    """병렬로 요약 처리 - 별도 반환"""
    tasks = []
    
    # 1. 이전 결과물 요약 태스크 (데이터가 있을 때만)
    if outputs_str and outputs_str.strip():
        output_prompt = create_output_summary_prompt(outputs_str)
        tasks.append(_call_openai_api_async(output_prompt, "이전 결과물", openai_api_key, model))
    else:
        tasks.append(_create_empty_task(""))
    
    # 2. 피드백 요약 태스크 (피드백 또는 현재 결과물이 있을 때만)
    if (feedbacks_str and feedbacks_str.strip()) or (contents_str and contents_str.strip()):
        feedback_prompt = create_feedback_summary_prompt(feedbacks_str, contents_str)
        tasks.append(_call_openai_api_async(feedback_prompt, "피드백", openai_api_key, model))
    else:
        tasks.append(_create_empty_task(""))
    
    # 3. 두 태스크를 동시에 실행하고 완료될 때까지 대기
    output_summary, feedback_summary = await asyncio.gather(*tasks)
    
    # 4. 별도로 반환
    return output_summary, feedback_summary

# ============================================================================
# 유틸리티 함수들
# ============================================================================

async def _create_empty_task(result: str) -> str:
    """빈 태스크 생성 (즉시 완료)"""
    return result

def _convert_to_string(data: Any) -> str:
    """데이터를 문자열로 변환"""
    if isinstance(data, str):
        return data
    return json.dumps(data, ensure_ascii=False)

# ============================================================================
# OpenAI API 호출 함수들
# ============================================================================

async def _call_openai_api_async(prompt: str, task_name: str, openai_api_key: str, model: str = "gpt-4o-mini") -> str:
    """OpenAI API 호출 (지수 백오프 재시도, 타임아웃, 비치명)"""
    client = AsyncOpenAI(api_key=openai_api_key)

    if task_name == "피드백":
            system_prompt = """당신은 피드백 분석 및 통합 전문가입니다.

핵심 사명:
- **최신 피드백 최우선**: 시간 흐름을 파악하여 가장 최신 피드백을 최우선으로 반영
- **문맥 파악**: 피드백들 간의 연결고리와 전체적인 문맥을 정확히 이해
- **진짜 의도 파악**: 표면적 피드백이 아닌 진짜 의도와 숨은 요구사항을 정확히 파악
- **종합적 분석**: 결과물과 피드백을 함께 고려하여 핵심 문제점과 개선사항 도출
- **실행 가능성**: 추상적 지시가 아닌 구체적이고 실행 가능한 개선사항 제시

작업 원칙:
1. **시간성**: 최신 피드백을 최우선으로 하여 시간 흐름 파악
2. **통합성**: 자연스럽고 통합된 하나의 완전한 피드백으로 작성
3. **구체성**: 구체적이고 실행 가능한 개선사항을 누락 없이 포함
4. **명확성**: 다음 작업자가 즉시 이해할 수 있도록 명확하게
5. **완전성**: 다음 작업자가 이 피드백만 보고도 즉시 정확한 작업을 수행할 수 있도록

상황별 대응:
- 품질 문제 → 구체적인 품질 개선 방향 제시
- 방식 문제 → 접근법 변경 및 새로운 방법론 제안
- 기능 문제 → 필요한 기능과 구현 방법 명시
- 부분 수정 → 정확한 수정 범위와 방법 제시
- 전면 재작업 → 새로운 접근 방향과 전략 제시

목표: 다음 작업자가 즉시 정확하고 효과적인 작업을 수행할 수 있도록 하는 완벽한 가이드 제공"""
    else:  # "이전 결과물" 등 다른 모든 경우
            system_prompt = """당신은 작업 결과물을 정확하게 정리하는 전문가입니다.

핵심 사명:
- **정보 손실 방지**: 짧은 내용은 요약하지 말고 그대로 유지 (오히려 정보 손실 위험)
- **의미 보존 최우선**: 왜곡이나 의미 변경 절대 금지, 원본 의미 그대로 보존
- **객관적 정보 완전 보존**: 수치, 목차, 인물명, 물건명, 날짜, 시간 등 객관적 정보는 반드시 포함
- **효율적 정리**: 긴 내용만 적절히 요약하여 핵심 정보 전달
- **통합성 확보**: 하나의 통합된 문맥으로 작성하여 다음 작업자가 즉시 이해 가능

작업 원칙:
1. **정확성**: 원본 정보를 왜곡 없이 그대로 기록
2. **완전성**: 중복된 부분만 정리하고 핵심 내용은 모두 보존
3. **구조화**: 원본의 논리적 흐름과 구조를 최대한 보존
4. **실용성**: 다음 작업자가 즉시 이해할 수 있도록 명확하게
5. **객관성**: 객관적 사실만 포함, 불필요한 부연설명만 제거

금지사항:
- 짧은 내용의 무분별한 요약
- 수치, 날짜, 인명 등 객관적 정보 누락
- 원본 의미의 왜곡이나 변경
- 개인적 해석이나 추가 제안"""
        
    async def _once() -> str:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            timeout=30.0,
        )
        return response.choices[0].message.content.strip()

    async def _retry(fn: Callable[[], Any], *, retries: int = 3, base_delay: float = 0.8) -> str:
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                return await fn()
            except Exception as e:
                last_error = e
                jitter = random.uniform(0, 0.3)
                delay = base_delay * (2 ** (attempt - 1)) + jitter
                handle_error(f"{task_name} OpenAI 재시도 {attempt}/{retries}", e, raise_error=False, extra={"delay": round(delay, 2), "model": model})
                await asyncio.sleep(delay)
        handle_error(f"{task_name} OpenAI 최종실패", last_error or Exception("unknown"), raise_error=True)
        return ""

    result = await _retry(_once)
    if result:
        log(f"{task_name} 요약 완료: {len(result)}자")
    return result
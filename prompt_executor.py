from openai import OpenAI
import json
from prompt import (
    create_execution_plan_prompt,
    create_slide_generation_prompt,
    create_text_form_generation_prompt,
    create_summary_prompt,
    create_toc_prompt
)

# OpenAI API 키는 함수 호출 시 인자로 전달

def generate_execution_plan(form_types: list, openai_api_key: str, model: str = "gpt-4.1") -> str:
    prompt = create_execution_plan_prompt(form_types)
    client = OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    return response.choices[0].message.content.strip()


def generate_slide_from_report(report_content: str, user_info: list, openai_api_key: str, model: str = "gpt-4.1") -> str:
    prompt = create_slide_generation_prompt(report_content, user_info)
    client = OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    return response.choices[0].message.content.strip()


def generate_text_form_values(report_content: str, topic: str, text_form_keys: list, user_info: list, openai_api_key: str, model: str = "gpt-4.1") -> str:
    prompt = create_text_form_generation_prompt(report_content, topic, text_form_keys, user_info)
    client = OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    return response.choices[0].message.content.strip()

def generate_summary(outputs, feedbacks, openai_api_key: str, model: str = "gpt-4.1") -> str:
    outputs_str = outputs if isinstance(outputs, str) else json.dumps(outputs, ensure_ascii=False)
    feedbacks_str = feedbacks if isinstance(feedbacks, str) else json.dumps(feedbacks, ensure_ascii=False)
    prompt = create_summary_prompt(outputs_str, feedbacks_str)
    system_prompt = """당신은 전문적인 요약 전문가입니다.\n\n주요 역할:\n- 복잡한 산출물(보고서, 폼 등)을 구조화된 형식으로 정확히 요약\n- 목차별 핵심 내용을 빠짐없이 추출\n- 메타데이터와 중요 데이터를 정확히 파악\n- 비즈니스 문서의 핵심 가치를 보존하면서 간결하게 정리\n\n작업 원칙:\n1. 정확성: 원문의 내용을 왜곡하지 않고 정확히 요약\n2. 완전성: 모든 목차와 중요 정보를 누락 없이 포함\n3. 구조화: 일관된 형식으로 읽기 쉽게 정리\n4. 간결성: 핵심만 추출하여 효율적으로 전달\n5. 실용성: 후속 작업에 활용하기 쉬운 형태로 가공"""
    client = OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1
    )
    return response.choices[0].message.content.strip()

def generate_toc(context_summary: str, feedbacks: str, openai_api_key: str, model: str = "gpt-4.1") -> str:
    prompt = create_toc_prompt(context_summary, feedbacks)
    system_prompt = """당신은 전문 보고서 구조 설계 전문가입니다.\n\n## 핵심 역할\n- 복잡한 정보를 논리적이고 체계적인 보고서 구조로 설계\n- 독자 친화적이면서도 전문적인 목차(TOC) 생성\n- 실무에서 즉시 활용 가능한 실용적 구조 제공\n- 컨텍스트를 완벽히 이해하고 맞춤형 목차 구성\n\n## 전문성 기준\n1. **논리성**: 명확한 도입-본론-결론 구조\n2. **체계성**: 일관된 분류와 위계질서\n3. **실용성**: 실제 작성시 활용도 높은 구조\n4. **완성도**: 누락 없는 포괄적 구성\n5. **독창성**: 컨텍스트에 특화된 맞춤형 설계\n\n## 작업 방식\n- 컨텍스트 정보를 철저히 분석하여 핵심 영역 파악\n- 논리적 흐름을 고려한 순서 배치\n- 각 레벨별 적절한 분량과 깊이 조절\n- 실무 활용도를 최우선으로 고려한 구조 설계\n- 독자 편의성과 전문성의 균형 유지\n\n## 품질 기준\n⭐ 우수: 논리적 흐름이 완벽하고, 실무 활용도가 매우 높음\n⭐ 양호: 구조적 완성도는 있으나, 일부 개선 여지 존재\n⭐ 미흡: 기본 구조는 갖추었으나, 논리성이나 실용성 부족\n\n목표: 항상 ⭐ 우수 수준의 목차 생성"""
    client = OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1
    )
    return response.choices[0].message.content.strip() 
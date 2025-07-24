import os
import pytest
from dotenv import load_dotenv

# 테스트 환경 설정
os.environ['ENV'] = 'test'
load_dotenv('.env.test', override=True)

from core.database import initialize_db, get_db_client
from core.polling_manager import _prepare_task_inputs
from flows.multi_format_flow import PromptMultiFormatFlow

# DB 초기화
initialize_db()

# ============================================================================
# 테스트 케이스들
# ============================================================================

@pytest.mark.asyncio
async def test_prepare_phase():
    """
    1) todolist 테이블에서 실제 todo_id로 row를 가져와,
    2) _prepare_task_inputs가 올바른 dict 구조를 반환하는지 검증
    """
    todo_id = "529a7104-978c-4953-ae88-6deb9b8d3fa5"
    client = get_db_client()
    resp = (
        client
        .table('todolist')
        .select('*')
        .eq('id', todo_id)
        .single()
        .execute()
    )
    row = resp.data
    assert row, f"Todo ID {todo_id}가 DB에 없습니다"
    
    # Row 입력 확인
    print(f"\n입력 Row:")
    print(f"  activity_name: '{row.get('activity_name')}'")
    print(f"  tool: '{row.get('tool')}'")
    print(f"  user_id: '{row.get('user_id')}'")
    print(f"  tenant_id: '{row.get('tenant_id')}'")
    
    # _prepare_task_inputs 실행 및 결과 검증
    inputs = await _prepare_task_inputs(row)
    print(f"\n결과 검증:")
    
    problems = []
    
    # 각 필드 출력하면서 동시에 검증
    topic = inputs.get('topic')
    print(f"  topic: '{topic}' {'✓' if topic else '❌ 빈값'}")
    if not topic:
        problems.append("topic 빈값")
    
    proc_form_id = inputs.get('proc_form_id')
    print(f"  proc_form_id: '{proc_form_id}' {'✓' if proc_form_id else '❌ 없음'}")
    if not proc_form_id:
        problems.append("proc_form_id 없음")
    
    form_types = inputs.get('form_types', [])
    is_default = len(form_types) == 1 and form_types[0].get('type') == 'default'
    print(f"  form_types: {'❌ 기본값' if is_default else f'✓ {len(form_types)}개'} {form_types}")
    if is_default:
        problems.append("form_types 기본값")
    
    user_info = inputs.get('user_info', [])
    has_participants = user_info
    print(f"  참가자: {'✓' if has_participants else '❌ 없음'} (user:{len(user_info)})")
    if not has_participants:
        problems.append("참가자 정보 없음")
    
    print(f"  previous_context: {len(inputs.get('previous_context', ''))}자")
    
    # 문제 있으면 바로 실패
    if problems:
        assert False, f"❌ 문제 발견: {', '.join(problems)}"
    print(f"✓ 모든 검증 통과")

@pytest.mark.asyncio
async def test_full_flow_phase():
    """
    PromptMultiFormatFlow 전체 실행 흐름 테스트
    """
    todo_id = "529a7104-978c-4953-ae88-6deb9b8d3fa5"
    client = get_db_client()
    row = (
        client
        .table('todolist')
        .select('*')
        .eq('id', todo_id)
        .single()
        .execute()
    ).data
    inputs = await _prepare_task_inputs(row)

    flow = PromptMultiFormatFlow()
    for k, v in inputs.items():
        setattr(flow.state, k, v)

    print(f"\n플로우 단계별 실행:")
    problems = []

    # 1. create_execution_plan
    plan = await flow.create_execution_plan()
    has_plan = plan and hasattr(plan, 'report_phase')
    print(f"  create_execution_plan: {'✓' if has_plan else '❌ 실행계획 없음'}")
    if not has_plan:
        problems.append("execution_plan 없음")
        
    # 실행계획 세부 확인
    report_forms = plan.report_phase.forms if has_plan else []
    slide_forms = plan.slide_phase.forms if has_plan else []
    text_forms = plan.text_phase.forms if has_plan else []
    print(f"    - report_phase: {len(report_forms)}개")
    print(f"    - slide_phase: {len(slide_forms)}개") 
    print(f"    - text_phase: {len(text_forms)}개")

    # 2. generate_reports (실행계획에 따라 검증)
    reports = await flow.generate_reports()
    should_have_reports = len(report_forms) > 0
    has_reports = isinstance(reports, dict) and (bool(reports) if should_have_reports else True)
    status = "✓" if has_reports else "❌"
    print(f"  generate_reports: {status} {len(reports) if isinstance(reports, dict) else 0}개 (예상: {len(report_forms)}개)")
    if should_have_reports and not reports:
        problems.append("reports 없음 (실행계획에는 있음)")

    # 3. generate_slides (실행계획에 따라 검증)
    slides = await flow.generate_slides()
    should_have_slides = len(slide_forms) > 0
    has_slides = isinstance(slides, dict) and (bool(slides) if should_have_slides else True)
    status = "✓" if has_slides else "❌"
    print(f"  generate_slides: {status} {len(slides) if isinstance(slides, dict) else 0}개 (예상: {len(slide_forms)}개)")
    if should_have_slides and not slides:
        problems.append("slides 없음 (실행계획에는 있음)")

    # 4. generate_texts (실행계획에 따라 검증)
    texts = await flow.generate_texts()
    should_have_texts = len(text_forms) > 0
    has_texts = isinstance(texts, dict) and (bool(texts) if should_have_texts else True)
    status = "✓" if has_texts else "❌"
    print(f"  generate_texts: {status} {len(texts) if isinstance(texts, dict) else 0}개 (예상: {len(text_forms)}개)")
    if should_have_texts and not texts:
        problems.append("texts 없음 (실행계획에는 있음)")

    # 5. save_final_results
    await flow.save_final_results()
    print(f"  save_final_results: ✓ 완료")

    # 문제 있으면 바로 실패
    if problems:
        assert False, f"❌ 플로우 실행 실패: {', '.join(problems)}"
    
    print(f"✓ 전체 플로우 성공") 
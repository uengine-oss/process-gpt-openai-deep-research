import os
import json
import asyncio
from typing import Dict, List, Any, Optional
from crewai.flow.flow import Flow, start, listen
from pydantic import BaseModel, Field
import uuid

from prompt_executor import (
    generate_execution_plan,
    generate_toc,
    generate_slide_from_report,
    generate_text_form_values
)
from api_deep_research import execute_research_section
from database import save_task_result
from event_logger import EventLogger

# ============================================================================
# 유틸리티 함수
# ============================================================================

def clean_json_response(raw_text: Any) -> str:
    """AI 응답에서 코드 블록 마크다운을 제거하여 순수 JSON만 추출"""
    import re
    text = str(raw_text or "")
    # ```json ... ``` 패턴 제거
    match = re.search(r"```(?:json)?[\r\n]+(.*?)[\r\n]+```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1)
    # 전체 코드 블록 제거
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.split("\n")
        return "\n".join(lines[1:-1])
    return text

# ============================================================================
# 데이터 모델 정의
# ============================================================================

class Phase(BaseModel):
    """실행 단계별 폼 목록을 담는 모델"""
    forms: List[Dict[str, Any]] = Field(default_factory=list)

class ExecutionPlan(BaseModel):
    """전체 실행 계획을 담는 모델 (리포트 → 슬라이드 → 텍스트)"""
    report_phase: Phase = Field(default_factory=Phase)
    slide_phase: Phase = Field(default_factory=Phase)
    text_phase: Phase = Field(default_factory=Phase)

class PromptMultiFormatState(BaseModel):
    """프롬프트 기반 다중 포맷 플로우의 전체 상태를 관리하는 모델"""
    topic: str = ""
    user_info: List[Dict[str, Any]] = Field(default_factory=list)
    form_types: List[Dict[str, Any]] = Field(default_factory=list)
    execution_plan: Optional[ExecutionPlan] = None
    report_sections: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)  # report_key -> sections
    section_contents: Dict[str, Dict[str, str]] = Field(default_factory=dict)  # report_key -> {section_title -> content}
    report_contents: Dict[str, str] = Field(default_factory=dict)
    slide_contents: Dict[str, str] = Field(default_factory=dict)
    text_contents: Dict[str, Any] = Field(default_factory=dict)
    todo_id: Optional[int] = None
    proc_inst_id: Optional[str] = None
    previous_context: str = ""
    proc_form_id: Optional[str] = None


# ============================================================================
# 메인 플로우 클래스
# ============================================================================

class PromptMultiFormatFlow(Flow[PromptMultiFormatState]):
    """프롬프트 기반 다중 포맷 생성 플로우 (리포트 → 슬라이드 → 텍스트)"""
    
    def __init__(self):
        super().__init__()
        self.event_logger = EventLogger()

    def _handle_error(self, stage: str, error: Exception) -> None:
        """통합 에러 처리 및 로깅"""
        error_msg = f"❌ [{stage}] 오류 발생: {str(error)}"
        print(error_msg)
        raise Exception(f"{stage} 실패: {error}")

    # ========================================================================
    # 1단계: 실행 계획 생성
    # ========================================================================

    @start()
    async def create_execution_plan(self) -> ExecutionPlan:
        """폼 타입을 분석하여 실행 계획을 생성 (시작점)"""
        try:
            self.event_logger.emit_event(
                event_type="task_started",
                data={
                    "goal": "다양한 폼 양식 유형을 분석하고 콘텐츠 생성 실행 계획을 작성합니다.",
                    "name": "OpenAI Deep Research",
                    "role": "다중 형식 분석을 통해 콘텐츠 생성 실행 계획을 작성하는 에이전트",
                    "agent_profile": "/images/chat-icon.png"
                },
                job_id="api-deep-research_planning_form",
                crew_type="planning",
                todo_id=self.state.todo_id,
                proc_inst_id=self.state.proc_inst_id
            )
            
            api_key = os.getenv("OPENAI_API_KEY")
            plan_str = generate_execution_plan(self.state.form_types, api_key)
            
            # JSON 파싱 및 계획 저장
            cleaned_text = clean_json_response(plan_str)
            plan_data = json.loads(cleaned_text).get("execution_plan", {})
            self.state.execution_plan = ExecutionPlan.parse_obj(plan_data)
            
            # 추가: 토픽, 유저 정보, 폼 타입 로그
            print(f"🔖 토픽: {self.state.topic}")
            print(f"👥 유저 정보:\n{json.dumps(self.state.user_info, indent=2, ensure_ascii=False)}")
            print(f"📑 폼 타입:\n{json.dumps(self.state.form_types, indent=2, ensure_ascii=False)}")

            # 추가: 실행 계획 상세 로그
            print(f"🗒️ 실행 계획 상세:\n{json.dumps(plan_data, indent=2, ensure_ascii=False)}")

            print(f"📋 실행 계획 생성 완료: 리포트 {len(self.state.execution_plan.report_phase.forms)}개, "
                  f"슬라이드 {len(self.state.execution_plan.slide_phase.forms)}개, "
                  f"텍스트 {len(self.state.execution_plan.text_phase.forms)}개")
            
            # 실행 계획 결과를 final_result로 저장
            self.event_logger.emit_event(
                event_type="task_completed",
                data={
                    "final_result": cleaned_text
                },
                job_id="api-deep-research_planning_form",
                crew_type="planning",
                todo_id=self.state.todo_id,
                proc_inst_id=self.state.proc_inst_id
            )

            return self.state.execution_plan
        except Exception as e:
            self._handle_error("실행계획생성", e)

    # ========================================================================
    # 2단계: 리포트 생성
    # ========================================================================

    @listen("create_execution_plan")
    async def generate_reports(self) -> Dict[str, str]:
        """실행 계획에 따라 리포트들을 생성"""
        # 리포트 생성 계획이 없으면 스킵
        if not (self.state.execution_plan and self.state.execution_plan.report_phase.forms):
            print("⚠️ 리포트 생성 계획이 없어 스킵합니다.")
            return {}
        try:
            for report_form in self.state.execution_plan.report_phase.forms:
                report_key = report_form.get('key', 'report')
                
                # TOC 생성
                sections = await self._create_report_sections(report_key)
                # 추가: TOC 목록 로그
                print(f"🔍 [{report_key}] TOC 목록:\n{json.dumps(sections, indent=2, ensure_ascii=False)}")
                self.state.report_sections[report_key] = sections
                self.state.section_contents[report_key] = {}
                
                # 섹션별 콘텐츠 생성
                await self._generate_section_contents(report_key, sections)
                
                # 섹션 병합
                await self._merge_report_sections(report_key, sections)
                
            return self.state.report_contents
        except Exception as e:
            self._handle_error("리포트생성", e)

    async def _create_report_sections(self, report_key: str) -> List[Dict[str, Any]]:
        """리포트의 TOC(목차) 생성"""
        try:
            self.event_logger.emit_event(
                event_type="task_started",
                data={
                    "goal": "컨텍스트를 분석하여, 현재 상황에 맞는 목차(TOC)를 생성합니다.",
                    "name": "OpenAI Deep Research",
                    "role": "컨텍스트를 분석하여, 현재 상황에 맞는 목차(TOC)를 생성하는 에이전트",
                    "agent_profile": "/images/chat-icon.png"
                },
                job_id=f"api-deep-research_planning_sections_{report_key}",
                crew_type="planning",
                todo_id=self.state.todo_id,
                proc_inst_id=self.state.proc_inst_id
            )

            api_key = os.getenv("OPENAI_API_KEY")
            toc_str = generate_toc(self.state.previous_context, "", api_key)
            
            # JSON 파싱
            cleaned_text = clean_json_response(toc_str)
            toc_json = json.loads(cleaned_text)
            sections = toc_json.get("toc", [])
            
            print(f"📋 [{report_key}] TOC 생성 완료: {len(sections)}개 섹션")

            self.event_logger.emit_event(
                event_type="task_completed",
                data={
                    "final_result": cleaned_text
                },
                job_id=f"api-deep-research_planning_sections_{report_key}",
                crew_type="planning",
                todo_id=self.state.todo_id,
                proc_inst_id=self.state.proc_inst_id
            )

            return sections
        except Exception as e:
            print(f"❌ [{report_key}] TOC 생성 실패: {str(e)}")
            return []

    async def _generate_section_contents(self, report_key: str, sections: List[Dict[str, Any]]) -> None:
        """섹션별 내용을 병렬로 생성하고 완료 순서대로 처리"""
        # 섹션별 비동기 작업 생성
        tasks = []
        task_job_map = {}
        section_map = {}
        for sec in sections:
            section_title = sec.get('title', 'unknown')
            
            # 섹션별 고유 job_id 생성
            section_job_id = str(uuid.uuid4())
            
            # 섹션 시작 이벤트
            self.event_logger.emit_event(
                event_type="task_started",
                data={
                    "goal": f"{section_title} 섹션의 내용을 생성하기 위해 리서치를 진행합니다.",
                    "name": "OpenAI Deep Research",
                    "role": "리서치를 진행하여 섹션의 내용을 생성하는 에이전트",
                    "agent_profile": "/images/chat-icon.png"
                },
                job_id=f"api_{section_job_id}_{report_key}",
                crew_type="report",
                todo_id=self.state.todo_id,
                proc_inst_id=self.state.proc_inst_id
            )
            
            task = asyncio.create_task(
                execute_research_section(
                    section_info=sec,
                    topic=self.state.topic, 
                    previous_context=self.state.previous_context,
                    event_logger=self.event_logger,
                    todo_id=self.state.todo_id,
                    proc_inst_id=self.state.proc_inst_id,
                    job_id=f"api_{section_job_id}_{report_key}"
                )
            )
            tasks.append(task)
            task_job_map[task] = section_job_id
            section_map[task] = sec
        
        # 완료 순서대로 처리
        pending_tasks = set(tasks)
        
        while pending_tasks:
            done_tasks, pending_tasks = await asyncio.wait(pending_tasks, return_when=asyncio.FIRST_COMPLETED)
            
            for task in done_tasks:
                section = section_map[task]
                title = section.get('title', 'unknown')
                
                try:
                    content = task.result()
                    self.state.section_contents[report_key][title] = content
                    print(f"✅ [{report_key}] 섹션 완료: {title}")
                    # 추가: 섹션 내용 로그
                    print(f"📄 [{report_key}] '{title}' 내용:\n{content}")
                    
                    # 섹션 완료 이벤트
                    self.event_logger.emit_event(
                        event_type="task_completed",
                        data={"final_result": {report_key: content}},
                        job_id=f"api_{task_job_map[task]}_{report_key}",
                        crew_type="report",
                        todo_id=self.state.todo_id,
                        proc_inst_id=self.state.proc_inst_id
                    )
                    
                except Exception as e:
                    self.state.section_contents[report_key][title] = f"섹션 생성 실패: {str(e)}"
                    print(f"❌ [{report_key}] 섹션 실패: {title} - {str(e)}")
        
                # 중간 결과 저장
                await self._save_intermediate_result(report_key, sections)

    async def _merge_report_sections(self, report_key: str, sections: List[Dict[str, Any]]) -> None:
        """완성된 섹션들을 TOC 순서대로 병합"""
        # 병합 시작 이벤트
        self.event_logger.emit_event(
            event_type="task_started",
            data={
                "goal": "리포트의 섹션들을 순서대로 병합하여, 최종 리포트를 생성합니다.",
                "name": "OpenAI Deep Research",
                "role": "병합된 섹션들을 TOC 순서대로 병합하는 에이전트",
                "agent_profile": "/images/chat-icon.png"
            },
            job_id=f"api-deep-research_final_report_merge_{report_key}",
            crew_type="report",
            todo_id=self.state.todo_id,
            proc_inst_id=self.state.proc_inst_id
        )
        
        # TOC 순서 유지하여 병합
        ordered_titles = [sec["title"] for sec in sections]
        merged_content = "\n\n---\n\n".join([
            self.state.section_contents[report_key][title]
            for title in ordered_titles
            if title in self.state.section_contents[report_key]
        ])
        
        self.state.report_contents[report_key] = merged_content
        print(f"📄 [{report_key}] 리포트 병합 완료: {len(merged_content)}자")
        # 추가: 최종 리포트 내용 로그
        print(f"📑 [{report_key}] 최종 리포트 내용:\n{merged_content}")
        
        # 병합 완료 이벤트
        self.event_logger.emit_event(
            event_type="task_completed",
            data={
                "final_result": {report_key: merged_content}
            },
            job_id=f"api-deep-research_final_report_merge_{report_key}",
            crew_type="report",
            todo_id=self.state.todo_id,
            proc_inst_id=self.state.proc_inst_id
        )

    async def _save_intermediate_result(self, report_key: str, sections: List[Dict[str, Any]]) -> None:
        """완성된 섹션들을 DB에 중간 저장"""
        # 현재까지 완성된 섹션들만 병합
        ordered_titles = [sec["title"] for sec in sections]
        merged_content = "\n\n---\n\n".join([
            self.state.section_contents[report_key][title]
            for title in ordered_titles
            if title in self.state.section_contents[report_key]
        ])
        
        self.state.report_contents[report_key] = merged_content
        
        # DB 저장
        if self.state.todo_id and self.state.proc_form_id and merged_content.strip():
            result = {self.state.proc_form_id: {report_key: merged_content}}
            await save_task_result(self.state.todo_id, result)
            print(f"💾 [{report_key}] 중간 저장 완료: {len(self.state.section_contents[report_key])}/{len(sections)} 섹션")

    # ========================================================================
    # 3단계: 슬라이드 생성
    # ========================================================================

    @listen("generate_reports")
    async def generate_slides(self) -> Dict[str, str]:
        """리포트를 기반으로 슬라이드들을 생성"""
        # 슬라이드 생성 계획이 없으면 스킵
        if not (self.state.execution_plan and self.state.execution_plan.slide_phase.forms):
            print("⚠️ 슬라이드 생성 계획이 없어 스킵합니다.")
            return {}
        try:
            print("▶️ 슬라이드 생성 시작")
            
            # 리포트 기반 슬라이드 생성
            if self.state.report_contents:
                for report_key, content in self.state.report_contents.items():
                    await self._create_slides_from_report(report_key, content)
            else:
                # 이전 컨텍스트 기반 슬라이드 생성
                await self._create_slides_from_context()
            
            
            print("✅ 슬라이드 생성 완료")
            return self.state.slide_contents
            
        except Exception as e:
            self._handle_error("슬라이드생성", e)

    async def _create_slides_from_report(self, report_key: str, content: str) -> None:
        """특정 리포트에 의존하는 슬라이드만 생성"""
        api_key = os.getenv("OPENAI_API_KEY")
        
        for slide_form in self.state.execution_plan.slide_phase.forms:
            # 의존성 체크
            if report_key in slide_form.get('dependencies', []):
                slide_key = slide_form['key']
                
                # 슬라이드 시작 이벤트
                self.event_logger.emit_event(
                    event_type="task_started",
                    data={
                        "goal": f"리포트 내용을 기반으로 슬라이드를 생성합니다.",
                        "name": "OpenAI Deep Research",
                        "role": "리포트 내용을 기반으로 슬라이드를 생성하는 에이전트",
                        "agent_profile": "/images/chat-icon.png"
                    },
                    job_id=f"api-deep-research_generate_slides_{slide_key}",
                    crew_type="slide",
                    todo_id=self.state.todo_id,
                    proc_inst_id=self.state.proc_inst_id
                )
                # 슬라이드 생성
                slide_content = generate_slide_from_report(
                    content, self.state.user_info, api_key
                )
                self.state.slide_contents[slide_key] = slide_content
                print(f"🎯 [{slide_key}] 슬라이드 생성 완료 (from {report_key})")
                # 슬라이드 완료 이벤트
                self.event_logger.emit_event(
                    event_type="task_completed",
                    data={"final_result": {slide_key: slide_content}},
                    job_id=f"api-deep-research_generate_slides_{slide_key}",
                    crew_type="slide",
                    todo_id=self.state.todo_id,
                    proc_inst_id=self.state.proc_inst_id
                )

    async def _create_slides_from_context(self) -> None:
        """이전 컨텍스트를 기반으로 슬라이드 생성"""
        api_key = os.getenv("OPENAI_API_KEY")
        
        for slide_form in self.state.execution_plan.slide_phase.forms:
            slide_key = slide_form['key']
            # 슬라이드 시작 이벤트 (context)
            self.event_logger.emit_event(
                event_type="task_started",
                data={
                    "goal": "컨텍스트를 기반으로 슬라이드를 생성합니다.",
                    "name": "OpenAI Deep Research",
                    "role": "컨텍스트를 기반으로 슬라이드를 생성하는 에이전트",
                    "agent_profile": "/images/chat-icon.png"
                },
                job_id=f"api-deep-research_generate_slides_{slide_key}",
                crew_type="slide",
                todo_id=self.state.todo_id,
                proc_inst_id=self.state.proc_inst_id
            )
            # 슬라이드 생성
            slide_content = generate_slide_from_report(
                self.state.previous_context, self.state.user_info, api_key
            )
            self.state.slide_contents[slide_key] = slide_content
            print(f"🎯 [{slide_key}] 슬라이드 생성 완료 (from context)")
            # 슬라이드 완료 이벤트 (context)
            self.event_logger.emit_event(
                event_type="task_completed",
                data={"final_result": {slide_key: slide_content}},
                job_id=f"api-deep-research_generate_slides_{slide_key}",
                crew_type="slide",
                todo_id=self.state.todo_id,
                proc_inst_id=self.state.proc_inst_id
            )

    # ========================================================================
    # 4단계: 텍스트 생성
    # ========================================================================

    @listen("generate_slides")
    async def generate_texts(self) -> Dict[str, Any]:
        """리포트를 기반으로 텍스트 폼들을 생성"""
        # 텍스트 생성 계획이 없으면 스킵
        if not (self.state.execution_plan and self.state.execution_plan.text_phase.forms):
            print("⚠️ 텍스트 생성 계획이 없어 스킵합니다.")
            return {}
        try:
            print("▶️ 텍스트 생성 시작")
            # 텍스트 생성 시작 이벤트
            self.event_logger.emit_event(
                event_type="task_started",
                data={
                    "goal": "컨텍스트 텍스트 폼을 생성합니다.",
                    "name": "OpenAI Deep Research",
                    "role": "리포트를 기반으로 텍스트 폼을 생성하는 에이전트",
                    "agent_profile": "/images/chat-icon.png"
                },
                job_id="api-deep-research_generate_texts",
                crew_type="text",
                todo_id=self.state.todo_id,
                proc_inst_id=self.state.proc_inst_id
            )
            
            # 리포트 기반 텍스트 생성
            if self.state.report_contents:
                for report_key, content in self.state.report_contents.items():
                    await self._create_texts_from_report(report_key, content)
            else:
                # 이전 컨텍스트 기반 텍스트 생성
                await self._create_texts_from_context()
            
            # 텍스트 생성 완료 이벤트
            self.event_logger.emit_event(
                event_type="task_completed",
                data={
                    "final_result": self.state.text_contents
                },
                job_id="api-deep-research_generate_texts",
                crew_type="text",
                todo_id=self.state.todo_id,
                proc_inst_id=self.state.proc_inst_id
            )
            
            print("✅ 텍스트 생성 완료")
            return self.state.text_contents
            
        except Exception as e:
            self._handle_error("텍스트생성", e)

    async def _create_texts_from_report(self, report_key: str, content: str) -> None:
        """특정 리포트에 의존하는 텍스트 폼들만 생성"""
        api_key = os.getenv("OPENAI_API_KEY")
        
        # 의존성이 있는 텍스트 폼들 찾기
        dependent_forms = [
            form for form in self.state.execution_plan.text_phase.forms
            if report_key in form.get('dependencies', [])
        ]
        
        if dependent_forms:
            form_keys = [form['key'] for form in dependent_forms]
            await self._generate_text_content(content, form_keys, report_key)

    async def _create_texts_from_context(self) -> None:
        """이전 컨텍스트를 기반으로 텍스트 생성"""
        if self.state.execution_plan.text_phase.forms:
            form_keys = [form['key'] for form in self.state.execution_plan.text_phase.forms]
            await self._generate_text_content("", form_keys, "context")

    async def _generate_text_content(self, content: str, form_keys: List[str], source: str) -> None:
        """텍스트 내용 생성 및 결과 파싱"""
        api_key = os.getenv("OPENAI_API_KEY")
        
        result_text = generate_text_form_values(
            content,
            self.state.topic,
            form_keys,
            self.state.user_info,
            api_key
        )
        
        await self._parse_text_results(result_text, form_keys, source)

    async def _parse_text_results(self, raw_result: str, form_keys: List[str], source: str) -> None:
        """텍스트 생성 결과를 파싱하여 각 폼에 할당"""
        try:
            # JSON 파싱 시도
            cleaned_result = clean_json_response(raw_result)
            parsed_results = json.loads(cleaned_result)
            
            for form_key in form_keys:
                if form_key in parsed_results:
                    self.state.text_contents[form_key] = parsed_results[form_key]
                    print(f"📝 [{form_key}] 텍스트 생성 완료 (from {source})")
                else:
                    self.state.text_contents[form_key] = raw_result
                    print(f"📝 [{form_key}] 텍스트 생성 완료 (raw, from {source})")
                    
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 원본 텍스트를 모든 폼에 할당
            for form_key in form_keys:
                self.state.text_contents[form_key] = raw_result
                print(f"📝 [{form_key}] 텍스트 생성 완료 (fallback, from {source})")

    # ========================================================================
    # 5단계: 최종 저장
    # ========================================================================

    @listen("generate_texts")
    async def save_final_results(self) -> None:
        """모든 결과를 최종 저장하고 완료 이벤트 발행"""
        try:
            print("\n" + "="*60)
            print("🎉 프롬프트 다중 포맷 생성 완료!")
            print("="*60)
            
            # 최종 결과 DB 저장
            if self.state.todo_id and self.state.proc_form_id:
                all_results = {
                    **self.state.report_contents,
                    **self.state.slide_contents,
                    **self.state.text_contents
                }
                
                if all_results:
                    final_result = {self.state.proc_form_id: all_results}
                    await save_task_result(self.state.todo_id, final_result, final=True)
                    
                    # 처리 결과 출력
                    report_count = len(self.state.report_contents)
                    slide_count = len(self.state.slide_contents)
                    text_count = len(self.state.text_contents)
                    print(f"📊 처리 결과: 리포트 {report_count}개, 슬라이드 {slide_count}개, 텍스트 {text_count}개")
            
        except Exception as e:
            self._handle_error("최종결과저장", e) 
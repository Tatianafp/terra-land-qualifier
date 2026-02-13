"""
LangGraph Qualification Agent (Refatorado)

Objetivos da refatoração:
1. Manter CONTEXTO de conversa (não repetir perguntas)
2. Usar LLM para extração estruturada (sem regex frágil)
3. Preencher progressivamente QualificationState
4. Perguntar apenas o que está faltando
"""

import sys
import uuid
from pathlib import Path
from enum import Enum
from typing import Literal, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_llm
from guardrails.geographic_validator import geographic_validator
from guardrails.output_parser import output_parser
from models.schemas import LeadQualification, NextStep, OwnerType
from prompts.system_prompt import get_system_prompt
from agents.state import QualificationState

class QualificationStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"

# -----------------------------
# PROMPT DE EXTRAÇÃO ESTRUTURADA
# -----------------------------
EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """
Você é um assistente especializado em extração de informações imobiliárias.

Extraia APENAS os campos abaixo, se estiverem presentes na conversa.
Se não houver informação suficiente, retorne null.

Campos:
- bairro
- cidade
- land_size_m2 (número)
- asking_price (número)
- legal_status (string curta)
- owner_type: corretor | proprietario
- differentials (texto livre)

Responda APENAS em JSON válido.
"""),
    ("human", "CONVERSA:\n{conversation}")
])


class QualifierAgent:
    def __init__(self):
        self.llm = get_llm()
        self.system_prompt = get_system_prompt()
        self.graph = self._build_graph()

    # -----------------------------
    # GRAPH
    # -----------------------------
    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(QualificationState)

        workflow.add_node("conversation", self._conversation_node)
        workflow.add_node("extract", self._llm_extract_node)
        workflow.add_node("validate", self._validate_location_node)
        workflow.add_node("output", self._generate_output_node)

        workflow.set_entry_point("conversation")

        workflow.add_conditional_edges(
            "conversation",
            self._route_after_conversation,
            {
                "extract": "extract",
                "output": "output",
                "continue": END
            }
        )

        workflow.add_edge("extract", "validate")

        workflow.add_conditional_edges(
            "validate",
            self._route_after_validation,
            {
                "output": "output",
                "continue": "conversation"
            }
        )

        workflow.add_edge("output", END)

        return workflow.compile()

    # -----------------------------
    # NODES
    # -----------------------------
    def _conversation_node(self, state: QualificationState) -> QualificationState:
        messages = state["messages"]

        prompt = [SystemMessage(content=self.system_prompt)] + messages
        response = self.llm.invoke(prompt)

        state["messages"] = messages + [AIMessage(content=response.content)]
        state["turn_count"] = state.get("turn_count", 0) + 1

        return state

    def _llm_extract_node(self, state: QualificationState) -> QualificationState:
        conversation_text = self._conversation_as_text(state["messages"])

        extraction = self.llm.invoke(
            EXTRACTION_PROMPT.format_messages(conversation=conversation_text)
        )

        try:
            data = output_parser.safe_json_loads(extraction.content)
        except Exception:
            return state

        # Merge incremental state (não sobrescreve valores existentes)
        for field, value in data.items():
            if value is not None and not state.get(field):
                state[field] = value

        return state

    def _validate_location_node(self, state: QualificationState) -> QualificationState:
        if not state.get("bairro"):
            return state

        is_valid, matched, _ = geographic_validator.validate_location(
            bairro=state.get("bairro"),
            cidade=state.get("cidade")
        )

        state["location_validated"] = True
        state["is_qualified"] = is_valid

        if matched:
            state["bairro"] = matched

        return state

    def _generate_output_node(self, state: QualificationState) -> QualificationState:
        qualification = LeadQualification(
            lead_qualified=state.get("is_qualified", False),
            owner_type=OwnerType(state.get("owner_type", "corretor")),
            location={
                "bairro": state.get("bairro"),
                "cidade": state.get("cidade", "Florianópolis")
            },
            land_size_m2=state.get("land_size_m2"),
            asking_price=state.get("asking_price"),
            legal_status=state.get("legal_status"),
            obs=state.get("differentials"),
            next_step=NextStep.AGENDAR_REUNIAO
            if state.get("is_qualified") else NextStep.DISQUALIFIED
        )

        json_output = qualification.model_dump_json(indent=2)

        state["messages"] = state["messages"] + [AIMessage(content=json_output)]
        state["qualification_complete"] = True
        state["next_step"] = qualification.next_step.value

        return state

    # -----------------------------
    # ROUTING LOGIC
    # -----------------------------
    def _route_after_conversation(self, state: QualificationState) -> Literal["extract", "output", "continue"]:
        if isinstance(state["messages"][-1], HumanMessage):
            return "extract"

        if self._has_all_required_data(state):
            return "output"

        return "continue"

    def _route_after_validation(self, state: QualificationState) -> Literal["output", "continue"]:
        if self._has_all_required_data(state):
            return "output"
        return "continue"

    # -----------------------------
    # HELPERS
    # -----------------------------
    def _has_all_required_data(self, state: QualificationState) -> bool:
        return all([
            state.get("bairro"),
            state.get("land_size_m2"),
            state.get("asking_price"),
            state.get("legal_status")
        ])

    def _conversation_as_text(self, messages: List) -> str:
        lines = []
        for m in messages:
            role = "User" if isinstance(m, HumanMessage) else "Assistant"
            lines.append(f"{role}: {m.content}")
        return "\n".join(lines)

    # -----------------------------
    # PUBLIC API
    # -----------------------------
    def run(self, messages: list, conversation_id: str = None) -> dict:
        state = QualificationState(
        messages=messages,
        conversation_id=conversation_id,
        turn_count=len(messages)
        )

        result = self.graph.invoke(state)
        last_message = result["messages"][-1]

        print(result)

        print('LAST MESSAGE:  ', last_message)

        qualification_result = None
        if result.get("qualification_complete"):
            qualification_result = output_parser.parse_qualification(last_message.content)

        is_complete = result.get("qualification_complete", False)
        qualification_status = (
            QualificationStatus.COMPLETE if is_complete 
            else QualificationStatus.IN_PROGRESS
        )

        return {
            "chat_message": last_message.content,
            "qualification_status": qualification_status.value,
            "qualification_result": qualification_result,
            "conversation_id": conversation_id,
        }
        return {
            "response": last_message.content,
            "conversation_id": conversation_id,
            "qualification_complete": result.get("qualification_complete", False),
            "qualification_result": qualification_result,
            "state": result
        }


qualifier_agent = QualifierAgent()
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

# PROMPT DE EXTRAÇÃO ESTRUTURADA
EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Você é um extrator de dados de conversas sobre imóveis.

Analise TODA a conversa abaixo e extraia APENAS as informações que foram CLARAMENTE mencionadas.

Campos para extrair (use null se não mencionado):
- owner_type: APENAS se EXPLICITAMENTE mencionado - "corretor" OU "proprietario" (NÃO INFIRA! Se não for explícito, use null)
- bairro: nome do bairro (ex: "Campeche", "Centro", "Jurerê Internacional")
- cidade: nome da cidade (use "Florianópolis" como padrão, mas verifique se outra cidade foi mencionada)
- land_size_m2: tamanho em metros quadrados como NÚMERO (ex: "450m²" vira 450)
- asking_price: preço em reais como NÚMERO (ex: "850 mil" vira 850000, "1 milhão" vira 1000000)
- legal_status: se possui escritura (ex: "com escritura" vira "Sim", "sem escritura" vira "Não")
- differentials: texto livre sobre diferenciais (ex: "vista mar", "frente para o mar") (Se não for detalhado, como apenas 'sim', use null)
     
CRÍTICO SOBRE bairro e cidade:
- Atente-se a sinônimos das cidades como "Floripa" = "Florianópolis"
- se a cidade for diferente de Florianópolis, o bairro é inválido, caso não tenha sido identificado use 'não informado'

CRÍTICO SOBRE owner_type e legal_status:
- APENAS extraia se o usuário DISSE EXPLICITAMENTE "sou corretor", "sou proprietário", "sou o dono", "é regularizado" etc
- NÃO infira baseado em contexto como "tenho um terreno" ou "vender"
- Se houver QUALQUER dúvida, use null
- Exemplos VÁLIDOS: "Sou corretor" → "corretor", "Sou o proprietário" → "proprietario"
- Exemplos INVÁLIDOS: "Tenho um terreno" → null (não é explícito)
     
CRÍTICO SOBRE differentials:
- Se o diferencial não estiver bem definido, coloque como null

IMPORTANTE: 
- Converta valores em texto para números (850 mil = 850000, 1 milhão = 1000000)
- Se não tiver certeza, use null
- NUNCA infira nenhuma das informações, mantenha null até que elas sejam mencionadas e confirmadas
- Retorne APENAS JSON válido, sem explicações

Exemplo de resposta:
{{"bairro": "Campeche", "land_size_m2": 450, "asking_price": 850000, "legal_status": "Sim", "owner_type": "proprietario", "differentials": "vista mar"}}
"""),
    ("human", "{conversation}")
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
        """
        Constrói o grafo de estados do agente.
        
        Fluxo correto (UMA execução por turno de conversa):
        1. conversation → extract (sempre extrai após conversa)
        2. extract → validate (sempre valida após extração)
        3. validate → Decide:
           - Se completo/desqualificado → output → END
           - Se incompleto → END (aguarda próximo turno/chamada da API)
        
        O "loop" acontece entre chamadas da API, não dentro de uma única execução.
        """
        workflow = StateGraph(QualificationState)

        # Adiciona os nós
        workflow.add_node("conversation", self._conversation_node)
        workflow.add_node("extract", self._llm_extract_node)
        workflow.add_node("validate", self._validate_location_node)
        workflow.add_node("output", self._generate_output_node)

        # Define o ponto de entrada
        workflow.set_entry_point("conversation")

        # conversation → SEMPRE vai para extract
        workflow.add_edge("conversation", "extract")
        
        # extract → SEMPRE vai para validate
        workflow.add_edge("extract", "validate")

        # validate → Decide se finaliza ou aguarda próximo turno
        workflow.add_conditional_edges(
            "validate",
            self._route_after_validation,
            {
                "output": "output",  # Completo → gera output final
                "disqualified": "output", # Desqualificado -> gera o output final
                "end": END           # Incompleto → END (aguarda próxima mensagem do usuário)
            }
        )

        # output → END
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
        """Extrai dados estruturados da conversa usando LLM."""
        conversation_text = self._conversation_as_text(state["messages"])
        
        print(f"\n[EXTRACTION] Processando conversa...")

        try:
            extraction = self.llm.invoke(
                EXTRACTION_PROMPT.format_messages(conversation=conversation_text)
            )
            print(f"[EXTRACTION] Resposta do LLM:\n{extraction.content}\n")
            
            # Usa o método correto do output_parser
            data = output_parser.extract_json_from_text(extraction.content)
            
            if not data:
                print(f"[EXTRACTION ERROR] Não conseguiu parsear JSON da resposta")
                return state
                
            print(f"[EXTRACTION] Dados parseados: {data}")
            
        except Exception as e:
            print(f"[EXTRACTION ERROR] Falha ao processar: {e}")
            return state

        # Atualiza o estado com os dados extraídos (sem sobrescrever)
        for field, value in data.items():
            if value is not None:
                if not state.get(field):  # Só atualiza se ainda não tem valor
                    state[field] = value
                    print(f"[EXTRACTION] Definido {field} = {value}")

        return state

    def _validate_location_node(self, state: QualificationState) -> QualificationState:
        bairro = state.get("bairro")
        print(f"[VALIDATION] Validando localização: {bairro}")
        
        if not bairro:
            print("[VALIDATION] Nenhum bairro fornecido, pulando validação")
            return state

        is_valid, matched, _ = geographic_validator.validate_location(
            bairro=bairro,
            cidade=state.get("cidade")
        )

        state["location_validated"] = True
        state["is_qualified"] = is_valid
        
        print(f"[VALIDATION] Bairro válido: {is_valid}")
        print(f"[VALIDATION] Bairro matched: {matched}")

        if matched:
            state["bairro"] = matched

        return state

    def _generate_output_node(self, state: QualificationState) -> QualificationState:
        """Gera o resultado final da qualificação."""
        print(f"\n[OUTPUT] ========== GERANDO QUALIFICAÇÃO FINAL ==========")
        print(f"[OUTPUT] Bairro: {state.get('bairro')}")
        print(f"[OUTPUT] Cidade: {state.get('cidade')}")
        print(f"[OUTPUT] Tamanho: {state.get('land_size_m2')} m²")
        print(f"[OUTPUT] Preço: R$ {state.get('asking_price')}")
        print(f"[OUTPUT] Status legal: {state.get('legal_status')}")
        print(f"[OUTPUT] Qualificado: {state.get('is_qualified')}")
        print(f"[OUTPUT] ===============================================\n")
        
        # Determinar se o lead foi qualificado
        is_qualified = state.get("is_qualified", False)
        
        # Normalizar legal_status
        legal_status_raw = state.get("legal_status", "")
        if legal_status_raw:
            # Converte "Sim", "sim", "com escritura" → "Sim, possui escritura pública"
            if any(word in legal_status_raw.lower() for word in ["sim", "com escritura", "possui", "regularizado"]):
                legal_status = "Sim, possui escritura pública"
            # Converte "Não", "não", "sem escritura" → "Não possui escritura"
            elif any(word in legal_status_raw.lower() for word in ["não", "nao", "sem escritura"]):
                legal_status = "Não possui escritura"
            else:
                legal_status = legal_status_raw
        else:
            legal_status = "Não informado"
        
        # Valores com fallback para desqualificações
        bairro = state.get("bairro") or "Não especificado"
        cidade = state.get("cidade") or "Florianópolis"
        land_size_m2 = state.get("land_size_m2") or 0.1
        asking_price = state.get("asking_price") or 0.1
        
        qualification = LeadQualification(
            lead_qualified=is_qualified,
            owner_type=OwnerType(state.get("owner_type", "corretor")),
            location={
                "bairro": bairro,
                "cidade": cidade
            },
            land_size_m2=land_size_m2,
            asking_price=asking_price,
            legal_status=legal_status,
            obs=state.get("differentials") or "Nenhuma observação adicional",
            next_step=NextStep.AGENDAR_REUNIAO if is_qualified else NextStep.DISQUALIFIED
        )

        json_output = qualification.model_dump_json(indent=2)
        
        print(f"[OUTPUT] Próximo passo: {qualification.next_step}")

        state["messages"] = state["messages"] + [AIMessage(content=json_output)]
        state["qualification_complete"] = True
        state["next_step"] = qualification.next_step.value

        return state

    # -----------------------------
    # ROUTING LOGIC
    # -----------------------------
    def _route_after_validation(self, state: QualificationState) -> Literal["output", "end"]:
        """
        Decide se finaliza ou aguarda próximo turno após validação.
        
        Finaliza (output) quando:
        1. Tem todos os dados necessários (lead qualificado), OU
        2. Bairro foi validado mas é inválido (lead desqualificado)
        
        Aguarda próximo turno (end) quando:
        - Dados ainda incompletos
        
        O próximo turno será uma nova chamada da API com nova mensagem do usuário.
        """
        has_all_data = self._has_all_required_data(state)
        location_validated = state.get("location_validated", False)
        is_qualified = state.get("is_qualified")
        
        print(f"\n[ROUTING] Pós-validação:")
        print(f"  - Tem todos os dados: {has_all_data}")
        print(f"  - Localização validada: {location_validated}")
        print(f"  - É qualificado: {is_qualified}")
        
        # Se validou localização e NÃO é qualificado → desqualificado, finalizar
        if location_validated and is_qualified == False:
            print("[ROUTING] ✅ Lead DESQUALIFICADO (bairro inválido) → OUTPUT\n")
            return "output"
        
        # Se tem todos os dados necessários → finalizar
        if has_all_data:
            print("[ROUTING] ✅ Todos os dados coletados → OUTPUT\n")
            return "output"
        
        # Senão, aguardar próximo turno (nova mensagem do usuário)
        print("[ROUTING] ⏸️  Dados incompletos → END (aguardando próximo turno)\n")
        return "end"

    # -----------------------------
    # HELPERS
    # -----------------------------
    def _has_all_required_data(self, state: QualificationState) -> bool:
        """
        Verifica se todos os dados obrigatórios foram coletados.
        
        Dados obrigatórios (6 campos):
        1. owner_type (corretor ou proprietário)
        2. bairro
        3. land_size_m2
        4. asking_price
        5. legal_status
        6. (differentials é opcional)
        """
        required_fields = {
            "owner_type": state.get("owner_type"),
            "bairro": state.get("bairro"),
            "land_size_m2": state.get("land_size_m2"),
            "asking_price": state.get("asking_price"),
            "legal_status": state.get("legal_status"),
            "differentials": state.get("differentials")
        }
        
        # Debug: mostrar quais campos estão faltando
        missing = [k for k, v in required_fields.items() if not v]
        if missing:
            print(f"[HAS_ALL_DATA] Campos faltando: {missing}")
        
        return all(required_fields.values())

    def _conversation_as_text(self, messages: List) -> str:
        """Converte mensagens em texto para o LLM de extração."""
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

        qualification_result = None
        if result.get("qualification_complete"):
            qualification_result = output_parser.parse_qualification(last_message.content)

        is_complete = result.get("qualification_complete", False)
        qualification_status = (
            QualificationStatus.COMPLETE if is_complete 
            else QualificationStatus.IN_PROGRESS
        )

        if is_complete:
            last_message = result["messages"][-2]

        return {
            "chat_message": last_message.content,
            "qualification_status": qualification_status.value,
            "qualification_result": qualification_result,
            "conversation_id": conversation_id,
        }


qualifier_agent = QualifierAgent()
"""
Streamlit Frontend for Terra Qualifier Agent.

This module provides an interactive chat interface for
testing and using the qualification agent.
"""

import json
from datetime import datetime
from typing import Optional

import httpx
import streamlit as st

# Configuration
API_URL = "http://localhost:8000"

# Page config
st.set_page_config(
    page_title="Terra - Qualifier Agent",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .user-message {
        background-color: #e3f2fd;
        border-left: 4px solid #2196f3;
    }
    .agent-message {
        background-color: #f5f5f5;
        border-left: 4px solid #4caf50;
    }
    .qualification-result {
        background-color: #fff3e0;
        border: 2px solid #ff9800;
        border-radius: 0.5rem;
        padding: 1.5rem;
        margin-top: 1rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize Streamlit session state."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = None
    if "qualification_result" not in st.session_state:
        st.session_state.qualification_result = None
    if "api_status" not in st.session_state:
        st.session_state.api_status = None


def check_api_health() -> bool:
    """
    Check if the API is running.
    
    Returns:
        True if API is healthy
    """
    try:
        response = httpx.get(f"{API_URL}/health", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False


def send_message(message: str) -> Optional[dict]:
    """
    Send message to the API.
    
    Args:
        message: User message
    
    Returns:
        API response dict or None if failed
    """
    try:
        response = httpx.post(
            f"{API_URL}/api/chat",
            json={
                "message": message,
                "conversation_id": st.session_state.conversation_id
            },
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Erro ao comunicar com API: {e}")
        return None


def display_qualification_result(result: dict):
    """Display qualification result in a nice format."""
    st.markdown("### 📋 Resultado da Qualificação")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status = "✅ Qualificado" if result["lead_qualified"] else "❌ Desqualificado"
        st.markdown(f"**Status:** {status}")
    
    with col2:
        st.markdown(f"**Tipo:** {result['owner_type']}")
    
    with col3:
        st.markdown(f"**Próximo Passo:** {result['next_step']}")
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**📍 Localização:**")
        st.write(f"Bairro: {result['location']['bairro']}")
        st.write(f"Cidade: {result['location']['cidade']}")
        
        st.markdown("**📏 Tamanho:**")
        st.write(f"{result['land_size_m2']} m²")
    
    with col2:
        st.markdown("**💰 Valor:**")
        st.write(f"R$ {result['asking_price']:,.2f}")
        
        st.markdown("**📜 Situação Jurídica:**")
        st.write(result['legal_status'])
    
    if result.get("obs"):
        st.markdown("**🎯 Observações:**")
        st.info(result['obs'])
    
    # JSON download
    st.markdown("---")
    st.download_button(
        label="📥 Download JSON",
        data=json.dumps(result, indent=2, ensure_ascii=False),
        file_name=f"qualification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json"
    )


def main():
    """Main application."""
    init_session_state()
    
    # Header
    st.markdown('<div class="main-header">🏢 Terra - Qualifier Agent</div>', 
                unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Agente de Pré-Qualificação Imobiliária</div>', 
                unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown("## ⚙️ Configurações")
        
        # API Status
        api_healthy = check_api_health()
        status_emoji = "🟢" if api_healthy else "🔴"
        status_text = "Online" if api_healthy else "Offline"
        
        st.markdown(f"**Status da API:** {status_emoji} {status_text}")
        
        if not api_healthy:
            st.warning("⚠️ API não está respondendo. Certifique-se de que o backend está rodando.")
            st.code("python src/backend/main.py", language="bash")
        
        st.markdown("---")
        
        # Conversation controls
        st.markdown("## 💬 Conversa")
        
        if st.button("🔄 Nova Conversa", use_container_width=True):
            st.session_state.messages = []
            st.session_state.conversation_id = None
            st.session_state.qualification_result = None
            st.rerun()
        
        if st.session_state.conversation_id:
            st.text_input(
                "ID da Conversa",
                value=st.session_state.conversation_id,
                disabled=True
            )
        
        # Metrics
        if st.session_state.messages:
            st.markdown("---")
            st.markdown("## 📊 Métricas")
            
            total_messages = len(st.session_state.messages)
            user_messages = sum(1 for m in st.session_state.messages if m["role"] == "user")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total", total_messages)
            with col2:
                st.metric("Usuário", user_messages)
        
        st.markdown("---")
        
        # Info
        st.markdown("## ℹ️ Sobre")
        st.markdown("""
        Este agente qualifica terrenos para investimento imobiliário.
        
        **Áreas de Atuação:**
        - Centro
        - Itacorubi
        - Campeche
        - Jurerê Internacional
        
        **Dados Coletados:**
        - Localização
        - Tamanho (m²)
        - Valor (R$)
        - Situação Jurídica
        - Diferenciais
        """)
    
    # Main chat area
    if not api_healthy:
        st.error("⚠️ API não está disponível. Inicie o backend primeiro.")
        return
    
    # Display chat messages
    chat_container = st.container()
    
    with chat_container:
        for message in st.session_state.messages:
            role = message["role"]
            content = message["content"]
            
            if role == "user":
                st.markdown(
                    f'<div class="chat-message user-message"><strong>Você:</strong><br>{content}</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div class="chat-message agent-message"><strong>Terra:</strong><br>{content}</div>',
                    unsafe_allow_html=True
                )
    
    # Display qualification result if complete
    if st.session_state.qualification_result:
        with st.container():
            display_qualification_result(st.session_state.qualification_result)
    
    # Chat input
    with st.container():
        col1, col2 = st.columns([6, 1])
        
        with col1:
            user_input = st.text_input(
                "Digite sua mensagem",
                key="user_input",
                placeholder="Ex: Tenho um terreno no Campeche...",
                label_visibility="collapsed"
            )
        
        with col2:
            send_button = st.button("Enviar", use_container_width=True, type="primary")
        
        if send_button and user_input:
            # Add user message
            st.session_state.messages.append({
                "role": "user",
                "content": user_input
            })
            
            # Send to API
            with st.spinner("Terra está pensando..."):
                response = send_message(user_input)
            
            if response:
                # Update conversation ID
                st.session_state.conversation_id = response["conversation_id"]
                
                # Add agent response
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response["response"]
                })
                
                # Check if qualification is complete
                if response.get("qualification_complete"):
                    st.session_state.qualification_result = response["qualification_result"]
                    st.balloons()
                
                st.rerun()


if __name__ == "__main__":
    main()
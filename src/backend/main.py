"""
FastAPI application for Terra Qualifier Agent.

This module provides REST API endpoints for:
- Chat interactions
- Qualification retrieval
- Health checks
"""

import logging
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict

import mlflow
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from agents.qualifier_agent import qualifier_agent
from config import settings
from models.schemas import ChatRequest, ChatResponse

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# In-memory conversation storage (in production, use Redis/DB)
conversations: Dict[str, list] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting Terra Qualifier API...")
    logger.info(f"LLM Provider: {settings.llm_provider}")
    
    # Initialize MLflow
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment_name)
    logger.info(f"MLflow tracking: {settings.mlflow_tracking_uri}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Terra Qualifier API...")


# Create FastAPI app
app = FastAPI(
    title="Terra Qualifier Agent API",
    description="AI-powered lead qualification agent for real estate properties",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Terra Qualifier Agent API",
        "version": "1.0.0",
        "status": "running",
        "llm_provider": settings.llm_provider.value,
        "endpoints": {
            "chat": "/api/chat",
            "health": "/health",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "llm_provider": settings.llm_provider.value
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint for interacting with the Terra agent.
    
    Args:
        request: Chat request with user message
    
    Returns:
        ChatResponse with agent response and qualification status
    
    Raises:
        HTTPException: If processing fails
    """
    try:
        logger.info(f"Chat request: {request.message[:50]}...")
        
        # Start MLflow run
        with mlflow.start_run(run_name=f"chat_{request.conversation_id or 'new'}"):
            # Log input
            mlflow.log_param("llm_provider", settings.llm_provider.value)
            mlflow.log_param("model", 
                           settings.groq_model if settings.llm_provider.value == "groq" 
                           else settings.gemini_model)
            mlflow.log_param("conversation_id", request.conversation_id)
            
            start_time = datetime.utcnow()
            
            # Run agent

            # Recupera ou cria conversa
            conv_id = request.conversation_id or str(uuid.uuid4())

            if conv_id not in conversations:
                conversations[conv_id] = []

            # 🔑 monta histórico no formato LangChain
            messages = []

            for turn in conversations[conv_id]:
                messages.append(HumanMessage(content=turn["user"]))
                messages.append(AIMessage(content=turn["agent"]))

            # adiciona nova mensagem do usuário
            messages.append(HumanMessage(content=request.message))

            # roda o agente COM CONTEXTO
            result = qualifier_agent.run(
                messages=messages,
                conversation_id=conv_id
            )

            print(result)
            # Calculate metrics
            end_time = datetime.utcnow()
            response_time = (end_time - start_time).total_seconds()
            
            
            # Store conversation
            conv_id = result["conversation_id"]
            if conv_id not in conversations:
                conversations[conv_id] = []
            
            conversations[conv_id].append({
                "timestamp": datetime.utcnow().isoformat(),
                "user": request.message,
                "agent": result["chat_message"],
                "qualification_status": result["qualification_status"]
            })
            
            logger.info(f"Response generated in {response_time:.2f}s")
            
            # Build response
            response = ChatResponse(
                response=result["chat_message"],
                conversation_id=conv_id,
                qualification_status=result["qualification_status"],
                qualification_result=result.get("qualification_result"),
            )

            print('RESPONSE:\n\n', response)
            
            return response
    
    except Exception as e:
        logger.error(f"Error processing chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """
    Retrieve conversation history.
    
    Args:
        conversation_id: Conversation ID
    
    Returns:
        Conversation history
    
    Raises:
        HTTPException: If conversation not found
    """
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {
        "conversation_id": conversation_id,
        "messages": conversations[conversation_id]
    }


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """
    Delete conversation history.
    
    Args:
        conversation_id: Conversation ID
    
    Returns:
        Deletion confirmation
    """
    if conversation_id in conversations:
        del conversations[conversation_id]
        return {"message": "Conversation deleted", "conversation_id": conversation_id}
    
    raise HTTPException(status_code=404, detail="Conversation not found")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True
    )
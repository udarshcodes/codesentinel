import pytest
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq

def test_llm_instantiation():
    llm1 = ChatOpenAI(model="gpt-4o-mini", api_key="fake")
    assert llm1 is not None

    llm2 = ChatGroq(model="qwen/qwen3.6-27b", api_key="fake")
    assert llm2 is not None

def test_langgraph_imports():
    from langgraph.graph import StateGraph, END
    assert StateGraph is not None
    assert END is not None

def test_llm_router_imports():
    from tools.llm_router import invoke_llm, PRIMARY_MODELS
    assert invoke_llm is not None
    assert len(PRIMARY_MODELS) > 0

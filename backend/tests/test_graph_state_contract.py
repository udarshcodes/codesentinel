from langgraph.graph import StateGraph, END
from models.pipeline_state import PipelineState
from orchestrator import get_entry_node


def test_real_graph_preserves_resume_cursor_when_filtering_input_state():
    graph = StateGraph(PipelineState)
    graph.add_node('fresh', lambda state: {'status': 'FRESH'})
    graph.add_node('resumed', lambda state: {'status': 'RESUMED'})
    graph.set_conditional_entry_point(get_entry_node, {'repo_mapper': 'fresh', 'dependency_analyzer': 'resumed'})
    graph.add_edge('fresh', END)
    graph.add_edge('resumed', END)
    result = graph.compile().invoke({'last_completed_node': 'repo_mapper'})
    assert result['status'] == 'RESUMED'


def test_real_graph_security_retry_counter_survives_node_updates():
    graph = StateGraph(PipelineState)
    graph.add_node('verify', lambda state: {'security_retry_count': state.get('security_retry_count', 0) + 1})
    graph.set_entry_point('verify')
    graph.add_conditional_edges('verify', lambda state: END if state['security_retry_count'] >= 3 else 'verify')
    result = graph.compile().invoke({'security_retry_count': 0})
    assert result['security_retry_count'] == 3

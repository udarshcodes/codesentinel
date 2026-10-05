import { describe, it, expect } from 'vitest';
import { reconstructProgress, AGENT_ORDER } from '../pipelineProgress';

describe('reconstructProgress', () => {
  it('1. last_completed_node = repo_mapper (RUNNING)', () => {
    const state = {
      status: 'RUNNING',
      last_completed_node: 'repo_mapper',
      completed_nodes: [] // missing event history
    };
    const result = reconstructProgress(state);
    expect(result.completedAgents.has('repo_mapper')).toBe(true);
    expect(result.currentAgent).toBe('dependency_analyzer');
    expect(result.skippedAgents.size).toBe(0);
  });

  it('2. last_completed_node = dependency_analyzer (FAILED)', () => {
    const state = {
      status: 'FAILED',
      last_completed_node: 'dependency_analyzer',
      completed_nodes: []
    };
    const result = reconstructProgress(state);
    expect(result.completedAgents.has('repo_mapper')).toBe(true);
    expect(result.completedAgents.has('dependency_analyzer')).toBe(true);
    expect(result.currentAgent).toBe('static_analysis');
    expect(result.isError).toBe(true);
  });

  it('3. last_completed_node = static_analysis (RUNNING)', () => {
    const state = {
      status: 'RUNNING',
      last_completed_node: 'static_analysis',
      completed_nodes: []
    };
    const result = reconstructProgress(state);
    expect(result.completedAgents.has('repo_mapper')).toBe(true);
    expect(result.completedAgents.has('dependency_analyzer')).toBe(true);
    expect(result.completedAgents.has('static_analysis')).toBe(true);
    expect(result.currentAgent).toBe('bug_investigator');
  });

  it('4. last_completed_node = pr_author (COMPLETED)', () => {
    const state = {
      status: 'COMPLETED',
      last_completed_node: 'pr_author',
      completed_nodes: []
    };
    const result = reconstructProgress(state);
    AGENT_ORDER.forEach(agent => {
      expect(result.completedAgents.has(agent)).toBe(true);
    });
    expect(result.currentAgent).toBeNull();
  });

  it('5. completed_nodes present, last_completed_node missing (COMPLETED)', () => {
    const state = {
      status: 'COMPLETED',
      completed_nodes: ['repo_mapper', 'dependency_analyzer']
    };
    const result = reconstructProgress(state);
    expect(result.completedAgents.has('repo_mapper')).toBe(true);
    expect(result.completedAgents.has('dependency_analyzer')).toBe(true);
    expect(result.completedAgents.has('static_analysis')).toBe(false);
    expect(result.currentAgent).toBeNull();
  });

  it('6. completed_nodes missing completely, status RUNNING', () => {
    const state = {
      status: 'RUNNING'
    };
    const result = reconstructProgress(state);
    expect(result.completedAgents.size).toBe(0);
    expect(result.currentAgent).toBe('repo_mapper');
  });

  it('7. status RUNNING + some nodes completed', () => {
    const state = {
      status: 'RUNNING',
      completed_nodes: ['repo_mapper', 'dependency_analyzer'],
      last_completed_node: 'dependency_analyzer'
    };
    const result = reconstructProgress(state);
    expect(result.completedAgents.size).toBe(2);
    expect(result.currentAgent).toBe('static_analysis');
  });

  it('8. status COMPLETED without last_completed_node uses completed_nodes', () => {
    const state = {
      status: 'COMPLETED',
      completed_nodes: ['repo_mapper', 'pr_author']
    };
    const result = reconstructProgress(state);
    expect(result.completedAgents.has('repo_mapper')).toBe(true);
    expect(result.completedAgents.has('pr_author')).toBe(true);
    expect(result.currentAgent).toBeNull();
  });

  it('9. status FAILED with no progress information', () => {
    const state = {
      status: 'FAILED',
      completed_nodes: []
    };
    const result = reconstructProgress(state);
    expect(result.completedAgents.size).toBe(0);
    expect(result.currentAgent).toBe('repo_mapper'); // The first one failed
    expect(result.isError).toBe(true);
  });

  it('10. status WAITING_FOR_APPROVAL', () => {
    const state = {
      status: 'WAITING_FOR_APPROVAL',
      last_completed_node: 'bug_investigator'
    };
    const result = reconstructProgress(state);
    expect(result.completedAgents.has('bug_investigator')).toBe(true);
    expect(result.completedAgents.has('static_analysis')).toBe(true);
    expect(result.currentAgent).toBe('repair_planner'); // Overridden correctly
    expect(result.isPaused).toBe(true);
  });

  it('11. no progress information at all', () => {
    const state = {
      status: 'QUEUED'
    };
    const result = reconstructProgress(state);
    expect(result.completedAgents.size).toBe(0);
    expect(result.currentAgent).toBeNull();
  });

  it('12. incomplete event history but last_completed_node exists', () => {
    const state = {
      status: 'RUNNING',
      completed_nodes: ['dependency_analyzer'], // missing repo_mapper
      last_completed_node: 'dependency_analyzer'
    };
    const result = reconstructProgress(state);
    // reconstructProgress should fill in the gap for repo_mapper
    expect(result.completedAgents.has('repo_mapper')).toBe(true);
    expect(result.completedAgents.has('dependency_analyzer')).toBe(true);
    expect(result.currentAgent).toBe('static_analysis');
  });
});

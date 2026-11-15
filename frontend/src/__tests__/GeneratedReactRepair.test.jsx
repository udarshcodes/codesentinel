import React, { useState, useEffect } from 'react';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

// Exercise the actual Python repair against a component with the Portfolio contract.
// Plain createElement keeps this cross-runtime fixture independent of a JSX compiler.
const source = `function Popup({ theme, toggleTheme }) {
  const [isVisible, setIsVisible] = useState(false);
  useEffect(() => {
    if (theme !== 'light') {
      setIsVisible(false);
      return;
    }
    if (localStorage.getItem('themeSuggestionDismissed')) return;
    const timer = setTimeout(() => setIsVisible(true), 2500);
    return () => clearTimeout(timer);
  }, [theme]);
  const dismiss = () => {
    setIsVisible(false);
    localStorage.setItem('themeSuggestionDismissed', 'true');
  };
  const switchTheme = () => { dismiss(); toggleTheme(); };
  if (!isVisible) return null;
  return React.createElement('div', null,
    React.createElement('button', { onClick: dismiss }, 'Dismiss'),
    React.createElement('button', { onClick: switchTheme }, 'Switch theme'));
}`;

const backend = path.resolve(globalThis.process.cwd(), '../backend');
const repaired = execFileSync('python', ['-c', `import json,sys
from tools.remediations import deferred_effect_state_patch
source=json.load(sys.stdin)
patch=deferred_effect_state_patch(source,5)
assert patch
old,new=patch.split('<<<REPLACE>>>',1)
old=old.removeprefix('<<<SEARCH>>>\\n').rstrip('\\n')
new=new.removeprefix('\\n').rstrip('\\n')
assert source.count(old)==1
print(json.dumps(source.replace(old,new,1)))
`], { input: JSON.stringify(source), encoding: 'utf8', env: { ...globalThis.process.env, PYTHONPATH: backend }, cwd: path.resolve(backend, '..') });
const Popup = new Function('React', 'useState', 'useEffect', `${JSON.parse(repaired)}; return Popup;`)(React, useState, useEffect);

afterEach(() => { cleanup(); vi.useRealTimers(); localStorage.clear(); });

describe('generated React effect repair behavior', () => {
  it('preserves the delay and closes immediately on dismiss', () => {
    vi.useFakeTimers();
    render(<Popup theme="light" toggleTheme={() => {}} />);
    expect(screen.queryByRole('button', { name: 'Dismiss' })).toBeNull();
    act(() => vi.advanceTimersByTime(2499));
    expect(screen.queryByRole('button', { name: 'Dismiss' })).toBeNull();
    act(() => vi.advanceTimersByTime(1));
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(screen.queryByRole('button', { name: 'Dismiss' })).toBeNull();
    expect(localStorage.getItem('themeSuggestionDismissed')).toBe('true');
  });

  it('resets visibility on dark mode and retains the switch action', () => {
    vi.useFakeTimers();
    const toggle = vi.fn();
    const view = render(<Popup theme="light" toggleTheme={toggle} />);
    act(() => vi.advanceTimersByTime(2500));
    view.rerender(<Popup theme="dark" toggleTheme={toggle} />);
    act(() => vi.advanceTimersByTime(0));
    expect(screen.queryByRole('button', { name: 'Dismiss' })).toBeNull();
    view.rerender(<Popup theme="light" toggleTheme={toggle} />);
    act(() => vi.advanceTimersByTime(2499));
    expect(screen.queryByRole('button', { name: 'Dismiss' })).toBeNull();
    act(() => vi.advanceTimersByTime(1));
    fireEvent.click(screen.getByRole('button', { name: 'Switch theme' }));
    expect(toggle).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: 'Dismiss' })).toBeNull();
  });
});

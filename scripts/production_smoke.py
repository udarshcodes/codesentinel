"""Exercise production from a remote runner; never starts a local application.

Repository analysis is opt-in and uses the same public UI as a visitor.
Screenshots and a credential-free report remain available on failure.
"""
import json
import os
from pathlib import Path
import time

from playwright.sync_api import sync_playwright


def main():
    site = os.environ['SMOKE_SITE_URL'].rstrip('/')
    api = os.environ['SMOKE_API_URL'].rstrip('/')
    repo = os.getenv('SMOKE_REPO_URL', '').strip()
    evidence = Path('smoke-evidence')
    evidence.mkdir(exist_ok=True)
    report = {'checks': [], 'errors': []}

    def check(name, condition, detail=''):
        report['checks'].append({'name': name, 'passed': bool(condition), 'detail': detail})
        print(('PASS ' if condition else 'FAIL ') + name + (': ' + detail if detail else ''), flush=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=os.getenv('SMOKE_BROWSER_CHANNEL') or None)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: report['errors'].append(str(error)))
        try:
            for route in ['/health', '/live', '/ready']:
                try:
                    response = page.request.get(api + route, timeout=30000)
                    check(route, response.status == 200, str(response.status))
                except Exception as error:
                    check(route, False, str(error))
            try:
                response = page.request.get(api + '/api/v1/admin/telemetry', timeout=30000)
                check('Admin telemetry requires authentication', response.status == 401, str(response.status))
                response = page.request.get(api + '/admin', timeout=30000)
                check('Admin UI is bundled', response.status == 200 and 'id="root"' in response.text())
            except Exception as error:
                check('Admin endpoints respond', False, str(error))

            for width in [390, 768, 1024, 1440]:
                page.set_viewport_size({'width': width, 'height': 1000})
                page.goto(site, wait_until='domcontentloaded', timeout=60000)
                page.get_by_role('heading', level=1).wait_for()
                page.screenshot(path=str(evidence / f'landing-{width}.png'))
                dimensions = page.evaluate('({width: document.documentElement.clientWidth, content: document.documentElement.scrollWidth})')
                check(f'No horizontal overflow at {width}px', dimensions['content'] <= dimensions['width'])
                nav = page.get_by_role('navigation', name='Main navigation')
                check(f'Navigation exists at {width}px', nav.count() == 1)
                if width < 1536 and nav.count():
                    nav.get_by_text('Menu', exact=True).click()
                    nav.get_by_role('link', name='Analyze Repository', exact=True).click(no_wait_after=True)
                else:
                    page.get_by_role('button', name='Analyze Repository', exact=True).first.click(no_wait_after=True)
                field = page.get_by_role('textbox', name='Repository URL', exact=True)
                field.wait_for(state='visible')
                page.screenshot(path=str(evidence / f'analyzer-{width}.png'))

            # Invalid input must be rejected before any backend request or workspace transition.
            field.fill('https://example.com/owner/repository')
            field.press('Enter')
            check('Invalid URL rejected inline', page.get_by_role('alert').count() == 1)
            check('Invalid URL keeps form available', field.is_visible())
            check('No uncaught UI errors', not report['errors'], '; '.join(report['errors']))

            if repo:
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.goto(site, wait_until='domcontentloaded')
                page.get_by_role('textbox', name='Repository URL', exact=True).fill(repo)
                page.get_by_role('button', name='Analyze', exact=True).click()
                page.wait_for_function('new URLSearchParams(location.search).has("task")', timeout=90000)
                task = page.evaluate('new URLSearchParams(location.search).get("task")')
                check('Analysis task created through deployed UI', bool(task), task)
                initial_color = page.locator('body').evaluate('element => getComputedStyle(element).backgroundColor')
                page.get_by_role('button', name='Toggle theme').click()
                page.wait_for_timeout(100)
                changed_color = page.locator('body').evaluate('element => getComputedStyle(element).backgroundColor')
                check('Theme toggle changes dashboard appearance', initial_color != changed_color)
                page.get_by_role('button', name='Toggle theme').click()
                page.reload(wait_until='domcontentloaded')
                page.get_by_role('heading', name='Analysis Workspace', exact=True).wait_for()
                check('Reload restores the selected analysis', page.evaluate('new URLSearchParams(location.search).get("task")') == task)
                deadline = time.monotonic() + 1500
                state = {}
                while time.monotonic() < deadline:
                    # Read only this task's view capability from the browser session.
                    # It is used in memory and never stored in report or screenshots.
                    state = page.evaluate('''async ({api, task}) => {
                        const token = sessionStorage.getItem(`view_token_${task}`);
                        const response = await fetch(`${api}/api/v1/job/${encodeURIComponent(task)}/view`, {
                            headers: token ? {Authorization: `Bearer ${token}`} : {},
                            signal: AbortSignal.timeout(30000)
                        });
                        if (!response.ok) return {http_status: response.status};
                        const data = await response.json();
                        return {status: data.status, pipeline: data.pipeline_state};
                    }''', {'api': api, 'task': task})
                    status = state.get('status')
                    print('Analysis status: ' + str(status or state.get('http_status')), flush=True)
                    if status in {'COMPLETED', 'FAILED', 'NEEDS_REVIEW', 'WAITING_FOR_APPROVAL'}:
                        break
                    page.wait_for_timeout(15000)
                pipeline = state.get('pipeline') or {}
                report['analysis'] = {key: pipeline.get(key) for key in [
                    'pr_url', 'pr_error', 'confidence_score', 'security_verified',
                    'validation_results', 'scanner_notes', 'pipeline_error', 'rag_status', 'dependency_blocked_files']}
                report['analysis']['status'] = state.get('status')
                page.screenshot(path=str(evidence / 'analysis-result.png'), full_page=True)
                for label, section in [('Findings', '#findings-section'), ('Patches', '#patches-section')]:
                    page.get_by_role('button', name=label, exact=True).click()
                    check(f'{label} section is available', page.locator(section).count() == 1)
                for width in [390, 768, 1440]:
                    page.set_viewport_size({'width': width, 'height': 1000})
                    dimensions = page.evaluate('({width: document.documentElement.clientWidth, content: document.documentElement.scrollWidth})')
                    check(f'Dashboard has no horizontal overflow at {width}px', dimensions['content'] <= dimensions['width'])
                    page.get_by_role('button', name='Overview', exact=True).click()
                    page.screenshot(path=str(evidence / f'dashboard-{width}.png'))
                    if state.get('status') in {'COMPLETED', 'FAILED', 'NEEDS_REVIEW'}:
                        check(f'Outcome summary is available at {width}px', page.locator('#pr-summary').count() == 1)
                        page.get_by_role('button', name='Pull Request', exact=True).click()
                        page.wait_for_function('''() => {
                            const rect = document.querySelector('#pr-summary').getBoundingClientRect();
                            return rect.top < innerHeight && rect.bottom > 0;
                        }''')
                        page.wait_for_timeout(700)
                        page.screenshot(path=str(evidence / f'outcome-{width}.png'))
                check('Analysis reached a terminal outcome', state.get('status') in {'COMPLETED', 'FAILED', 'NEEDS_REVIEW'})
                check('Analysis fully completed', state.get('status') == 'COMPLETED')
                if pipeline.get('material_files') or pipeline.get('patches'):
                    check('Security verification passed for generated changes', pipeline.get('security_verified') is True)
                    check('Pull request was produced for generated changes', bool(pipeline.get('pr_url')))
        except Exception as error:
            check('Smoke workflow completed', False, str(error))
            page.screenshot(path=str(evidence / 'failure.png'))
        finally:
            browser.close()
            (evidence / 'report.json').write_text(json.dumps(report, indent=2))
    if any(not item['passed'] for item in report['checks']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()

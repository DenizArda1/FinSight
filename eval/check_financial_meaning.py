"""Run five fixed source-meaning checks with the configured Critic (uses the API)."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from src.agents.agent_states import create_initial_state
from src.agents.critic import run_critic
from src.utils.utils import load_json, load_yaml, save_json
from src.verification.agent_answer import (
    build_agent_evidence, build_fact_catalog, compose_template, render_agent_template,
)


async def evaluate_cases(cases, config):
    results = []
    for case in cases:
        state = create_initial_state(case['question'])
        state['request_type'] = 'mixed'
        state['trace'] = [{
            'type': 'tool', 'status': 'completed', 'name': 'search_company_updates', 'arguments': {},
            'result': {'matches': [{'text': case['source_text'],
                                    'metadata': {'section': 'Synthetic regression fixture'}}]},
        }]
        state['evidence'] = build_agent_evidence(state['trace'])
        state['composition'] = {'kind': 'answer', 'facts': [], 'text': case['text']}
        catalog = build_fact_catalog(state['evidence'])
        template = compose_template(state['composition'], catalog)
        state['draft'] = render_agent_template(template, state['evidence'])
        await run_critic(state, config, locate_repairs=True)
        verdict = state['verification']
        matched = verdict['status'] != 'error' and verdict['supported'] == case['expected_supported']
        results.append({'id': case['id'], 'expected_supported': case['expected_supported'],
                        'matched': matched, 'verification': verdict})
        print(f"{case['id']}: {'matched' if matched else 'FAILED'}", flush=True)
    return results


def main():
    root = Path(__file__).resolve().parents[1]
    cases = load_json(root / 'eval/diagnostics/financial_meaning_cases.json')
    config = load_yaml(root / 'configs/settings.yaml')['llm']
    results = asyncio.run(evaluate_cases(cases, config))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = root / 'eval/results' / f'financial_meaning_{stamp}.json'
    save_json(results, output)
    print(output)
    if not all(row['matched'] for row in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()

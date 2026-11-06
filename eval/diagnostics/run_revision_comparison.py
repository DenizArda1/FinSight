"""Compare full and paragraph revisions on identical saved tool evidence.

This is a development replay, not a fresh MCP run or an accuracy benchmark.
Model verdicts and independent reviews are deliberately stored separately.
"""

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from jsonschema import Draft202012Validator

from src.agents.agent_states import create_initial_state
from src.agents.critic import run_critic
from src.agents.writer import run_writer
from src.utils.utils import load_yaml, save_json
from src.verification.agent_answer import (
    build_agent_evidence, build_fact_catalog, composition_schema, compose_template, render_agent_template,
)

ROOT = Path(__file__).resolve().parents[2]
CASES = {
    "msft_mixed_tr": ("project_audit_microsoft_20261030.json", None),
    "nvda_export_risk_en": ("nvda_bilingual_multi_agent_mcp_20261024T144127_752034Z_7b4d5b7e.json", "nvda_export_risk_en"),
}


def load_case(case_id):
    filename, saved_id = CASES[case_id]
    path = ROOT / "eval/results" / filename
    raw = path.read_bytes()
    data = json.loads(raw)
    saved = next(row for row in data if row["id"] == saved_id) if saved_id else data["state"]
    state = create_initial_state(saved["question"])
    state["request_type"] = saved.get("request_type") or "filing"
    state["trace"] = deepcopy([event for event in saved["trace"] if event.get("type") == "tool"])
    state["evidence"] = build_agent_evidence(state["trace"])
    catalog = build_fact_catalog(state["evidence"])
    # Select the first saved Writer output, not the best-looking revision.
    event = next(event for event in saved["trace"] if event.get("type") == "model"
                 and event.get("phase") == "writer" and event.get("status") == "completed")
    state["composition"] = json.loads(event["content"])
    Draft202012Validator(composition_schema(catalog, state["request_type"], state["evidence"])).validate(state["composition"])
    state["draft"] = render_agent_template(compose_template(state["composition"], catalog), state["evidence"])
    return state, {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(raw).hexdigest()}


def candidate_snapshot(state):
    return {key: deepcopy(state[key]) for key in ("composition", "draft", "verification", "revision_count")}


async def compare_case(state, config, max_revisions, checkpoint, initial_feedback=None):
    branches = {}
    for mode in ("full", "paragraph"):
        current = deepcopy(state)
        branch = {"candidates": [], "review": None, "state": current}
        branches[mode] = branch
        started = perf_counter()
        try:
            for revision in range(max_revisions + 1):
                current["revision_count"] = revision
                if revision == 0 and initial_feedback is not None:
                    current["verification"] = {
                        "status": "failed", "supported": False,
                        "method": "assistant_source_review_control", **deepcopy(initial_feedback),
                    }
                else:
                    await run_critic(current, config, locate_repairs=(mode == "paragraph"))
                branch["candidates"].append(candidate_snapshot(current))
                verdict = current["verification"]
                print(mode, revision, verdict["status"], verdict["issues"], flush=True)
                checkpoint(branches)
                if verdict["status"] != "failed" or revision == max_revisions:
                    break
                feedback = {
                    "previous_composition": deepcopy(current["composition"]),
                    "issues": deepcopy(verdict["issues"]),
                }
                if mode == "paragraph":
                    targets = verdict.get("repair_targets", [])
                    if not targets:
                        branch["stop_reason"] = "Critic failed without usable paragraph targets"
                        break
                    feedback["repair_targets"] = targets
                await run_writer(current, config, feedback)
        except Exception as error:
            branch["error"] = {"type": type(error).__name__, "message": str(error)}
        finally:
            branch["elapsed_seconds"] = perf_counter() - started
            model_events = [event for event in current["trace"] if event.get("type") == "model"]
            branch["usage"] = {key: sum(event[key] for event in model_events if key in event)
                               for key in ("input_tokens", "output_tokens")
                               if any(key in event for event in model_events)}
            checkpoint(branches)
    return branches


async def main(args):
    if not 0 <= args.max_revisions <= 2:
        raise ValueError("Choose zero, one or two revisions")
    selected = args.case or list(CASES)
    prepared = [(case_id, *load_case(case_id)) for case_id in selected]
    initial_feedback = None
    if args.fixed_feedback:
        if selected != ["msft_mixed_tr"] or args.max_revisions != 1:
            raise ValueError("Fixed-feedback control requires --case msft_mixed_tr --max-revisions 1")
        state = prepared[0][1]
        # An explicit counterfactual isolates repair ability from Critic detection.
        # This is a constructed control, not a claimed naturally generated answer.
        state["composition"] = {"kind": "answer", "facts": [], "text": (
            "Microsoft'un FY{{2:records/0/fiscal_year}} döneminde (dönem sonu: {{2:records/0/end}}) "
            "geliri {{2:records/0/value}} {{2:records/0/unit}}, satışların maliyeti "
            "{{3:records/0/value}} {{3:records/0/unit}} ve faaliyet giderleri "
            "{{4:records/0/value}} {{4:records/0/unit}} olarak raporlandı. "
            "Satışların maliyeti ve faaliyet giderleri ayrı gider kalemleridir.\n\n"
            "ABD dolarının değer kazanması, uluslararası operasyonlardan raporlanan geliri artırmış, "
            "raporlanan giderler üzerinde önemli bir etki yaratmamıştır. Ticaret politikası değişiklikleri "
            "tedarik zinciri zorlukları ve maliyet oynaklığı yaratarak faaliyet sonuçlarını olumsuz etkileyebilir. [Source 5]"
        )}
        catalog = build_fact_catalog(state["evidence"])
        state["draft"] = render_agent_template(compose_template(state["composition"], catalog), state["evidence"])
        reason = ("Paragraph 2 invents dollar appreciation. Source 5 says fluctuations increased reported revenue "
                  "and did not materially impact reported expenses from international operations. "
                  "It does not establish whether the dollar appreciated or depreciated. "
                  "Replace the unsupported direction with fluctuations; keep the supported effects and potential trade risks.")
        initial_feedback = {"issues": [reason], "repair_targets": [
            {"paragraph_id": 2, "source_ids": [5], "reason": reason},
        ]}
    if args.validate_only:
        print("Validated saved evidence and initial compositions:", selected)
        return
    config = load_yaml(ROOT / "configs/settings.yaml")["llm"]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    output = ROOT / "eval/results" / f"revision_comparison_{timestamp}_{uuid4().hex[:8]}.json"
    payload = {
        "scope": "Saved-evidence development replay; not new retrieval, not independently scored",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "llm_config": {key: config[key] for key in ("model", "think", "options") if key in config},
        "max_revisions": args.max_revisions,
        "fixed_feedback_control": args.fixed_feedback,
        "code_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in [ROOT / name for name in (
                            "src/agents/writer.py", "src/agents/critic.py", "src/agents/revisions.py",
                            "src/llm/prompts.py", "src/verification/agent_answer.py",
                            "src/verification/evidence.py", "eval/diagnostics/run_revision_comparison.py")]},
        "cases": [],
    }
    print("Output:", output, flush=True)
    for case_id, state, provenance in prepared:
        case = {"id": case_id, "question": state["question"], "source": provenance, "branches": {}}
        payload["cases"].append(case)
        def checkpoint(branches):
            case["branches"] = branches
            save_json(payload, output)
        await compare_case(state, config, args.max_revisions, checkpoint, initial_feedback)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", choices=CASES)
    parser.add_argument("--max-revisions", type=int, default=2)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--fixed-feedback", action="store_true",
                        help="Construct a two-paragraph control with a known FX error and source-based feedback")
    asyncio.run(main(parser.parse_args()))

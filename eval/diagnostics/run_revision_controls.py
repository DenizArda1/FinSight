"""Short source-grounded positive/negative controls, not a general benchmark."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from src.agents.agent_states import create_initial_state
from src.agents.critic import run_critic
from src.utils.utils import load_yaml, save_json
from src.verification.agent_answer import build_agent_evidence, build_fact_catalog, compose_template, render_agent_template

ROOT = Path(__file__).resolve().parents[2]
CONTROLS = [
    {
        "id": "fx_supported_tr", "expected_supported": True,
        "question": "Rapora göre döviz kuru dalgalanmalarının uluslararası operasyonların gelir ve giderlerine etkisini açıkla.",
        "text": "Döviz kuru dalgalanmaları, uluslararası operasyonlardan raporlanan geliri artırmış; raporlanan giderler üzerinde önemli bir etki yaratmamıştır. [Source 1]",
        "rationale": "The source explicitly reports increased revenue and no material expense impact.",
    },
    {
        "id": "fx_invented_direction_tr", "expected_supported": False,
        "question": "Rapora göre döviz kuru dalgalanmalarının uluslararası operasyonların gelir ve giderlerine etkisini açıkla.",
        "text": "ABD dolarının değer kazanması, uluslararası operasyonlardan raporlanan geliri artırmış; raporlanan giderler üzerinde önemli bir etki yaratmamıştır. [Source 1]",
        "rationale": "The source says fluctuations, not appreciation; the currency direction was invented.",
    },
    {
        "id": "trade_possible_en", "expected_supported": True,
        "question": "What potential effects of trade policy changes does the report describe?",
        "text": "Trade policy changes, including tariffs and import or export controls, could increase supply chain challenges, cost volatility and uncertainty, potentially harming operating results. [Source 1]",
        "rationale": "This preserves the source's potential effects and uncertainty.",
    },
    {
        "id": "trade_actual_en", "expected_supported": False,
        "question": "What potential effects of trade policy changes does the report describe?",
        "text": "Trade policy changes, including tariffs and import or export controls, increased supply chain challenges, cost volatility and uncertainty and harmed operating results. [Source 1]",
        "rationale": "This converts possible impacts into observed outcomes without evidence.",
    },
]


def control_state(control, source):
    state = create_initial_state(control["question"])
    state["request_type"] = "filing"
    state["trace"] = [{"type": "tool", "status": "completed", "name": source["tool"],
                       "arguments": source["arguments"], "result": deepcopy(source["result"])}]
    state["evidence"] = build_agent_evidence(state["trace"])
    state["composition"] = {"kind": "answer", "text": control["text"], "facts": []}
    catalog = build_fact_catalog(state["evidence"])
    state["draft"] = render_agent_template(compose_template(state["composition"], catalog), state["evidence"])
    return state


def score_controls(rows):
    """Never count verification errors as correct semantic rejections."""
    scores = {}
    for mode in ("full", "paragraph"):
        selected = [row for row in rows if row["mode"] == mode]
        scores[mode] = {"correct": 0, "false_accept": 0, "false_reject": 0, "error": 0}
        for row in selected:
            verdict = row["verification"]
            if verdict["status"] == "error":
                key = "error"
            elif verdict["supported"] == row["expected_supported"]:
                key = "correct"
            else:
                key = "false_accept" if verdict["supported"] else "false_reject"
            scores[mode][key] += 1
    return scores


async def main():
    saved_path = ROOT / "eval/results/project_audit_microsoft_20261030.json"
    raw = saved_path.read_bytes()
    saved = json.loads(raw)["state"]
    source = next(item for item in saved["evidence"] if item["source_id"] == 5)
    passage = source["result"]["matches"][0]["context"]["text"]
    if "increased reported revenue and did not have a material impact" not in passage:
        raise ValueError("The expected FX source passage is absent")
    if "could result in increased supply chain challenges" not in passage:
        raise ValueError("The expected trade source passage is absent")
    config = load_yaml(ROOT / "configs/settings.yaml")["llm"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    output = ROOT / "eval/results" / f"revision_controls_{stamp}_{uuid4().hex[:8]}.json"
    report = {
        "scope": "Four source-based development controls. Labels are assistant-authored, not human calibration.",
        "source_path": str(saved_path.relative_to(ROOT)), "source_sha256": hashlib.sha256(raw).hexdigest(),
        "llm_config": {key: config[key] for key in ("model", "think", "options") if key in config},
        "cases": [],
    }
    print("Output:", output, flush=True)
    for control in CONTROLS:
        for mode in ("full", "paragraph"):
            state = control_state(control, source)
            # Only question/text/source go to the model; labels and rationale stay in the result file.
            await run_critic(state, config, locate_repairs=(mode == "paragraph"))
            report["cases"].append({**control, "mode": mode, "verification": state["verification"],
                                    "trace": state["trace"]})
            report["scores"] = score_controls(report["cases"])
            save_json(report, output)
            print(control["id"], mode, state["verification"], flush=True)


if __name__ == "__main__":
    asyncio.run(main())

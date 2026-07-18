#!/usr/bin/env python3
"""Prepare a reproducible AI request without calling an external model."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FACTS_PATH = ROOT / "data" / "processed" / "weekly_report.json"
PROMPT_PATH = ROOT / "prompts" / "weekly_analysis_prompt.md"
OUTPUT_PATH = ROOT / "data" / "processed" / "ai_request.json"


def main() -> int:
    facts = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    request = {
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "model": None,
        "provider": None,
        "external_call": False,
        "prompt_template": str(PROMPT_PATH),
        "facts_source": str(FACTS_PATH),
        "system_prompt": prompt_template.split("## 输入", 1)[0].strip(),
        "facts_json": facts,
        "required_output_format": "json",
        "note": "尚未调用外部 AI 服务；需要配置模型和 API 后才能生成分析。",
    }
    OUTPUT_PATH.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "external_call": False,
        "week_end": facts["week_end"],
        "facts_only": facts["facts_only"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

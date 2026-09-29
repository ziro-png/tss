"""Generated project bridge for the shared LiteLLM Router."""
from __future__ import annotations

import importlib.util
from pathlib import Path

source = Path(__file__).resolve().parents[1] / "llm_router.py"
spec = importlib.util.spec_from_file_location("_animista_shared_llm_router", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
safe_completion = module.safe_completion

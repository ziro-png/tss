# -*- coding: utf-8 -*-
"""
ANIMISTA - الواجهة البسيطة
الاستخدام:
  python main.py --script story.txt --model gpt-4o
  python main.py --script story.txt --model ollama/llama3.1 --api_base http://localhost:11434
  python main.py                          # إدخال النص يدوياً
المفاتيح: ضعها في ملف .env (OPENAI_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY ...)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # يحمّل مفاتيح أي مزود تلقائياً


def main() -> int:
    parser = argparse.ArgumentParser(description="Animista: text -> 2D sketch animation")
    parser.add_argument("--script", help="path to the narration text file (.txt)")
    parser.add_argument("--model", default="gemini/gemini-2.5-flash",
                        help="any LiteLLM model id: gemini/gemini-2.5-flash | "
                             "claude-sonnet-4.5 | ollama/llama3.1 | huggingface/...")
    parser.add_argument("--api_base", default=None,
                        help="e.g. http://localhost:11434 for local Ollama")
    parser.add_argument("--project", default="animista_project", help="output folder name")
    args = parser.parse_args()

    # -- إدخال النص --
    if args.script:
        script_path = Path(args.script)
        if not script_path.exists():
            print(f"ERROR: script file not found: {script_path}")
            return 1
        script_text = script_path.read_text(encoding="utf-8")
    else:
        print("Paste your script below, then press Ctrl+D (or Ctrl+Z on Windows):")
        script_text = sys.stdin.read()

    if len(script_text.strip()) < 10:
        print("ERROR: script too short.")
        return 1

    # -- تشغيل الحلقة الخطية --
    from animista_core import AnimistaCore
    core = AnimistaCore(model=args.model, api_base=args.api_base)
    try:
        result = core.run(script_text, project_name=args.project)
    except RuntimeError as e:
        print(f"PIPELINE HALTED (zero-error gate): {e}")
        return 2

    # -- التسليم --
    root = result["paths"]["root"]
    print("\n================ ANIMISTA READY ================")
    print(f"Project : {root}")
    print(f"Render  : python \"{result['render_script']}\"")
    print("Notes   : put narration.mp3 in assets/ for audio sync,")
    print("          and ensure ffmpeg is installed (moviepy needs it).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
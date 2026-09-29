# -*- coding: utf-8 -*-
"""
ANIMISTA CORE - عقل النظام
حلقة تنفيذ خطية (Linear Execution Loop):
  قراءة النص -> توليد الستوري بورد (JSON قياسي) -> توليد بطاقات الشخصيات
  -> Skill_1 (هيكل المشروع) -> Skill_2 (سكربت الرندر) -> Skill_3 (فحص ذاتي)
التشغيل مرن: أي مزود عبر LiteLLM (OpenAI / Gemini / Anthropic / Ollama / HF)
دون تعديل الكود - يكفي تغيير اسم النموذج فقط.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field


# ============================================================
# HARD-CODED ARTISTIC LOCKS (قفل فني - لا يتغير أبداً)
# ============================================================
STYLE_LOCK = (
    "2D flat explainer animation, single focal illustration per scene framed inside a "
    "thin black-bordered letterbox, white/paper margins, ONE unified flat palette of "
    "5-6 colors reused for the entire video (never introduce new illustration styles "
    "mid-video - no mixing photoreal/glossy-3D assets with flat-vector assets), "
    "consistent line weight, slight hand-drawn line wobble, cel-shading only, 12fps, "
    "absolutely NO photorealism, NO glossy 3D render, NO gradients"
)

CONSISTENCY_LOCK = (
    "Character consistency is law: same face, same palette, same clothing across "
    "every scene. Reference the character bible before each scene. Never redesign. "
    "The host character defined in the character bible must appear, at least "
    "partially (hand, shoulder, reaction pose), in every single scene."
)

AUDIO_LOCK = (
    "Sync visuals to narration keywords; simple lip shapes A/E/O/M/B/Rest; "
    "1-2s comic-timing pauses after punchlines."
)

TRANSITION_LOCK = (
    "Clean cuts and match cuts only; hand-drawn wipe allowed if justified; "
    "never flashy transitions, never 3D rotations, never light leaks. At least every "
    "other scene should end on a shared element/motion direction carried into the "
    "next scene (true match cut, not just a hard cut)."
)

CAPTION_LOCK = (
    "Every scene carries its OWN short top-bar caption (3-6 words) that reflects "
    "THAT scene's idea. Never repeat one fixed title/word across the whole video - "
    "the caption must change scene to scene, in sync with the narration."
)

MOTION_LOCK = (
    "No scene may be a fully static, frozen image. Each scene has exactly one "
    "dominant motion: a slow Ken-Burns zoom/pan across the focal illustration, or a "
    "small idle motion on the host character. Never combine more than one motion."
)

QUALITY_GATE = (
    "Before finalizing: (1) every narration sentence is visually covered, (2) first "
    "3 seconds hook the viewer, (3) characters match their bible 100%, (4) motion has "
    "natural ease-in/out and is never fully static, (5) one dominant motion per scene, "
    "(6) comfortable pacing with negative space, no flashing, (7) understandable even "
    "on mute, (8) the top caption changes every scene, (9) illustration style is "
    "visually identical across every scene (no style clash)."
)


# ============================================================
# المخطط القياسي للبيانات (JSON Schema - بيئة-محايد)
# ============================================================
class Scene(BaseModel):
    scene_id: int
    duration_sec: float = Field(gt=0, le=30)
    visual_description: str
    motion: str
    narration: str
    caption: str = ""                 # عنوان علوي قصير خاص بهذا المشهد فقط
    transition: str = "cut"           # cut | match_cut | wipe
    consistency_notes: str = ""
    characters: List[str] = []


class Character(BaseModel):
    name: str
    body_shape: str
    head_shape: str
    eyes: str
    hair: str
    clothing: str
    palette: Dict[str, str]           # skin / hair / shirt / pants


class Storyboard(BaseModel):
    title: str
    hook: str
    scenes: List[Scene] = Field(min_length=1)


# ============================================================
# محرك النداءات (LiteLLM - Omni-Provider)
# ============================================================
def _call_llm(model: str, system: str, user: str, api_base: str | None = None,
              max_retries: int = 3) -> str:
    """
    نداء موحّد عبر LiteLLM. يدعم:
      - OpenAI:        model="gpt-4o"
      - Gemini:        model="gemini/gemini-2.5-pro"
      - Anthropic:     model="claude-sonnet-4.5"
      - Ollama محلي:   model="ollama/llama3.1"  (+ api_base="http://localhost:11434")
      - HF مفتوح:      model="huggingface/..."
    JSON-mode عندما يدعمه المزود، وإلا استخراج يدوي مع تحقق.
    """
    from llm_router import safe_completion

    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if api_base:
        kwargs["api_base"] = api_base

    try:
        resp = safe_completion(
            model=model,
            messages=kwargs["messages"],
            api_base=api_base,
            response_format={"type": "json_object"},
        )
    except Exception:
        # Some providers reject JSON mode; preserve the existing plain retry path.
        resp = safe_completion(
            model=model,
            messages=kwargs["messages"],
            api_base=api_base,
        )
    return resp.choices[0].message.content


def extract_json(text: str) -> Dict[str, Any]:
    """استخراج أول كائن أو قائمة JSON صالحة من نص النموذج."""
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
            if isinstance(value, (dict, list)):
                return value
        except json.JSONDecodeError:
            continue
    raise ValueError(f"No JSON object or array found in model output: {text[:200]}...")


# ============================================================
# برومبتات التوليد (مغلّفة بالقفل الفني)
# ============================================================
SYSTEM_STORYBOARD = f"""You are Animista, an expert 2D animation director.
Convert the user's script into a professional storyboard as ONE valid JSON object
matching this exact schema:
{{"title": str, "hook": str,
  "scenes": [{{"scene_id": int, "duration_sec": number(4-12),
              "visual_description": str, "motion": str, "narration": str,
              "caption": str, "transition": "cut"|"match_cut"|"wipe",
              "consistency_notes": str, "characters": [str]}}]}}

Rules:
- One idea per scene. Keep every scene between 2 and 3 seconds for fast pacing.
- Cover EVERY sentence of the script visually. Never invent scenes.
- Hook within first 3 seconds. Alternate calm dialogue with dynamic scenes.
- End each scene linked to the next (match cut / shared element / motion direction),
  and make at least every other scene a true match_cut.
- "caption": a SHORT (3-6 word) top-bar phrase unique to THIS scene's idea, in the
  same language as the script. Never reuse the same caption across scenes.
- "motion": exactly one dominant motion for this scene (e.g. "slow zoom in on the
  illustration" or "host character raises hand"). Never "static" / "none".
- "characters": always include the host character's name, even if only partially
  visible reacting to the illustration.

STYLE LOCK: {STYLE_LOCK}
AUDIO LOCK: {AUDIO_LOCK}
TRANSITION LOCK: {TRANSITION_LOCK}
CAPTION LOCK: {CAPTION_LOCK}
MOTION LOCK: {MOTION_LOCK}
QUALITY GATE: {QUALITY_GATE}

Output ONLY the JSON. No prose, no markdown fences."""

SYSTEM_CHARACTERS = f"""You are Animista's character designer.
From the script and storyboard below, extract every recurring character and output
ONE valid JSON array matching this schema:
[{{"name": str, "body_shape": str, "head_shape": str, "eyes": str, "hair": str,
   "clothing": str,
   "palette": {{"skin": "#hex", "hair": "#hex", "shirt": "#hex", "pants": "#hex"}}}}]

Constraints:
- 4-6 total colors across ALL characters (flat pastel palette).
- Simple appealing design: simplified body, slightly large head, exaggerated expressions.
- Design must be drawable with basic shapes and consistent from every angle.

{CONSISTENCY_LOCK}

Output ONLY the JSON array. No prose."""


# ============================================================
# الحلقة الخطية الرئيسية
# ============================================================
class AnimistaCore:
    def __init__(self, model: str = "gemini/gemini-2.5-flash", api_base: str | None = None,
                 max_retries: int = 3):
        self.model = model            # أي مزود: gpt-4o / gemini/... / ollama/...
        self.api_base = api_base
        self.max_retries = max_retries

    # -- الخطوة 1: نص -> ستوري بورد قياسي --
    def generate_storyboard(self, script_text: str) -> Storyboard:
        raw = _call_llm(self.model, SYSTEM_STORYBOARD, script_text, self.api_base,
                        self.max_retries)
        data = extract_json(raw)
        storyboard = Storyboard(**data)     # pydantic: أي خط مخطط = فشل فوري قبل الرندر
        for scene in storyboard.scenes:
            scene.duration_sec = min(3.0, max(2.0, scene.duration_sec))
        return storyboard

    # -- الخطوة 2: شخصيات ثابتة (بطاقة الهوية) --
    def generate_characters(self, script_text: str, storyboard: Storyboard) -> List[Character]:
        payload = {
            "script": script_text,
            "characters_mentioned": sorted({c for s in storyboard.scenes for c in s.characters}),
        }
        raw = _call_llm(self.model, SYSTEM_CHARACTERS, json.dumps(payload, ensure_ascii=False),
                        self.api_base, self.max_retries)
        data = extract_json(raw)
        if isinstance(data, dict):
            data = data.get("characters", [])
        return [Character(**c) for c in data]

    # -- الحلقة الخطية الكاملة: فهم <- ستوري بورد <- هيكل <- رندر <- فحص --
    def run(self, script_text: str, project_name: str = "animista_project") -> Dict[str, Any]:
        import skills  # Skill_1 / Skill_2 / Skill_3

        print("[1/5] Generating storyboard (JSON schema locked)...")
        storyboard = self.generate_storyboard(script_text)

        print("[2/5] Building character bible (consistency locked)...")
        characters = self.generate_characters(script_text, storyboard)

        print("[3/5] Skill_1: generating project structure...")
        paths = skills.generate_project_structure(
            project_name,
            storyboard.model_dump(),
            [c.model_dump() for c in characters],
        )

        print("[4/5] Skill_2: writing render automation...")
        render_script = skills.write_python_automation(paths["root"])

        print("[5/5] Skill_3: auto-debugging all files (zero-error gate)...")
        verdict = skills.auto_debug_files(
            paths["storyboard_json"], paths["characters_json"],
            paths["config_json"], render_script,
        )
        if not verdict["ok"]:
            raise RuntimeError(f"Quality gate FAILED: {json.dumps(verdict['report'], ensure_ascii=False, indent=2)}")

        print(f"[OK] Pipeline clean. Fixed: {verdict['fixed'] or 'nothing'}")
        return {"paths": paths, "render_script": render_script, "debug": verdict,
                "storyboard": storyboard}
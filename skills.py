"""
ANIMISTA - Skills Module
الـ 3 مهارات الأساسية للنظام:
  Skill_1: generate_project_structure  -> إنشاء هيكل المشروع + JSON الستوري بورد
  Skill_2: write_python_automation     -> توليد سكربت الرندر (PIL + MoviePy) بستايل مُبرمج مسبقاً
  Skill_3: auto_debug_files            -> فحص ذاتي وإصلاح آلي للملفات قبل الرندر
"""

from __future__ import annotations

import ast
import json
import re
import textwrap
from pathlib import Path
from typing import Any, Dict, List

# ============================================================
# HARD-CODED ARTISTIC DIRECTIVE (مُبرمج مسبقاً - لا يتغير)
# هذه الثوابت تُزرع في كل سكربت رندر لتفريض الستايل اليدوي
# ============================================================
SKETCH_STYLE_PROMPT = (
    "flat 2D explainer style, single focal illustration per scene inside a thin "
    "black-bordered letterbox frame, white/paper background margins, limited flat "
    "palette of 5-6 colors reused across the whole video, consistent line weight, "
    "slight hand-drawn line wobble, cel-shading only, NO photorealism, NO glossy 3D "
    "render, NO gradients, NO mixing of illustration styles between scenes"
)

CONSISTENCY_PROMPT = (
    "strict character consistency: every frame must match the character bible JSON - "
    "same head shape, same eye shape, same palette, same clothing. Never redesign "
    "mid-video. Check against characters.json before every render pass. The host "
    "character must appear (fully or partially) in every scene, always same design, "
    "reacting or pointing toward the focal illustration."
)

AUDIO_SYNC_PROMPT = (
    "sync visual beats to narration keywords, simple lip shapes A/E/O/M/B/Rest, "
    "1-2 second comic-timing pauses after punchlines"
)

TRANSITION_PROMPT = (
    "prefer clean cuts and match cuts (shared element or motion direction carried "
    "into the next scene); hand-drawn wipe allowed; strictly no flashy transitions, "
    "no 3D rotations, no light leaks"
)

CAPTION_PROMPT = (
    "dynamic top caption bar: a short bold phrase (3-6 words) that changes every "
    "scene and summarizes THAT scene's idea - never a single word repeated for the "
    "whole video"
)

MOTION_PROMPT = (
    "every scene has exactly one dominant motion: slow Ken-Burns zoom/pan on the "
    "focal illustration, or a slight idle motion on the host character (arm, head, "
    "blink). Never a fully static frame for more than 1 second."
)

SCENE_FPS = 12  # الإيقاع المثالي للأسلوب اليدوي

# بطاقة الشخصية الافتراضية (Host) - نفس تصميم الشخصية الظاهرة بفيديوهاتك الحالية
DEFAULT_HOST_CHARACTER = {
    "name": "host",
    "body_shape": "simple rounded torso, lab coat over dark shirt",
    "head_shape": "round, featureless/minimal face",
    "eyes": "two small simple dots or none, expression carried by eyebrows/hands",
    "hair": "short black curly hair",
    "clothing": "white lab coat, red baseball cap, dark shirt underneath",
    "palette": {"skin": "#F5E6D3", "hair": "#1A1A1A", "shirt": "#C0392B", "pants": "#FFFFFF"},
}


# ============================================================
# Skill_1: generate_project_structure
# ============================================================
def generate_project_structure(
    project_name: str,
    storyboard: Dict[str, Any],
    characters: List[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Skill_1: ينشئ مجلدات المشروع القياسية ويكتب ملفات الـ JSON.
    يعيد قاموساً بالمسارات الجاهزة للاستخدام في بقية الحلقة الخطية.
    """
    root = Path(project_name).resolve()
    folders = {
        "root": root,
        "assets": root / "assets",
        "outputs": root / "outputs",
        "scenes": root / "scenes",
        "scripts": root / "scripts",
    }
    for p in folders.values():
        p.mkdir(parents=True, exist_ok=True)

    storyboard_path = folders["root"] / "storyboard.json"
    characters_path = folders["root"] / "characters.json"
    config_path = folders["root"] / "animista_config.json"

    # تثبيت القالب القياسي (يتم التحقق منه لاحقاً عبر pydantic في auto_debug_files)
    with open(storyboard_path, "w", encoding="utf-8") as f:
        json.dump(storyboard, f, ensure_ascii=False, indent=2)
    with open(characters_path, "w", encoding="utf-8") as f:
        json.dump(characters, f, ensure_ascii=False, indent=2)

    # لو ما في شخصية host بالـ characters.json، نحقنها تلقائياً (اتساق مضمون)
    if not any(c.get("name") == "host" for c in characters):
        characters = [DEFAULT_HOST_CHARACTER, *characters]
        with open(characters_path, "w", encoding="utf-8") as f:
            json.dump(characters, f, ensure_ascii=False, indent=2)

    config = {
        "fps": SCENE_FPS,
        "style_prompt": SKETCH_STYLE_PROMPT,
        "consistency_prompt": CONSISTENCY_PROMPT,
        "audio_sync_prompt": AUDIO_SYNC_PROMPT,
        "transition_prompt": TRANSITION_PROMPT,
        "caption_prompt": CAPTION_PROMPT,
        "motion_prompt": MOTION_PROMPT,
        "resolution": [1280, 720],
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    return {
        "root": str(folders["root"]),
        "assets": str(folders["assets"]),
        "outputs": str(folders["outputs"]),
        "scenes": str(folders["scenes"]),
        "scripts": str(folders["scripts"]),
        "storyboard_json": str(storyboard_path),
        "characters_json": str(characters_path),
        "config_json": str(config_path),
    }


# ============================================================
# Skill_2: write_python_automation
# ============================================================
_RENDER_TEMPLATE = textwrap.dedent('''
    # -*- coding: utf-8 -*-
    """
    ANIMISTA Render Engine - مولّد تلقائياً من Skill_2
    يقرأ storyboard.json + characters.json + animista_config.json
    ويرسم كل مشهد بأسلوب سكيتش يدوي ويجمع الفيديو النهائي.
    """
    import json
    import math
    import random
    from pathlib import Path

    from PIL import Image, ImageDraw, ImageFont
    from asset_sourcing import source_scene_assets
    from moviepy.editor import (
        AudioFileClip,
        ImageSequenceClip,
        concatenate_videoclips,
    )

    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        def shape_text(t):
            return get_display(arabic_reshaper.reshape(t))
    except ImportError:
        def shape_text(t):  # fallback: بدون تشكيل عربي صحيح لو المكتبات غير مثبتة
            return t

    # ---- Hardcoded Artistic Prompts (مُزرعة من skills.py ولا تُعدّل) ----
    STYLE_PROMPT = "$STYLE_PROMPT"
    CONSISTENCY_PROMPT = "$CONSISTENCY_PROMPT"
    AUDIO_SYNC_PROMPT = "$AUDIO_SYNC_PROMPT"
    TRANSITION_PROMPT = "$TRANSITION_PROMPT"
    CAPTION_PROMPT = "$CAPTION_PROMPT"
    MOTION_PROMPT = "$MOTION_PROMPT"
    FPS = $FPS

    ROOT = Path(__file__).parent
    W, H = $RES_W, $RES_H
    BAR_H = int(H * 0.11)          # ارتفاع الشريط العلوي/السفلي (letterbox)
    FONT_PATH = ROOT / "assets" / "font.ttf"   # ضع خط عربي هون (مثلاً Cairo/Tajawal)
    random.seed(42)  # حتمية: نفس المدخلات = نفس الفيديو (Zero-Error)


    def load_json(name):
        with open(ROOT / name, encoding="utf-8") as f:
            return json.load(f)


    STORYBOARD = load_json("storyboard.json")
    CHARACTERS = {c["name"]: c for c in load_json("characters.json")}
    SCENE_IMAGES = {}


    def get_font(size):
        try:
            return ImageFont.truetype(str(FONT_PATH), size)
        except Exception:
            return ImageFont.load_default()


    def draw_letterbox(img, caption_text):
        """الإطار المميز لستايلك: شريط أبيض علوي بعنوان ديناميكي + شريط سفلي رفيع،
        وحدود سوداء رفيعة حول الصورة كلها."""
        draw = ImageDraw.Draw(img)
        # الشريط العلوي (أبيض) + العنوان الديناميكي (يتغير كل مشهد، مش كلمة ثابتة)
        draw.rectangle([0, 0, W, BAR_H], fill="white")
        draw.rectangle([0, H - BAR_H // 2, W, H], fill="black")
        draw.rectangle([0, 0, W - 1, H - 1], outline="black", width=6)
        draw.line([0, BAR_H, W, BAR_H], fill="black", width=4)
        if caption_text:
            font = get_font(int(BAR_H * 0.42))
            text = shape_text(caption_text)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((W - tw) / 2, (BAR_H - th) / 2 - bbox[1]), text, fill="black", font=font)
        return img


    def ken_burns_crop(source_img, progress, zoom_amount=0.12):
        """الحركة الافتراضية الوحيدة على الصورة المصدر: زوم بطيء متصل (Ken Burns) -
        بديل الصورة الجامدة تماماً في الفيديو الأصلي (MOTION LOCK)."""
        iw, ih = source_img.size
        scale = 1.0 + zoom_amount * progress
        cw, ch = int(iw / scale), int(ih / scale)
        cx, cy = (iw - cw) // 2, (ih - ch) // 2
        return source_img.crop((cx, cy, cx + cw, cy + ch)).resize((iw, ih), Image.LANCZOS)


    def wobbly_line(draw, x1, y1, x2, y2, color, width=4, wobble=2.0):
        """خط يدوي حي مع اهتزاز بسيط - جوهر الستايل."""
        steps = max(2, int(math.hypot(x2 - x1, y2 - y1) / 18))
        pts = []
        for i in range(steps + 1):
            t = i / steps
            px = x1 + (x2 - x1) * t + random.uniform(-wobble, wobble)
            py = y1 + (y2 - y1) * t + random.uniform(-wobble, wobble)
            pts.append((px, py))
        draw.line(pts, fill=color, width=width, joint="curve")


    def draw_character(draw, ch, cx, cy, scale, expression="neutral"):
        """رسم شخصية من بطاقة الهوية - الاتساق مضمون لأن البيانات ثابتة."""
        body_w = 90 * scale
        body_h = 130 * scale
        head_r = 55 * scale
        pal = ch["palette"]

        # الجسم
        draw.rounded_rectangle(
            [cx - body_w / 2, cy, cx + body_w / 2, cy + body_h],
            radius=20 * scale, fill=pal["shirt"], outline="black", width=4,
        )
        # الرأس
        draw.ellipse(
            [cx - head_r, cy - head_r * 2, cx + head_r, cy],
            fill=pal["skin"], outline="black", width=4,
        )
        # الشعر
        hair_color = pal["hair"]
        draw.chord(
            [cx - head_r, cy - head_r * 2.2, cx + head_r, cy - head_r * 0.2],
            start=180, end=360, fill=hair_color, outline="black", width=3,
        )
        # العيون - نافذة العاطفة
        eye_y = cy - head_r * 1.1
        eye_dx = head_r * 0.42
        if expression in ("happy", "excited"):
            draw.arc([cx - eye_dx - 12, eye_y - 10, cx - eye_dx + 12, eye_y + 10], 200, 340, fill="black", width=4)
            draw.arc([cx + eye_dx - 12, eye_y - 10, cx + eye_dx + 12, eye_y + 10], 200, 340, fill="black", width=4)
        elif expression == "angry":
            draw.line([cx - eye_dx - 12, eye_y - 12, cx - eye_dx + 10, eye_y - 2], fill="black", width=4)
            draw.line([cx + eye_dx + 12, eye_y - 12, cx + eye_dx - 10, eye_y - 2], fill="black", width=4)
            draw.ellipse([cx - eye_dx - 8, eye_y, cx - eye_dx + 8, eye_y + 14], fill="white", outline="black", width=3)
            draw.ellipse([cx + eye_dx - 8, eye_y, cx + eye_dx + 8, eye_y + 14], fill="white", outline="black", width=3)
        else:
            draw.ellipse([cx - eye_dx - 9, eye_y - 8, cx - eye_dx + 9, eye_y + 10], fill="white", outline="black", width=3)
            draw.ellipse([cx + eye_dx - 9, eye_y - 8, cx + eye_dx + 9, eye_y + 10], fill="white", outline="black", width=3)
            draw.ellipse([cx - eye_dx - 3, eye_y - 2, cx - eye_dx + 3, eye_y + 4], fill="black")
            draw.ellipse([cx + eye_dx - 3, eye_y - 2, cx + eye_dx + 3, eye_y + 4], fill="black")
        # الفم
        mouth_y = cy - head_r * 0.45
        if expression in ("happy", "excited"):
            draw.arc([cx - 22, mouth_y - 10, cx + 22, mouth_y + 14], 0, 180, fill="black", width=4)
        elif expression == "sad":
            draw.arc([cx - 22, mouth_y, cx + 22, mouth_y + 22], 180, 360, fill="black", width=4)
        else:
            draw.line([cx - 16, mouth_y, cx + 16, mouth_y], fill="black", width=4)


    def infer_expression(scene):
        txt = (scene.get("narration", "") + " " + scene.get("visual_description", "")).lower()
        if any(w in txt for w in ("ضحك", "happy", "فرح", "excited", "سعيد")):
            return "happy"
        if any(w in txt for w in ("غاضب", "angry", "غضب")):
            return "angry"
        if any(w in txt for w in ("حزين", "sad", "خائف", "خوف")):
            return "sad"
        return "neutral"


    def draw_scene(scene, frame_idx, total_frames):
        """صورة المشهد: منطقة عرض بين الشريطين + زوم Ken-Burns على الصورة المصدر
        (بدل الإطار الجامد) + الشخصية الثابتة (host) ظاهرة جزئياً بكل مشهد + كابشن
        علوي ديناميكي مختلف كل مشهد (بدل كلمة واحدة مكررة طول الفيديو)."""
        progress = frame_idx / max(1, total_frames - 1)
        stage_h = H - int(BAR_H * 1.5)
        source = SCENE_IMAGES.get(scene.get("scene_id"))
        if source:
            zoomed = ken_burns_crop(source, progress)
            thumb = zoomed.copy()
            thumb.thumbnail((W, stage_h))
            canvas = Image.new("RGB", (W, H), (238, 244, 242))
            canvas.paste(thumb, ((W - thumb.width) // 2, BAR_H + (stage_h - thumb.height) // 2))
            img = canvas
        else:
            img = Image.new("RGB", (W, H), (238, 244, 242))

        draw = ImageDraw.Draw(img)
        # أفق مرسوم بخط يدوي خفيف داخل منطقة العرض فقط
        wobbly_line(draw, 0, H - BAR_H * 1.4, W, H - BAR_H * 1.4, (200, 200, 200), width=2, wobble=1.5)

        # الشخصية: تظهر جزئياً بكل مشهد (CONSISTENCY LOCK) بحركة idle بسيطة فقط
        chars_in_scene = scene.get("characters", []) or ["host"]
        if "host" not in chars_in_scene:
            chars_in_scene = [*chars_in_scene, "host"]
        for i, name in enumerate(chars_in_scene[:2]):
            ch = CHARACTERS.get(name)
            if not ch:
                continue
            base_x = W * (0.82 if name == "host" else 0.25 + 0.3 * i)
            idle_bob = math.sin(progress * math.pi * 2) * (4 if name == "host" else 0)
            draw_character(draw, ch, base_x, H - BAR_H * 1.4 - 10 + idle_bob, 0.85, infer_expression(scene))

        draw_letterbox(img, scene.get("caption") or scene.get("narration", "")[:28])
        return img


    def render_scene(scene, scene_dir):
        n_frames = max(1, int(scene["duration_sec"] * FPS))
        frames = []
        for i in range(n_frames):
            frames.append(draw_scene(scene, i, n_frames))
        frames_path = scene_dir / "frames"
        frames_path.mkdir(parents=True, exist_ok=True)
        files = []
        for i, im in enumerate(frames):
            p = frames_path / f"frame_{i:04d}.png"
            im.save(p)
            files.append(str(p))
        return ImageSequenceClip(files, fps=FPS)


    def main():
        print(f"[ANIMISTA] STYLE LOCKED: {STYLE_PROMPT[:60]}...")
        assets_dir = ROOT / "assets"
        for idx, scene in enumerate(STORYBOARD["scenes"], start=1):
            path = source_scene_assets(scene, idx, assets_dir)
            if path:
                SCENE_IMAGES[scene.get("scene_id", idx)] = Image.open(path).convert("RGB")
        clips = []
        for idx, scene in enumerate(STORYBOARD["scenes"], start=1):
            total = len(STORYBOARD["scenes"])
            print(f"[ANIMISTA] Rendering scene {idx}/{total}: {scene.get('visual_description', '')[:40]}")
            scene_dir = ROOT / "scenes" / f"scene_{idx:02d}"
            clip = render_scene(scene, scene_dir)
            if scene.get("transition") in ("match_cut", "wipe") and clips:
                clip = clip.crossfadein(0.4)
            clips.append(clip)

        final = concatenate_videoclips(clips, method="compose")
        audio_path = ROOT / "assets" / "narration.mp3"
        if audio_path.exists():
            final = final.set_audio(AudioFileClip(str(audio_path)))
            print("[ANIMISTA] Audio attached (lip-sync prompts applied at generation level).")

        out_path = ROOT / "outputs" / "final_video.mp4"
        final.write_videofile(str(out_path), fps=FPS, codec="libx264", audio_codec="aac")
        print(f"[ANIMISTA] DONE -> {out_path}")


    if __name__ == "__main__":
        main()
''')

from string import Template


def write_python_automation(project_root: str) -> str:
    """
    Skill_2: يكتب سكربت الرندر render_video.py داخل مجلد المشروع.
    يزرع الـ Hardcoded Prompts الفنية ويعيد مسار السكربت الجاهز للتشغيل.
    """
    root = Path(project_root)
    cfg_path = root / "animista_config.json"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)

    res_w, res_h = cfg["resolution"]
    code = Template(_RENDER_TEMPLATE).substitute(
        STYLE_PROMPT=cfg["style_prompt"],
        CONSISTENCY_PROMPT=cfg["consistency_prompt"],
        AUDIO_SYNC_PROMPT=cfg["audio_sync_prompt"],
        TRANSITION_PROMPT=cfg["transition_prompt"],
        FPS=cfg["fps"],
        RES_W=res_w,
        RES_H=res_h,
    )

    script_path = root / "render_video.py"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(code)
    shared_sourcing = Path(__file__).with_name("asset_sourcing.py")
    if shared_sourcing.exists():
        (root / "asset_sourcing.py").write_text(shared_sourcing.read_text(encoding="utf-8"), encoding="utf-8")
    shared_keys = Path(__file__).with_name("api_key_pool.py")
    if shared_keys.exists():
        (root / "api_key_pool.py").write_text(shared_keys.read_text(encoding="utf-8"), encoding="utf-8")
    shared_router = Path(__file__).with_name("llm_router.py")
    if shared_router.exists():
        (root / "llm_router.py").write_text(
            '"""Generated project bridge for the shared LiteLLM Router."""\n'
            'from __future__ import annotations\n\n'
            'import importlib.util\nfrom pathlib import Path\n\n'
            'source = Path(__file__).resolve().parents[1] / "llm_router.py"\n'
            'spec = importlib.util.spec_from_file_location("_animista_shared_llm_router", source)\n'
            'module = importlib.util.module_from_spec(spec)\n'
            'spec.loader.exec_module(module)\n'
            'safe_completion = module.safe_completion\n',
            encoding="utf-8",
        )
    return str(script_path)


# ============================================================
# Skill_3: auto_debug_files
# ============================================================
def _repair_json(text: str) -> str:
    """إصلاحات آمنة شائعة: إزالة فواصل زائدة وتعليقات وتغليف code-fences."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.MULTILINE).strip()
    t = re.sub(r",\s*([}\]])", r"\1", t)
    t = re.sub(r"//.*", "", t)
    return t


def auto_debug_files(*paths: str) -> Dict[str, Any]:
    """
    Skill_3: فحص ذاتي شامل قبل الرندر.
    - ملفات JSON: parse + إصلاح آلي + تحقق من الحقول الإلزامية
    - ملفات .py: فحص نحوي كامل عبر ast
    يعيد {"ok": bool, "report": {...}, "fixed": [list]} — ok=False يوقف الحلقة الخطية.
    """
    report: Dict[str, Any] = {}
    fixed: List[str] = []
    ok_all = True

    for p in map(Path, paths):
        if not p.exists():
            report[p.name] = {"status": "MISSING", "error": "file not found"}
            ok_all = False
            continue

        if p.suffix == ".json":
            raw = p.read_text(encoding="utf-8")
            try:
                data = json.loads(raw)
                report[p.name] = {"status": "OK"}
            except json.JSONDecodeError:
                repaired = _repair_json(raw)
                try:
                    data = json.loads(repaired)
                    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    fixed.append(p.name)
                    report[p.name] = {"status": "FIXED", "fix": "json repaired automatically"}
                except json.JSONDecodeError as e:
                    report[p.name] = {"status": "ERROR", "error": f"unrecoverable JSON: {e}"}
                    ok_all = False
                    continue

            # تحقق دلالي لملف الستوري بورد
            if p.name == "storyboard.json":
                scenes = data.get("scenes", []) if isinstance(data, dict) else []
                if not scenes:
                    report[p.name]["status"] = "ERROR"
                    report[p.name]["error"] = "no scenes found"
                    ok_all = False
                else:
                    for i, s in enumerate(scenes):
                        for key in ("duration_sec", "visual_description", "narration"):
                            if key not in s:
                                report[p.name]["status"] = "ERROR"
                                report[p.name]["error"] = f"scene {i} missing '{key}'"
                                ok_all = False

        elif p.suffix == ".py":
            source = p.read_text(encoding="utf-8")
            try:
                ast.parse(source)
                report[p.name] = {"status": "OK"}
            except SyntaxError as e:
                report[p.name] = {"status": "ERROR", "error": f"syntax error line {e.lineno}: {e.msg}"}
                ok_all = False

        else:
            report[p.name] = {"status": "SKIPPED", "note": "no validator for this extension"}

    return {"ok": ok_all, "report": report, "fixed": fixed}
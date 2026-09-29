
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

# ---- Hardcoded Artistic Prompts (مُزرعة من skills.py ولا تُعدّل) ----
STYLE_PROMPT = "hand-drawn 2D sketch animation, imperfect live ink lines with slight wobble, flat pastel palette of 4-6 colors only, white paper background, simple appealing characters with exaggerated expressions, hand-sketched backgrounds, NO 3D, NO photorealism, NO gradients, cel-shading only, 12fps animatic feel"
CONSISTENCY_PROMPT = "strict character consistency: every frame must match the character bible JSON - same head shape, same eye shape, same palette, same clothing. Never redesign mid-video. Check against characters.json before every render pass."
AUDIO_SYNC_PROMPT = "sync visual beats to narration keywords, simple lip shapes A/E/O/M/B/Rest, 1-2 second comic-timing pauses after punchlines"
TRANSITION_PROMPT = "prefer clean cuts and match cuts; hand-drawn wipe allowed; strictly no flashy transitions, no 3D rotations, no light leaks"
FPS = 12

ROOT = Path(__file__).parent
W, H = 1280, 720
random.seed(42)  # حتمية: نفس المدخلات = نفس الفيديو (Zero-Error)


def load_json(name):
    with open(ROOT / name, encoding="utf-8") as f:
        return json.load(f)


STORYBOARD = load_json("storyboard.json")
CHARACTERS = {c["name"]: c for c in load_json("characters.json")}
SCENE_IMAGES = {}


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
    """صورة المشهد إن توفرت، مع رسم الشخصيات فوقها وحركة بسيطة."""
    source = SCENE_IMAGES.get(scene.get("scene_id"))
    if source:
        img = source.copy()
        img.thumbnail((W, H))
        canvas = Image.new("RGB", (W, H), (238, 244, 242))
        canvas.paste(img, ((W - img.width) // 2, (H - img.height) // 2))
        img = canvas
    else:
        img = Image.new("RGB", (W, H), (238, 244, 242))
    draw = ImageDraw.Draw(img)

    # أفق مرسوم بخط يدوي خفيف
    wobbly_line(draw, 0, H * 0.82, W, H * 0.82, (200, 200, 200), width=2, wobble=1.5)

    progress = frame_idx / max(1, total_frames - 1)
    chars_in_scene = scene.get("characters", [])
    names = chars_in_scene if chars_in_scene else list(CHARACTERS.keys())[:1]
    for i, name in enumerate(names):
        ch = CHARACTERS.get(name)
        if not ch:
            continue
        base_x = W * (0.3 + 0.4 * i)
        # حركة واحدة رئيسية: انزلاق أفقي هادئ
        offset = math.sin(progress * math.pi) * W * 0.05
        draw_character(draw, ch, base_x + offset, H * 0.38, 1.0, infer_expression(scene))
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

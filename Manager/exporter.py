"""牌谱导出：把某一序号的所有何切记录与疑问小局导出为长图 / PDF / ZIP。

- 长图 / PDF：供人阅读的汇总。
- ZIP：把该牌谱的照片 + manifest.json 打包，用于在不同用户之间分享/导入。

内容顺序（长图/PDF）：
    顶部：该牌谱共用的链接（原牌谱 / AI 复盘 / 参考 AI 复盘）
    一、何切记录（按何切序号）：每条含标签、截图与文字解读
    二、疑问小局：每条含小局与疑问点
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PAGE_WIDTH = 1000
PADDING = 28
CONTENT_WIDTH = PAGE_WIDTH - 2 * PADDING
BG = (255, 255, 255)
FG = (25, 25, 25)
MUTED = (110, 110, 110)
ACCENT = (30, 90, 160)
SEP = (215, 215, 215)

_MEASURE = ImageDraw.Draw(Image.new("RGB", (1, 1)))
_FONT_CACHE: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}

_FONT_CANDIDATES_REGULAR = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]
_FONT_CANDIDATES_BOLD = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    candidates = _FONT_CANDIDATES_BOLD if bold else _FONT_CANDIDATES_REGULAR
    font = None
    for path in candidates:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def _wrap(text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text).split("\n"):
        if paragraph == "":
            lines.append("")
            continue
        line = ""
        for ch in paragraph:
            if _MEASURE.textlength(line + ch, font=font) <= max_width:
                line += ch
            else:
                lines.append(line)
                line = ch
        lines.append(line)
    return lines


def _text_block(text, font, color=FG, max_width=CONTENT_WIDTH, spacing=6, indent=0):
    lines = _wrap(text, font, max_width - indent)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + spacing
    height = max(line_h * len(lines), line_h)
    block = Image.new("RGB", (PAGE_WIDTH, height), BG)
    draw = ImageDraw.Draw(block)
    y = 0
    for line in lines:
        draw.text((PADDING + indent, y), line, font=font, fill=color)
        y += line_h
    return block


def _image_block(path, label=None, max_width=CONTENT_WIDTH):
    blocks = []
    if label:
        blocks.append(_text_block(label, _font(18), MUTED, spacing=2))
    if path and Path(path).exists():
        try:
            with Image.open(path) as image:
                image = image.convert("RGB")
        except OSError:
            return blocks
        if image.width > max_width:
            ratio = max_width / image.width
            image = image.resize((max_width, max(1, int(image.height * ratio))), Image.LANCZOS)
        block = Image.new("RGB", (PAGE_WIDTH, image.height + 10), BG)
        block.paste(image, ((PAGE_WIDTH - image.width) // 2, 5))
        blocks.append(block)
    return blocks


def _separator():
    block = Image.new("RGB", (PAGE_WIDTH, 17), BG)
    draw = ImageDraw.Draw(block)
    draw.line((PADDING, 8, PAGE_WIDTH - PADDING, 8), fill=SEP, width=1)
    return block


def _stack(blocks) -> Image.Image:
    height = sum(block.height for block in blocks) + PADDING
    result = Image.new("RGB", (PAGE_WIDTH, height), BG)
    y = PADDING // 2
    for block in blocks:
        result.paste(block, (0, y))
        y += block.height
    return result


def _game_data(storage, game_id):
    scenes = [s for s in storage.list_scenes() if s.game_id == game_id]
    questions = [q for q in storage.list_questions() if q.game_id == game_id]
    return scenes, questions


def _shared_links(scenes, questions) -> list[tuple[str, str]]:
    """同一序号的链接相同，取第一条非空值，统一放在文档最前面。"""

    def first(attr):
        for item in list(scenes) + list(questions):
            value = getattr(item, attr, "")
            if value:
                return value
        return ""

    result = []
    paifu = first("paifu_link")
    ai = first("ai_link")
    ai2 = first("ai_link2")
    if paifu:
        result.append(("原牌谱链接", paifu))
    if ai:
        result.append(("AI 复盘链接", ai))
    if ai2:
        result.append(("参考 AI 复盘链接", ai2))
    return result


def render_game_image(storage, game_id: int) -> Image.Image:
    scenes, questions = _game_data(storage, game_id)
    blocks = [
        _text_block(f"牌谱 #{game_id}", _font(34, True), FG),
        _text_block(
            f"何切记录 {len(scenes)} 条　疑问 {len(questions)} 条", _font(20), MUTED
        ),
    ]
    for label, link in _shared_links(scenes, questions):
        blocks.append(_text_block(f"{label}：{link}", _font(18), MUTED))
    blocks.append(_separator())
    blocks.append(_text_block("一、何切记录", _font(26, True), ACCENT))

    if not scenes:
        blocks.append(_text_block("（本牌谱暂无何切记录）", _font(20), MUTED))
    for scene in scenes:
        blocks.append(
            _text_block(f"{scene.title}　进度 {scene.progress}/3", _font(24, True), FG)
        )
        blocks.append(
            _text_block(f"主要标签：{'、'.join(scene.tags) or '（无）'}", _font(20), FG)
        )
        if scene.tags2:
            blocks.append(_text_block(f"次要标签：{'、'.join(scene.tags2)}", _font(20), MUTED))
        blocks += _image_block(scene.whatcut_path, label="何切模式截图")
        blocks += _image_block(scene.ai_path, label="AI 权重截图")
        blocks += _image_block(scene.ai2_path, label="参考 AI 权重截图")
        if scene.comment:
            blocks.append(_text_block(f"文字解读：{scene.comment}", _font(20), FG))
        blocks.append(_separator())

    blocks.append(_text_block("二、疑问小局", _font(26, True), ACCENT))
    if not questions:
        blocks.append(_text_block("（本牌谱暂无疑问记录）", _font(20), MUTED))
    for question in questions:
        blocks.append(
            _text_block(f"#{question.game_id} {question.small_round}", _font(22, True), FG)
        )
        blocks.append(_text_block("疑问点：", _font(20), FG))
        blocks.append(_text_block(question.note or "（无）", _font(20), FG, indent=24))
        blocks.append(_separator())

    return _stack(blocks)


def export_game(storage, game_id: int, fmt: str, out_path) -> None:
    """fmt: "png"（长图）/ "pdf" / "zip"（打包）。"""
    out_path = Path(out_path)
    fmt = fmt.lower()
    if fmt == "zip":
        export_zip(storage, game_id, out_path)
        return
    image = render_game_image(storage, game_id)
    if fmt == "pdf":
        image.save(out_path, "PDF", resolution=150.0)
    else:
        image.save(out_path, "PNG")


def _scene_images(scene) -> list[str]:
    return [name for name in (scene.whatcut_img, scene.ai_img, scene.ai_img2) if name]


def export_zip(storage, game_id: int, out_path) -> tuple[int, int]:
    """把某序号的所有何切（照片 + 信息）与疑问打包为 zip。返回 (何切数, 疑问数)。"""
    scenes = [s for s in storage.list_scenes() if s.game_id == game_id]
    questions = [q for q in storage.list_questions() if q.game_id == game_id]
    manifest = {
        "format": "luckyj_export",
        "version": 1,
        "game_id": game_id,
        "scenes": [],
        "questions": [],
    }
    for scene in scenes:
        manifest["scenes"].append(
            {
                "cut_id": scene.cut_id,
                "paifu_link": scene.paifu_link,
                "ai_link": scene.ai_link,
                "ai_link2": scene.ai_link2,
                "tags": list(scene.tags),
                "tags2": list(scene.tags2),
                "comment": scene.comment,
                "progress": scene.progress,
                "whatcut_img": scene.whatcut_img,
                "ai_img": scene.ai_img,
                "ai_img2": scene.ai_img2,
            }
        )
    for question in questions:
        manifest["questions"].append(
            {
                "small_round": question.small_round,
                "note": question.note,
                "paifu_link": question.paifu_link,
                "ai_link": question.ai_link,
                "ai_link2": question.ai_link2,
            }
        )
    out_path = Path(out_path)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for scene in scenes:
            for name in _scene_images(scene):
                image_path = scene.folder / name
                if image_path.exists():
                    archive.write(image_path, name)
    return len(scenes), len(questions)


def peek_zip_manifest(zip_path) -> dict | None:
    """读取 zip 中 manifest.json，失败返回 None。"""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            return json.loads(archive.read("manifest.json").decode("utf-8"))
    except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError):
        return None


def peek_zip_game_id(zip_path) -> int | None:
    manifest = peek_zip_manifest(zip_path)
    return manifest.get("game_id") if isinstance(manifest, dict) else None


def _extract_member(archive, tmp: Path, name) -> str | None:
    if not name:
        return None
    try:
        data = archive.read(name)
    except KeyError:
        return None
    target = tmp / Path(name).name
    target.write_bytes(data)
    return str(target)


def import_zip(
    storage,
    zip_path,
    target_game_id: int,
    scene_cut_ids=None,
    question_indices=None,
) -> tuple[int, int]:
    """从 zip 导入牌谱到目标序号。

    scene_cut_ids：要导入的何切 cut_id 列表（None=全部）。
    question_indices：要导入的疑问在 manifest 中的下标列表（None=全部）。
    返回 (导入何切数, 导入疑问数)。
    """
    with zipfile.ZipFile(zip_path) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        tmp = Path(tempfile.mkdtemp(prefix="lj_import_"))
        try:
            scene_count = 0
            scenes = sorted(
                manifest.get("scenes", []),
                key=lambda item: int(item.get("cut_id", 0) or 0),
            )
            for scene in scenes:
                cut_id = int(scene.get("cut_id", 0) or 0)
                if scene_cut_ids is not None and cut_id not in scene_cut_ids:
                    continue
                storage.create_scene(
                    game_id=target_game_id,
                    ai_link=str(scene.get("ai_link", "") or ""),
                    tags=list(scene.get("tags", []) or []),
                    ai_img_src=_extract_member(archive, tmp, scene.get("ai_img")),
                    whatcut_img_src=_extract_member(archive, tmp, scene.get("whatcut_img")),
                    paifu_link=str(scene.get("paifu_link", "") or ""),
                    comment=str(scene.get("comment", "") or ""),
                    ai_link2=str(scene.get("ai_link2", "") or ""),
                    ai_img2_src=_extract_member(archive, tmp, scene.get("ai_img2")),
                    tags2=list(scene.get("tags2", []) or []),
                )
                scene_count += 1
            question_count = 0
            for index, question in enumerate(manifest.get("questions", [])):
                if question_indices is not None and index not in question_indices:
                    continue
                storage.add_question(
                    target_game_id,
                    str(question.get("small_round", "") or ""),
                    str(question.get("note", "") or ""),
                    str(question.get("paifu_link", "") or ""),
                    str(question.get("ai_link", "") or ""),
                    str(question.get("ai_link2", "") or ""),
                )
                question_count += 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return scene_count, question_count

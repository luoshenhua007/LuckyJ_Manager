"""LuckyJ_Manager 数据层。

负责 .json 何切文件的读写、截图复制重命名、tag 仓库维护与复习进度管理。

目录结构：
    Files/
    ├── tag.txt
    ├── <牌谱序号>/
    │   ├── <何切序号>/
    │   │   ├── <何切序号>.json
    │   │   ├── <何切序号>_WhatCut.png
    │   │   └── <何切序号>_AI.png
    │   └── ...
    └── ...
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

MASTERED = 3
"""复习进度达到该值表示「不再复习」。"""


def get_base_dir() -> Path:
    """返回项目根目录（包含 Files/ 的目录）。

    打包成 exe 后以 exe 所在目录为准，否则以本文件的上上级目录为准。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def parse_tags(text: str) -> list[str]:
    """把用户输入拆成去重后的标签列表。"""
    parts = re.split(r"[,，;；\s]+", text.strip())
    return _dedupe([p for p in parts if p])


def _dedupe(items) -> list[str]:
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result


@dataclass
class Scene:
    """一道何切题目。"""

    game_id: int
    cut_id: int
    ai_link: str = ""
    ai_link2: str = ""
    tags: list[str] = field(default_factory=list)
    tags2: list[str] = field(default_factory=list)
    progress: int = 0
    paifu_link: str = ""
    comment: str = ""
    whatcut_img: str | None = None
    ai_img: str = ""
    ai_img2: str = ""
    folder: Path | None = None
    match_score: int = 0
    """查找时的匹配得分（命中的输入标签数，不写入 json）。"""
    match_total: int = 0
    """查找时的总命中数（主要+次要，不写入 json）。"""

    # ---- 路径 ----
    @property
    def json_path(self) -> Path | None:
        if self.folder is None:
            return None
        return self.folder / f"{self.cut_id}.json"

    def _image_path(self, name: str | None) -> Path | None:
        if not name or self.folder is None:
            return None
        path = self.folder / name
        return path if path.exists() else None

    @property
    def whatcut_path(self) -> Path | None:
        return self._image_path(self.whatcut_img)

    @property
    def ai_path(self) -> Path | None:
        return self._image_path(self.ai_img)

    @property
    def ai2_path(self) -> Path | None:
        return self._image_path(self.ai_img2)

    @property
    def review_path(self) -> Path | None:
        """复习时展示的图片：优先何切模式截图，否则 AI 权重截图。"""
        return self.whatcut_path or self.ai_path

    @property
    def title(self) -> str:
        return f"#{self.game_id}-{self.cut_id}"

    @property
    def mastered(self) -> bool:
        return self.progress >= MASTERED

    # ---- 序列化 ----
    @classmethod
    def from_file(cls, json_path: Path) -> "Scene":
        json_path = Path(json_path)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        folder = json_path.parent
        cut_id = _to_int(data.get("何切序号"), folder.name)
        game_id = _to_int(data.get("序号"), folder.parent.name)
        progress = _to_int(data.get("复习进度"), 0)
        return cls(
            game_id=game_id,
            cut_id=cut_id,
            ai_link=data.get("AI复盘链接", "") or "",
            ai_link2=data.get("参考AI复盘链接", "") or "",
            tags=list(data.get("标签", []) or []),
            tags2=list(data.get("次要标签", []) or []),
            progress=progress,
            paifu_link=data.get("原牌谱链接", "") or "",
            comment=data.get("文字解读", "") or "",
            whatcut_img=data.get("何切模式截图") or None,
            ai_img=data.get("AI权重截图", "") or "",
            ai_img2=data.get("参考AI权重截图", "") or "",
            folder=folder,
        )

    def to_dict(self) -> dict:
        return {
            "序号": self.game_id,
            "何切序号": self.cut_id,
            "原牌谱链接": self.paifu_link,
            "AI复盘链接": self.ai_link,
            "参考AI复盘链接": self.ai_link2,
            "何切模式截图": self.whatcut_img,
            "AI权重截图": self.ai_img,
            "参考AI权重截图": self.ai_img2,
            "标签": self.tags,
            "次要标签": self.tags2,
            "文字解读": self.comment,
            "复习进度": self.progress,
        }

    def save(self, json_path: Path | None = None) -> None:
        path = Path(json_path) if json_path is not None else self.json_path
        if path is None:
            raise ValueError("Scene 没有关联的 json 路径。")
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _to_int(value, default) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(default)
        except (TypeError, ValueError):
            return 0


@dataclass
class Question:
    """一条疑问记录（不参与复习）。"""

    qid: int
    game_id: int
    small_round: str = ""
    note: str = ""
    paifu_link: str = ""
    ai_link: str = ""
    ai_link2: str = ""

    @property
    def title(self) -> str:
        return f"#{self.game_id} {self.small_round}".strip()

    @classmethod
    def from_dict(cls, data: dict) -> "Question":
        return cls(
            qid=_to_int(data.get("id"), 0),
            game_id=_to_int(data.get("序号"), 0),
            small_round=str(data.get("小局", "") or ""),
            note=str(data.get("疑问点", "") or ""),
            paifu_link=str(data.get("原牌谱链接", "") or ""),
            ai_link=str(data.get("AI复盘链接", "") or ""),
            ai_link2=str(data.get("参考AI复盘链接", "") or ""),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.qid,
            "序号": self.game_id,
            "小局": self.small_round,
            "疑问点": self.note,
            "原牌谱链接": self.paifu_link,
            "AI复盘链接": self.ai_link,
            "参考AI复盘链接": self.ai_link2,
        }


class Storage:
    """Files/ 目录的访问入口。"""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.files_dir = self.base_dir / "Files"
        self.tag_file = self.files_dir / "tags.json"
        self.question_file = self.files_dir / "questions.json"
        self.state_file = self.files_dir / "last.json"
        self.settings_file = self.files_dir / "settings.json"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        if not self.tag_file.exists():
            self.tag_file.write_text("[]\n", encoding="utf-8")

    # ---- 读取 ----
    def list_scenes(self) -> list[Scene]:
        scenes: list[Scene] = []
        for json_path in self.files_dir.glob("*/*/*.json"):
            try:
                scenes.append(Scene.from_file(json_path))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        scenes.sort(key=lambda s: (s.game_id, s.cut_id))
        return scenes

    def find_scenes(self, query: str, mode: str = "strict") -> list[Scene]:
        """按标签查找。

        mode：
          - "strict"  严格匹配：必须命中全部输入标签（主要+次要标签）。
          - "primary" 尽量匹配主标签：按命中主要标签的数量从多到少排序。
          - "any"     尽量匹配标签：按命中（主要+次要）标签的数量从多到少排序。

        标签匹配为子串、忽略大小写；输入多个标签用空格/逗号分隔。
        """
        wanted = [t.lower() for t in parse_tags(query)]
        scenes = self.list_scenes()
        if not wanted:
            for scene in scenes:
                scene.match_score = 0
            return scenes

        results: list[Scene] = []
        for scene in scenes:
            prim = [t.lower() for t in scene.tags]
            both = prim + [t.lower() for t in scene.tags2]
            primary_hits = sum(1 for w in wanted if any(w in tag for tag in prim))
            total_hits = sum(1 for w in wanted if any(w in tag for tag in both))
            scene.match_total = total_hits
            if mode == "strict":
                if total_hits == len(wanted):
                    scene.match_score = total_hits
                    results.append(scene)
            elif mode == "primary":
                if total_hits >= 1:
                    scene.match_score = primary_hits
                    results.append(scene)
            else:  # "any"
                if total_hits >= 1:
                    scene.match_score = total_hits
                    results.append(scene)

        if mode == "strict":
            results.sort(key=lambda s: (s.game_id, s.cut_id))
        elif mode == "primary":
            results.sort(
                key=lambda s: (-s.match_score, -s.match_total, s.game_id, s.cut_id)
            )
        else:
            results.sort(key=lambda s: (-s.match_score, s.game_id, s.cut_id))
        return results

    # ---- 写入 ----
    def next_cut_id(self, game_id: int) -> int:
        game_dir = self.files_dir / str(game_id)
        if not game_dir.exists():
            return 1
        ids = [int(d.name) for d in game_dir.iterdir() if d.is_dir() and d.name.isdigit()]
        return max(ids, default=0) + 1

    def create_scene(
        self,
        game_id: int,
        ai_link: str,
        tags: list[str],
        ai_img_src: str | Path | None,
        whatcut_img_src: str | Path | None = None,
        paifu_link: str = "",
        comment: str = "",
        ai_link2: str = "",
        ai_img2_src: str | Path | None = None,
        tags2: list[str] | None = None,
    ) -> Scene:
        cut_id = self.next_cut_id(game_id)
        folder = self.files_dir / str(game_id) / str(cut_id)
        folder.mkdir(parents=True, exist_ok=True)

        ai_name = self._copy_image(ai_img_src, folder, f"{cut_id}_AI")
        ai2_name = self._copy_image(ai_img2_src, folder, f"{cut_id}_AI2")
        whatcut_name = self._copy_image(whatcut_img_src, folder, f"{cut_id}_WhatCut")

        scene = Scene(
            game_id=game_id,
            cut_id=cut_id,
            ai_link=ai_link,
            ai_link2=ai_link2,
            tags=list(tags),
            tags2=list(tags2 or []),
            progress=0,
            paifu_link=paifu_link,
            comment=comment,
            whatcut_img=whatcut_name,
            ai_img=ai_name or "",
            ai_img2=ai2_name or "",
            folder=folder,
        )
        scene.save()
        self.add_tags(list(tags) + list(tags2 or []))
        self.set_last_game(game_id, paifu_link, ai_link, ai_link2)
        return scene

    # ---- 上次录入的牌谱（方便恢复序号） ----
    def get_last_game(self) -> dict:
        if not self.state_file.exists():
            return {}
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def set_last_game(
        self,
        game_id: int,
        paifu_link: str = "",
        ai_link: str = "",
        ai_link2: str = "",
    ) -> None:
        data = {
            "序号": int(game_id),
            "原牌谱链接": paifu_link or "",
            "AI复盘链接": ai_link or "",
            "参考AI复盘链接": ai_link2 or "",
        }
        self.state_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def update_progress(self, scene: Scene, progress: int) -> None:
        scene.progress = max(0, min(MASTERED, progress))
        scene.save()

    @staticmethod
    def _copy_image(src, folder: Path, stem: str) -> str | None:
        """把截图复制到 folder 并统一转换为 <stem>.png。"""
        if not src:
            return None
        src_path = Path(src)
        if not src_path.exists():
            return None
        name = f"{stem}.png"
        dst = folder / name
        try:
            from PIL import Image

            with Image.open(src_path) as image:
                if image.mode not in ("RGB", "RGBA", "L", "LA"):
                    image = image.convert("RGBA")
                image.save(dst, "PNG")
            return name
        except ImportError:
            # 没有 Pillow 时退化为按原扩展名复制。
            ext = src_path.suffix.lower() or ".png"
            name = f"{stem}{ext}"
            shutil.copyfile(src_path, folder / name)
            return name

    @staticmethod
    def _remove_file(path) -> None:
        if path is None:
            return
        try:
            Path(path).unlink()
        except OSError:
            pass

    @staticmethod
    def _find_image(folder: Path, stem: str) -> str | None:
        if folder is None or not folder.exists():
            return None
        for path in folder.iterdir():
            if path.is_file() and path.stem == stem:
                return path.name
        return None

    def update_scene(
        self,
        scene: Scene,
        *,
        game_id: int | None = None,
        ai_link: str | None = None,
        ai_link2: str | None = None,
        tags: list[str] | None = None,
        tags2: list[str] | None = None,
        paifu_link: str | None = None,
        comment: str | None = None,
        ai_img_src=None,
        ai_img2_src=None,
        whatcut_img_src=None,
        remove_whatcut: bool = False,
        remove_ai2: bool = False,
    ) -> Scene:
        folder = scene.folder
        if folder is None:
            raise ValueError("Scene 没有关联的目录。")

        if game_id is not None and int(game_id) != scene.game_id:
            new_game = int(game_id)
            new_cut = self.next_cut_id(new_game)
            dest = self.files_dir / str(new_game) / str(new_cut)
            dest.parent.mkdir(parents=True, exist_ok=True)
            old_game_dir = folder.parent
            shutil.move(str(folder), str(dest))
            self._cleanup_empty(old_game_dir)
            folder = dest
            if new_cut != scene.cut_id:
                old_cut = scene.cut_id
                for path in list(folder.iterdir()):
                    if path.name.startswith(str(old_cut)):
                        path.rename(folder / (str(new_cut) + path.name[len(str(old_cut)):]))
            scene.folder = folder
            scene.game_id = new_game
            scene.cut_id = new_cut
            scene.ai_img = self._find_image(folder, f"{new_cut}_AI") or scene.ai_img
            scene.ai_img2 = self._find_image(folder, f"{new_cut}_AI2") or scene.ai_img2
            scene.whatcut_img = self._find_image(folder, f"{new_cut}_WhatCut")

        if ai_link is not None:
            scene.ai_link = ai_link
        if ai_link2 is not None:
            scene.ai_link2 = ai_link2
        if tags is not None:
            scene.tags = list(tags)
        if tags2 is not None:
            scene.tags2 = list(tags2)
        if paifu_link is not None:
            scene.paifu_link = paifu_link
        if comment is not None:
            scene.comment = comment

        if ai_img_src:
            self._remove_file(folder / scene.ai_img if scene.ai_img else None)
            new_name = self._copy_image(ai_img_src, folder, f"{scene.cut_id}_AI")
            if new_name:
                scene.ai_img = new_name
        if remove_ai2:
            if scene.ai_img2:
                self._remove_file(folder / scene.ai_img2)
            scene.ai_img2 = ""
        elif ai_img2_src:
            if scene.ai_img2:
                self._remove_file(folder / scene.ai_img2)
            scene.ai_img2 = self._copy_image(
                ai_img2_src, folder, f"{scene.cut_id}_AI2"
            ) or ""
        if remove_whatcut:
            if scene.whatcut_img:
                self._remove_file(folder / scene.whatcut_img)
            scene.whatcut_img = None
        elif whatcut_img_src:
            if scene.whatcut_img:
                self._remove_file(folder / scene.whatcut_img)
            scene.whatcut_img = self._copy_image(
                whatcut_img_src, folder, f"{scene.cut_id}_WhatCut"
            )

        expected = folder / f"{scene.cut_id}.json"
        for stale in folder.glob("*.json"):
            if stale != expected:
                self._remove_file(stale)
        scene.save(expected)
        self.add_tags(list(scene.tags) + list(scene.tags2))
        return scene

    def delete_scene(self, scene: Scene) -> None:
        folder = scene.folder
        if folder is None or not folder.exists():
            return
        parent = folder.parent
        shutil.rmtree(folder)
        self._cleanup_empty(parent)

    @staticmethod
    def _cleanup_empty(folder: Path) -> None:
        try:
            if folder.exists() and not any(folder.iterdir()):
                folder.rmdir()
        except OSError:
            pass

    # ---- tag 仓库 ----
    def get_all_tags(self) -> list[str]:
        if not self.tag_file.exists():
            return []
        try:
            data = json.loads(self.tag_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return _dedupe([str(t) for t in data if str(t)])

    def add_tags(self, tags) -> None:
        existing = self.get_all_tags()
        for tag in tags:
            if tag and tag not in existing:
                existing.append(tag)
        self._write_tags(existing)

    def tag_counts(self) -> dict[str, int]:
        """统计每个标签被多少道何切使用（主/次要标签合计，动态统计）。"""
        counts: dict[str, int] = {}
        for scene in self.list_scenes():
            for tag in list(scene.tags) + list(scene.tags2):
                counts[tag] = counts.get(tag, 0) + 1
        return counts

    @staticmethod
    def _merge_tag_list(tags, sources, target) -> tuple[list[str], bool]:
        changed = False
        result: list[str] = []
        for tag in tags:
            merged = target if tag in sources else tag
            if merged != tag:
                changed = True
            if merged not in result:
                result.append(merged)
        return result, changed

    def merge_tags(self, sources, target: str) -> None:
        """把 sources 中的标签全部合并为 target（用于消除重复/相近标签）。"""
        if not target:
            return
        sources = [s for s in _dedupe(list(sources)) if s and s != target]
        if not sources:
            return
        for scene in self.list_scenes():
            tags, changed1 = self._merge_tag_list(scene.tags, sources, target)
            tags2, changed2 = self._merge_tag_list(scene.tags2, sources, target)
            if changed1 or changed2:
                scene.tags = tags
                scene.tags2 = tags2
                scene.save()
        remaining = [t for t in self.get_all_tags() if t not in sources and t != target]
        remaining.append(target)
        self._write_tags(remaining)

    def rename_tag(self, old: str, new: str) -> None:
        if not old or not new or old == new:
            return
        for scene in self.list_scenes():
            changed = False
            if old in scene.tags:
                scene.tags = _dedupe([new if t == old else t for t in scene.tags])
                changed = True
            if old in scene.tags2:
                scene.tags2 = _dedupe([new if t == old else t for t in scene.tags2])
                changed = True
            if changed:
                scene.save()
        self._write_tags([new if t == old else t for t in self.get_all_tags()])

    def delete_tag(self, tag: str) -> None:
        if not tag:
            return
        for scene in self.list_scenes():
            changed = False
            if tag in scene.tags:
                scene.tags = [t for t in scene.tags if t != tag]
                changed = True
            if tag in scene.tags2:
                scene.tags2 = [t for t in scene.tags2 if t != tag]
                changed = True
            if changed:
                scene.save()
        self._write_tags([t for t in self.get_all_tags() if t != tag])

    def _write_tags(self, tags) -> None:
        cleaned = _dedupe([t for t in tags if t])
        self.tag_file.write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    # ---- 疑问记录 ----
    def list_questions(self) -> list[Question]:
        if not self.question_file.exists():
            return []
        try:
            data = json.loads(self.question_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        questions = [Question.from_dict(item) for item in data if isinstance(item, dict)]
        questions.sort(key=lambda q: (q.game_id, q.qid))
        return questions

    def add_question(
        self,
        game_id: int,
        small_round: str,
        note: str,
        paifu_link: str = "",
        ai_link: str = "",
        ai_link2: str = "",
    ) -> Question:
        questions = self.list_questions()
        next_id = max((q.qid for q in questions), default=0) + 1
        question = Question(
            next_id, game_id, small_round, note, paifu_link, ai_link, ai_link2
        )
        questions.append(question)
        self._write_questions(questions)
        return question

    def update_question(
        self,
        qid: int,
        game_id: int,
        small_round: str,
        note: str,
        paifu_link: str = "",
        ai_link: str = "",
        ai_link2: str = "",
    ) -> None:
        questions = self.list_questions()
        for question in questions:
            if question.qid == qid:
                question.game_id = game_id
                question.small_round = small_round
                question.note = note
                question.paifu_link = paifu_link
                question.ai_link = ai_link
                question.ai_link2 = ai_link2
                break
        self._write_questions(questions)

    def delete_question(self, qid: int) -> None:
        self._write_questions([q for q in self.list_questions() if q.qid != qid])

    def _write_questions(self, questions) -> None:
        data = [q.to_dict() for q in sorted(questions, key=lambda q: (q.game_id, q.qid))]
        self.question_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    # ---- 设置 ----
    def get_settings(self) -> dict:
        defaults = {
            "default_export_format": "png",
            "default_export_dir": "",
            "default_match_mode": "strict",
        }
        if not self.settings_file.exists():
            return defaults
        try:
            loaded = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return defaults
        if not isinstance(loaded, dict):
            return defaults
        result = dict(defaults)
        for key in defaults:
            if key in loaded:
                result[key] = loaded[key]
        return result

    def set_settings(self, settings: dict) -> None:
        data = self.get_settings()
        for key, value in settings.items():
            data[key] = value
        self.settings_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

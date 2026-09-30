"""LuckyJ_Manager 图形界面（Tkinter）。"""

from __future__ import annotations

import os
import random
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk

from storage import MASTERED, Scene, Storage, parse_tags
from exporter import export_game, import_zip, peek_zip_manifest

MAX_IMAGE = (900, 600)
QUESTION_IMAGE = (560, 520)
ANSWER_IMAGE = (460, 320)
IMAGE_TYPES = [
    ("图片", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
    ("所有文件", "*.*"),
]
MODE_KEYS = {
    "严格匹配": "strict",
    "尽量匹配主tag": "primary",
    "尽量匹配tag": "any",
}
MODE_LABELS = {value: key for key, value in MODE_KEYS.items()}
EXPORT_FORMAT_LABELS = {"png": "长图 (PNG)", "pdf": "PDF", "zip": "打包 (ZIP)"}
EXPORT_FORMAT_KEYS = {value: key for key, value in EXPORT_FORMAT_LABELS.items()}


def parse_positive_int(text):
    """把输入解析为正整数，非法（非纯 ASCII 数字或 <=0）返回 None。"""
    text = (text or "").strip()
    if text.isascii() and text.isdigit():
        value = int(text)
        if value > 0:
            return value
    return None


def load_photo(path, max_size):
    """读取图片并等比缩放至不超过 max_size，失败返回 None。

    优先使用 Pillow 获得平滑缩放；不可用时退化为 Tk 内置 PhotoImage 的整数倍缩放。
    """
    if not path:
        return None
    path = str(path)
    try:
        from PIL import Image, ImageTk

        with Image.open(path) as image:
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA")
            else:
                image = image.copy()
        image.thumbnail(max_size, Image.LANCZOS)
        return ImageTk.PhotoImage(image)
    except Exception:
        pass

    try:
        img = tk.PhotoImage(file=path)
    except tk.TclError:
        return None
    width, height = img.width(), img.height()
    max_w, max_h = max_size
    factor_x = (width + max_w - 1) // max_w if width > max_w else 1
    factor_y = (height + max_h - 1) // max_h if height > max_h else 1
    factor = max(factor_x, factor_y, 1)
    if factor > 1:
        img = img.subsample(factor, factor)
    return img


def open_path(path) -> None:
    if not path:
        return
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except OSError:
        pass


def open_url(url) -> None:
    if url:
        webbrowser.open(url)


class BaseFrame(ttk.Frame):
    def __init__(self, master, app: "App"):
        super().__init__(master, padding=16)
        self.app = app
        self.storage: Storage = app.storage
        self._photo = None

    def header(self, title: str) -> ttk.Frame:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 12))
        ttk.Button(bar, text="← 返回", command=self.app.show_home).pack(side="left")
        ttk.Label(bar, text=title, font=("", 16, "bold")).pack(side="left", padx=16)
        return bar


class HomeFrame(BaseFrame):
    def __init__(self, master, app):
        super().__init__(master, app)
        container = ttk.Frame(self)
        container.pack(expand=True)
        ttk.Label(container, text="LuckyJ Manager", font=("", 30, "bold")).pack(pady=(40, 6))
        ttk.Label(container, text="牌谱何切管理", font=("", 12), foreground="#888").pack(
            pady=(0, 32)
        )
        for text, command in (
            ("新建", self.app.show_new),
            ("查找", self.app.show_search),
            ("复习", self.app.show_review),
            ("疑问", self.app.show_questions),
            ("标签管理", self.app.show_tag_manager),
            ("导出/导入", self.app.show_export),
            ("设置", self.app.show_settings),
        ):
            ttk.Button(container, text=text, width=26, command=command).pack(pady=5, ipady=3)
        ttk.Button(container, text="退出程序", width=26, command=self.app.destroy).pack(
            pady=(28, 0), ipady=3
        )


class QuestionDialog(tk.Toplevel):
    """在新增何切时快速记录一条疑问（不丢失当前表单内容）。"""

    def __init__(
        self,
        master,
        storage: Storage,
        game_id=None,
        on_saved=None,
        paifu_link: str = "",
        ai_link: str = "",
        ai_link2: str = "",
    ):
        super().__init__(master)
        self.storage = storage
        self.on_saved = on_saved
        self._paifu_link = paifu_link or ""
        self._ai_link = ai_link or ""
        self._ai_link2 = ai_link2 or ""
        self.title("记录疑问")
        self.geometry("440x300")
        self.transient(master)
        self.grab_set()

        self.game_var = tk.StringVar(value=str(game_id) if game_id is not None else "")
        self.round_var = tk.StringVar()

        form = ttk.Frame(self, padding=16)
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)
        form.rowconfigure(2, weight=1)

        ttk.Label(form, text="序号 *").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.game_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(form, text="小局 *").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.round_var).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Label(form, text="疑问点").grid(row=2, column=0, sticky="nw", pady=6)
        self.note_text = tk.Text(form, height=7, wrap="word")
        self.note_text.grid(row=2, column=1, sticky="nsew", padx=8, pady=6)
        ttk.Label(
            form,
            text="原牌谱 / AI 复盘链接将自动带入当前牌谱的链接。",
            foreground="#888",
            font=("", 9),
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 4))

        actions = ttk.Frame(self, padding=(16, 0))
        actions.pack(fill="x", pady=(0, 12))
        ttk.Button(actions, text="保存", command=self.save).pack(side="right")
        ttk.Button(actions, text="取消", command=self.destroy).pack(side="right", padx=8)

    def save(self):
        game_id = parse_positive_int(self.game_var.get())
        if game_id is None:
            messagebox.showwarning("提示", "序号必须是正整数。", parent=self)
            return
        small_round = self.round_var.get().strip()
        if not small_round:
            messagebox.showwarning("提示", "小局为必填项。", parent=self)
            return
        self.storage.add_question(
            game_id,
            small_round,
            self.note_text.get("1.0", "end").strip(),
            self._paifu_link,
            self._ai_link,
            self._ai_link2,
        )
        if self.on_saved:
            self.on_saved()
        self.destroy()


class NewFrame(BaseFrame):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.header("新建何切")

        self.game_var = tk.StringVar()
        self.paifu_var = tk.StringVar()
        self.ai_link_var = tk.StringVar()
        self.ai_link2_var = tk.StringVar()
        self.whatcut_var = tk.StringVar()
        self.ai_img_var = tk.StringVar()
        self.ai_img2_var = tk.StringVar()
        self.tags_var = tk.StringVar()
        self.tags2_var = tk.StringVar()
        self.status_var = tk.StringVar(value="带 * 的为必填项。")
        self.game_hint_var = tk.StringVar(value="")

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, minsize=300)

        game_box = ttk.LabelFrame(main, text="牌谱信息（一局可连续添加多道何切）", padding=10)
        game_box.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        game_box.columnconfigure(1, weight=1)
        self._add_entry(game_box, 0, "序号 *", self.game_var, hint="对应 xlsx 中的序号")
        self._add_entry(game_box, 1, "原牌谱链接", self.paifu_var, hint="天凤原牌谱链接（选填）")
        ttk.Label(game_box, textvariable=self.game_hint_var, foreground="#2a7").grid(
            row=2, column=1, columnspan=2, sticky="w", padx=8
        )
        ttk.Button(game_box, text="恢复上次序号", command=self.restore_last_game).grid(
            row=3, column=2, sticky="w", padx=8
        )
        self.game_var.trace_add("write", lambda *_: self._update_game_hint())

        cut_box = ttk.LabelFrame(main, text="何切信息", padding=10)
        cut_box.grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(12, 0))
        cut_box.columnconfigure(1, weight=1)
        self._add_entry(cut_box, 0, "AI 复盘链接 *", self.ai_link_var, hint="主要链接（必填）")
        self._add_entry(cut_box, 1, "参考 AI 复盘链接", self.ai_link2_var, hint="次要链接（选填）")
        self._add_file(cut_box, 2, "何切模式截图", self.whatcut_var)
        self._add_file(cut_box, 3, "AI 权重截图 *", self.ai_img_var)
        self._add_file(cut_box, 4, "参考 AI 权重截图", self.ai_img2_var)
        self._add_entry(cut_box, 5, "主要标签 *", self.tags_var, hint="影响何切选择的主要因素")
        self._add_entry(cut_box, 6, "次要标签", self.tags2_var, hint="次要/辅助标签（选填）")
        self.comment_text = self._add_text(cut_box, 7, "文字解读", height=4)

        tag_box = ttk.LabelFrame(main, text="已有标签（按使用次数排序，双击加到主要标签）", padding=8)
        tag_box.grid(row=0, column=1, rowspan=2, sticky="nsew")
        self.tag_list = tk.Listbox(tag_box, exportselection=False)
        self.tag_list.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(tag_box, orient="vertical", command=self.tag_list.yview)
        scroll.pack(side="right", fill="y")
        self.tag_list.configure(yscrollcommand=scroll.set)
        self.tag_list.bind("<Double-Button-1>", self._add_tag_from_list)
        tag_btns = ttk.Frame(tag_box)
        tag_btns.pack(side="right", fill="y", padx=(8, 0))
        ttk.Button(tag_btns, text="加到主要 →", command=self._add_selected_to_primary).pack(fill="x")
        ttk.Button(tag_btns, text="加到次要 →", command=self._add_selected_to_secondary).pack(
            fill="x", pady=(6, 0)
        )
        self._refresh_tags()

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="保存并继续添加", command=self.save).pack(side="left")
        ttk.Button(actions, text="清空何切", command=self.clear_cut).pack(side="left", padx=8)
        ttk.Button(actions, text="清空全部", command=self.clear_all).pack(side="left")
        ttk.Button(actions, text="记录疑问…", command=self.open_question_dialog).pack(
            side="right"
        )
        ttk.Label(self, textvariable=self.status_var, foreground="#555").pack(
            anchor="w", pady=(8, 0)
        )

    def _add_entry(self, parent, row, label, var, hint=""):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", padx=8, pady=6)
        ttk.Label(parent, text=hint, foreground="#888").grid(row=row, column=2, sticky="w")

    def _add_file(self, parent, row, label, var):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8, pady=6)
        ttk.Button(parent, text="选择…", command=lambda: self._pick_file(var)).grid(
            row=row, column=2, sticky="w"
        )

    def _add_text(self, parent, row, label, height=4):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="nw", pady=6)
        box = ttk.Frame(parent)
        box.grid(row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=6)
        text = tk.Text(box, height=height, wrap="word")
        text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(box, orient="vertical", command=text.yview)
        scroll.pack(side="right", fill="y")
        text.configure(yscrollcommand=scroll.set)
        return text

    def _pick_file(self, var):
        path = filedialog.askopenfilename(title="选择截图", filetypes=IMAGE_TYPES)
        if path:
            var.set(path)

    def _refresh_tags(self):
        self.tag_list.delete(0, "end")
        counts = self.storage.tag_counts()
        tags = sorted(self.storage.get_all_tags(), key=lambda t: (-counts.get(t, 0), t))
        self._tag_names = tags
        for tag in tags:
            self.tag_list.insert("end", f"{tag} ({counts.get(tag, 0)})")

    def _add_tag_from_list(self, _event):
        self._add_selected_tag(self.tags_var)

    def _add_selected_to_primary(self):
        self._add_selected_tag(self.tags_var)

    def _add_selected_to_secondary(self):
        self._add_selected_tag(self.tags2_var)

    def _add_selected_tag(self, var):
        selection = self.tag_list.curselection()
        if not selection:
            return
        names = getattr(self, "_tag_names", [])
        if selection[0] >= len(names):
            return
        tag = names[selection[0]]
        current = parse_tags(var.get())
        if tag not in current:
            current.append(tag)
            var.set(" ".join(current))

    def open_question_dialog(self):
        prefill = parse_positive_int(self.game_var.get())
        QuestionDialog(
            self,
            self.storage,
            game_id=prefill,
            paifu_link=self.paifu_var.get().strip(),
            ai_link=self.ai_link_var.get().strip(),
            ai_link2=self.ai_link2_var.get().strip(),
        )

    def restore_last_game(self):
        last = self.storage.get_last_game()
        game_id = last.get("序号")
        if game_id is None:
            messagebox.showinfo("提示", "没有可恢复的上次序号。")
            return
        self.game_var.set(str(game_id))
        if not self.paifu_var.get().strip() and last.get("原牌谱链接"):
            self.paifu_var.set(last["原牌谱链接"])
        if not self.ai_link_var.get().strip() and last.get("AI复盘链接"):
            self.ai_link_var.set(last["AI复盘链接"])
        if not self.ai_link2_var.get().strip() and last.get("参考AI复盘链接"):
            self.ai_link2_var.set(last["参考AI复盘链接"])
        self.status_var.set(f"已恢复上次序号 #{game_id}（含牌谱/复盘链接）。")

    def _update_game_hint(self):
        game_id = parse_positive_int(self.game_var.get())
        if game_id is None:
            self.game_hint_var.set("")
            return
        count = sum(1 for s in self.storage.list_scenes() if s.game_id == game_id)
        next_id = self.storage.next_cut_id(game_id)
        self.game_hint_var.set(f"该牌谱已有 {count} 道何切，下一道为 #{game_id}-{next_id}。")

    def clear_cut(self, keep_links: bool = False):
        if not keep_links:
            self.ai_link_var.set("")
            self.ai_link2_var.set("")
        for var in (
            self.whatcut_var,
            self.ai_img_var,
            self.ai_img2_var,
            self.tags_var,
            self.tags2_var,
        ):
            var.set("")
        self.comment_text.delete("1.0", "end")
        self.status_var.set("已清空何切信息，牌谱信息保留。")

    def clear_all(self):
        self.clear_cut()
        self.game_var.set("")
        self.paifu_var.set("")
        self.status_var.set("带 * 的为必填项。")

    def save(self):
        game_id = parse_positive_int(self.game_var.get())
        if game_id is None:
            messagebox.showwarning("提示", "序号必须是正整数。")
            return
        ai_link = self.ai_link_var.get().strip()
        if not ai_link:
            messagebox.showwarning("提示", "AI 复盘链接为必填项。")
            return
        ai_img = self.ai_img_var.get().strip()
        if not ai_img or not os.path.exists(ai_img):
            messagebox.showwarning("提示", "请选择有效的 AI 权重截图。")
            return
        tags = parse_tags(self.tags_var.get())
        if not tags:
            messagebox.showwarning("提示", "至少填写一个主要标签。")
            return
        tags2 = parse_tags(self.tags2_var.get())
        whatcut = self.whatcut_var.get().strip()
        if whatcut and not os.path.exists(whatcut):
            messagebox.showwarning("提示", "何切模式截图路径不存在。")
            return

        try:
            scene = self.storage.create_scene(
                game_id=game_id,
                ai_link=ai_link,
                tags=tags,
                ai_img_src=ai_img,
                whatcut_img_src=whatcut or None,
                paifu_link=self.paifu_var.get().strip(),
                comment=self.comment_text.get("1.0", "end").strip(),
                ai_link2=self.ai_link2_var.get().strip(),
                ai_img2_src=self.ai_img2_var.get().strip() or None,
                tags2=tags2,
            )
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc))
            return

        self.clear_cut(keep_links=True)
        self._refresh_tags()
        self._update_game_hint()
        self.status_var.set(f"已保存 {scene.title}，可继续添加下一道何切（AI 链接已保留）。")
        messagebox.showinfo("成功", f"已保存 {scene.title}。")


class SceneEditor(tk.Toplevel):
    """编辑已有何切题目的弹窗。"""

    def __init__(self, master, storage: Storage, scene: Scene, on_saved):
        super().__init__(master)
        self.storage = storage
        self.scene = scene
        self.on_saved = on_saved
        self._ai_src: str | None = None
        self._ai2_src: str | None = None
        self._whatcut_src: str | None = None
        self._remove_whatcut = False
        self._remove_ai2 = False

        self.title(f"编辑 {scene.title}")
        self.geometry("780x640")
        self.transient(master)
        self.grab_set()

        self.game_var = tk.StringVar(value=str(scene.game_id))
        self.paifu_var = tk.StringVar(value=scene.paifu_link)
        self.ai_link_var = tk.StringVar(value=scene.ai_link)
        self.ai_link2_var = tk.StringVar(value=scene.ai_link2)
        self.tags_var = tk.StringVar(value=" ".join(scene.tags))
        self.tags2_var = tk.StringVar(value=" ".join(scene.tags2))
        self.ai_img_var = tk.StringVar(value=scene.ai_img or "（无）")
        self.ai_img2_var = tk.StringVar(value=scene.ai_img2 or "（无）")
        self.whatcut_var = tk.StringVar(
            value=scene.whatcut_img or "（无）"
        )

        self._build()

    def _build(self):
        form = ttk.Frame(self, padding=16)
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="序号 *").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.game_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(form, text="（修改后该题会移动到新的牌谱目录）", foreground="#888").grid(
            row=0, column=2, sticky="w"
        )

        ttk.Label(form, text="原牌谱链接").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.paifu_var).grid(row=1, column=1, columnspan=2, sticky="ew", padx=8)

        ttk.Label(form, text="AI 复盘链接 *").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.ai_link_var).grid(row=2, column=1, columnspan=2, sticky="ew", padx=8)

        ttk.Label(form, text="参考 AI 复盘链接").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.ai_link2_var).grid(row=3, column=1, columnspan=2, sticky="ew", padx=8)

        ttk.Label(form, text="何切模式截图").grid(row=4, column=0, sticky="w", pady=6)
        ttk.Label(form, textvariable=self.whatcut_var).grid(row=4, column=1, sticky="w", padx=8)
        wc_btns = ttk.Frame(form)
        wc_btns.grid(row=4, column=2, sticky="w")
        ttk.Button(wc_btns, text="选择新图", command=self._pick_whatcut).pack(side="left")
        ttk.Button(wc_btns, text="移除", command=self._remove_whatcut_image).pack(side="left", padx=6)

        ttk.Label(form, text="AI 权重截图 *").grid(row=5, column=0, sticky="w", pady=6)
        ttk.Label(form, textvariable=self.ai_img_var).grid(row=5, column=1, sticky="w", padx=8)
        ttk.Button(form, text="选择新图", command=self._pick_ai).grid(row=5, column=2, sticky="w")

        ttk.Label(form, text="参考 AI 权重截图").grid(row=6, column=0, sticky="w", pady=6)
        ttk.Label(form, textvariable=self.ai_img2_var).grid(row=6, column=1, sticky="w", padx=8)
        ai2_btns = ttk.Frame(form)
        ai2_btns.grid(row=6, column=2, sticky="w")
        ttk.Button(ai2_btns, text="选择新图", command=self._pick_ai2).pack(side="left")
        ttk.Button(ai2_btns, text="移除", command=self._remove_ai2_image).pack(side="left", padx=6)

        ttk.Label(form, text="主要标签 *").grid(row=7, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.tags_var).grid(row=7, column=1, columnspan=2, sticky="ew", padx=8)

        ttk.Label(form, text="次要标签").grid(row=8, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.tags2_var).grid(row=8, column=1, columnspan=2, sticky="ew", padx=8)

        ttk.Label(form, text="文字解读").grid(row=9, column=0, sticky="nw", pady=6)
        self.comment_text = tk.Text(form, height=5, wrap="word")
        self.comment_text.grid(row=9, column=1, columnspan=2, sticky="ew", padx=8, pady=6)
        self.comment_text.insert("1.0", self.scene.comment)

        actions = ttk.Frame(self, padding=(16, 0))
        actions.pack(fill="x", pady=12)
        ttk.Button(actions, text="保存", command=self._save).pack(side="left")
        ttk.Button(actions, text="取消", command=self.destroy).pack(side="left", padx=8)

    def _pick_ai(self):
        path = filedialog.askopenfilename(title="选择 AI 权重截图", filetypes=IMAGE_TYPES)
        if path:
            self._ai_src = path
            self.ai_img_var.set(path)

    def _pick_ai2(self):
        path = filedialog.askopenfilename(title="选择参考 AI 权重截图", filetypes=IMAGE_TYPES)
        if path:
            self._ai2_src = path
            self._remove_ai2 = False
            self.ai_img2_var.set(path)

    def _remove_ai2_image(self):
        self._ai2_src = None
        self._remove_ai2 = True
        self.ai_img2_var.set("（无）")

    def _pick_whatcut(self):
        path = filedialog.askopenfilename(title="选择何切模式截图", filetypes=IMAGE_TYPES)
        if path:
            self._whatcut_src = path
            self._remove_whatcut = False
            self.whatcut_var.set(path)

    def _remove_whatcut_image(self):
        self._whatcut_src = None
        self._remove_whatcut = True
        self.whatcut_var.set("（无）")

    def _save(self):
        game_id = parse_positive_int(self.game_var.get())
        if game_id is None:
            messagebox.showwarning("提示", "序号必须是正整数。", parent=self)
            return
        ai_link = self.ai_link_var.get().strip()
        if not ai_link:
            messagebox.showwarning("提示", "AI 复盘链接为必填项。", parent=self)
            return
        tags = parse_tags(self.tags_var.get())
        if not tags:
            messagebox.showwarning("提示", "至少填写一个主要标签。", parent=self)
            return
        try:
            self.storage.update_scene(
                self.scene,
                game_id=game_id,
                ai_link=ai_link,
                ai_link2=self.ai_link2_var.get().strip(),
                tags=tags,
                tags2=parse_tags(self.tags2_var.get()),
                paifu_link=self.paifu_var.get().strip(),
                comment=self.comment_text.get("1.0", "end").strip(),
                ai_img_src=self._ai_src,
                ai_img2_src=self._ai2_src,
                whatcut_img_src=self._whatcut_src,
                remove_whatcut=self._remove_whatcut,
                remove_ai2=self._remove_ai2,
            )
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        self.on_saved()
        self.destroy()


class SearchFrame(BaseFrame):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.header("查找何切")
        self._scenes: dict[str, Scene] = {}

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="标签：").pack(side="left")
        self.query_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.query_var)
        entry.pack(side="left", fill="x", expand=True, padx=6)
        entry.bind("<Return>", lambda _e: self.search())
        ttk.Button(top, text="查找", command=self.search).pack(side="left")
        ttk.Button(top, text="显示全部", command=self.show_all).pack(side="left", padx=6)
        ttk.Label(top, text="匹配：").pack(side="left", padx=(12, 0))
        default_mode = self.storage.get_settings().get("default_match_mode", "strict")
        self.mode_var = tk.StringVar(value=MODE_LABELS.get(default_mode, "严格匹配"))
        mode_box = ttk.Combobox(
            top,
            textvariable=self.mode_var,
            width=15,
            state="readonly",
            values=list(MODE_KEYS.keys()),
        )
        mode_box.pack(side="left", padx=6)
        mode_box.bind("<<ComboboxSelected>>", lambda _e: self.search())

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=12)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        self.tree = ttk.Treeview(
            left, columns=("tags", "tags2", "match", "progress"), show="tree headings"
        )
        self.tree.heading("#0", text="题目")
        self.tree.heading("tags", text="主要标签")
        self.tree.heading("tags2", text="次要标签")
        self.tree.heading("match", text="匹配")
        self.tree.heading("progress", text="进度")
        self.tree.column("#0", width=80, anchor="w")
        self.tree.column("tags", width=190, anchor="w")
        self.tree.column("tags2", width=170, anchor="w")
        self.tree.column("match", width=50, anchor="center")
        self.tree.column("progress", width=50, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        right = ttk.LabelFrame(body, text="预览", padding=8)
        right.pack(side="right", fill="both", padx=(12, 0))
        img_frame = ttk.Frame(right)
        img_frame.pack(fill="both", expand=True)
        self.image_canvas = tk.Canvas(img_frame, bg="#f5f5f5", highlightthickness=0)
        self.image_canvas.pack(side="left", fill="both", expand=True)
        img_vbar = ttk.Scrollbar(img_frame, orient="vertical", command=self.image_canvas.yview)
        img_vbar.pack(side="right", fill="y")
        self.image_canvas.configure(yscrollcommand=img_vbar.set)
        img_hbar = ttk.Scrollbar(right, orient="horizontal", command=self.image_canvas.xview)
        img_hbar.pack(side="bottom", fill="x")
        self.image_canvas.configure(xscrollcommand=img_hbar.set)
        self.image_canvas.bind("<Configure>", self._on_canvas_resize)
        self.info_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.info_var, justify="left", wraplength=380).pack(
            anchor="w", pady=6
        )
        buttons = ttk.Frame(right)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="何切图", command=lambda: self.show_view("whatcut")).pack(side="left")
        ttk.Button(buttons, text="主AI图", command=lambda: self.show_view("ai")).pack(side="left", padx=6)
        ttk.Button(buttons, text="参考AI图", command=lambda: self.show_view("ai2")).pack(side="left")
        ttk.Button(buttons, text="打开原图", command=self.open_image).pack(side="left", padx=6)
        ttk.Button(buttons, text="打开AI链接", command=self.open_ai_link).pack(side="left")
        ttk.Button(buttons, text="打开参考链接", command=self.open_ai_link2).pack(side="left", padx=6)
        ttk.Button(buttons, text="打开原牌谱", command=self.open_paifu).pack(side="left")

        edit_buttons = ttk.Frame(right)
        edit_buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(edit_buttons, text="编辑题目", command=self.edit_scene).pack(side="left")
        ttk.Button(edit_buttons, text="删除题目", command=self.delete_scene).pack(side="left", padx=6)

        self._current: Scene | None = None
        self._view = "whatcut"
        self.show_all()

    def _populate(self, scenes: list[Scene]):
        self.tree.delete(*self.tree.get_children())
        self._scenes.clear()
        query = self.query_var.get().strip()
        has_query = bool(query)
        total = len(parse_tags(query)) if has_query else 0
        mode = MODE_KEYS.get(self.mode_var.get(), "strict")
        for scene in scenes:
            iid = scene.title
            if not has_query:
                match = "-"
            elif mode == "strict":
                match = f"{total}/{total}"
            else:
                match = f"{scene.match_score}/{total}"
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=scene.title,
                values=(
                    ", ".join(scene.tags),
                    ", ".join(scene.tags2),
                    match,
                    f"{scene.progress}/{MASTERED}",
                ),
            )
            self._scenes[iid] = scene
        self._current = None
        self._current_path = None
        self.info_var.set("")
        self._reset_canvas()

    def show_all(self):
        self.query_var.set("")
        self._populate(self.storage.list_scenes())

    def search(self):
        mode = MODE_KEYS.get(self.mode_var.get(), "strict")
        self._populate(self.storage.find_scenes(self.query_var.get(), mode))

    def _on_select(self, _event):
        selection = self.tree.selection()
        if not selection:
            return
        self._current = self._scenes.get(selection[0])
        self._view = "whatcut"
        self._render()

    def show_view(self, view):
        if self._current is None:
            messagebox.showinfo("提示", "请先在左侧选择一道题目。")
            return
        self._view = view
        self._render()

    def _render(self):
        scene = self._current
        if scene is None:
            return
        candidates = {
            "whatcut": (scene.whatcut_path, "何切模式截图"),
            "ai": (scene.ai_path, "AI 权重截图"),
            "ai2": (scene.ai2_path, "参考 AI 权重截图"),
        }
        path, kind = candidates.get(self._view, (None, ""))
        if path is None:
            for key in ("whatcut", "ai", "ai2"):
                candidate, label = candidates[key]
                if candidate is not None:
                    path, kind, self._view = candidate, label, key
                    break
        self._current_path = path
        self._draw_image()
        info = (
            f"{scene.title}\n主要标签：{', '.join(scene.tags)}\n"
            f"次要标签：{', '.join(scene.tags2) or '（无）'}\n"
            f"进度：{scene.progress}/{MASTERED}\n当前显示：{kind}"
        )
        if scene.comment:
            info += f"\n文字解读：{scene.comment}"
        self.info_var.set(info)

    def _reset_canvas(self):
        self.image_canvas.delete("all")
        self.image_canvas.configure(scrollregion=(0, 0, 0, 0))
        self.image_canvas.create_text(
            160, 80, text="选择左侧题目查看", fill="#888"
        )

    def _draw_image(self):
        canvas = self.image_canvas
        canvas.delete("all")
        path = getattr(self, "_current_path", None)
        if not path:
            canvas.create_text(160, 80, text="（无可用截图）", fill="#888")
            return
        width = canvas.winfo_width()
        if width < 60:
            width = 640
        photo = load_photo(path, (width - 4, 100000))
        self._photo = photo
        if photo is None:
            canvas.create_text(160, 80, text="（无法加载图片）", fill="#888")
            return
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_resize(self, _event):
        if getattr(self, "_current", None) is not None:
            self._draw_image()

    def open_ai_link(self):
        if self._current:
            open_url(self._current.ai_link)

    def open_ai_link2(self):
        if self._current and self._current.ai_link2:
            open_url(self._current.ai_link2)
        elif self._current:
            messagebox.showinfo("提示", "该题没有填写参考 AI 复盘链接。")

    def open_paifu(self):
        if self._current:
            open_url(self._current.paifu_link)

    def open_image(self):
        if self._current is None:
            return
        scene = self._current
        path = {
            "whatcut": scene.whatcut_path,
            "ai": scene.ai_path,
            "ai2": scene.ai2_path,
        }.get(self._view)
        open_path(path or scene.review_path)

    def edit_scene(self):
        if self._current is None:
            messagebox.showinfo("提示", "请先在左侧选择一道题目。")
            return
        SceneEditor(self, self.storage, self._current, on_saved=self.search)

    def delete_scene(self):
        if self._current is None:
            messagebox.showinfo("提示", "请先在左侧选择一道题目。")
            return
        if not messagebox.askyesno("确认删除", f"确定删除 {self._current.title}？该操作不可恢复。"):
            return
        self.storage.delete_scene(self._current)
        self.search()


class ReviewFrame(BaseFrame):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.header("复习何切")

        self.info_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.info_var, justify="left").pack(anchor="w", pady=(0, 8))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        q_box = ttk.LabelFrame(body, text="题目", padding=8)
        q_box.pack(side="left", fill="both", expand=True)
        self.question_label = ttk.Label(q_box, text="", anchor="center")
        self.question_label.pack(fill="both", expand=True)

        a_box = ttk.LabelFrame(body, text="答案（AI 权重 + 文字解读）", padding=8)
        a_box.pack(side="right", fill="both", padx=(12, 0))
        self.answer_container = ttk.Frame(a_box)
        self.answer_container.pack(fill="both", expand=True)
        self.reveal_btn = ttk.Button(self.answer_container, text="显示答案", command=self.reveal)
        self.answer_label = ttk.Label(self.answer_container, text="", anchor="center")
        self.ai_toggle_btn = ttk.Button(
            self.answer_container, text="查看参考AI图", command=self.toggle_answer_image
        )
        self.comment_text = tk.Text(
            self.answer_container, height=6, wrap="word", state="disabled"
        )

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(10, 0))
        self.correct_btn = ttk.Button(buttons, text="做对了", command=self.on_correct)
        self.correct_btn.pack(side="left")
        self.wrong_btn = ttk.Button(buttons, text="做错了", command=self.on_wrong)
        self.wrong_btn.pack(side="left", padx=8)
        self.stop_btn = ttk.Button(buttons, text="不再复习", command=self.on_stop)
        self.stop_btn.pack(side="left")

        self._current: Scene | None = None
        self._revealed = False
        self._answer_view = "ai"
        self.next_question()

    def _pool(self) -> list[Scene]:
        return [s for s in self.storage.list_scenes() if not s.mastered]

    def next_question(self):
        pool = self._pool()
        if not pool:
            self._current = None
            self._revealed = False
            self._set_buttons(False)
            self.reveal_btn.configure(state="disabled")
            self._hide_answer()
            self.question_label.configure(image="", text="没有需要复习的题目。")
            self.question_label.image = None
            self.info_var.set("所有题目均已掌握。")
            return
        choices = [s for s in pool if s is not self._current] or pool
        self._current = random.choice(choices)
        self._revealed = False
        self._reset_answer_area()
        self._set_buttons(False)
        self._render_question()

    def _set_buttons(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for btn in (self.correct_btn, self.wrong_btn, self.stop_btn):
            btn.configure(state=state)

    def _hide_answer(self):
        self.reveal_btn.pack_forget()
        self.answer_label.pack_forget()
        self.ai_toggle_btn.pack_forget()
        self.comment_text.pack_forget()

    def _reset_answer_area(self):
        self.answer_label.pack_forget()
        self.ai_toggle_btn.pack_forget()
        self.comment_text.pack_forget()
        self.reveal_btn.configure(state="normal")
        self.reveal_btn.pack(pady=40)

    def _render_question(self):
        scene = self._current
        if scene is None:
            return
        question_path = scene.whatcut_path or scene.ai_path
        photo = load_photo(question_path, QUESTION_IMAGE)
        self._photo = photo
        if photo is not None:
            self.question_label.configure(image=photo, text="")
            self.question_label.image = photo
        else:
            self.question_label.configure(image="", text="（无可用截图）")
            self.question_label.image = None
        self.info_var.set(
            f"{scene.title}　标签：{', '.join(scene.tags)}　进度：{scene.progress}/{MASTERED}"
        )

    def reveal(self):
        scene = self._current
        if scene is None:
            return
        self._revealed = True
        self.reveal_btn.pack_forget()

        self._answer_view = "ai"
        self._render_answer_image()
        self.answer_label.pack(fill="both", expand=True)
        if scene.ai2_path is not None:
            self.ai_toggle_btn.configure(text="查看参考AI图")
            self.ai_toggle_btn.pack(pady=4)

        self.comment_text.configure(state="normal")
        self.comment_text.delete("1.0", "end")
        self.comment_text.insert("1.0", scene.comment or "（无文字解读）")
        self.comment_text.configure(state="disabled")
        self.comment_text.pack(fill="both", expand=True, pady=(8, 0))

        self._set_buttons(True)

    def toggle_answer_image(self):
        if self._current is None:
            return
        if self._answer_view == "ai" and self._current.ai2_path is not None:
            self._answer_view = "ai2"
            self.ai_toggle_btn.configure(text="查看主AI图")
        else:
            self._answer_view = "ai"
            self.ai_toggle_btn.configure(text="查看参考AI图")
        self._render_answer_image()

    def _render_answer_image(self):
        scene = self._current
        if scene is None:
            return
        path = scene.ai2_path if self._answer_view == "ai2" else scene.ai_path
        photo = load_photo(path, ANSWER_IMAGE)
        self._answer_photo = photo
        if photo is not None:
            self.answer_label.configure(image=photo, text="")
            self.answer_label.image = photo
        else:
            self.answer_label.configure(image="", text="（无 AI 权重截图）")
            self.answer_label.image = None

    def on_correct(self):
        if self._current is None:
            return
        new_progress = self._current.progress + 1
        self.storage.update_progress(self._current, new_progress)
        if new_progress >= MASTERED:
            messagebox.showinfo("完成", f"{self._current.title} 已连续做对三次，不再复习。")
        self.next_question()

    def on_wrong(self):
        if self._current is None:
            return
        self.storage.update_progress(self._current, 0)
        self.next_question()

    def on_stop(self):
        if self._current is None:
            return
        self.storage.update_progress(self._current, MASTERED)
        self.next_question()


class TagManagerFrame(BaseFrame):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.header("标签管理")
        self._tag_names: list[str] = []

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="标签列表（按使用次数排序，可多选）", padding=8)
        left.pack(side="left", fill="y")
        self.listbox = tk.Listbox(left, exportselection=False, selectmode="extended", width=28)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        right = ttk.LabelFrame(body, text="操作", padding=16)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        inner = ttk.Frame(right)
        inner.pack(anchor="n", fill="x")
        ttk.Label(inner, text="标签名：").pack(anchor="w")
        self.entry_var = tk.StringVar()
        ttk.Entry(inner, textvariable=self.entry_var, width=32).pack(fill="x", pady=6)
        ttk.Button(inner, text="添加标签", command=self.add_tag).pack(fill="x", pady=3)
        ttk.Button(inner, text="重命名为输入框内容", command=self.rename_tag).pack(fill="x", pady=3)
        ttk.Button(inner, text="删除选中标签", command=self.delete_tag).pack(fill="x", pady=3)
        ttk.Button(inner, text="合并选中标签…", command=self.merge_tags).pack(fill="x", pady=3)
        ttk.Separator(inner, orient="horizontal").pack(fill="x", pady=10)
        self.count_var = tk.StringVar()
        ttk.Label(inner, textvariable=self.count_var, justify="left", wraplength=280).pack(
            anchor="w"
        )
        ttk.Label(
            inner,
            text="提示：可按住 Ctrl / Shift 多选，再删除或合并。",
            foreground="#888",
            font=("", 9),
        ).pack(anchor="w", pady=(10, 0))

        self.refresh()

    def refresh(self):
        self.listbox.delete(0, "end")
        counts = self.storage.tag_counts()
        tags = sorted(self.storage.get_all_tags(), key=lambda t: (-counts.get(t, 0), t))
        self._tag_names = tags
        for tag in tags:
            self.listbox.insert("end", f"{tag} ({counts.get(tag, 0)})")
        scenes = self.storage.list_scenes()
        self.count_var.set(f"共 {len(tags)} 个标签，{len(scenes)} 道何切题。")

    def _selected_names(self) -> list[str]:
        names = []
        for index in self.listbox.curselection():
            if index < len(self._tag_names):
                names.append(self._tag_names[index])
        return names

    def _on_select(self, _event):
        names = self._selected_names()
        if names:
            self.entry_var.set(names[-1])

    def add_tag(self):
        tags = parse_tags(self.entry_var.get())
        if not tags:
            messagebox.showinfo("提示", "请输入标签名。")
            return
        self.storage.add_tags(tags)
        self.entry_var.set("")
        self.refresh()

    def rename_tag(self):
        names = self._selected_names()
        new = self.entry_var.get().strip()
        if not names:
            messagebox.showinfo("提示", "请先在左侧选择要重命名的标签。")
            return
        old = names[0]
        if not new or new == old:
            messagebox.showinfo("提示", "请在输入框填写新的标签名。")
            return
        self.storage.rename_tag(old, new)
        self.entry_var.set("")
        self.refresh()

    def delete_tag(self):
        names = self._selected_names()
        if not names:
            messagebox.showinfo("提示", "请先在左侧选择要删除的标签。")
            return
        if not messagebox.askyesno(
            "确认删除", f"确定删除标签「{'、'.join(names)}」？\n这些标签会从所有题目中移除。"
        ):
            return
        for tag in names:
            self.storage.delete_tag(tag)
        self.entry_var.set("")
        self.refresh()

    def merge_tags(self):
        names = self._selected_names()
        if len(names) < 2:
            messagebox.showinfo("提示", "请至少选择两个标签进行合并。")
            return
        target = simpledialog.askstring(
            "合并标签",
            "把选中的标签合并为（输入目标标签名）：\n\n" + "、".join(names),
            initialvalue=names[0],
            parent=self,
        )
        if target is None:
            return
        target = target.strip()
        if not target:
            messagebox.showinfo("提示", "目标标签名不能为空。")
            return
        self.storage.merge_tags(names, target)
        self.entry_var.set("")
        self.refresh()
        messagebox.showinfo("完成", f"已合并为「{target}」。")


class QuestionFrame(BaseFrame):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.header("疑问小局")
        self._questions: dict[str, object] = {}
        self._current = None

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        self.tree = ttk.Treeview(left, columns=("round", "note"), show="tree headings")
        self.tree.heading("#0", text="序号")
        self.tree.heading("round", text="小局")
        self.tree.heading("note", text="疑问点")
        self.tree.column("#0", width=70, anchor="w")
        self.tree.column("round", width=130, anchor="w")
        self.tree.column("note", width=420, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        right = ttk.LabelFrame(body, text="记录疑问", padding=10)
        right.pack(side="right", fill="y", padx=(12, 0))

        ttk.Label(right, text="序号 *").pack(anchor="w")
        self.game_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.game_var, width=30).pack(fill="x", pady=4)

        ttk.Label(right, text="小局 *").pack(anchor="w")
        self.round_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.round_var, width=30).pack(fill="x", pady=4)

        ttk.Label(right, text="原牌谱链接").pack(anchor="w")
        self.paifu_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.paifu_var, width=30).pack(fill="x", pady=4)

        ttk.Label(right, text="AI 复盘链接").pack(anchor="w")
        self.ai_link_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.ai_link_var, width=30).pack(fill="x", pady=4)

        ttk.Label(right, text="参考 AI 复盘链接").pack(anchor="w")
        self.ai_link2_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.ai_link2_var, width=30).pack(fill="x", pady=4)

        link_btns = ttk.Frame(right)
        link_btns.pack(fill="x", pady=(0, 4))
        ttk.Button(link_btns, text="打开原牌谱", command=lambda: self._open_link(self.paifu_var.get(), "原牌谱链接")).pack(side="left")
        ttk.Button(link_btns, text="打开AI链接", command=lambda: self._open_link(self.ai_link_var.get(), "AI 复盘链接")).pack(side="left", padx=4)
        ttk.Button(link_btns, text="打开参考链接", command=lambda: self._open_link(self.ai_link2_var.get(), "参考 AI 复盘链接")).pack(side="left")

        ttk.Label(right, text="疑问点").pack(anchor="w")
        self.note_text = tk.Text(right, width=36, height=7, wrap="word")
        self.note_text.pack(fill="both", expand=True, pady=4)

        buttons = ttk.Frame(right)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="新增", command=self.add).pack(side="left")
        ttk.Button(buttons, text="保存修改", command=self.update).pack(side="left", padx=6)
        ttk.Button(buttons, text="删除", command=self.delete).pack(side="left")
        ttk.Button(right, text="清空", command=self.clear).pack(fill="x", pady=(6, 0))

        self.status_var = tk.StringVar(value="带 * 的为必填项。")
        ttk.Label(right, textvariable=self.status_var, foreground="#555", wraplength=240).pack(
            anchor="w", pady=(6, 0)
        )

        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._questions.clear()
        for question in self.storage.list_questions():
            iid = str(question.qid)
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=str(question.game_id),
                values=(question.small_round, question.note.replace("\n", " ")),
            )
            self._questions[iid] = question
        self._current = None

    def _on_select(self, _event):
        selection = self.tree.selection()
        if not selection:
            return
        question = self._questions.get(selection[0])
        if question is None:
            return
        self._current = question
        self.game_var.set(str(question.game_id))
        self.round_var.set(question.small_round)
        self.paifu_var.set(question.paifu_link)
        self.ai_link_var.set(question.ai_link)
        self.ai_link2_var.set(question.ai_link2)
        self.note_text.delete("1.0", "end")
        self.note_text.insert("1.0", question.note)
        self.status_var.set(f"正在编辑 #{question.game_id} {question.small_round}")

    def _read_form(self):
        game_id = parse_positive_int(self.game_var.get())
        if game_id is None:
            messagebox.showwarning("提示", "序号必须是正整数。")
            return None
        small_round = self.round_var.get().strip()
        if not small_round:
            messagebox.showwarning("提示", "小局为必填项。")
            return None
        return (
            game_id,
            small_round,
            self.note_text.get("1.0", "end").strip(),
            self.paifu_var.get().strip(),
            self.ai_link_var.get().strip(),
            self.ai_link2_var.get().strip(),
        )

    def _open_link(self, url, label):
        url = (url or "").strip()
        if not url:
            messagebox.showinfo("提示", f"没有填写{label}。")
            return
        open_url(url)

    def add(self):
        parsed = self._read_form()
        if parsed is None:
            return
        self.storage.add_question(*parsed)
        self.clear()
        self.refresh()
        self.status_var.set("已新增疑问。")

    def update(self):
        if self._current is None:
            messagebox.showinfo("提示", "请先在左侧选择要修改的疑问。")
            return
        parsed = self._read_form()
        if parsed is None:
            return
        self.storage.update_question(self._current.qid, *parsed)
        self.clear()
        self.refresh()
        self.status_var.set("已保存修改。")

    def delete(self):
        if self._current is None:
            messagebox.showinfo("提示", "请先在左侧选择要删除的疑问。")
            return
        title = f"#{self._current.game_id} {self._current.small_round}"
        if not messagebox.askyesno("确认删除", f"确定删除「{title}」的疑问？"):
            return
        self.storage.delete_question(self._current.qid)
        self.clear()
        self.refresh()
        self.status_var.set("已删除。")

    def clear(self):
        self._current = None
        self.game_var.set("")
        self.round_var.set("")
        self.paifu_var.set("")
        self.ai_link_var.set("")
        self.ai_link2_var.set("")
        self.note_text.delete("1.0", "end")
        for iid in self.tree.selection():
            self.tree.selection_remove(iid)
        self.status_var.set("带 * 的为必填项。")


class ImportDialog(tk.Toplevel):
    """选择要导入的何切与疑问（默认全选）。"""

    def __init__(self, master, storage: Storage, manifest: dict):
        super().__init__(master)
        self.storage = storage
        self.manifest = manifest
        self.result = None
        self._scenes = sorted(
            manifest.get("scenes", []),
            key=lambda item: int(item.get("cut_id", 0) or 0),
        )
        self._questions = manifest.get("questions", [])
        self.title("选择要导入的内容")
        self.geometry("560x560")
        self.transient(master)
        self.grab_set()

        top = ttk.Frame(self, padding=16)
        top.pack(fill="x")
        ttk.Label(top, text="目标序号 *").pack(side="left")
        self.game_var = tk.StringVar(value=str(manifest.get("game_id", "")))
        ttk.Entry(top, textvariable=self.game_var, width=14).pack(side="left", padx=8)

        body = ttk.Frame(self, padding=(16, 0))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        body.rowconfigure(3, weight=1)

        ttk.Label(body, text=f"何切记录（{len(self._scenes)}）").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self.scene_list = tk.Listbox(body, selectmode="extended", exportselection=False)
        self.scene_list.grid(row=1, column=0, sticky="nsew")
        for scene in self._scenes:
            self.scene_list.insert(
                "end", f"#{scene.get('cut_id')}  主要标签：{', '.join(scene.get('tags', []))}"
            )

        ttk.Label(body, text=f"疑问小局（{len(self._questions)}）").grid(
            row=2, column=0, sticky="w", pady=(12, 4)
        )
        self.question_list = tk.Listbox(body, selectmode="extended", exportselection=False)
        self.question_list.grid(row=3, column=0, sticky="nsew")
        for question in self._questions:
            self.question_list.insert(
                "end", f"{question.get('small_round', '')}　{question.get('note', '')}"
            )

        buttons = ttk.Frame(self, padding=16)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="全选", command=self.select_all).pack(side="left")
        ttk.Button(buttons, text="全不选", command=self.select_none).pack(side="left", padx=8)
        ttk.Button(buttons, text="导入", command=self.confirm).pack(side="right")
        ttk.Button(buttons, text="取消", command=self.destroy).pack(side="right", padx=8)

        self.select_all()

    def _set_all(self, listbox, selected: bool):
        listbox.selection_clear(0, "end")
        if selected:
            listbox.selection_set(0, "end")

    def select_all(self):
        self._set_all(self.scene_list, True)
        self._set_all(self.question_list, True)

    def select_none(self):
        self._set_all(self.scene_list, False)
        self._set_all(self.question_list, False)

    def confirm(self):
        game_id = parse_positive_int(self.game_var.get())
        if game_id is None:
            messagebox.showwarning("提示", "序号必须是正整数。", parent=self)
            return
        scene_ids = [int(self._scenes[i].get("cut_id", 0) or 0) for i in self.scene_list.curselection()]
        question_indices = list(self.question_list.curselection())
        if not scene_ids and not question_indices:
            messagebox.showwarning("提示", "请至少选择一项要导入的内容。", parent=self)
            return
        self.result = (game_id, scene_ids, question_indices)
        self.destroy()


class ExportFrame(BaseFrame):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.header("导出 / 导入")
        self.status_var = tk.StringVar(value="输入序号，选择格式后点“生成…”。")

        wrap = ttk.Frame(self)
        wrap.pack(expand=True)

        export_box = ttk.LabelFrame(wrap, text="导出", padding=24)
        export_box.pack(fill="x")

        form = ttk.Frame(export_box)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="序号 *").grid(row=0, column=0, sticky="w", pady=8)
        self.game_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.game_var, width=16).grid(
            row=0, column=1, sticky="w", padx=12
        )

        ttk.Label(form, text="格式").grid(row=1, column=0, sticky="w", pady=8)
        default_fmt = self.storage.get_settings().get("default_export_format", "png")
        self.format_var = tk.StringVar(value=EXPORT_FORMAT_LABELS.get(default_fmt, "长图 (PNG)"))
        ttk.Combobox(
            form,
            textvariable=self.format_var,
            width=14,
            state="readonly",
            values=list(EXPORT_FORMAT_KEYS.keys()),
        ).grid(row=1, column=1, sticky="w", padx=12)

        ttk.Button(export_box, text="生成…", command=self.generate).pack(fill="x", pady=(12, 0))
        ttk.Label(
            export_box,
            text="内容：该序号下所有何切记录（图片 + 文字解读），以及所有疑问小局与疑问点。",
            foreground="#888",
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(12, 0))

        import_box = ttk.LabelFrame(wrap, text="导入", padding=24)
        import_box.pack(fill="x", pady=(12, 0))
        ttk.Label(
            import_box,
            text="选择他人分享的 ZIP 文件，把其中的何切与疑问收入本机。",
            foreground="#888",
            wraplength=420,
            justify="left",
        ).pack(anchor="w")
        ttk.Button(import_box, text="导入 ZIP…", command=self.import_zip).pack(
            fill="x", pady=(8, 0)
        )

        ttk.Label(self, textvariable=self.status_var, foreground="#555", wraplength=420).pack(
            anchor="w", pady=(12, 0)
        )

    def generate(self):
        game_id = parse_positive_int(self.game_var.get())
        if game_id is None:
            messagebox.showwarning("提示", "序号必须是正整数。")
            return
        label = self.format_var.get()
        fmt = EXPORT_FORMAT_KEYS.get(label, "png")
        ext = {"png": ".png", "pdf": ".pdf", "zip": ".zip"}[fmt]
        scenes = [s for s in self.storage.list_scenes() if s.game_id == game_id]
        questions = [q for q in self.storage.list_questions() if q.game_id == game_id]
        if not scenes and not questions:
            messagebox.showinfo("提示", f"牌谱 #{game_id} 没有何切记录或疑问记录。")
            return
        default_dir = self.storage.get_settings().get("default_export_dir", "") or str(
            self.storage.base_dir
        )
        path = filedialog.asksaveasfilename(
            title="保存导出文件",
            initialdir=default_dir,
            initialfile=f"牌谱_{game_id}{ext}",
            defaultextension=ext,
            filetypes=[(label, f"*{ext}"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            export_game(self.storage, game_id, fmt, path)
        except Exception as exc:  # noqa: BLE001 - 导出失败原因多样，统一提示
            messagebox.showerror("导出失败", str(exc))
            return
        self.status_var.set(f"已导出：{path}")
        messagebox.showinfo("完成", f"已导出到：\n{path}")

    def import_zip(self):
        path = filedialog.askopenfilename(
            title="选择要导入的 ZIP 文件",
            filetypes=[("ZIP 打包", "*.zip"), ("所有文件", "*.*")],
        )
        if not path:
            return
        manifest = peek_zip_manifest(path)
        if not isinstance(manifest, dict):
            messagebox.showerror("导入失败", "无法读取 ZIP 中的清单文件（manifest.json）。")
            return
        dialog = ImportDialog(self, self.storage, manifest)
        self.wait_window(dialog)
        result = dialog.result
        if result is None:
            return
        game_id, scene_ids, question_indices = result
        try:
            scene_count, question_count = import_zip(
                self.storage, path, game_id, scene_ids, question_indices
            )
        except Exception as exc:  # noqa: BLE001 - 导入失败原因多样，统一提示
            messagebox.showerror("导入失败", str(exc))
            return
        self.status_var.set(
            f"已导入 {scene_count} 道何切、{question_count} 条疑问到 #{game_id}。"
        )
        messagebox.showinfo(
            "完成", f"已导入 {scene_count} 道何切、{question_count} 条疑问到 #{game_id}。"
        )


class SettingsFrame(BaseFrame):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.header("设置")
        self.status_var = tk.StringVar(value="")
        settings = self.storage.get_settings()

        wrap = ttk.Frame(self)
        wrap.pack(expand=True)
        box = ttk.LabelFrame(wrap, text="偏好设置", padding=24)
        box.pack()

        form = ttk.Frame(box)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="默认导出格式").grid(row=0, column=0, sticky="w", pady=8)
        self.format_var = tk.StringVar(
            value=EXPORT_FORMAT_LABELS.get(settings.get("default_export_format", "png"), "长图 (PNG)")
        )
        ttk.Combobox(
            form,
            textvariable=self.format_var,
            width=16,
            state="readonly",
            values=list(EXPORT_FORMAT_KEYS.keys()),
        ).grid(row=0, column=1, sticky="w", padx=12)

        ttk.Label(form, text="默认导出目录").grid(row=1, column=0, sticky="w", pady=8)
        dir_row = ttk.Frame(form)
        dir_row.grid(row=1, column=1, sticky="ew", padx=12)
        self.dir_var = tk.StringVar(
            value=settings.get("default_export_dir", "") or str(self.storage.base_dir)
        )
        ttk.Entry(dir_row, textvariable=self.dir_var).pack(side="left", fill="x", expand=True)
        ttk.Button(dir_row, text="选择…", command=self._pick_dir).pack(side="left", padx=6)

        ttk.Label(form, text="默认匹配方式").grid(row=2, column=0, sticky="w", pady=8)
        self.mode_var = tk.StringVar(
            value=MODE_LABELS.get(settings.get("default_match_mode", "strict"), "严格匹配")
        )
        ttk.Combobox(
            form,
            textvariable=self.mode_var,
            width=16,
            state="readonly",
            values=list(MODE_KEYS.keys()),
        ).grid(row=2, column=1, sticky="w", padx=12)

        ttk.Separator(box, orient="horizontal").pack(fill="x", pady=12)
        ttk.Label(
            box,
            text=f"数据目录（只读）：{self.storage.files_dir}",
            foreground="#888",
            wraplength=460,
            justify="left",
        ).pack(anchor="w")
        ttk.Label(box, textvariable=self.status_var, foreground="#2a7", wraplength=460).pack(
            anchor="w", pady=(10, 0)
        )
        ttk.Button(box, text="保存设置", command=self.save).pack(fill="x", pady=(16, 0))

    def _pick_dir(self):
        chosen = filedialog.askdirectory(
            title="选择默认导出目录",
            initialdir=self.dir_var.get() or str(self.storage.base_dir),
        )
        if chosen:
            self.dir_var.set(chosen)

    def save(self):
        self.storage.set_settings(
            {
                "default_export_format": EXPORT_FORMAT_KEYS.get(self.format_var.get(), "png"),
                "default_export_dir": self.dir_var.get().strip(),
                "default_match_mode": MODE_KEYS.get(self.mode_var.get(), "strict"),
            }
        )
        self.status_var.set("已保存设置。")


class App(tk.Tk):
    def __init__(self, storage: Storage | None = None):
        super().__init__()
        self.storage = storage or Storage()
        self.title("LuckyJ Manager")
        self.geometry("1280x720")
        self.minsize(940, 680)
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self.show_home()

    def _swap(self, factory):
        for child in self.container.winfo_children():
            child.destroy()
        frame = factory(self.container, self)
        frame.pack(fill="both", expand=True)

    def show_home(self):
        self._swap(HomeFrame)

    def show_new(self):
        self._swap(NewFrame)

    def show_search(self):
        self._swap(SearchFrame)

    def show_review(self):
        self._swap(ReviewFrame)

    def show_questions(self):
        self._swap(QuestionFrame)

    def show_tag_manager(self):
        self._swap(TagManagerFrame)

    def show_export(self):
        self._swap(ExportFrame)

    def show_settings(self):
        self._swap(SettingsFrame)

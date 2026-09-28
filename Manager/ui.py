"""LuckyJ_Manager 图形界面（Tkinter）。"""

from __future__ import annotations

import os
import random
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from storage import MASTERED, Scene, Storage, parse_tags

MAX_IMAGE = (900, 600)
QUESTION_IMAGE = (560, 520)
ANSWER_IMAGE = (460, 320)
IMAGE_TYPES = [
    ("图片", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
    ("所有文件", "*.*"),
]


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
        ttk.Label(self, text="LuckyJ Manager", font=("", 30, "bold")).pack(pady=(80, 50))
        for text, command in (
            ("新建", self.app.show_new),
            ("查找", self.app.show_search),
            ("复习", self.app.show_review),
            ("标签管理", self.app.show_tag_manager),
        ):
            ttk.Button(self, text=text, width=22, command=command).pack(pady=8)


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
        self.status_var = tk.StringVar(value="带 * 的为必填项。")
        self.game_hint_var = tk.StringVar(value="")

        game_box = ttk.LabelFrame(self, text="牌谱信息（一局可连续添加多道何切）", padding=10)
        game_box.pack(fill="x")
        game_box.columnconfigure(1, weight=1)
        self._add_entry(game_box, 0, "序号 *", self.game_var, hint="对应 xlsx 中的序号")
        self._add_entry(game_box, 1, "原牌谱链接", self.paifu_var, hint="天凤原牌谱链接（选填）")
        ttk.Label(game_box, textvariable=self.game_hint_var, foreground="#2a7").grid(
            row=2, column=1, columnspan=2, sticky="w", padx=8
        )
        self.game_var.trace_add("write", lambda *_: self._update_game_hint())

        cut_box = ttk.LabelFrame(self, text="何切信息", padding=10)
        cut_box.pack(fill="x", pady=(12, 0))
        cut_box.columnconfigure(1, weight=1)
        self._add_entry(cut_box, 0, "AI 复盘链接 *", self.ai_link_var, hint="主要链接（必填）")
        self._add_entry(cut_box, 1, "参考 AI 复盘链接", self.ai_link2_var, hint="次要链接（选填）")
        self._add_file(cut_box, 2, "何切模式截图", self.whatcut_var)
        self._add_file(cut_box, 3, "AI 权重截图 *", self.ai_img_var)
        self._add_file(cut_box, 4, "参考 AI 权重截图", self.ai_img2_var)
        self._add_entry(cut_box, 5, "标签 *", self.tags_var, hint="多个标签用空格或逗号分隔")
        self.comment_text = self._add_text(cut_box, 6, "文字解读", height=4)

        tag_box = ttk.LabelFrame(self, text="已有标签（双击添加）", padding=8)
        tag_box.pack(fill="x", pady=(12, 0))
        self.tag_list = tk.Listbox(tag_box, height=4, exportselection=False)
        self.tag_list.pack(side="left", fill="x", expand=True)
        scroll = ttk.Scrollbar(tag_box, orient="vertical", command=self.tag_list.yview)
        scroll.pack(side="right", fill="y")
        self.tag_list.configure(yscrollcommand=scroll.set)
        self.tag_list.bind("<Double-Button-1>", self._add_tag_from_list)
        self._refresh_tags()

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=12)
        ttk.Button(actions, text="保存并继续添加", command=self.save).pack(side="left")
        ttk.Button(actions, text="清空何切", command=self.clear_cut).pack(side="left", padx=8)
        ttk.Button(actions, text="清空全部", command=self.clear_all).pack(side="left")
        ttk.Label(self, textvariable=self.status_var, foreground="#555").pack(anchor="w")

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
        for tag in self.storage.get_all_tags():
            self.tag_list.insert("end", tag)

    def _add_tag_from_list(self, _event):
        selection = self.tag_list.curselection()
        if not selection:
            return
        tag = self.tag_list.get(selection[0])
        current = parse_tags(self.tags_var.get())
        if tag not in current:
            current.append(tag)
            self.tags_var.set(" ".join(current))

    def _update_game_hint(self):
        text = self.game_var.get().strip()
        if not text.isdigit() or int(text) <= 0:
            self.game_hint_var.set("")
            return
        game_id = int(text)
        count = sum(1 for s in self.storage.list_scenes() if s.game_id == game_id)
        next_id = self.storage.next_cut_id(game_id)
        self.game_hint_var.set(f"该牌谱已有 {count} 道何切，下一道为 #{game_id}-{next_id}。")

    def clear_cut(self):
        for var in (
            self.ai_link_var,
            self.ai_link2_var,
            self.whatcut_var,
            self.ai_img_var,
            self.ai_img2_var,
            self.tags_var,
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
        game_text = self.game_var.get().strip()
        if not game_text.isdigit() or int(game_text) <= 0:
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
            messagebox.showwarning("提示", "至少填写一个标签。")
            return
        whatcut = self.whatcut_var.get().strip()
        if whatcut and not os.path.exists(whatcut):
            messagebox.showwarning("提示", "何切模式截图路径不存在。")
            return

        try:
            scene = self.storage.create_scene(
                game_id=int(game_text),
                ai_link=ai_link,
                tags=tags,
                ai_img_src=ai_img,
                whatcut_img_src=whatcut or None,
                paifu_link=self.paifu_var.get().strip(),
                comment=self.comment_text.get("1.0", "end").strip(),
                ai_link2=self.ai_link2_var.get().strip(),
                ai_img2_src=self.ai_img2_var.get().strip() or None,
            )
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc))
            return

        self.clear_cut()
        self._refresh_tags()
        self._update_game_hint()
        self.status_var.set(f"已保存 {scene.title}，可继续添加下一道何切。")
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

        ttk.Label(form, text="标签 *").grid(row=7, column=0, sticky="w", pady=6)
        ttk.Entry(form, textvariable=self.tags_var).grid(row=7, column=1, columnspan=2, sticky="ew", padx=8)

        ttk.Label(form, text="文字解读").grid(row=8, column=0, sticky="nw", pady=6)
        self.comment_text = tk.Text(form, height=5, wrap="word")
        self.comment_text.grid(row=8, column=1, columnspan=2, sticky="ew", padx=8, pady=6)
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
        game_text = self.game_var.get().strip()
        if not game_text.isdigit():
            messagebox.showwarning("提示", "序号必须是非负整数。", parent=self)
            return
        ai_link = self.ai_link_var.get().strip()
        if not ai_link:
            messagebox.showwarning("提示", "AI 复盘链接为必填项。", parent=self)
            return
        tags = parse_tags(self.tags_var.get())
        if not tags:
            messagebox.showwarning("提示", "至少填写一个标签。", parent=self)
            return
        try:
            self.storage.update_scene(
                self.scene,
                game_id=int(game_text),
                ai_link=ai_link,
                ai_link2=self.ai_link2_var.get().strip(),
                tags=tags,
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

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=12)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        self.tree = ttk.Treeview(left, columns=("tags", "progress"), show="tree headings")
        self.tree.heading("#0", text="题目")
        self.tree.heading("tags", text="标签")
        self.tree.heading("progress", text="进度")
        self.tree.column("#0", width=90, anchor="w")
        self.tree.column("tags", width=260, anchor="w")
        self.tree.column("progress", width=60, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        right = ttk.LabelFrame(body, text="预览", padding=8)
        right.pack(side="right", fill="both", padx=(12, 0))
        self.image_label = ttk.Label(right, text="选择左侧题目查看", anchor="center")
        self.image_label.pack(fill="both", expand=True)
        self.info_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.info_var, justify="left", wraplength=380).pack(
            anchor="w", pady=6
        )
        buttons = ttk.Frame(right)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="切换截图", command=self.toggle_image).pack(side="left")
        ttk.Button(buttons, text="参考AI图", command=self.show_ai2).pack(side="left", padx=6)
        ttk.Button(buttons, text="打开原图", command=self.open_image).pack(side="left")
        ttk.Button(buttons, text="打开AI链接", command=self.open_ai_link).pack(side="left", padx=6)
        ttk.Button(buttons, text="打开参考链接", command=self.open_ai_link2).pack(side="left")
        ttk.Button(buttons, text="打开原牌谱", command=self.open_paifu).pack(side="left", padx=6)

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
        for scene in scenes:
            iid = scene.title
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=scene.title,
                values=(", ".join(scene.tags), f"{scene.progress}/{MASTERED}"),
            )
            self._scenes[iid] = scene
        self.image_label.configure(image="", text="选择左侧题目查看")
        self.image_label.image = None
        self._current = None
        self.info_var.set("")

    def show_all(self):
        self.query_var.set("")
        self._populate(self.storage.list_scenes())

    def search(self):
        self._populate(self.storage.find_scenes(self.query_var.get()))

    def _on_select(self, _event):
        selection = self.tree.selection()
        if not selection:
            return
        self._current = self._scenes.get(selection[0])
        self._view = "whatcut"
        self._render()

    def toggle_image(self):
        if self._current is None:
            return
        order = ["whatcut", "ai", "ai2"]
        self._view = order[(order.index(self._view) + 1) % len(order)]
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
        photo = load_photo(path, MAX_IMAGE)
        self._photo = photo
        if photo is not None:
            self.image_label.configure(image=photo, text="")
            self.image_label.image = photo
        else:
            self.image_label.configure(image="", text="（无可用截图）")
            self.image_label.image = None
        info = (
            f"{scene.title}\n标签：{', '.join(scene.tags)}\n"
            f"进度：{scene.progress}/{MASTERED}\n当前显示：{kind}"
        )
        if scene.comment:
            info += f"\n文字解读：{scene.comment}"
        self.info_var.set(info)

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

    def show_ai2(self):
        if self._current is None:
            messagebox.showinfo("提示", "请先在左侧选择一道题目。")
            return
        self._view = "ai2"
        self._render()

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

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="标签列表", padding=8)
        left.pack(side="left", fill="both", expand=True)
        self.listbox = tk.Listbox(left, exportselection=False)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        right = ttk.LabelFrame(body, text="操作", padding=8)
        right.pack(side="right", fill="y", padx=(12, 0))
        ttk.Label(right, text="标签名：").pack(anchor="w")
        self.entry_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.entry_var, width=24).pack(fill="x", pady=6)
        ttk.Button(right, text="添加", command=self.add_tag).pack(fill="x", pady=2)
        ttk.Button(right, text="重命名为输入框内容", command=self.rename_tag).pack(fill="x", pady=2)
        ttk.Button(right, text="删除选中标签", command=self.delete_tag).pack(fill="x", pady=2)
        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=8)
        self.count_var = tk.StringVar()
        ttk.Label(right, textvariable=self.count_var, justify="left", wraplength=220).pack(anchor="w")

        self.refresh()

    def refresh(self):
        self.listbox.delete(0, "end")
        tags = self.storage.get_all_tags()
        for tag in tags:
            self.listbox.insert("end", tag)
        scenes = self.storage.list_scenes()
        self.count_var.set(f"共 {len(tags)} 个标签，{len(scenes)} 道何切题。")

    def _on_select(self, _event):
        selection = self.listbox.curselection()
        if selection:
            self.entry_var.set(self.listbox.get(selection[0]))

    def add_tag(self):
        tags = parse_tags(self.entry_var.get())
        if not tags:
            messagebox.showinfo("提示", "请输入标签名。")
            return
        self.storage.add_tags(tags)
        self.entry_var.set("")
        self.refresh()

    def rename_tag(self):
        selection = self.listbox.curselection()
        new = self.entry_var.get().strip()
        if not selection:
            messagebox.showinfo("提示", "请先在左侧选择要重命名的标签。")
            return
        old = self.listbox.get(selection[0])
        if not new or new == old:
            messagebox.showinfo("提示", "请在输入框填写新的标签名。")
            return
        self.storage.rename_tag(old, new)
        self.entry_var.set("")
        self.refresh()

    def delete_tag(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showinfo("提示", "请先在左侧选择要删除的标签。")
            return
        tag = self.listbox.get(selection[0])
        if not messagebox.askyesno(
            "确认删除", f"确定删除标签「{tag}」？\n该标签会从所有题目中移除。"
        ):
            return
        self.storage.delete_tag(tag)
        self.entry_var.set("")
        self.refresh()


class App(tk.Tk):
    def __init__(self, storage: Storage | None = None):
        super().__init__()
        self.storage = storage or Storage()
        self.title("LuckyJ Manager")
        self.geometry("1120x780")
        self.minsize(900, 640)
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

    def show_tag_manager(self):
        self._swap(TagManagerFrame)

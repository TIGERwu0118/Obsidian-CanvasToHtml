# Obsidian-CanvasToHtml

**简体中文** | [English](./README.md)

> 将 Obsidian 的 **`.canvas`** 导出为可移植、自包含的 HTML 包 —— 附带 `attachments/` 文件夹，包含所有引用的笔记和图片。

![导出效果](./examples/demo-screenshot.png)

把这样一个文件：

```
my-note.canvas   （Obsidian Canvas 核心插件生成的 JSON）
```

变成这样一个文件夹：

```
my-note_html/
├── my-note.html          ← 任意浏览器打开，完全离线
└── attachments/
    ├── note1.md
    ├── note2.md
    ├── figure1.png       ← 内联嵌入
    └── figure2.png
```

导出的页面是 canvas 的**可交互、可平移缩放**复刻版：分组显示为虚线容器，文本卡片渲染为 Obsidian 风味的 markdown，文件卡片渲染其 `.md` 内容或内嵌图片，连线绘制为带标签的贝塞尔曲线。把整个文件夹拷进 U 盘、发邮件、静态托管都行 —— 无需 Obsidian、无需服务器、无需联网。

---

## ✨ 特性

- **忠于原布局** —— 保留 canvas 的坐标系、颜色、分组嵌套和连线走向。
- **天生可移植** —— 每个被引用的笔记和图片都复制进 `attachments/`；HTML 只用相对路径。
- **Obsidian 风味 markdown** —— 表格、带语法高亮 class 的代码块、任务列表、wikilink `[[目标]]`、`![[图片.png]]` 嵌入全部可渲染。
- **可交互** —— 中键拖拽平移，滚轮以游标为中心缩放，左键拖卡片移动，左键拖右下角缩放卡片。连线和标签实时跟随。
- **缺文件不崩溃** —— vault 路径失效时渲染为带标签的占位符，而不是直接报错。
- **零网络** —— 转换器是单文件 Python 脚本，没有任何 HTTP 调用，可放心离线运行。

---

## 📦 安装

### 作为 ZCode / Claude Code skill

这个仓库**本身就是 skill**。克隆到任意 skill 发现目录即可：

```bash
# 用户级（所有项目可用）
git clone https://github.com/TIGERwu0118/Obsidian-CanvasToHtml.git \
  ~/.zcode/skills/Obsidian-CanvasToHtml

# 或项目级
git clone https://github.com/TIGERwu0118/Obsidian-CanvasToHtml.git \
  ./.zcode/skills/Obsidian-CanvasToHtml
```

之后只需说一句 *"把这个 canvas 导出成 html"*，skill 就会触发。完整触发词和 agent 工作流见 [`SKILL.md`](./SKILL.md)。

### 作为独立脚本

不需要 skill 加载器，转换器本身就是一个普通 CLI：

```bash
git clone https://github.com/TIGERwu0118/Obsidian-CanvasToHtml.git
cd Obsidian-CanvasToHtml
pip install -r requirements.txt
python scripts/canvas_to_html.py path/to/my.canvas
```

---

## 🚀 用法

```bash
python scripts/canvas_to_html.py <输入.canvas> [选项]
```

| 选项 | 作用 |
|------|------|
| `<canvas>` *(位置参数)* | `.canvas` 文件路径，必填。 |
| `--vault-root DIR` | Obsidian vault 根目录，省略时自动向上查找 `.obsidian/`。 |
| `--output-dir DIR` | 输出目录，默认在 canvas 旁生成 `<canvas名>_html/`。 |
| `--title TEXT` | HTML `<title>` 和顶栏标题，默认用 canvas 文件名。 |
| `--open` | 转换完成后用默认浏览器打开结果。 |

### 示例

```bash
# 基本用法 —— 输出到 ./report_html/
python scripts/canvas_to_html.py report.canvas

# 指定输出位置和标题
python scripts/canvas_to_html.py report.canvas \
  --output-dir ./site/report \
  --title "Q3 研究地图"

# canvas 在 vault 外 —— 显式指定 vault 根
python scripts/canvas_to_html.py ~/Downloads/notes.canvas \
  --vault-root ~/Obsidian/MyVault
```

---

## 🖱️ 交互速查

| 操作 | 按键 |
|---|---|
| **平移画布** | 鼠标中键拖拽 *（全局有效 —— 落在卡片、手柄、空白处都行）* |
| **移动卡片** | 左键拖卡片本体 |
| **缩放卡片** | 左键拖右下角手柄 *（hover 时显现）* |
| **缩放视图** | 滚轮 *（以游标为中心）* |
| **适应全部** | 顶栏 `Fit` 按钮 |
| **重置视图** | 顶栏 `Reset` 按钮 |

---

## 🧠 工作原理

1. **解析** `.canvas` JSON（`nodes[]` + `edges[]`）。
2. **定位 vault 根** —— 从 canvas 路径向上查找 `.obsidian/`。
3. **渲染**每个节点：
   - `group` → 带颜色标签的虚线容器
   - `text` → Obsidian 风味 markdown（基于 `python-markdown` + `pymdown-extensions`）
   - `file` → 图片则内联嵌入；`.md` 则渲染内容并复制源文件；其它则给出链接
   - `link` → 外部锚点
4. **复制**所有被引用的文件到 `attachments/`（按文件名 + 大小去重）。
5. **输出**单个 HTML 文件（内嵌全部 CSS + JS）外加 `attachments/` 文件夹。

视口是一个绝对定位的节点层，由单个 CSS `translate()+scale()` 变换驱动；SVG 连线层共享同一变换，所以两者平移缩放完全同步。卡片移动或缩放时连线几何实时重算，每条连线的文字标签重新定位到贝塞尔曲线中点（t=0.5），始终钉在曲线上。

---

## 📁 项目结构

```
Obsidian-CanvasToHtml/
├── SKILL.md                       # skill 定义（触发词 + agent 工作流）
├── README.md                      # 英文说明
├── README.zh-CN.md                # 你在这里
├── LICENSE                        # MIT
├── requirements.txt               # markdown / pymdown-extensions / Pygments
└── scripts/
    └── canvas_to_html.py          # 转换器（单文件，约 800 行）
```

完整导出示例见 [`examples/`](./examples/)（README 里有复现步骤）。

---

## ⚙️ 依赖

- **Python 3.9+**
- `markdown >= 3.7`
- `pymdown-extensions >= 10`
- `Pygments >= 2.18` *（仅用于代码高亮的 CSS class）*

全部列在 [`requirements.txt`](./requirements.txt)，其余只用标准库。

---

## 📝 说明与限制

- canvas 坐标系用的是 Obsidian 的像素单位，出现负坐标是正常的。导出器会计算包围盒并在加载时自动 fit。
- wikilink `[[目标]]` 会变成页内锚点，跳到对应卡片 id（尽力而为；仅当目标笔记也是同一 canvas 上的节点时生效）。
- Excalidraw 画的"伪 canvas"（`.excalidraw.md`）**不支持** —— 只支持原生 `.canvas` JSON。
- 几百个节点的大 canvas 仍可运行，但初始布局是 O(n)；浏览器内的视图本身很轻。

---

## 📄 许可证

MIT —— 见 [`LICENSE`](./LICENSE)。

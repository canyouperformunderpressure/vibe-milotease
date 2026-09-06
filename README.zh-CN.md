# Vibe MiloTease

[English](README.md)

**Vibe MiloTease** 是一个本地优先的创作工具集，用于创建、编辑、验证、预览和部署交互式 **Milovana EOS WebTease**。

它将面向 AI 的创作 Skill、名为 **Milo IR** 的结构化源格式、可视化 **Tease Graph**、本地 MiloAIEditor、媒体工具、验证/编译、Preview、旧版 EOS 迁移，以及浏览器辅助部署工作流组合在一起。

这个项目主要面向那些已经复杂到不适合继续维护为一个巨大 EOSScript 文档的 Tease。与其把生成后的 `eosscript.json` 当作创作源文件，Vibe MiloTease 会把设计、可执行源文件、生成输出、媒体资源和图布局拆分成明确的文件，让它们可以被独立审阅和修改。

```text
Idea → Outline → Milo IR → build / validate → Preview → Deploy
```

- **Outline** 描述体验结构、节点用途以及允许的路线。
- **Milo IR** 是可编辑的可执行源文件。
- **`eosscript.json`** 在 Milo IR 项目中属于生成输出。
- **Tease Graph** 提供 Outline 及其分支的可视化视图。
- **MiloAIEditor** 承载本地 EOS Editor、Preview 运行环境、编译器、媒体工作流以及部署集成。

## 为什么使用 Vibe MiloTease？

大型 EOS 项目可能包含大量页面、分支、选项、计时器、变量、媒体引用、条件、可复用场景、预加载规则以及多个结局。直接在生成后的 EOSScript 中维护这些内容，会让结构性修改变得难以推理，也更容易出错。

Vibe MiloTease 为 EOS 创作增加了一层面向源文件的工作方式：

- 将高层结构保存在 `outline.yaml`；
- 将全局状态和可复用定义保存在 `milo.yaml`；
- 将节点级行为拆分到 `src/*.milo.yaml`；
- 在替换生成的 EOSScript 之前验证引用和结构；
- 使用 Tease Graph 可视化检查分支；
- 在本地 Preview 中检查编译结果；
- 在能够保持等价性的前提下迁移已有旧版 EOS 项目；
- 让 AI 编码/创作 Agent 面向明确的项目源文件工作，而不是反复改写一个不透明的大型 JSON 文档。

## AI 辅助，而不是一键生成

Vibe MiloTease 的目标，是让 AI 成为制作 WebTease 时真正实用的助手，而不是承诺输入一句话就能生成一个完整成品。

一个好的 Tease 仍然需要人的想法。用户需要决定想做什么样的体验、希望它呈现什么感觉、如何推进、哪些选择或规则重要，以及结果不符合预期时应该修改什么。实际创作通常是一个反复迭代的过程：

```text
Idea → Outline → Draft → Preview → Feedback → Revision → Preview again
```

当前 AI 模型通常很擅长技术部分：写代码、遵循 schema、连接分支、转换重复结构、修复验证错误、重构项目文件。但创意写作的稳定性要差得多。对白可能变得泛化、过于正式、重复、语气不一致，或者单纯显得很奇怪。节奏和情绪推进也可能偏离作者原本的意图。

因此，AI 生成的文字应该被当作草稿，而不是成品。想要得到更好的结果，通常需要持续给出提示和具体反馈：缩短一段文字、改变语气、让角色没那么正式、重写尴尬的对话、调整节奏，或者直接替换掉整个不合适的场景。

Vibe MiloTease 更适合那些有自己概念和审美，并愿意不断 Review、Preview、修改、再重复一遍这个过程的用户。如果你想要的是一句“帮我做一个 tease”就立刻生成可直接发布的成品，这个项目并不是为这种目标设计的。

这个项目本身也仍然存在不少粗糙之处和限制。它更适合被看作一个持续演进的创作工具集，而不是人类创意工作的替代品，也不能替代在 Milovana Editor 中进行认真测试。

## 截图

### MiloAIEditor

![MiloAIEditor project browser](docs/screenshots/milo-editor.png)

本地 MiloAIEditor 承载 Milovana EOS Editor 集成、项目浏览器、Preview 运行环境、编译器接口、媒体工具以及部署工作流。上面的截图来自一个空白本地工作区，不包含任何用户项目数据。

### Tease Graph

![Tease Graph](docs/screenshots/tease-graph.png)

Tease Graph 会可视化显示 Outline 节点和路线，并提供面向图结构的编辑工具。截图使用仓库内置的 golden example，而不是个人项目。

## 主要功能

### Milo IR 结构化创作

Milo IR 是 Vibe MiloTease 使用的可编辑可执行源格式。它支持完整的 EOSScript YAML，同时也提供一些可选简写，用来减少重复性创作代码。

一个 Milo IR 项目可以表示：

- 页面与场景；
- 文字、通知、计时器、选项、条件和随机行为；
- 变量与持久状态；
- 媒体资源与项目媒体；
- 可复用 asset 与初始化逻辑；
- 在编译期间以惰性源代码形式保留的 JavaScript 表达式；
- 分支、循环、失败路线以及结局。

编译器会解析并验证创作源文件、展开支持的简写、物化媒体资源、验证生成后的 EOS 结构，并以原子方式替换 `eosscript.json`。如果 build 失败，会保留上一次成功生成的输出。

### 可视化 Tease Graph

Tease Graph 提供 `outline.yaml` 的可视化表示，并支持以图结构方式编辑节点和路线。

内置 Outline 模板覆盖了多种常见结构，包括线性阶段、章节/日程布局、Hub + Mission 循环、资源/RPG 推进、随机事件池以及探索型结构。

### 本地 MiloAIEditor

MiloAIEditor 是基于 FastAPI 的本地主机，用于承载：

- Milovana EOS Editor 前端；
- Preview；
- Tease Graph；
- Milo IR 解析、验证与编译；
- 项目存储与历史记录；
- 媒体搜索/导入工作流；
- Milovana 浏览和部署集成。

提供的 Windows 启动脚本会绑定到 `127.0.0.1`，因此默认不会把编辑器暴露到网络上。

### 旧版 EOS 迁移

已有的 `legacy-eos` 项目仍然可以继续把 `eosscript.json` 当作可编辑文件。迁移流程会尝试重建 Milo 源文件，并且只有在重新 build 后得到的 EOS JSON 与原始解析脚本保持深度等价时，才会将项目切换到 Milo IR 模式。

### 媒体工作流

仓库中包含媒体搜索/获取、项目导入、图片描述、图片转终端字符、视频处理、富文本媒体处理，以及前端资源抓取等辅助工具。

请只使用你有权访问和重新分发的媒体资源。

## 内置工具

`skills/miloai-tease/tools/` 包含一组由 Skill、MiloAIEditor 和更高级创作流程使用的辅助工具。完成基础项目并不需要全部使用它们，但它们可以让不少重复性或专业化任务变得可复现。

| 工具 | 用途 | 常见使用场景 |
| --- | --- | --- |
| `milo_workflow/` | 本地工作流桥接工具，用于创建项目、build Milo IR、验证、迁移旧项目、按需启动 Editor 以及打开 Preview。 | 日常创作以及 AI Agent 工作流。 |
| `import_project/` | 将已有 EOS 项目及其媒体导入本地项目工作区，不修改原始源目录。 | 将已有 Tease 带入 MiloAIEditor 继续制作。 |
| `image_describer/` | 使用 AI 模型批量描述图片目录，并输出对应 Markdown 描述和 manifest。支持递归、并发、限速、重试和 dry run。 | 为 AI Agent 提供大型图片集合的可搜索文字上下文。 |
| `image_to_half_block/` | 将图片转换为紧凑的、预计算的彩色 Unicode 半块字符数据，供 Milo Say 使用。 | 通过文本/终端风格输出渲染小型静态图像效果。 |
| `rich_text/` | 使用内置 Node 工具把图片内容转换为字符/颜色矩阵数据。 | 为富文本渲染实验和创作效果准备图片衍生数据。 |
| `video_to_eos/` | 将视频转换为按时间播放的 EOS 图片序列 WebTease 项目，包括提取帧媒体和生成 EOS 结构。 | 在 EOS 限制下实验性实现类似视频的播放效果。 |
| `capture_frontend/` | 抓取当前 Milovana EOS Editor 前端及其引用资源到本地 Editor 目录，并在 manifest 中记录 hash。 | 维护/开发时刷新本地托管的 Editor 前端。 |

最常用的命令行入口是 `milo_workflow.py`：

```powershell
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py --help
```

如果需要批量理解图片：

```powershell
python skills/miloai-tease/tools/image_describer/describe_images.py --help
```

部分工具还有额外的运行环境或依赖要求。例如，`image_describer` 需要其 README 中描述的兼容本地模型接口，`rich_text` 使用 Node 包，`video_to_eos` 依赖内置 Python 媒体栈。`capture_frontend` 更适合作为维护者工具，而不是普通创作命令，因为它会从在线 Milovana 站点镜像资源。

## 推荐使用方式：让 AI 帮你制作

Vibe MiloTease 最推荐的使用方式，是配合一个能够读取和修改本地项目、运行命令的 AI Agent。你主要负责提供想法、素材和反馈，AI 负责理解项目结构并完成具体实现。

开始时，先让 AI 加载：

```text
skills/miloai-tease/SKILL.md
```

然后明确告诉 AI 要新建或修改哪个项目。已有项目建议直接提供项目 ID 或项目路径，不要让 AI 自己猜。

之后直接用自然语言描述你想做什么即可。你可以提供剧情、已经写好的文本、图片、整体框架、玩法、分支要求，或者对现有内容的修改意见。AI 会按照 Skill 中的规则处理 Outline、Milo IR、媒体引用、Build 和验证等具体工作。

图片既可以由你自己提供，也可以让 AI 使用项目内的媒体工具帮助寻找和整理。不过自动寻找图片的效果目前比较依赖来源和搜索结果，通常不如直接提供你已经挑选好的素材稳定。如果对画面有明确要求，建议优先提供自己的图片，再让 AI 负责整理和接入项目。

完成一轮修改后，让 AI Build 并检查错误，然后打开 Preview 实际体验。如果剧情、节奏、图片、玩法或分支不符合预期，直接把问题告诉 AI，让它继续修改。

核心流程就是：

```text
剧情 / 文本 / 图片 / 框架
          ↓
         AI
          ↓
   修改 MiloTease 项目
          ↓
   Build / Validate
          ↓
       Preview
          ↓
      提出修改意见
          ↓
      AI 继续修改
```

对当前项目有任何问题，也可以直接询问 AI，例如项目结构、剧情流程、节点关系、变量用途、Build 错误、媒体引用或 Preview 问题。AI 可以先读取项目，再根据实际内容回答。

为了获得更好的效果，建议使用当前能力较强、具备本地文件读写和命令执行能力的 AI Agent。

## 快速开始

### 环境要求

- Python，并且 `pip` 可通过 `PATH` 使用。
- Windows PowerShell，用于运行内置的 `start.ps1` 启动脚本。
- Chrome 或 Edge 只在交互式 Milovana 部署/浏览器工作流中需要。

### 1. 安装 Editor 依赖

在仓库根目录执行：

```powershell
python -m pip install -r milo-editor/requirements.txt
```

### 2. 启动 MiloAIEditor

```powershell
.\milo-editor\start.ps1
```

然后打开：

```text
http://127.0.0.1:8001/eos/editor/teases
```

也可以指定其他端口：

```powershell
.\milo-editor\start.ps1 -Port 8010
```

### 3. 创建项目

在仓库根目录执行：

```powershell
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py new --title "Example" --project-id 100001 --json
```

省略 `--project-id` 时，会自动分配下一个可用的数字项目 ID。

### 4. Build 与验证

```powershell
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py build --project-id 100001 --json
```

如果希望 build 后直接打开本地 Preview：

```powershell
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py build --project-id 100001 --open
```

### 5. 迁移已有 EOS 项目

```powershell
python skills/miloai-tease/tools/milo_workflow/milo_workflow.py migrate --project-id 39504 --json
```

迁移流程比较保守：只有重新 build 并解析后的 EOS 结果与原始内容保持深度等价时，项目才会切换到 Milo IR 模式。

## 与 AI Agent 一起使用 Vibe MiloTease

`skills/miloai-tease/` 目录设计为供能够读取和编辑本地仓库的 AI 编码或创作 Agent 使用。

Skill 定义了一套持续创作流程：

```text
Outline → explicit confirmation → Milo IR → compile / validate → Preview
```

Agent 应该把 `outline.yaml` 和 Milo 源文件作为事实来源，在 Milo IR 项目中不应该直接编辑生成的 `eosscript.json`。

### 支持的 Agent 初始化目标

内置 system-prompt bootstrap 支持以下 Agent ID：

| Agent ID | 项目级目标文件 |
| --- | --- |
| `claude` | `CLAUDE.md` |
| `codex` | `AGENTS.md` |
| `opencode` | `AGENTS.md` |
| `pi` | `.pi/APPEND_SYSTEM.md` |

安装项目级指令：

```powershell
powershell -ExecutionPolicy Bypass -File skills/miloai-tease/system-prompt/init-system-prompt.ps1 --agent codex
```

根据需要将 `codex` 替换为 `claude`、`opencode` 或 `pi`。

安装器只追加内容、不会越出仓库根目录，并使用标记避免重复写入模块。新安装的指令/模块会由**新的 Agent 会话**加载，不会逆向注入已经运行中的会话。

也提供 Bash 版本：

```bash
bash skills/miloai-tease/system-prompt/init-system-prompt.sh --agent codex
```

如果新进程需要使用 Agent 对应的 API/system-instruction 机制，可以使用 launcher：

```powershell
powershell -ExecutionPolicy Bypass -File skills/miloai-tease/system-prompt/run-system-agent.ps1 --agent codex -- <agent arguments>
```

每种支持 Agent 的具体行为请参见 `skills/miloai-tease/system-prompt/INSTALL.md`。

### 典型 Agent 工作流

1. 给 Agent 一个概念、已有 Outline，或明确的项目 ID/路径。
2. Agent 加载当前任务所需的创作参考资料。
3. Agent 创建或修改 `outline.yaml`，并展示结构设计供确认。
4. 确认后，在 `milo.yaml` 和 `src/*.milo.yaml` 中实现设计。
5. 运行编译器/验证器，并修复源文件层面的错误。
6. Build 成功后，提供本地 Preview URL 供检查。
7. 将 Preview 反馈应用回创作源文件，然后再次 build。

对于已有项目，请提供准确的数字项目 ID 或项目路径。这个 Skill 有意设计为不会通过扫描无关工作区去猜测项目。

## 项目目录结构

仓库级结构：

```text
milovana/
├─ LICENSE
├─ README.md
├─ README.zh-CN.md
├─ THIRD_PARTY_NOTICES.md
├─ docs/
│  └─ screenshots/
├─ milo-editor/
│  ├─ app/                 # FastAPI 后端、项目 API、Milo IR 编译器
│  ├─ editor-web/          # 本地托管的 EOS Editor 前端资源
│  ├─ local-assets/        # MiloAIEditor 集成脚本
│  ├─ runtime/             # 本地 Preview / runtime 资源
│  ├─ tease-graph/         # Tease Graph 源码/build
│  ├─ vendor/              # 内置第三方/runtime 资源
│  ├─ requirements.txt
│  └─ start.ps1
├─ projects/               # 本地创作项目
└─ skills/
   └─ miloai-tease/
      ├─ SKILL.md          # Agent 工作流与操作约定
      ├─ agents/           # Agent 元数据
      ├─ references/       # 创作、实现、玩法和媒体文档
      ├─ system-prompt/    # 项目级 Agent bootstrap/launcher
      └─ tools/            # 工作流和媒体工具
```

一个 Milo IR 项目使用以下结构：

```text
projects/<id>/
├─ project.json
├─ outline.yaml
├─ milo.yaml
├─ src/
│  └─ <node>.milo.yaml
├─ media/
├─ tease-graph-layout.json
├─ eosscript.json
├─ history/
└─ storage/
   └─ state.json
```

### 源文件权威关系

| 文件 | 负责内容 |
| --- | --- |
| `outline.yaml` | 整体体验结构、节点用途以及允许的跨节点路线 |
| `milo.yaml` | 全局 EOS 字段、状态、模块、初始化、catalog 和可复用 asset |
| `src/*.milo.yaml` | 页面、对白、媒体操作、选项、条件、计时器、JavaScript 字符串以及节点内部行为 |
| `tease-graph-layout.json` | 图布局元数据 |
| `eosscript.json` | Milo IR 模式下生成的运行时输出 |

当设计发生变化时，应修改对应的创作源文件并重新 build，而不是直接 patch 生成后的 EOSScript。

## 部署到 Milovana

MiloAIEditor 为本地项目提供内置的 **Deploy to Milovana** 集成。

部署使用已经 build 的 `eosscript.json` 和物化后的媒体。它会打开一个独立、用户可见的 Chrome/Edge profile，你可以正常登录。正常部署流程不要求 Python 后端使用导出的 Milovana Cookie。

远端发布仍然必须由用户明确触发。浏览器或 Cloudflare 验证可能需要你在可见浏览器窗口中手动操作。

更多部署细节请参见 `milo-editor/README.md`。

## 已知限制

Vibe MiloTease 仍在持续演进，目前还有不少粗糙之处。下面明确列出这些限制，便于用户了解哪些地方仍然需要人工审阅、耐心或手动干预。

- **实验性工具。** Vibe MiloTease 是独立创作工具，不是 Milovana 官方产品。
- **Windows 优先的便捷工作流。** 打包内提供的启动辅助脚本基于 PowerShell，目前发布流程主要在 Windows 上测试。Python 后端可以在其他平台手动启动，但并不保证所有浏览器/部署路径表现完全一致。
- **本地服务器假设。** Editor 按 localhost 使用场景设计，没有被加固或配置成公开的多用户 Web 服务。
- **AI 输出仍需要大量审阅。** Agent 生成的 Outline、源文件、时间控制、分支以及创作文案，都应该在发布前进行验证并在 Preview 中检查。技术输出通常比文案、对白、节奏等创意写作更可靠；后者可能需要多轮提示和人工修改。
- **迁移无法让所有旧项目都变得“原生 Milo IR”。** 迁移会保守地保持 EOS 结构；复杂或特殊的旧版脚本即使成功完成等价迁移，之后仍可能需要人工整理源文件。
- **生成的 EOSScript 不是 Milo IR 源文件。** 在 `milo-ir` 模式下，Editor 保存接口会有意拒绝直接编辑 `eosscript.json`。请修改 `outline.yaml`、`milo.yaml` 或 `src/*.milo.yaml`，然后重新 build。
- **部署依赖真实浏览器会话。** Milovana 登录、Cloudflare 验证、网站改动或浏览器行为都可能中断自动部署流程，并要求人工操作。
- **外部媒体可用性无法保证。** 搜索/获取辅助工具依赖外部来源及其当前访问规则，不应把这些来源当作永久素材托管。
- **第三方组件拥有独立条款。** 根目录 MIT License 适用于 Vibe MiloTease 原创项目代码；内置或 vendored 组件仍遵循各自上游 License 和重新分发要求。

## 隐私与发布清理

不要提交或重新分发本地项目数据、浏览器 profile、登录/session 状态、凭据、API Key、测试产物、抓取文件、缓存或机器相关开发文件。

发布归档应从干净的 staging 目录构建，而不是直接压缩开发 checkout。

## 文档

建议从以下内容开始：

- `skills/miloai-tease/SKILL.md` — AI Agent 工作流与项目约定。
- `skills/miloai-tease/references/authoring.md` — 创作与设计指南。
- `skills/miloai-tease/references/implementation.md` — Milo IR 与编译器语义。
- `skills/miloai-tease/references/media.md` — 媒体工作流。
- `milo-editor/README.md` — Editor、build、迁移与部署细节。

## License

Vibe MiloTease 原创项目代码使用 **MIT License**。详见 `LICENSE`。

内置和 vendored 第三方组件保留各自的 License 与声明。详见 `THIRD_PARTY_NOTICES.md`。

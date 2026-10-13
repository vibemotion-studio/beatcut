<div align="center">

# beatcut

**把你自己的几段视频，做成竖屏卡点短片。**

上色转场 · 甩镜旋转 · 全程不断的 BGM · 字幕 · 配音 · 17 种特效 · 9 种转场 · 铁花落下收尾

[English](README.md) | [简体中文](README_CN.md)

<img src="assets/demo.gif" alt="beatcut 演示：标题与上色、每拍一切、铁花落下收尾" width="216" />

<sub>37.9 秒成片的节选，素材是打铁花：开场上色、卡点快切、收尾。</sub>

</div>

**beatcut** 既是智能体技能，也是命令行工具。给它几段视频，它按拍点规划整条短片，渲染成 1080×1920，并把音乐、原声、配音和音效混成一个 MP4。它基于 [colorize](https://github.com/vibe-motion/colorize) 引擎（黑白到彩色，带丁达尔旋焦）。

## 特点

- **按拍点编排。** 默认 96 拍、152 bpm（37.9 秒），每个切点都踩在拍上，10 拍以上的任意长度都能自动缩放。
- **完整的结构。** 闪白开场加上色，慢放光轨，快切，旋焦过场，第二次上色，每拍一切，时间切片三联屏，最后铁花落下收尾。
- **音乐不断。** 合成的 D 大调 BGM 从第一个采样响到最后一个，也可以换成你自己的音乐。
- **纯白字幕。** 6 种版式，只靠位置和入场方式区分，不靠字体和光晕。
- **剪映风格工具箱。** 17 种特效、9 种转场，可按拍点或指定拍数区间叠加。
- **配音会让位。** macOS `say` 的配音会压低音乐和原声，并自动出字幕。
- **如实校验。** 每次运行最后都会对尺寸、时长、削波、爆音和静音做数值检查。

## 快速开始

可以装成智能体技能，也可以直接用命令行。

```bash
git clone https://github.com/vibemotion-studio/beatcut.git
cd beatcut
python3 -m pip install -r scripts/requirements.txt

# Claude Code（也可以放到 ~/.codex/skills、~/.agents/skills）
ln -s "$(pwd)" ~/.claude/skills/beatcut
```

需要 Python 3.9+、`PATH` 里有 `ffmpeg` 和 `ffprobe`，以及支持 OpenGL 3.3 的驱动。

装好后可以这样对智能体说：

| 你说 | 它做 |
| --- | --- |
| 「用这几段做一条卡点短片：/abs/a.mp4 /abs/b.mp4」 | 先渲染 540×960 预览，再渲染完整 1080×1920 |
| 「加标题『上海』，左下角加字幕『外滩』」 | `--title`、`--caption bloom:外滩@brk` |
| 「中间那段每拍加一个故障特效」 | `--effect glitch@52-68:beat` |
| 「换成这首音乐」 | `--bgm /abs/music.mp3`，自动循环并裁到成片长度 |
| 「加一段配音」 | `--voiceover`，自动压低音乐并出字幕 |

## 命令行

```bash
# 快速预览
python3 scripts/make_reel.py a.mp4 b.mp4 c.mp4 -o out/p.mp4 --size 540x960 --beats 24 --crf 23

# 打铁花预设（字幕是为打铁花素材写的）
python3 scripts/make_reel.py a.mp4 b.mp4 c.mp4 d.mp4 -o out/reel.mp4 --preset datihua

# 自定义标题、字幕、特效、转场、配音
python3 scripts/make_reel.py a.mp4 b.mp4 -o out/r.mp4 --title "上海" --subtitle "SHANG HAI" \
  --caption "bloom:外滩@brk+0.2/1.5" --effect "glitch@52-68:beat:0.6" --transition whip \
  --voiceover "这是第一句@s2"

python3 scripts/make_reel.py --list     # 全部特效、转场、字幕版式和段落
```

运行结束会打印 `VALIDATION=PASS` 和 `OUTPUT_VIDEO=<路径>`。全部参数见 [SKILL.md](SKILL.md)。

## 短片怎么编排

段落以 96 拍为基准，会随 `--beats` 缩放。素材按传入顺序使用：第一段开场，最后一段负责收尾。

| 段落 | 拍数 | 内容 |
| --- | --- | --- |
| `intro` | 0-8 | 闪白，停在第 1 段，上色，大标题 |
| `s2` | 8-20 | 半速慢放，带光轨 |
| `groove1` | 20-32 | 每 4 拍一段的快切，最后一段带甩镜旋转 |
| `brk` | 32-36 | 放大定格 |
| `groove2` | 36-44 | 最后一段快切继续播放 |
| `bridge` | 44-46 | 旋焦过场，结尾一次光爆 |
| `chill` | 46-52 | 第二次上色 |
| `peak` | 52-68 | 每拍一切，每拍有一次脉冲 |
| `ramp` | 68-72 | 时间切片三联屏 |
| `fin` | 72-96 | 慢放素材上铁花落下，再渐黑 |

## 特效、转场、字幕

| 特效 | |
| --- | --- |
| `rgb_split` `shake` `flash` `glitch` `zoom_pulse` `mirror` | 色差 抖动 闪白 故障 心跳 镜像 |
| `mosaic` `grain` `vhs` `letterbox` `radial_blur` `motion_blur` | 马赛克 胶片颗粒 复古VHS 电影黑边 变焦模糊 动感模糊 |
| `strobe` `invert` `blur` `ripple` `mono` | 频闪 反色 模糊 水波纹 黑白 |

特效模式：`always` `beat` `start` `end` `ramp`。写法：`--effect name[@from-to][:mode][:amt]`，`from-to` 的单位是拍。

**转场：** `fade` `slide` `zoom` `whip` `glitch` `flash` `wipe` `spin` `mosaic`，用在快切、第二次上色和三联屏处。

**字幕版式：** `ignite`（竖排）· `bloom`（左下多行）· `focus`（顶部，字距收紧）· `meteors`（斜向流星）· `grand`（底部逐字踩拍）· `subtitle`（配音字幕）。写法：`--caption layout:text@section[+offset][/dur]`。

## 配置文件

预设和 `--preset file.json` 的键与命令行参数一一对应：

```json
{
  "title": "打铁花", "subtitle": "IRON FIREWORKS",
  "bpm": 152, "beats": 96, "bgm": "synth", "transition": "whip",
  "captions": [{"layout": "bloom", "text": "铁水成花", "tag": "MOLTEN IRON", "at": "brk", "dur": 1.55}],
  "effects": [{"name": "glitch", "from": 52, "to": 68, "mode": "beat", "amt": 0.6}],
  "voiceover": [{"text": "这是第一句", "at": "s2"}],
  "voice": "Ting-Ting", "duck": 0.5
}
```

未知的键和不合法的值会被拒绝并给出提示。

## 校验

`VALIDATION` 只做数值检查：输出尺寸、时长、音轨、削波采样、相邻采样跳变（爆音），以及开着音乐时是否有 0.25 秒的静音窗口。它不判断画面好不好看，成片请自己看一遍。字幕风格守则和它所依据的参考短片数据见 [references/style-guide.md](references/style-guide.md)。

## 目录结构

```text
beatcut/
├── SKILL.md                 # 智能体入口：流程、参数、段落
├── presets/datihua.json     # 打铁花预设
├── references/style-guide.md
├── assets/                  # 效果贴图、引擎参数、演示 GIF
├── agents/openai.yaml
├── scripts/
│   ├── make_reel.py         # 命令行入口
│   └── reel/                # engine, plan, render, media, layouts, effects, transitions,
│                            # text, sparks, bgm, synth, audio, spec, checks, fonts
└── tests/                   # 单元测试 + 合成素材端到端
```

## 局限

- 配音和默认字体（宋体 SC、苹方 SC）依赖 macOS。其他系统请用 `REEL_FONT_SERIF`、`REEL_FONT_SANS` 指定中文字体，这条路径没测过。
- 字幕版式是为 1080×1920 设计的，其他尺寸会按比例缩放，没逐一验证。
- `datihua` 预设和演示 GIF 使用的是打铁花素材。

## 声明

- `scripts/reel/engine.py` 中的渲染部分改写自 [vibe-motion/colorize](https://github.com/vibe-motion/colorize)，该仓库没有附带许可证文件。再分发前请自行确认其条款。
- `assets/effect_maps/` 中的颜色查找表与焦点遮罩取自剪映效果包，仅供学习研究。再分发前请自行确认授权。

## 测试

```bash
python3 -m pytest tests
```

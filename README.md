# Nano Banana Lab 🍌

[English](#english) | [中文](#中文)

---

<a name="english"></a>
## English

A learning project exploring Google Gemini 3 Pro Image (Nano Banana Pro) capabilities for AI image generation.

### Features & Experiments

| # | Experiment | File | Description | Status |
|---|------------|------|-------------|--------|
| 01 | Basic Generation | `experiments/01_basic.py` | Text-to-image generation with customizable aspect ratio | ✅ |
| 02 | Thinking Process | `experiments/02_thinking.py` | Visualize model's reasoning before image generation | ✅ |
| 03 | Search Grounding | `experiments/03_search.py` | Integrate real-time Google Search data into images | ✅ |
| 04 | 4K Generation | `experiments/04_4k.py` | Ultra-high resolution image generation (up to 4096x4096) | ✅ |
| 05 | Multilingual | `experiments/05_multilang.py` | Multi-turn chat for cross-language image translation | ✅ |
| 06 | Image Blending | `experiments/06_blend.py` | Combine multiple images with style transfer | ✅ |

### Function Details

#### 01_basic.py - Basic Image Generation
```python
generate_basic_image(prompt, aspect_ratio="16:9")
```
- Generate images from text prompts
- Supports various aspect ratios: `16:9`, `1:1`, `9:16`, etc.
- Output: `outputs/01_basic.png`

#### 02_thinking.py - Thinking Process Visualization
```python
generate_with_thinking(prompt, aspect_ratio="16:9")
```
- Enable model's thinking feature with `ThinkingConfig(include_thoughts=True)`
- Display model's reasoning process before image generation
- Output: `outputs/02_thinking.png`

#### 03_search.py - Search Grounding
```python
generate_with_search(prompt, aspect_ratio="16:9")
```
- Integrate real-time Google Search data using `tools=[{"google_search": {}}]`
- Generate images with up-to-date information (weather, news, etc.)
- Output: `outputs/03_search.png`

#### 04_4k.py - 4K Ultra HD Generation
```python
generate_4k_image(prompt, resolution="4K", aspect_ratio="16:9")
```
- Support multiple resolutions: `1K`, `2K`, `4K`
- 4K generates 4096x4096 images
- Output: `outputs/04_4K.png`

#### 05_multilang.py - Multilingual Capabilities
```python
generate_multilingual_image(prompt, aspect_ratio="16:9", filename="05_multilang.png")
chat_and_translate()
```
- Multi-turn conversation mode for image translation
- Maintain visual consistency across languages
- Output: `outputs/05_multilang_en.png`, `outputs/05_multilang_zh.png`

#### 06_blend.py - Advanced Image Blending
```python
blend_images(prompt, image_paths, aspect_ratio="16:9")
demo_style_transfer()
```
- Blend up to 14 images (Pro model)
- Style transfer capabilities
- Output: `outputs/06_base_photo.png`, `outputs/06_style_ref.png`, `outputs/06_blend.png`

### Quick Start

#### 1. Environment Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### 2. Configure API Key

```bash
# Copy environment template
cp .env.example .env

# Edit .env file and add your API Key
# Get it from: https://aistudio.google.com/app/apikey
```

#### 3. Run Experiments

```bash
# Run basic generation experiment
python experiments/01_basic.py

# Generated images are saved in outputs/ directory
```

### Output Gallery

#### 01 - Basic Generation
![Basic Generation](outputs/01_basic.png)
*A cute corgi wearing sunglasses on a beach at sunset - photorealistic style*

#### 02 - Thinking Process
![Thinking Process](outputs/02_thinking.png)
*Viral-worthy image generated with visible AI reasoning process - a dog working at a desk*

#### 03 - Search Grounding
![Search Grounding](outputs/03_search.png)
*Real-time weather forecast for Guangdong Province, China - 5-day forecast visualization*

#### 04 - 4K Ultra HD
![4K Generation](outputs/04_4K.png)
*Four seasons of an oak tree - 4096x4096 ultra-high resolution image*

#### 05 - Multilingual (English)
![Multilingual English](outputs/05_multilang_en.png)
*Coffee journey infographic - English version*

#### 05 - Multilingual (Chinese)
![Multilingual Chinese](outputs/05_multilang_zh.png)
*Coffee journey infographic - Chinese version (same layout, translated content)*

#### 06 - Image Blending

| Base Photo | Style Reference | Blended Result |
|------------|-----------------|----------------|
| ![Base](outputs/06_base_photo.png) | ![Style](outputs/06_style_ref.png) | ![Blend](outputs/06_blend.png) |
| *Cat on windowsill* | *Abstract watercolor* | *Watercolor style cat* |

### Project Structure

```
nano-banana-lab/
├── .env.example        # Environment template
├── .env                # Your API Key (do not commit)
├── requirements.txt    # Python dependencies
├── config.py           # Client initialization & timing instrumentation
├── experiments/        # Experiment scripts
│   ├── 01_basic.py     # Basic text-to-image
│   ├── 02_thinking.py  # Thinking process visualization
│   ├── 03_search.py    # Search-grounded generation
│   ├── 04_4k.py        # High-resolution generation
│   ├── 05_multilang.py # Multilingual support
│   └── 06_blend.py     # Image blending & style transfer
├── outputs/            # Generated images
└── README.md
```

### Pricing Reference

| Resolution | Price per Image | Notes |
|------------|-----------------|-------|
| 1K / 2K | $0.134 | Standard quality |
| 4K | $0.24 | Print-quality |
| Batch API | -50% | Use for bulk generation |

### References

- [Official Documentation](https://ai.google.dev/gemini-api/docs)
- [Google AI Studio](https://aistudio.google.com)
- [Pricing Page](https://ai.google.dev/pricing)

---

<a name="中文"></a>
## 中文

基于 Google Gemini 3 Pro Image (Nano Banana Pro) 的 AI 图像生成学习实验项目。

### 功能实验清单

| 序号 | 实验 | 文件 | 说明 | 状态 |
|------|------|------|------|------|
| 01 | 基础生成 | `experiments/01_basic.py` | 文本到图像生成，支持自定义宽高比 | ✅ |
| 02 | 思考过程 | `experiments/02_thinking.py` | 可视化模型生成图像前的推理过程 | ✅ |
| 03 | 搜索落地 | `experiments/03_search.py` | 将实时 Google 搜索数据融入图像生成 | ✅ |
| 04 | 4K 生成 | `experiments/04_4k.py` | 超高分辨率图像生成（最高 4096x4096） | ✅ |
| 05 | 多语言 | `experiments/05_multilang.py` | 多轮对话实现跨语言图像翻译 | ✅ |
| 06 | 图像混合 | `experiments/06_blend.py` | 多图融合与风格迁移 | ✅ |

### 功能详解

#### 01_basic.py - 基础图像生成
```python
generate_basic_image(prompt, aspect_ratio="16:9")
```
- 根据文本提示生成图像
- 支持多种宽高比：`16:9`、`1:1`、`9:16` 等
- 输出：`outputs/01_basic.png`

#### 02_thinking.py - 思考过程可视化
```python
generate_with_thinking(prompt, aspect_ratio="16:9")
```
- 使用 `ThinkingConfig(include_thoughts=True)` 启用思考功能
- 展示模型在生成图像前的推理过程
- 输出：`outputs/02_thinking.png`

#### 03_search.py - 搜索落地
```python
generate_with_search(prompt, aspect_ratio="16:9")
```
- 使用 `tools=[{"google_search": {}}]` 集成实时 Google 搜索数据
- 生成包含最新信息的图像（天气、新闻等）
- 输出：`outputs/03_search.png`

#### 04_4k.py - 4K 超高清生成
```python
generate_4k_image(prompt, resolution="4K", aspect_ratio="16:9")
```
- 支持多种分辨率：`1K`、`2K`、`4K`
- 4K 生成 4096x4096 图像
- 输出：`outputs/04_4K.png`

#### 05_multilang.py - 多语言能力
```python
generate_multilingual_image(prompt, aspect_ratio="16:9", filename="05_multilang.png")
chat_and_translate()
```
- 多轮对话模式实现图像翻译
- 保持跨语言的视觉一致性
- 输出：`outputs/05_multilang_en.png`、`outputs/05_multilang_zh.png`

#### 06_blend.py - 高级图像混合
```python
blend_images(prompt, image_paths, aspect_ratio="16:9")
demo_style_transfer()
```
- 最多可混合 14 张图像（Pro 模型）
- 风格迁移功能
- 输出：`outputs/06_base_photo.png`、`outputs/06_style_ref.png`、`outputs/06_blend.png`

### 快速开始

#### 1. 环境准备

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

#### 2. 配置 API Key

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的 API Key
# 获取地址: https://aistudio.google.com/app/apikey
```

#### 3. 运行实验

```bash
# 运行基础生成实验
python experiments/01_basic.py

# 生成的图片会保存在 outputs/ 目录
```

### 效果展示

#### 01 - 基础生成
![基础生成](outputs/01_basic.png)
*沙滩上戴墨镜的可爱柯基 - 照片级真实风格*

#### 02 - 思考过程
![思考过程](outputs/02_thinking.png)
*带有可见 AI 推理过程生成的病毒式传播图像 - 一只在办公桌前工作的狗*

#### 03 - 搜索落地
![搜索落地](outputs/03_search.png)
*广东省实时天气预报 - 5天预报可视化*

#### 04 - 4K 超高清
![4K生成](outputs/04_4K.png)
*橡树的四季变化 - 4096x4096 超高分辨率图像*

#### 05 - 多语言（英文）
![多语言英文](outputs/05_multilang_en.png)
*咖啡之旅信息图 - 英文版*

#### 05 - 多语言（中文）
![多语言中文](outputs/05_multilang_zh.png)
*咖啡之旅信息图 - 中文版（相同布局，翻译内容）*

#### 06 - 图像混合

| 基础照片 | 风格参考 | 混合结果 |
|----------|----------|----------|
| ![基础](outputs/06_base_photo.png) | ![风格](outputs/06_style_ref.png) | ![混合](outputs/06_blend.png) |
| *窗台上的猫* | *抽象水彩画* | *水彩风格的猫* |

### 项目结构

```
nano-banana-lab/
├── .env.example        # 环境变量模板
├── .env                # 你的 API Key（不要提交到 Git）
├── requirements.txt    # Python 依赖
├── config.py           # 客户端初始化与计时统计
├── experiments/        # 实验脚本
│   ├── 01_basic.py     # 基础文本生图
│   ├── 02_thinking.py  # 思考过程可视化
│   ├── 03_search.py    # 搜索落地生成
│   ├── 04_4k.py        # 高分辨率生成
│   ├── 05_multilang.py # 多语言支持
│   └── 06_blend.py     # 图像混合与风格迁移
├── outputs/            # 生成的图片
└── README.md
```

### 费用参考

| 分辨率 | 每张价格 | 备注 |
|--------|----------|------|
| 1K / 2K | $0.134 | 标准质量 |
| 4K | $0.24 | 印刷级质量 |
| Batch API | -50% | 批量生成时使用 |

### 参考资料

- [官方文档](https://ai.google.dev/gemini-api/docs)
- [Google AI Studio](https://aistudio.google.com)
- [定价页面](https://ai.google.dev/pricing)

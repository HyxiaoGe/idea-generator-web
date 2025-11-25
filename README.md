# Nano Banana Lab 🍌

基于 Google Gemini 3 Pro Image (Nano Banana Pro) 的学习实验项目。

## 功能实验清单

| 序号 | 实验 | 文件 | 状态 |
|------|------|------|------|
| 01 | 基础生成 | `experiments/01_basic.py` | ⬜ |
| 02 | 思考过程 | `experiments/02_thinking.py` | ⬜ |
| 03 | 搜索落地 | `experiments/03_search.py` | ⬜ |
| 04 | 4K 生成 | `experiments/04_4k.py` | ⬜ |
| 05 | 多语言 | `experiments/05_multilang.py` | ⬜ |
| 06 | 图像混合 | `experiments/06_blend.py` | ⬜ |

## 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的 API Key
# 获取地址: https://aistudio.google.com/app/apikey
```

### 3. 运行实验

```bash
# 运行基础生成实验
python experiments/01_basic.py

# 生成的图片会保存在 outputs/ 目录
```

## 项目结构

```
nano-banana-lab/
├── .env.example        # 环境变量模板
├── .env                # 你的 API Key (不要提交到 Git)
├── requirements.txt    # Python 依赖
├── config.py           # 客户端初始化
├── experiments/        # 实验脚本
│   ├── 01_basic.py
│   ├── 02_thinking.py
│   ├── 03_search.py
│   ├── 04_4k.py
│   ├── 05_multilang.py
│   └── 06_blend.py
├── outputs/            # 生成的图片
└── README.md
```

## 费用参考

- 1K/2K 图片: $0.134/张
- 4K 图片: $0.24/张
- 使用 Batch API 可节省 50%

## 参考资料

- [官方文档](https://ai.google.dev/gemini-api/docs)
- [Google AI Studio](https://aistudio.google.com)
- [定价页面](https://ai.google.dev/pricing)
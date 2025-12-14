# 内容审核审计日志系统

## 📋 系统概述

审计日志系统记录所有内容审核检查的完整链路，用于：
- 🔍 分析误报和漏报
- 📊 优化关键词列表
- 🎯 改进 AI 检测准确性
- 📈 生成统计报告

---

## 🗂️ 数据结构

### 日志存储路径（R2）

```
logs/content_moderation/
  ├── 2025/
  │   └── 12/
  │       └── 14/
  │           ├── blocked/        # 被阻止的记录
  │           │   └── 20251214_153045_uuid.json
  │           ├── allowed/        # 通过的记录
  │           │   └── 20251214_154030_uuid.json
  │           └── flagged/        # 标记需要复审的
  │               └── 20251214_161500_uuid.json
  └── summary/
      └── 2025-12-14_summary.json  # 每日汇总
```

### 日志条目格式

```json
{
  "log_id": "uuid-v4",
  "timestamp": "2025-12-14T15:30:45.123Z",

  "user_input": {
    "prompt": "用户的完整提示词",
    "prompt_hash": "SHA256哈希",
    "length": 50
  },

  "layer1_keyword": {
    "checked": true,
    "passed": false,
    "matched_keywords": ["sexy"],
    "execution_time_ms": 0.8,
    "total_keywords_count": 110
  },

  "layer2_ai": {
    "checked": true,
    "passed": true,
    "classification": "safe",
    "reason": "",
    "execution_time_ms": 320,
    "model": "gemini-2.0-flash-exp",
    "cache_hit": false
  },

  "final_decision": {
    "allowed": false,
    "blocked_by": "keyword",
    "blocked_reason": "keyword:sexy",
    "total_time_ms": 321
  },

  "context": {
    "generation_mode": "basic",
    "resolution": "1K",
    "user_id_hash": "SHA256(user_id)",
    "session_id": "会话ID"
  },

  "analysis_flags": {
    "needs_review": false,
    "review_reason": [],
    "confidence": "high"
  }
}
```

---

## 🛠️ 使用工具

### 1. 生成每日汇总

```bash
# 查看今天的统计
python scripts/analyze_moderation_logs.py summary

# 查看指定日期
python scripts/analyze_moderation_logs.py summary --date 2025-12-14
```

**输出示例**：
```
============================================================
  Content Moderation Summary - 2025-12-14
============================================================

📊 Overall Statistics
   Total Checks:    1500
   ✅ Allowed:      1380 (92.0%)
   ❌ Blocked:      120 (8.0%)
   🚩 Flagged:      15 (1.0%)

🛡️ Block Breakdown
   Layer 1 (Keywords): 80
   Layer 2 (AI):       40

🔑 Top Blocked Keywords
   • sexy                (25 times)
   • nude                (18 times)
   • porn                (15 times)

🤖 AI Classifications
   • nsfw_content        (25 times)
   • violence            (10 times)
   • minors              (5 times)

⚡ Performance Metrics
   Layer 1 Avg:  0.8ms
   Layer 2 Avg:  320ms
   Total Avg:    321ms

📈 Accuracy Metrics
   Block Rate:  8.0%
   Flag Rate:   1.0%
```

---

### 2. 查找误报候选

识别可能被错误阻止的提示词：

```bash
# 查找误报候选
python scripts/analyze_moderation_logs.py false-positives

# 限制结果数量
python scripts/analyze_moderation_logs.py false-positives --limit 10
```

**触发条件**：
- 长提示词（>100字符）被单个关键词阻止
- 系统自动标记为需要复审
- Layer 1 和 Layer 2 结果矛盾

**输出示例**：
```
🔍 Analyzing False Positive Candidates for 2025-12-14...

Found 3 potential false positives:

1. Prompt: romantic couple embracing passionately under moonlight with stars
   Reason: keyword:sexy
   Length: 120 chars
   Score:  0.70

2. Prompt: renaissance painting of nude David sculpture by Michelangelo
   Reason: keyword:nude
   Length: 150 chars
   Score:  0.70
```

---

### 3. 查找未使用的关键词

找出长期未被触发的关键词，可能是冗余的：

```bash
# 查找30天内未使用的关键词
python scripts/analyze_moderation_logs.py unused-keywords --days 30

# 查找7天内未使用的
python scripts/analyze_moderation_logs.py unused-keywords --days 7
```

**输出示例**：
```
🔎 Finding keywords unused in the last 30 days...

📊 Keyword Usage Statistics:
   Total Keywords:     110
   Used (last 30d):    95
   Unused:             15

Unused keywords:
   • shota
   • loli
   • opium
   ...
```

**操作建议**：
- 未使用的关键词可以考虑删除（减少误报）
- 但一些极端词汇即使未触发也应保留

---

### 4. 查看标记的日志

查看系统自动标记需要人工复审的案例：

```bash
# 查看今天标记的日志
python scripts/analyze_moderation_logs.py flagged

# 查看指定日期
python scripts/analyze_moderation_logs.py flagged --date 2025-12-14 --limit 20
```

**输出示例**：
```
🚩 Flagged Logs for Review - 2025-12-14

1. Log ID: abc-123-def
   Timestamp: 2025-12-14T15:30:45Z
   Prompt: couple embracing passionately...
   Decision: Blocked
   Reason: keyword:sexy
   Review Reason: long_prompt_keyword_block
   Confidence: medium
```

---

## 🔄 复盘工作流程

### 每日复盘（推荐）

```bash
#!/bin/bash
# daily_review.sh - 每日审核工作流程

TODAY=$(date +%Y-%m-%d)

echo "=== 每日内容审核复盘 - $TODAY ==="

# 1. 生成每日汇总
echo "1. 生成汇总..."
python scripts/analyze_moderation_logs.py summary --date $TODAY

# 2. 检查误报候选
echo -e "\n2. 检查误报..."
python scripts/analyze_moderation_logs.py false-positives --date $TODAY --limit 10

# 3. 查看标记案例
echo -e "\n3. 查看标记案例..."
python scripts/analyze_moderation_logs.py flagged --date $TODAY --limit 5

echo -e "\n=== 复盘完成 ==="
```

### 每周优化（推荐）

```bash
#!/bin/bash
# weekly_optimization.sh - 每周关键词优化

echo "=== 每周关键词优化 ==="

# 查找30天内未使用的关键词
echo "查找未使用的关键词..."
python scripts/analyze_moderation_logs.py unused-keywords --days 30

# 生成过去7天的汇总报告
for i in {0..6}; do
  DATE=$(date -d "$i days ago" +%Y-%m-%d)
  python scripts/analyze_moderation_logs.py summary --date $DATE >> weekly_report.txt
done

echo "报告已保存到 weekly_report.txt"
```

---

## 📊 分析场景

### 场景1：误报率过高

**问题**：用户经常投诉合法提示词被阻止

**解决步骤**：
1. 运行误报分析：
   ```bash
   python scripts/analyze_moderation_logs.py false-positives --limit 50
   ```

2. 检查高频误报关键词：
   - 如果是通用词（如 "bra" 误匹配 "embracing"）
   - 考虑删除或调整为多词组合

3. 更新关键词列表：
   ```bash
   # 编辑关键词文件
   vim scripts/banned_keywords_backup.json

   # 重新上传
   python scripts/upload_keywords.py
   ```

---

### 场景2：漏报问题

**问题**：不当内容通过了审核

**解决步骤**：
1. 查看通过的日志（手动筛选可疑内容）

2. 提取提示词中的关键特征

3. 添加新关键词或调整 AI 提示词

4. 更新并重新测试

---

### 场景3：性能问题

**问题**：AI 检测太慢

**解决步骤**：
1. 查看性能统计：
   ```bash
   python scripts/analyze_moderation_logs.py summary
   ```

2. 检查 Layer 2 平均时间
   - 如果 > 1000ms，检查缓存命中率
   - 如果缓存命中率低，考虑增加 TTL

3. 优化策略：
   - 增加关键词覆盖，减少 AI 调用
   - 调整 AI 模型（Flash → 更快的模型）

---

## 🎯 最佳实践

### 1. 定期复盘
- **每日**：查看汇总和标记案例（5分钟）
- **每周**：分析误报和优化关键词（30分钟）
- **每月**：全面审查策略和准确率（2小时）

### 2. 关键词管理
- ✅ 保留高价值关键词（即使未触发）
- ✅ 删除冗余和过时的词汇
- ✅ 定期添加新发现的规避词汇
- ⚠️ 避免过度通用的词（如 "love"）

### 3. 数据隐私
- 所有用户 ID 已哈希化（不可逆）
- 提示词完整记录（用于分析）
- 定期归档/删除旧日志（如90天后）

### 4. 持续优化
- 误报率目标：< 3%
- 漏报率目标：< 1%
- 平均响应时间：< 500ms
- 标记率：1-5%

---

## 🚨 告警设置

建议监控以下指标：

```python
# 告警阈值
ALERT_THRESHOLDS = {
    "block_rate_too_high": 15,      # 阻止率 > 15%
    "flag_rate_too_high": 10,       # 标记率 > 10%
    "avg_time_too_slow": 1000,      # 平均时间 > 1000ms
    "false_positive_count": 20,     # 每日误报候选 > 20
}
```

---

## 📝 环境变量

```bash
# .env 配置

# 启用审计日志（推荐开启）
AUDIT_LOGGING_ENABLED=true

# 异步上传（推荐开启，不阻塞用户）
AUDIT_ASYNC_UPLOAD=true
```

---

## 🔧 故障排除

### 问题：日志未上传到 R2

**检查**：
```bash
# 1. 验证 R2 配置
echo $R2_ENABLED
echo $R2_ACCESS_KEY_ID
echo $R2_SECRET_ACCESS_KEY

# 2. 检查 Python 日志
grep "AuditLogger" app.log
```

**解决**：
- 确保 R2_ENABLED=true
- 验证 R2 凭证正确
- 检查网络连接

---

### 问题：分析工具报错

**检查**：
```bash
# 验证依赖
pip list | grep boto3

# 测试 R2 连接
python -c "from services.r2_storage import get_r2_storage; print(get_r2_storage().is_available)"
```

---

## 📚 相关文档

- [内容安全指南](./CONTENT_SAFETY_GUIDE.md)
- [Cloudflare 安全配置](./CLOUDFLARE_SECURITY_SETUP.md)
- [AI 内容审核](./AI_CONTENT_MODERATION.md)

---

**最后更新**：2025-12-14
**状态**：✅ 生产就绪

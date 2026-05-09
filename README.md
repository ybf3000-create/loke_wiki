# 洛克王国世界 AI 知识库助手（小智）

本项目是一个本地运行的洛克王国知识库助手，支持：
- 精灵 / 技能 / 道具 / 蛋查询
- 属性克制查询（单属性 + 双属性）
- AI Agent 工具调用（Ollama）
- 语音输入（ASR）与语音播报（TTS）
- 托盘驻留、模型切换、AI行为规则可配置

> 目标：让 AI 回答“可控、可查证、可追溯”，优先基于本地数据库事实回答。

---

## 1. 核心功能

### 1.1 知识库查询
- 查精灵详情（属性、进化链、技能）
- 查技能详情（类型、威力、描述）
- 反向查技能学习者（谁会某技能）
- 查属性克制关系
- 查蛋与进化形态对应关系

### 1.2 AI Agent 全权代理（Tool Calling）
- 模型自主选择工具查询
- 查询结果结构化返回，AI负责最后总结
- 具备行为边界：仅回答洛克王国相关问题

### 1.3 语音能力
- ASR：`sounddevice + SpeechRecognition`
- TTS：微软离线语音（pyttsx3）+ MOSS-TTS-Nano（ONNX）

### 1.4 桌面体验
- 系统托盘
- 模型切换
- AI 规则文件可编辑
- 聊天窗口快捷操作

---

## 2. 最新版本重点更新

详见：`docs/更新日志.md`

本次重点：
1. **属性克制表统一重构**：单/双属性合并为统一四字段结构
2. **双属性克制查询上线**：可直接查询如“虫+翼被谁克制”
3. **Agent 稳定性修复**：同参 tool 重复请求不再导致中断
4. **AI 行为规则补充**：双属性系别归属（type1/type2 任一包含即算该系）

---

## 3. 环境要求

- Windows（推荐）
- Python 3.11+
- 本地 Ollama 服务（可选但推荐）

安装依赖：

```bash
pip install -r requirements.txt
```

启动：

```bash
python run.py
```

---

## 4. 目录结构（关键）

```text
loke_wiki/
├─ config/
│  ├─ settings.py
│  └─ ai_rules.txt
├─ data/
│  └─ db/
├─ docs/
│  ├─ AI行为规则说明.md
│  └─ 更新日志.md
├─ scripts/
│  ├─ import_unified_type_chart.py
│  └─ test_repeat_tool_finalize.py
├─ src/
│  ├─ core/
│  │  └─ database.py
│  ├─ ollama_client/
│  │  ├─ agent_loop.py
│  │  └─ tool_definitions.py
│  ├─ ui/
│  └─ voice/
└─ run.py
```

---

## 5. 属性克制查询说明（重要）

### 5.1 统一表结构（type_effectiveness）
当前克制表已统一为：
- `atk_type1`
- `atk_type2`（单属性时为 `无`）
- `def_type1`
- `def_type2`（单属性时为 `无`）
- `multiplier`

已包含：
- 单攻 vs 单防
- 单攻 vs 双防

共 3096 行。

### 5.2 双属性查询示例
- 问：`花魁蜂后(虫+翼)被谁克制？`
- 系统会走双属性克制查询，不再按单属性误判。

---

## 6. AI 行为规则

规则文件：`config/ai_rules.txt`

支持直接编辑（保存后重启生效），包括：
- 回答范围限定
- 查询行为约束
- 回复风格约束

已补充规则：
- 精灵只要包含某属性即视为该系（`type1` 或 `type2` 任一命中）

详细说明见：`docs/AI行为规则说明.md`

---

## 7. 常见问题（FAQ）

### Q1: 为什么会“答非所问”？
常见原因是用户问题表达歧义（例如“属性技能”被模型误解为“技能名查询”）。
建议：
- 直接指定查询目标（如“被火系4倍克制的精灵”）
- 使用双属性明确写法（如“虫+翼”）

### Q2: 为什么以前会“查到一半停住”？
历史原因是同参 tool 重复请求后直接中断。当前版本已修复：
- 检测重复后会强制基于已有结果收尾回答
- 不再产生半截 tool_call 会话

### Q3: 为什么克制关系和旧资料不一致？
本项目已切换到指定 wiki 矩阵并统一入库，优先以当前库内规则为准。

---

## 8. 开发说明

### 8.1 导入统一克制表

```bash
python scripts/import_unified_type_chart.py
```

### 8.2 重复调用回归测试

```bash
python scripts/test_repeat_tool_finalize.py
```

---

## 9. 免责声明

本项目为本地知识库辅助工具，最终内容以你维护的数据源为准。建议关键对战结论结合实际游戏版本复核。

# Level-Maker 剩余核对任务书（1-6）—— 交给 Codex 自包含说明

> 本文件让**没有任何本项目会话上下文**的接手者（Codex / 其他 agent / 人）能独立完成剩余核对。
> 先完整读本文件，再按「必读文件」顺序开工；每项核对完成后按「输出要求」回写。

---

## 0. 项目背景与规矩

- 项目：**Level-Maker** — 给已有 Unity 消除游戏（BlockColorMatch，App 内部名 "Pair Pair"）做 **AI 编关工具**。
- 工作目录：/Users/lingkunwang/Projects/Level-Maker
  - 规则定稿文档（唯一事实源）：docs/level-rules.md
  - 仓库核对审计（已完成部分 + 差异清单）：docs/level-rules-vs-repo.md
  - 接续指南：docs/CONTINUE.md
- 游戏仓库（Unity C#，事实源）：/Users/lingkunwang/Projects/twoblocks-frontend（Unity 项目在 BlockColorMatch/ 子目录下）
- **规矩（用户明确要求）**：
  1. **只看关卡编辑方面逻辑**（元素 / 障碍 / 棋盘 / 消除 / 计时 / 数据格式），**不要看**既有关卡（lv_*.json）的具体内容细节、不要管项目其他业务
  2. 以**仓库代码为唯一基准**（仓库 docs 的 .md 可能过期，源码 > 仓库文档）
  3. 不要改动游戏仓库任何文件；只改 Level-Maker/docs/ 下的文档
- **用户已拍板（本轮 2025-06 会话）**：
  - OK 9 制造机 = 手动制造机（ManualBlockDispenser）定稿；自动制造机暂不定稿
  - OK 10 颜色筛选 = 格子 color 属性（已入 level-rules.md 第2节）
  - OK 11 计时起点 = 首个棋子被选中后开始；限时来自 LevelContextMgr.levelCtx.baseTime（不在 JSON）（已入第1节）
  - OK 12 逻辑层级 BoardLogicLayer / stepLock 步数锁 / matchBlockOrder 消除顺序（已入 2.5、3 节）
  - OK 13 可玩色 12 种含黑白（已入第1节）
  - PENDING 7 钥匙、8 星/猫：用户暂不管，**不要定稿**
  - **1-6 是本任务书要完成的**

## 1. 必读文件（按顺序）

1. docs/level-rules.md（当前规则全貌；重点第1节基础规则、第2节元素清单、2.5节、第3节数据格式、第5节开放问题）
2. docs/level-rules-vs-repo.md（审计文档：1-6 冲突细节与仓库证据地址已写清）
3. 游戏仓库源码（按各项指引，重点）：
   - twoblocks-frontend/BlockColorMatch/Assets/Game/Scripts/GamePlay/Configs/BlockType.cs（形状枚举+格位+isSelectable）
   - .../GamePlay/Configs/LevelConfig.cs（所有配置类/枚举/字段默认值）
   - .../GamePlay/Mgrs/GamePlayMgr.cs（移动提交/消除结算/胜败/层级）
   - .../GamePlay/Mgrs/LevelTimer.cs（计时起点）
   - .../GamePlay/Abilities/MoveAbility.cs（拖拽移动语义）
   - .../GamePlay/Area.cs + DecorationArea.cs + LowerArea.cs + ShieldArea.cs
   - .../GamePlay/Door.cs + .../GamePlay/Configs/DoorType.cs
   - .../GamePlay/Wall.cs + .../GamePlay/Configs/WallType.cs
   - .../GamePlay/IceShaver.cs + .../GamePlay/Abilities/IceShaverAbility.cs
   - .../GamePlay/ColorTrain/ + .../GamePlay/Abilities/ColorTrainAbility.cs
   - .../GamePlay/Controllers/IceAreaController.cs（若存在）
   - .../GamePlay/Mgrs/EditorMgr.cs（编辑器保存/校验：Validate... 函数、SerializeFields 等）
   - .../MetaSystems/Data/LevelContexts.cs（baseTime 换算）
4. 仓库自带文档（参考，可能过期）：twoblocks-frontend/docs/Level/*.md、docs/LevelEditor/*.md

## 2. 待核对项 1-6 详情

### 1) 棋子形状枚举（最大差异）
- 现状（level-rules.md 第2节多格棋子）：12 种 = 1x1/1x2/1x3/1x4/1x5/2x2/2x3/7字形(5格)/L形(3格)/十字形(5格)/土字形(4格)/翻转L(5格)；含 ASCII 布局（用户此前亲手对齐）。注意**该清单与仓库代码不符**（只有「十字形」一致）。
- 仓库事实（BlockType.cs 已核实）：枚举 B_1X1=0, B_1X2=1, B_1X3=2, B_1X4=3, B_2X2=4, B_2X3=5, B_7=6, B_ARROW=7, B_CROSS=8, B_DELTA=9, B_J=10, B_1X5=11；每形状有 LocalGrids（pos + isSelectable，只有可选中格能拖）。
  - B_7(4格): (0,2),(1,0),(1,1),(1,2) — 竖3+左上1（"7/L 形"）
  - B_ARROW(3格): (0,0),(0,1),(1,0) — 三角/箭头
  - B_CROSS(5格): (0,1),(1,0),(1,1),(1,2),(2,1) — 3x3 十字（中心不可选）
  - B_DELTA(4格): (0,0),(1,0),(2,0),(1,1) — 倒三角
  - B_J(4格): (0,0),(1,0),(1,1),(1,2) — J 形
  - B_1X1..B_1X5: 竖条，两端 isSelectable=true、中间格 false（B_1X2 两格都可选）
  - B_2X2/B_2X3: 矩形
- **任务**：以 BlockType.cs 为准重写第2节形状枚举（含每个形状：枚举名/枚举值/格位坐标表/ASCII 布局/isSelectable 标记/是否可旋转4向不可镜像）。若 Codex 能看编辑器截图（用户可提供）更好；**没有截图时坐标表已足够精确**。对照文档旧清单删去 7字形5格/土字形/翻转L5格 等不存在的形状。

### 2) 移动语义与消除时机
- 现状（第1节）：滑行移动（沿直线、可自由停在路径任意空格、被棋子/边界阻挡才停）；消除 = 移动过程中出现相邻（含起点）第一个瞬间即消；起点相邻算挨着。
- 仓库事实（已核实）：
  - 移动 = **拖拽跟随**：MoveAbility.TryMoveTo 逐帧把块移向目标指针格（maxDragStep 0.5/1），ClusterPlaceable + PosPlaceable 判定可放置（含层级/墙/门/颜色筛选/占格）；轴向约束由 BlockMoveMode.BOTH/VER/HOR 提供；无“滑行惯性/路径滑动”。
  - 消除 = **提交后按当前格子结算**：ResolveImmediateDragInteractions 唯一入口（不依赖 Collider/拖拽方向）；同一次移动只消费一个目标，优先级 **门 -> 冰铲(IceShaver) -> ColorTrain -> 普通色块**；CanMatchBlocks 要求：相邻 unprotected grids、逻辑色相等、双方可移动可匹配、无 StepLock/KeyLock/Lock/Floor/Immune、非全冰覆盖、WithStar 双方需都带星、**同逻辑层**。
- **任务**：把第1节「移动/消除」两段改为拖拽+落点结算；删除“起点相邻自动消/路径中第一个相邻瞬间”。补充优先级与 CanMatchBlocks 条件；确认是否同层要求。

### 3) 墙与障碍（两类）
- 现状（第2节障碍物）：障碍 = 地形类，不可移动/不可消除/免疫一切事件/不算下方区域占用。
- 仓库事实（已核实）：walls 分两类：
  1. **结构墙** WallType 0-12（DOT/EDGE_T/B/L/R/OUTER_CORNER_*/INNER_CORNER_*）— 构成棋盘物理边界，BoardBase，不可破坏
  2. **障碍墙** WallType 100-104（WALL_OBS_CYCLE_PIPE / TWO_WHOLE_PIPE / TEE / TWO_PIPE_END / TWO_PIPE）— **可被破坏**（通过消除或道具），带 layer（玩法层），**只阻挡同一玩法层**；ReloadWalls 目前**只加载 WALL_OBS_CYCLE_PIPE**（其他类型代码在但未启用，需确认）
- **任务**：重写第2节障碍条目为两类墙；确认障碍墙破坏方式/HP/破坏后占位、棋盘边界 = 结构墙 or cells 范围；更新 open question「障碍墙 100-104 启用范围」。

### 4) 装修区域 与 门 拆分
- 现状（第2节装修区域（覆盖门））：合并一个元素（盖矩形、全局事件扣血、HP=0 解锁）。
- 仓库事实（已核实）：**两个独立机制**：
  1. **DecorationArea（装修区域）**：hp/width/height；视觉遮挡 + 锁覆盖范围内（层级不高于自身）元素的 Movable/Matchable；每次普通双块消除 HP-1 -> 归零解锁移除 -> 约等于旧“装修区域”
  2. **Door（门）**：D1/D2/D3 x T/B/L/R；**有颜色 blockColor**——同色块可“进门”（ConsumeBlock 消耗并弹飞消失）；带 StepLock（每次匹配 -1）、WithStar、Health（health 用途待确认）；占格阻挡放置。**门在当前关卡 JSON 未见持久化字段**（ReloadDoors 只清空；门由编辑器/历史/剪贴板创建）-> 门的序列化与加载链**待确认**
- **任务**：第2节拆成「装修区域 DecorationArea」+「门 Door」两条；确认 Door 的 JSON 持久化（当前不支持？还是藏在某字段/entity？）；health 用途。

### 5) 冰块：区域制冰区 + 冰面地形
- 现状（第2节冰冻方块）：冰冻方块（每枚独立计数 N 破冰、透明但颜色可见、破冰前不可移动不可消除）。
- 仓库事实（已核实）：
  - **iceArea** = Dictionary<int,int> 格子索引->冰层数（**区域制**，不是每枚独立计数）：被冰覆盖的元素挂 IcedOcclusionAbility（全冰覆盖 -> 不可移动/不可匹配）
  - **CellType.Ice 冰面格子**（cellType=1）：格子地形（滑冰面），文档此前未提及
  - 编辑器保存 cfg.iceArea = IceAreaController.Inst.IceArea；452 关中仅 2 关有 iceArea
- **任务**：重写第2节冰冻条目为「格子冰层区域（iceArea）+ 遮挡锁定（IcedOcclusionAbility）」；单列「冰面格子地形」；确认破冰规则（IceAreaController：如何减层、触发条件）与“颜色可见性”。

### 6) 颜色火车：沿轨道移动
- 现状（第2节颜色火车）：链式车厢、固定占位不可移动、头部激活、整车 HP、被动扣血 -2。
- 仓库事实（已核实）：ColorTrain **沿轨道移动**（tracks 坐标链 + TrackGraph；GridSelectAbility 轮选 wheel 决定移动目标，轨道受限时 collisionThreshold=0.01 沿轨走）：
  - 车厢配置 carriages：type(Colored/Empty)、directionFromPrevious、blocks（可带 stepLock/keyLock/bombSecs/key/lock/withKey/withStar）
  - 消耗顺序 consumeOrder(HeadFirst/TailFirst)、端消耗模式 endConsumeMode(HeadOnly/TailOnly/Both)
  - TryConsumeBlock/CanConsumeBlock（同色吸收）；ColorTrainRules.CalculateGridPositions（沿轨算车厢坐标）
  - 452 关中 38 关使用
- **任务**：重写第2节颜色火车为「沿轨道移动 + 车厢队列消耗（consumeOrder/endConsumeMode）」；确认火车移动触发（拖拽轮选移动 vs 自动推进?）、每普通对消推进规则、被动扣血是否仍存在。

## 3. 输出要求（完成每项后回写）

1. **改 docs/level-rules.md**：第1/2/2.5/3/5 节按增量更新，保持中文、保持现有条目风格；已修改条目标记 [已按仓库修正]；拿不准的保持 [待确认] 并写明卡点
2. **改 docs/level-rules-vs-repo.md**：开头「用户拍板进展」里把 1-6 状态从 PENDING 改为 OK（附一句结论）；第4节待确认清单同步收敛
3. **改 docs/CONTINUE.md**：更新「最近进展」与待办 #1
4. 每项核对留 2-4 行「结论摘要」写在 docs/level-rules-vs-repo.md 对应小节末尾

## 4. 工具提示

- 本目录（Level-Maker/docs）可自由读写；游戏仓库**只读**
- 源码查看用 ripgrep/grep 都行；bash 的 grep 在部分 .cs 文件上疑似间歇失效 -> 优先用 ripgrep 或 python 读取
- 想确认某个机制的触发点，优先搜 EventCenter.Inst.Emit/On + 事件名（该游戏的事件总线）
- 配置字段以 LevelConfig.cs 的 [ConfigField]/[JsonProperty] 为准；仓库 docs/*.md 可能过期

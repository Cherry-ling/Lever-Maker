# 仓库核对审计：level-rules.md 对照 twoblocks-frontend（源码证据，待用户确认）

> 状态：**第 1 项形状、第 2 项移动/消除、第 3 项墙已由用户确认；第 4–6 项源码核对完成，待你确认**。本文件保留“仓库事实 vs 文档”的逐条证据与差异；源码没有实现证据的项明确保留为 [待确认]。
> 核对范围：仅关卡编辑方面（棋盘 / 元素 / 障碍 / 消除 / 计时等玩法逻辑），不含既有 452+ 关卡的关卡内容细节（只统计了字段使用分布）。
> 事实源：`twoblocks-frontend/BlockColorMatch/Assets/Game/Scripts/`（BlockType.cs / LevelConfig.cs / GamePlayMgr.cs / Area*.cs / Door.cs / IceShaver.cs / Bomb.cs / LevelTimer.cs / MatchLockAbility.cs 等）+ 关卡 JSON 字段分布统计。

---

## 0. 关卡数据格式（仓库实锤）

LevelConfig JSON 字段：`cells / walls / blocks / entities / tracks / matchBlockOrder / iceArea`（文件内另有 `hash`）。**没有独立的 time / doors / 目标 字段**。

- `cells`：`gridPos`（Vector2Int，任意形状棋盘 ✓）+ `color`（BlockColor，非 NULL 即"颜色筛选格"）+ `cellType`（Default/Ice 冰面地形）— 每格最多一个颜色
- `walls`：`type`（结构墙 0-12 / 障碍墙 100-104）+ `rot` + `gridPos` + `layer`（BoardLogicLayer）
- `blocks`：`type/rot/color/gridPos/hasStar/withStar/hasCat/moveMode/stepLock/groupID/floor/keyLock/bombSecs/key/lock/withKey/customWidth/customHeight/layer/abilities`
- `entities`：`entityName/gridPos/layer/abilities`（区域类/冰铲/火车/制造机走这里）
- `tracks`：轨道格坐标列表（TrackBuilder / 带 GridSelectAbility 的普通块用；当前 ColorTrain 不读取）
- `matchBlockOrder`：`List<(int, int)>`（消除顺序 = "阅读理解"机制）
- `iceArea`：`Dictionary<int,int>`（**CellType.Ice 连通组件索引 → 整片冰剩余层数**，区域制冰冻）
- `hash`：部分文件有（疑似防篡改/校验，用途待确认）

**字段默认值序列化**：`DefaultValueHandling.IgnoreAndPopulate` + `[IgnoreEmptyCollection]` → JSON 最小化，默认值（type=0→B_1X1、rot=Rot0、color=NULL、计数=0 等）写入时省略。

---

## 1. 已确认一致 ✅（无需修改）

| 条目 | 仓库证据 |
|---|---|
| 棋盘 = 任意形状格子集合（cells），非固定矩形，有边界 | cells 列表任意 gridPos；`PosPlaceable` 要求目标格 ∈ allCells ✓ |
| 颜色分组、同色多对 | blockcolor 12 种可玩色，同色多枚 ✓ |
| 消除成对（两枚同色相消） | `Block.Event.BLOCK_MATCH`、`ResolveBlockMatch` 双方 ✓ |
| 消除后不自动填补、保留空位 | 无全局重力；仅组内无支撑下落（见 §3.9）✓ |
| 限时机制 = 纯倒计时、超时失败 | LevelTimer float timeTotal/timeRemain，`OnTimeUp → LEVEL_FAILED TIME_UP` ✓ |
| 无色方块：包装隐藏色、全局计数 N 解除、解除后恢复真实色 | PackagedAppearanceAbility + MatchLockAbility（count--，每非自身匹配 -1）✓ |
| 搓冰机：被动扣血 -2（按匹配色对应颜色段） | IceShaverAbility.DamageMatchedEndsInSequence(color, 2) ✓ |
| 装修区域：每 1 次消除事件 HP-1、HP=0 解锁移除 | DecorationArea（hp，每次普通双块消除 -1）✓ |
| 下方区域：区域内占用清零解锁 | LowerArea（覆盖范围无内容层元素时解锁）✓ |
| 无色区域（消除禁用区）：禁消除不禁移动 | ShieldArea（锁 Matchable、不锁 Movable、不遮挡）✓ |
| 绑定组整体移动 | groupID + Hinge（铰链）✓ |
| 炸弹爆炸 = 直接失败、无范围破坏 | Bomb 倒计时归零 → `EventBombExploded` → 关卡失败 ✓ |
| 箭头 = 轴向移动约束 | BlockMoveMode.BOTH/VER/HOR；CanMoveHorizontally/Vertically ✓ |
| 多格棋子：整块一起消除、计 1 次事件 | MatchEliminate 整块移除，COUNT 1 ✓ |

---

## 用户拍板进展（2025 本轮）
- ✅ **9 制造机**：先按手动制造机（ManualBlockDispenser）定稿；自动制造机（AutoBlockDispenser）暂不定稿
- ✅ **10 颜色筛选**：按仓库修正（= 格子 color 属性）
- ✅ **11 计时起点**：按仓库修正（首个棋子被选中后开始；限时来自 LevelContext.baseTime）
- ✅ **12 通用机制**：按仓库修正（逻辑层级 BoardLogicLayer / stepLock 步数锁 / matchBlockOrder 消除顺序）
- ✅ **13 可玩色**：按仓库（12 种含黑白，10 空洞占位）
- ⏸️ **7 钥匙 / 8 星·猫**：用户暂不管，不定稿
- ✅ **1 形状**：**用户已确认**。编辑器截图中的 12 个标准形状与 `BlockType.cs` 一一对应；支持 Rot0/90/180/270 四向旋转，无镜像。编辑器展示顺序中 `B_1X5` 排第 5，但其枚举值仍为 11。
- ✅ **2 移动与消除**：**用户已确认**。拖拽中每次成功更新到可放置的当前格位即检查并结算；松手仅作兜底复查。无滑行、无选中起点自动消；结算优先级和同层匹配条件已记录
- ✅ **3 墙**：**用户已确认**。棋盘边界只由 `cells` 定义；编关工具只支持当前实际加载的 `CYCLE_PIPE` 作为同层固定单格障碍。结构墙、其余障碍墙类型及可破坏/HP 规则不进入工具
- ✅ **4a 装修区域（DecorationArea）**：**用户拍板：按对齐规则定义（2025）**——覆盖 N×Z 矩形、每消除事件 HP-1、HP=0 解锁；与下方区域是两个机制；实现注记保留源码（DecorationAreaAbility 监听 BLOCK_MATCH 扣 HP）
- ⏳ **4b 门（Door）**：源码核对完成（同色块进门被消耗、D1/D2/D3×T/B/L/R、stepLock/withStar/health）；**Door 的 JSON 持久化和 `health` 仍无运行时落盘/用途证据** → 保持 [待确认]
- ✅ **5 冰冻方块**：**用户拍板：按对齐规则定义（2025）**——被冰封普通棋子、每枚独立计数 N 破冰、颜色可见、破冰前免疫；⚠️ 与源码区域制冰区（`CellType.Ice` 连通组件 + `iceArea` 组件层数、每 BLOCK_MATCH 全冰区 -1、默认隐藏颜色）不一致，已加"实现差异提示"；冰面格子地形按源码保留
- ✅ **6 ColorTrain**：**用户拍板：按源码结论定义（2025）**——车厢链端部消耗 + 普通对消最多两次同色联动；不读取 `tracks` 作可拖拽沿轨移动；PLAY 不可选
- ✅ **14 参数区间核对（2025）**：452 关语料 + Level 表统计完成（见 §5）——棋盘 50–75 格、每组 2–6 色块、空位 ≥4、限时 70–360s 等；并发现**普通 block 也支持 customWidth/customHeight 自定义矩形**（含 3×3/4×6，LevelConfig.cs:181/184）。
- ✅ **15 制造机多格尺寸判据（2025）**：**用户拍板 = 判据 C**——包围盒不超 3×3（全旋转宽≤3 且高≤3）且总格数<9；语料保留 568/597（95.1%），仅拒 B_1X4/B_1X5/3×3 整块（29 项/20 关），证据见 §5.2

---

## 2. 直接冲突 ⚠️（须以仓库为准修改）

### 2.1 棋子形状枚举（重大）
- 文档定稿 12 种：1×1/1×2/1×3/1×4/1×5/2×2/2×3/7字形(5格)/L形(3格)/十字形(5格)/土字形(4格)/翻转L(5格)
- **仓库 BlockType 12 种实际枚举（值 0~11 顺序）**：`B_1X1=0, B_1X2=1, B_1X3=2, B_1X4=3, B_2X2=4, B_2X3=5, B_7=6, B_ARROW=7, B_CROSS=8, B_DELTA=9, B_J=10, B_1X5=11`
  - `B_1X5` 枚举值 = **11**（不是文档记的"5"位置）
- 仓库实际格位布局（pos + isSelectable）：
  - B_1X1=(0,0)✗不可选（任务书旧摘要写为可选，与当前 `BlockType.cs` 不符）
  - B_1X2=(0,0)✓(0,1)✓
  - B_1X3=(0,0)✓(0,1)✗(0,2)✓（中格不可选）
  - B_1X4=(0,0)✓(0,1)✗(0,2)✗(0,3)✓
  - B_1X5=(0,0)✓(0,1)✗(0,2)✗(0,3)✗(0,4)✓
  - B_2X2=4 格
  - B_2X3=6 格
  - **B_7（4 格）**：(0,2),(1,0),(1,1),(1,2) — 竖3 + 左上1，即"7/L 形"，**不是文档的 5 格 7 字形**
  - **B_ARROW（3 格）**：(0,0),(0,1),(1,0) — 三角/箭头，文档没有
  - B_CROSS（5 格）= 3×3 十字 ✓ 与文档一致（中心 (1,1) 不可选）
  - **B_DELTA（4 格）**：(0,0),(1,0),(2,0),(1,1) — 倒三角，文档没有
  - **B_J（4 格）**：(0,0),(1,0),(1,1),(1,2) — J 形，文档"翻转L(5格)"仓库不存在
- **结论**：文档 §2 5 种特殊形状中仅"十字形"与仓库一致；"7字形/L形/土字形/翻转L"的布局与仓库 B_7/B_ARROW/B_DELTA/B_J 完全不同。须按仓库重写形状表。

> **结论摘要（1 形状，用户已确认）**：编辑器截图与 `BlockType.cs` 的 12 个标准形状一一对应；Rot0/90/180/270 是仅有的四向旋转，没有镜像。编辑器展示顺序与枚举值顺序不同：`B_1X5` 展示第 5、枚举值为 11。`B_1X1` 的唯一格在当前代码为不可选点，和任务书旧摘要不同。

### 2.2 移动语义：滑行 → 拖拽（drag）
- 文档：滑行移动（沿直线滑、可自由停在路径任意空格、路径被占则过不去）
- 仓库：`MoveAbility.TryMoveTo` = **拖拽跟随**（手指/鼠标拖动，块随之移动，逐帧往目标格靠，碰撞阈值判定可放置性 `ClusterPlaceable` + `PosPlaceable`）；轴向约束由 MoveMode 提供；**斜向不受限（BOTH）**。拖拽中每次成功应用当前格位后立即结算；松手仅再复查一次。无"滑行惯性/路径滑动"。

### 2.3 消除时机：移动过程中相邻 → 落点提交后结算
- 文档：移动过程中出现相邻（含起点）第一个瞬间即消
- 仓库：**`ResolveImmediateDragInteractions` 唯一入口**；它在每次成功拖到一个格位后调用，并在松手时复查当前格位。同一次结算只消费一个目标，优先级 **门 → 冰铲 → ColorTrain → 普通色块**；`CanMatchBlocks` 要求相邻 unprotected grids、逻辑色相等、同一逻辑层、双方可匹配/可移动、无 StepLock/KeyLock/Lock/Floor/Immune/全冰。`withStar` 现码是发起拖拽块带星时目标也必须带星；无“选中起点自动消”。

> **结论摘要（2 移动/消除，用户已确认）**：拖拽跟随且不是滑行；每次成功应用可放置的当前格位便立即检查相邻消除，松手仅作兜底复查。结算不是 Collider 物理碰撞，而是当前格位的四邻判定；证据已列出优先级与同层/锁/冰等前置条件。

### 2.4 墙：结构墙与障碍墙（当前破坏链未证实）
- 文档：把“障碍物”误写为可复用棋子形状的永久地形，且没有拆出结构墙与障碍墙
- 仓库：walls 分两类：
  1. **结构墙**（WallType 0-12：DOT/EDGE_T/B/L/R/OUTER_CORNER_*/INNER_CORNER_*）— 构成棋盘物理边界，BoardBase，不可破坏
  2. **障碍墙**（WallType 100-104：WALL_OBS_CYCLE_PIPE / TWO_WHOLE_PIPE / TEE / TWO_PIPE_END / TWO_PIPE）— 有 layer（属某一玩法层），只阻挡同一玩法层；`WallTypeExt.Poses()` 对每种墙均只返回 `(0,0)`。
  - 注意 `ReloadWalls` 当前**只加载 WALL_OBS_CYCLE_PIPE**；其它障碍类型代码有枚举/预制体地址但未实例化。源码未找到普通消除或道具伤害、HP、运行时删除的调用，不能把仓库旧文档的“可被破坏”当成当前运行时事实。

> **结论摘要（3 墙，用户已确认）**：棋盘边界由 `allCells`/cells 范围定义，非 cells 目标不可放置。编关工具仅采用当前实际加载的 `CYCLE_PIPE`，作为同层固定单格障碍；结构墙、其余 100–104 类型及破坏/HP/破坏后占位不支持。

### 2.5 计时起点：开局 → 首选中棋子后开始（含炸弹）
- 文档：纯倒计时开局起算；炸弹"出现时"起算
- 仓库：LevelTimer `timeTotal = LevelContextMgr.Inst.levelCtx.baseTime`（**限时来自关卡上下文/难度配置，不在关卡 JSON**）；倒计时由 `CountLock.Lock("ProcOnGameBegin")` 门控，**首个棋子被 SELECTED（首次操作）时解锁开始**；10s 警告；ADD_TIME 加时（复活/道具）。
- 炸弹 Bomb：`bombSecs` 生成 Bomb 能力（DynamicGen 不写 JSON），**第一次被选中时开始倒计时**（一次性注册），被打包（packaged）时暂停，归零 → 爆炸失败（无范围破坏）。

### 2.6 "装修区域（覆盖门）" 与 "门" 是两个不同机制
- 文档把"装修区域（覆盖门）"合并成一个元素（盖矩形、全局事件扣血、HP=0 解锁）
- 仓库拆成两个：
  1. **DecorationArea（装修区域）**：hp / width×height；视觉遮挡 + 锁覆盖范围内（层级不高于自身）元素的 Movable/Matchable；**每次普通双块消除 HP-1**，归零解锁移除 — ≈ 文档"装修区域"
  2. **Door（门）**：D1/D2/D3 × T/B/L/R 方向；**有颜色（blockColor）**，同色块可"进门"（`ConsumeBlock` 消耗该块并使其弹飞消失）；另带 StepLock（每次匹配 -1）、WithStar、Health（health 用途待确认）；占格阻挡放置 —— 独立于装修区域，文档**缺失此元素**
- ⚠️ 门在现有关卡 JSON 中**未见持久化字段**（ReloadDoors 只清空不加载；门由编辑器/运行时创建）→ **门的序列化与加载链待确认**

> **结论摘要（4 DecorationArea / Door，源码核对完成，待你确认）**：源码指向两个实体。DecorationArea 是区域视觉遮挡和可移动/可匹配锁，按合格 `BLOCK_MATCH` 扣 HP；Door 是同色块进门消耗、带方向与 StepLock 的独立占格物。DoorConfig 仅见于编辑器历史/剪贴板，顶层 JSON 保存和 `ReloadDoors` 都没有链路；`health` 也仅赋值未消费。

### 2.7 冰块：方块属性 → 区域制冰区（iceArea）+ 冰面地形
- 文档：冰冻方块（各枚独立计数 N 破冰、不可移动不可消除、冰块透明颜色可见）
- 仓库：**两块不同机制**：
  1. **iceArea**：`Dictionary<int,int>` 格子索引→冰层数（区域制）；被冰覆盖的元素挂 `IcedOcclusionAbility`（全冰覆盖时不可移动/不可匹配）；"冰冻遮挡"是视觉+锁定，不是每枚独立计数 → 与文档"各枚独立计数"不同
  2. **CellType.Ice 冰面格子**（cellType=1）：格子地形（滑冰面），文档未提及
- 结论：冰冻 = 格子冰层区域 + 遮挡锁定；须按此改写

> **结论摘要（5 冰区，源码核对完成，待你确认）**：`CellType.Ice` 先形成冰面连通组件，`iceArea` 的 key 是组件索引而非格子索引，value 是整片冰的层数。每个 `BLOCK_MATCH` 令所有存活冰区各减 1，归零整片解除；实体只有全占格被覆盖时被锁且默认隐藏真实颜色。不存在“每枚冰块独立 N 次破冰”的实现。

### 2.8 颜色筛选区域：独立实体 → cell.color 格子属性
- 文档：独立"颜色筛选区域"实体（1×1 单元可连片）
- 仓库：**就是格子的 `color` 字段**（NULL=无色、非 NULL=筛色）；`CanPassColorFilter(cell.color)`：未解锁的无色块不能通过任何筛选色；解锁后按逻辑色判断。颜色筛选不是独立区域实体，一格一色。

### 2.9 颜色火车：车厢链端部消耗（不读取 tracks）
- 文档：整列固定占位不可移动，头部激活机制
- 仓库：车厢（carriages）级配置 `type(Colored/Empty) / directionFromPrevious / blocks(可带 stepLock/keyLock/bombSecs/key/lock/withKey/withStar...)`；**消耗顺序 consumeOrder(HeadFirst/TailFirst) + 端消耗模式 endConsumeMode(HeadOnly/TailOnly/Both)**。PLAY 模式 ColorTrain 不可选，代码没有 `MoveAbility` / `GridSelectAbility`，也不读取顶层 `tracks`/`TrackGraph`；头部删车时仅将锚点重设到下一节，保持剩余车厢坐标。
- 每次普通同色双块匹配后，按 consumeOrder 跨火车扫描，最多移除 2 个同色、未锁且未冰冻的活动色层；拖拽块只能由参与端（头/尾由 endConsumeMode 决定）同色消耗。**文档“轨道移动、仅头部、整车 HP”须重写**。

> **结论摘要（6 颜色火车，源码核对完成，待你确认）**：源码指向方向配置形成的车厢链、端部接触消耗与普通对消后的最多两次同色联动。火车不是可沿顶层 tracks 拖拽/自动行驶的实体；车厢删除、空端清理才会改变链和锚点。求解器是否应按此建模，待你确认。

### 2.10 制造机：手动拖出 → 手动(ManualBlockDispenser) + 自动(AutoBlockDispenser) 两种
- 文档：一种制造机（拖出式，HP=数量、开口前方空位）
- 仓库：
  - **ManualBlockDispenser**（手动）：玩家从机器拖出（preview 拖拽），要求目标格合法（含临时地形）；HP = 队伍剩余数；DraggingPreview 时 StepLock 检查放宽；被拖出块脱离机器
  - **AutoBlockDispenser**（自动）：按 `items` 队列**自动向滑出区（slideRegion）推出方块**，定时（AutoCheckInterval）检查
  - 现有关卡 452 关中：Manual 82 个、**Auto 0 个**（未实际使用，但代码完整）

### 2.11 双色格子：嵌套外壳 → floor 叠放 + 外壳联动
- 文档：双色方块 = 两个普通方块嵌套（A 包 B），固定 2 层，血量 2，剥壳
- 仓库：BlockConfig `floor`（0/1 两层同格叠放）；Block 有嵌套外观（PackagedTie / 双层组合）；"**同格叠放时，嵌套色块只用外壳参与同色联动**"（内层颜色不作为提示目标）；`NormalizeNestedBlockStepLocks` 同步叠放步数锁。→ 双层通过 floor 实现，剥壳逻辑细节（外壳消除后内层如何）**待确认**

### 2.12 钥匙机制：暂缓 → 仓库已实现
- 文档：钥匙 [暂缓]
- 仓库：`key / keyLock / lock / withKey` 字段齐全；`Block.UnlockKeyLock`、`ColorTrain.UnlockLowestKeyLock`（全场 KeyLock 最小者解锁机制）；锁方块（lock）、钥匙方块（key 携带）。→ 钥匙 = 已实现元素，须补齐文档规则

### 2.13 星 / 猫：文档缺失
- 仓库：`hasStar / withStar / hasCat`。WithStar：**匹配要求双方都带星**（CanMatchBlocks）；门也带 WithStar（进门要求双方带星）。hasCat 用途待确认。→ 新增元素

---

## 3. 仓库新增、文档未对齐 ➕

1. **逻辑层（BoardLogicLayer）**：BoardBase=0 / Layer1=10 / Layer2=20 / Layer3=30；缺省→Layer2、40→Layer3。block/墙/实体均有 `layer` 字段；区域按层级约束（只锁层级不高于自身的元素）；下层块不阻挡上层移动；障碍墙只阻挡同玩法层。**文档无层级概念，需全篇补入**
2. **stepLock（步数锁）**：Block 的 `StepLock` >0 时不可匹配/不可放置（拖动被限）；每次相关匹配事件 -1（Block.cs:3005 / Door.cs:241）→ **方块/门可带步数锁**
3. **matchBlockOrder（消除顺序 / 阅读理解）**：`List<(EntityID, EntityID)>` 预期消除顺序；GamePlayMatchHintMgr 校验消除是否命中顺序队列，未预期消除只上报。→ 新机制
4. **炸弹倒计时起点 = 首次选中**（见 2.5）
5. **循环换色**：`loopTime` 难度配置 + `ApplyLoopOffset` 按可玩色集合循环轮换 → 关卡难度可整体偏移颜色
6. **可玩色 = 12 种（含黑白）**：RED..MAGENTA 0-9（10 空洞占位）、BLACK=11、WHITE=12；paletteSize 由难度配置决定用前 N 色
7. **hash**：部分关卡文件含 hash（用途待确认）
8. **低层块不占格**：LowerArea 下低层块不计数占格（`ShouldCountInBlockPositions`）
9. **groupID 绑定 + 组内无支撑下落**：`HandleGroupBlockFall`（组内某块消后同组同层块无支撑则下落一层）→ 绑定组有"悬空下落"行为

## 4. 待确认清单（下一轮）
- [~] 门（Door）的 JSON 持久化位置与加载链：**用户暂不管（2025）**，不定稿
- [~] 双色剥壳细节：**已定（2025）**——剥壳后剩普通单色方块；floor 叠放 1249 处为双色实现
- [ ] 障碍墙 100-104 实际启用范围（ReloadWalls 只加载 CYCLE_PIPE）：**语料实锤全部墙 type=100**；其余类型的破坏/HP 规则仍无实现 [待玩法实现]
- [~] matchBlockOrder 是否硬性拦截：**用户暂不管（2025）**，现代码仅上报
- [~] hasCat 语义：**用户暂不管（2025）**
- [x] 限时 baseTime 的难度换算：**已核对**（§5.1）——A 表 70–220s、B/C 表 80–360s、V1/V2 换算已记录；拍板细节用户暂不管
- [~] hash 用途：**用户暂不管（2025）**

## 5. 参数区间核对（452 关语料统计证据，2025-06）

> 面向 AI 编关的数值区间核对：统计 `BlockColorMatch/Assets/Game/Configs/levels/lv_*.json`（452 关，含特殊关）与 Level/Level_B/Level_C 表的字段分布。完整区间与推荐基准已写入 level-rules.md §6；本节只保留仓库证据锚点与最新发现。

### 5.1 仓库证据锚点（本轮新核）
- LevelConfig.cs:181/184：BlockConfig.customWidth / customHeight → **普通 block 也支持自定义矩形尺寸**（不限于 12 标准形状）；语料在用 31 处：1×5×17、3×3×8、2×4×4、1×6×1、4×6×2。
- DynamicLevelTimeMgr.CalculateFinalLevelTime（V1/V2）＝限时最终换算入口；V1 clamp 到 [max(MinSec, base×MinPercent)取整十, base×MaxPercent取整十]，V2 按近期胜率在 base×ControlMin/Std/MaxPercent 间插值后五舍六入整十。
- Level.json（A 表）仅 199 行（ID 1–199）＝主线限时来源（70–220s）；Level_B/C 各 1040 行（80–360s）；452 关文件中 253 关无 A 表行 → 用 B/C 表。
- ManualBlockDispenserItemConfig（ManualBlockDispenserAbility.cs:10-68）：type（12 标准形状）或 useCustomSize + customWidth/customHeight（自定义矩形）二选一；IsSupportedType = IsCustomSize || Enum.IsDefined(BlockType, type) —— 源码未对产出尺寸设上限，判据是编关约束不是运行时限制。
- IceShaverAbility.cs:91-95：leftColor/rightColor/leftHp/rightHp/orientation ＝ 双向段各自独立颜色与 HP；语料样例 5+0（单向 5 段）、2+2（双向各 2 段）。

### 5.2 制造机产出尺寸 vs "<3×3" 判据（待拍板证据）
- 语料 82 台手动制造机、共 597 个产出项，尺寸分布：B_1X1 42 / B_1X2 127 / B_1X3 133 / B_1X4 10 / B_1X5 2 / B_2X2 58 / B_2X3 17 / B_7 28 / B_ARROW 83 / B_CROSS 19 / B_DELTA 29 / B_J 32 / **custom 3×3 17**。
- 若判据＝包围盒 ≤ 2×2：只余 B_1X1/B_1X2/B_2X2/B_ARROW（310/597 = 52%），**48% 现有配置被拒**（含 17 个 3×3）。
- 若判据＝总格数 < 9：12 标准形状全合（最大 6 格），仅 17 个 custom 3×3 被拒（97% 兼容）。
- ✅ **结论（用户拍板 = 判据 C，2025）**：包围盒不超 3×3 范围（B_1X1/1X2/1X3/2X2/2X3/7/ARROW/CROSS/DELTA/J 全部 4 旋转合规）**且总格数<9** → 语料保留 568/597（95.1%）；仅拒 B_1X4(10)/B_1X5(2)/custom 3×3(17) 共 29 项、涉及 20 关。B_1X4/B_1X5 全旋转下任一边=4/5>3 超限；3×3 整块=9 格。

### 5.3 其余高频结论（详见 level-rules.md §6）
- 墙：99 关 / 414 面，全部 type=100（CYCLE_PIPE）→ 与 §2.4「ReloadWalls 只加载 CYCLE_PIPE」一致；障碍墙 100–104 的其余类型语料 0 使用。
- 区域类尺寸：DecorationArea 常见 3×3/2×3/5×3/8×3（hp 中位 6）；LowerArea 常见 6×4/5×5/5×4；ShieldArea 常见 4×5/2×3/8×4。
- ColorTrain 38 关、carriages 3–23 节（中位 14），语料 endConsumeMode/consumeOrder 全为默认 0。
- iceArea / 冰面 cellType：各 2 关（同为 lv_183/483）。
- 双层 floor（双色）：1249 个 block；绑定组 1404 组（中位 2 枚）；bombSecs 88 枚（10–45s，中位 20）；stepLock 1223 处（1–29，中位 6）。


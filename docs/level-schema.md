# 关卡数据 Schema（编关 agent 内部数据结构）v0.1（草案）

> 用途：编关 agent 的统一数据结构——**生成器写、校验器查、求解器读**，且序列化后就是游戏仓库可加载的关卡 JSON。
> 依据：`docs/level-making-sop.md`（制作流程）+ `docs/level-rules.md`（规则）+ 前 210 关真实结构 + LevelConfig.cs 枚举。
> 状态：**v1.0 定稿（2025）——5 项决策点已拍板**：①载体=TS 接口式；②校验器=Python；③生成器先只用 12 标准形状（**可旋转四向**），自定义矩形求解器成熟后再开；④黑白允许但尽量少用；⑤无色区域禁配元素清单边做边补。
>
> **设计原则**：
> 1. **与 JSON 落盘格式一一对应**（schema 即 LevelConfig 序列化格式的类型化描述；默认值省略规则见 §0.4）。
> 2. **区分两类字段**：`持久化字段`（写进关卡文件，加载即得）与 `求解器运行态`（只在求解内存中计算，不落盘——如"炸弹剩余秒数""冰区剩余层数"是游戏运行时状态，关卡文件里只有初始值）。
> 3. **三层校验分层**：格式校验（字段/枚举/必填）→ 结构校验（占格/超棋盘/区域参数）→ 语义校验（颜色配平/可解性，属求解器阶段）。
> 4. 无关/暂不管字段（hasStar/withStar/hasCat/key/lock/withKey/matchBlockOrder/doors/hash）在 schema 中**标记 [skip]**，不展开、不生成。

---

## 0. 基础枚举（已核准，LevelConfig.cs / BoardLogicLayer.cs）

| 枚举 | 值 | 说明 |
|---|---|---|
| BlockColor | RED=0 … MAGENTA=9, BLACK=11, WHITE=12 | **用户拍板 2025：只有 12 种可玩色，无 NULL 玩法色**；10=已移除空洞。color 缺失/NULL/列表外一律不可用（生成校验 --strict 报错；语料回归容忍，仅警告）。无色方块例外：顶层 color 省略 + MatchLockAbility.lockedColor（须∈12色） |
| DDRotation | Rot0=0, Rot90=1, Rot180=2, Rot270=3 | 逆时针 |
| BlockMoveMode | BOTH=0, VER=1, HOR=2 | 箭头轴向 |
| CellType | Default=0, Ice=1 | 地形 |
| BoardLogicLayer | BoardBase=0, Layer1=10, Layer2=20, Layer3=30 | 40 归档 Layer3 |
| BlockType | B_1X1=0 … B_J=10, B_1X5=11（12 种，坐标见 level-rules §2） | 形状 |
| IceShaverOrientation | Horizontal=0, Vertical=1 | |
| IceShaverShrinkDirection | Unspecified=-1, Right=0, Left=1, Up=2, Down=3 | |
| ColorTrainCarriageType | Empty=0, Colored=1 | |
| ColorTrainCarriageDirection | Right=0, Up=1, Left=2, Down=3 | directionFromPrevious |
| ColorTrainEndConsumeMode | HeadOnly, TailOnly, Both（数值 0/1/2） | |
| ColorTrainConsumeOrder | HeadFirst, TailFirst | |
| 墙 type | 100 = CYCLE_PIPE（唯一生成） | 其余 0-12/101-104 不生成 |

## 0.4 JSON 最小化（序列化规则，生成器必须遵守）

- 默认值写盘省略：`type=0`、`rot=0`、`layer=20`、`color=NULL(-1)`、`quantity=1`、`moveMode=0`、`(0,0)` 的 gridPos、空 abilities。
- **加载时按默认补全**（IgnoreAndPopulate），故生成器省略=合法。
- ⚠️ 无色方块：顶层 color **必须省略**（写 -1 或不写），真实色在 MatchLockAbility.lockedColor。

---

## 1. Level 顶层结构

```ts
interface Level {
  cells: Cell[];            // 棋盘定义（必填，非空）
  blocks?: Block[];         // 棋子（可空）
  walls?: Wall[];           // 障碍墙 CYCLE_PIPE（可空）
  entities?: Entity[];      // 特殊元素实体（可空）
  tracks?: unknown /*[skip]*/;        // [skip] 不生成
  matchBlockOrder?: unknown /*[skip]*/; // [skip] 用户暂不管
  iceArea?: Record<string, number>; // 冰区组件→层数（有 cellType=Ice 时）
  hash?: unknown /*[skip]*/; // [skip] 不生成
}
```

## 2. Cell（地形格）

```ts
interface Cell {
  gridPos: { x: number; y: number }; // (0,0) 可省略
  color?: number;   // 默认 -1；非 -1 = 颜色筛选格（一格一色）
  cellType?: CellType; // CellType.Default 可省略；Ice=1 参与冰区连通组件
}
```
- 任意形状集合即棋盘边界；生成时保证矩形/凹形/L 形都可。
- 冰面：cells 中若干 cellType=1 的同连通组件 → iceArea 键=组件索引、值=层数。

## 3. Wall（障碍墙）

```ts
interface Wall {
  type: 100;            // 仅 CYCLE_PIPE
  gridPos: { x: number; y: number };
  rot?: DDRotation;     // 结构墙保留字段；CYCLE_PIPE 单格一般 0
  layer?: BoardLogicLayer; // Layer2 默认；只挡同层
}
```

## 4. Block（棋子）

```ts
interface Block {
  type?: BlockType;           // 默认 B_1X1=0；与 customWidth/Height 二选一
  customWidth?: number;       // 自定义矩形（替代 type，语料 1×5/3×3/2×4/4×6）
  customHeight?: number;
  rot?: DDRotation;           // 默认 Rot0
  color?: number;             // 用户拍板：12 可玩色之一，无 NULL 色；无色方块省略（lockedColor 存真实色）
  gridPos?: { x: number; y: number }; // (0,0) 省略
  layer?: BoardLogicLayer;    // 默认 Layer2；下方区域下层棋子 Layer1(10)
  moveMode?: BlockMoveMode;   // 默认 BOTH；箭头=VER/HOR
  abilities?: Ability[];      // 普通块=三件套 [Tail, Outline, Move]
  stepLock?: number;          // 步数锁 >0
  bombSecs?: number;          // 炸弹秒数 >0
  groupID?: number;           // 绑定/双色同格组
  floor?: number;             // 双色上层 =1（与同格同 groupID 的下层配对）
  // [skip] hasStar/withStar/hasCat/key/lock/withKey/keyLock
}
```
- **普通块标准 abilities 三件套**：`TailAbility / OutlineAbility / MoveAbility`（有即全写）。
- **无色方块**：color 省略 + abilities 追加 `MatchLockAbility{count:N, lockedColor:真实色}`。
- **双色**：同 gridPos、同 groupID 两枚 Block，下层无 floor、上层 floor:1。

## 5. Entity（特殊元素实体）

统一外壳：

```ts
interface Entity {
  entityName: "ManualBlockDispenser" | "IceShaver" | "DecorationArea"
            | "LowerArea" | "ShieldArea" | "ColorTrain";
  gridPos?: { x: number; y: number };
  layer?: BoardLogicLayer;
  abilities: Ability[];  // 各实体一个能力，fields=[{Key, Value}]
}
```

### 5.1 ManualBlockDispenserAbility（制造机）
```
持久化: rotation(0-3) / bodyColor=-1 / bodyFrozen=false / bodyStepLock=0 /
        bodyKeyLock / bodyBombSecs / bodyKey / bodyLock / bodyMatchLock /
        bodyWithKey=false / bodyWithStar=false / items[]
item: { type | (useCustomSize+customWidth/customHeight), color必填, quantity(=1),
        rotation, moveMode, stepLock/keyLock/bombSecs/key/lock/withKey/withStar,
        abilities[]（产出块可带 MatchLock 等）, IsCustomSize, IsSupportedType(序列化带出) }
约束: 判据 C（包围盒不超 3×3 且总格数<9）；队列非空；每项 quantity>0
```

### 5.2 IceShaverAbility（搓冰机）
```
seq / leftColor / rightColor / leftHp / rightHp(单向=0) / orientation(0横/1纵)
机身 = leftHp+rightHp+1 段；一端共享底部占位
```

### 5.3 DecorationAreaAbility（装修区域）
```
hp(≥0) / width(>0) / height(>0)；覆盖矩形；未解锁阻挡
```

### 5.4 LowerAreaAbility（下方区域）
```
width / height；区域 layer 常为 Layer1(10)；下层预设棋子 = 同区 layer=10 的 blocks
解锁 = 区域内占用清零瞬间；可与无色区域叠放（无色在上层，见规则文档 §2）
```

### 5.5 ShieldAreaAbility（无色区域）
```
width / height；透明禁消区；可被装修区域覆盖、可叠在下方区域上层
```

### 5.6 ColorTrainAbility（颜色火车）
```
endConsumeMode(0/1/2) / consumeOrder(0/1)
carriages[]: { type(0=Empty/1=Colored), directionFromPrevious(0右/1上/2左/3下),
               blocks[]: [{color, stepLock, keyLock, bombSecs, key, lock, withKey, withStar,
                           abilities, MatchLockCount, IsPackaged}],
               ActiveBlock(运行时), IsStacked }
```

### 5.7 能力序列化外壳（Unity 格式）
```json
{"abilityName": "XxxAbility", "fields": [{"Key": "hp", "Value": 6}, ...]}
```

## 6. 求解器运行态（不落盘，内存建模）—— 设计接口占位

> 这些状态由求解器从关卡初始数据推导，不属于 schema 持久化字段。列此以便后续求解器阶段细化：

| 运行态 | 来源字段 | 演化 |
|---|---|---|
| 炸弹剩余秒数 | block.bombSecs | 每步 -Δt；覆盖/冰冻暂停 |
| 冰区剩余层数 | iceArea 值 | 每消除事件 -1 |
| MatchLock 剩余次数 | MatchLockAbility.count | 每普通消除 +1 计数/解除 |
| stepLock 剩余 | block.stepLock | 每相关匹配 -1 |
| 装修区域 HP | hp | 每消除事件 -1 |
| 制造机队列 | items | 拖出队首 → 移出 |
| 火车车厢层 | carriages | 端部消耗/联动移除层 |
| 下方区域占用 | 区域内 blocks | 清零瞬间解锁 |

## 7. 校验器三层设计（对应待办 #3 第二步）

| 层 | 检查内容 | 依据 | 状态 |
|---|---|---|---|
| L1 格式 | 枚举合法 / 必填字段 / 默认值省略规则 / abilities 外壳格式 | schema 定义 | ✅ 已实现（agent/validator.py） |
| L2 结构 | 占格 ∈ cells / 同层无占格冲突 / 区域参数合法(hp≥0, w,h>0) / 制造机 IsConfigValid / key-lock 配对 / iceArea 键对应组件 | EditorMgr 5 个 Validate + IsConfigValid | ✅ 已实现（agent/validator.py） |
| L3 语义 | 颜色配平（含双色剥壳） / 每色可达配对 / 炸弹时限 / 区域解锁可达成 | 求解器阶段 | ⏳ 求解器阶段 |

> **回归验证（2025）**：合法性与格式校验器（Python）已对 **452 关语料全量回归**：**451/452 通过**。
> - 唯一失败 lv_822 = **关卡数据自身占格重叠**（blocks[15] B_7 rot1 与 blocks[18] B_2X2 重叠 (0,9)/(1,9)；B_7/旋转/碰撞展开已与仓库 Block.LocalGrids 逐行核对一致 → 数据异常，非校验器误报）。孤立案例，记录为已知例外。
> - **重要语义修正（学习自回归）**：**NULL(-1) 色普通块合法**（语料 922 个），两枚同为 NULL 色的块可互为配对消除（GamePlayMgr 同色判定 LogicColor==LogicColor，NULL==NULL 成立）；无色方块仅指带 MatchLockAbility 的块。
> - 实现：agent/base.py（枚举/形状/旋转/默认值）+ agent/validator.py（LevelValidator，L1+L2）+ agent/cli.py（批量 CLI）。游戏仓库仍只读。

---

## 决策点（已全部拍板，2025）

1. **✅ schema 载体** = TS 接口式（可直接转 JSON Schema 驱动校验器）。
2. **✅ 校验器语言** = Python（沿用语料脚本生态，可立即对 452 关做回归）。
3. **✅ 生成器第一阶段只用 12 标准形状，且形状可四向旋转**；customWidth/Height 自定义矩形求解器成熟后再开（schema 已支持，生成器先不用）。
4. **✅ 黑白（11/12）允许进入编关色池，但尽量少用**（默认取前 5-8 色，黑白低频）。
5. **✅ 无色区域禁配元素清单边做边补**（当前已知：搓冰机；求解器建模时发现新冲突再补）。
6. **✅ 障碍墙 100-104 破坏链** = 暂不生成（维持现状）。
7. **✅（2025）关卡范围** = 只看编号 ≤250（实际 223 关，1-222+224）；250 之后不看。
8. **✅（2025）颜色** = 仅 12 可玩色，无 NULL；列表外不可用。
9. **✅（2025）求解器** = 完整状态搜索；全部算子进状态（拖拽移动/格位结算消除/制造机拖出/搓冰机消耗/火车端部消耗/区域解锁/双色剥壳/绑定体移动/炸弹倒计时含暂停/stepLock 解锁/无色区域边界）。
10. **✅（2025）棋盘规模** = ≥50 格、无上限、须连贯完整；普通关棋子 ≥15 对(30枚)，难关/超难关 ≥18 对(36枚)。
11. **✅（2025）求解器算法** = 分阶段：先可解性 BFS（无启发式、状态规范化去重），再最少步数 A*（对称剔除/启发式）。
12. **✅（2025）求解目标** = 可解性 + 最少步数都要（难度模型 = 最少步数 + 限时换算）。
13. **✅（2025）算子落地顺序** = ①基础对消(含双色剥壳/无色/绑定/箭头) → ②制造机 → ③区域(装修/下方/无色) → ④火车 → ⑤炸弹/stepLock。
14. **✅（2025）求解器入口** = 先跑现有 223 关做正确性/性能基线 + 最少步数分布，再接生成器。

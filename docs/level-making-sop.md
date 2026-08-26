# 关卡制作标准化流程（SOP）v1.0

> 用途：**AI 编关 agent 的制作操作手册** —— 每个元素/棋子/地形的最基础制作方法（怎么写在 JSON 里、放哪、哪些会被编辑器拒绝）。
> 依据：docs/level-rules.md（规则事实源）+ EditorMgr.cs 校验 + 前 210 关真实语料学习（lv_1..210_A.json）。
> 状态：**v1.1——用户审核回复已应用**：①冰冻以现有关卡为准；②下方区域下层棋子=layer10 块（确认）；③新增"下方×无色"叠放规则（无色在上层，语料无实例）。
> 粒度约定（用户拍板）：每卡只写做**最基础制作**所需的 5 个区——配置字段 / JSON 样例 / 占格与放置 / 校验 / 组合与冲突。求解器建模与难度参数不在此（属下一阶段 agent 设计，另行讨论）。

---

## 0. 三类落点速查

| 类别 | JSON 落点 | 卡号 |
|---|---|---|
| 棋子 | `blocks[]` | 1-7 |
| 元素 | `entities[]` | 8-13 |
| 地形 | `cells[]`/walls/iceArea | 14-17 |
| 跨对象属性 | - | 18-20 |

> 不建卡（用户暂不管/无持久化）：门 Door、钥匙、星·猫、matchBlockOrder、hash、自动制造机、时间方块。

---

# A. 棋子卡（blocks[]）

## 1. 棋子 普通棋子（单色 + 多格形状）

- **配置字段**（最小）：`type`(int，12 标准形状，0=B_1X1) · `color`(int 逻辑色，必填) · `gridPos` · `layer`(默认20)。可选：`rot`(0-3) · `customWidth/customHeight`(自定义矩形，替代 type) · `moveMode` · `abilities`。
- **JSON 样例**（最小，B_1X2 竖放红色）：
  ```json
  {"type": 1, "color": 7, "gridPos": {"x": 3, "y": 8}, "layer": 20,
   "abilities": [{"abilityName": "TailAbility"}, {"abilityName": "OutlineAbility"}, {"abilityName": "MoveAbility"}]}
  ```
  （单格 B_1X1 + rot=0 时 type/rot 可省略；abilities 三件套为普通块标准配置）
- **占格与放置**：占 type 对应 LocalGrids 全体格（含不可选中格）；目标格必须 ∈ cells；不能与**同层**其它块/墙/实体重叠。
- **校验**：EditorMgr 保存——同层占格冲突 → 拒绝保存。超棋盘（目标格不在 cells）→ 拒绝。
- **组合与冲突**：可叠加无色/双色/炸弹/stepLock/箭头/绑定（见各卡）；多格块整体移动与消除。

## 2. 棋子 无色方块（MatchLock）

- **配置字段**：`color` **省略(NULL=-1)**（顶层不写真实色）· `abilities` 加 `MatchLockAbility`：`count`(N 次解除) + `lockedColor`(真实色)。
- **JSON 样例**（lv_39 实测，无色+锁定 6 次解出红色）：
  ```json
  {"type": 7, "rot": 3, "gridPos": {"x": 2, "y": 0}, "layer": 20,
   "abilities": [{"abilityName": "TailAbility"}, {"abilityName": "OutlineAbility"}, {"abilityName": "MoveAbility"},
                 {"abilityName": "MatchLockAbility", "fields": [{"Key": "count", "Value": 6}, {"Key": "lockedColor", "Value": 0}]}]}
  ```
- **占格与放置**：同普通棋子；包装期间可移动、免疫消除。
- **校验**：无独立校验；按普通块规则（同层不冲突、在棋盘内）。
- **组合与冲突**：与双色/炸弹/stepLock 可叠加（lv_120 有无色+炸弹）；双层时顶层负责 MatchLock。
- **⚠️ 与"NULL 色普通块"区分**（回归学习 2025）：语料有大量 color=NULL 无 MatchLock 的块（922 个）——这类是**灰色普通块**，两枚 NULL 色可互为配对消除（同色判定 NULL==NULL），**不是无色方块**。无色方块特指带 MatchLockAbility 的块。

## 3. 棋子 双色方块（floor 叠放）

- **配置字段**：**同一格两个 block**：底层普通块（外层色 A，无 floor）+ 上层 `floor:1` 块（内层色 B，同 gridPos、同 `groupID`）。
- **JSON 样例**（lv_102 实测：外层灰8 + 内层红1）：
  ```json
  {"type": 4, "color": 8, "gridPos": {"x": 0, "y": 5}, "groupID": 1, "layer": 20, "abilities": [{"abilityName": "TailAbility"}, {"abilityName": "OutlineAbility"}, {"abilityName": "MoveAbility"}]}
  {"type": 4, "color": 1, "gridPos": {"x": 0, "y": 5}, "groupID": 1, "floor": 1, "layer": 20, "abilities": [{"abilityName": "TailAbility"}, {"abilityName": "OutlineAbility"}, {"abilityName": "MoveAbility"}]}
  ```
- **占格与放置**：两枚同格叠放（floor=1 为上层）；整体视为一个双色棋子，同层主占格。
- **校验**：同普通块；两枚必须同格同 groupID，floor 只在上层。
- **组合与冲突**：可叠加无色（底层 color 可 NULL，lv_102 组 4/5/6/8/9）；剥壳后内层变普通单色块。

## 4. 棋子 冰冻棋子（区域制冰，仓库现状）

- **配置字段**：仓库无"每枚独立计数"字段；冰冻 = **区域制**：cells 加 `cellType:1`(冰面格) + 顶层 `iceArea`(组件索引→层数)。
- **JSON 样例**（lv_183 实测，1 个冰区 3 层）：
  ```json
  "cells": [ {"gridPos": {"x": 3, "y": 4}, "color": -1, "cellType": 1} ],
  "iceArea": {"0": 3}
  ```
- **占格与放置**：冰区覆盖格上的棋子被冰冻；全格覆盖才锁定。
- **校验**：iceArea 键须为 ice cells 连通组件索引（工具落地时校验）。
- **⚠️ 组合与冲突**：**用户拍板（2025）：以现有关卡实际编辑文件为准**——人看到的（编辑器里可能显示为每枚独立冰块）与实际编关后的关卡文件不一致；生成既以仓库区域制（iceArea + CellType.Ice）为准。规则文档的"每枚独立计数 N + 颜色可见"暂不生成，待游戏实现后另议。

## 5. 棋子 箭头（moveMode 轴向）

- **配置字段**：块顶层 `moveMode`：0=BOTH(默认) / 1=VER(上下) / 2=HOR(左右)。
- **JSON 样例**（lv_51 实测：纵向箭头 B_1X2）：
  ```json
  {"type": 1, "gridPos": {"x": 3, "y": 3}, "moveMode": 1, "layer": 20,
   "abilities": [{"abilityName": "TailAbility"}, {"abilityName": "OutlineAbility"}, {"abilityName": "MoveAbility"}]}
  ```
- **占格与放置**：同普通棋子；箭头只限制拖拽轴向，不限制消除。
- **校验**：无独立校验。
- **组合与冲突**：仅可移动棋子可带；绑定×箭头叠加**编关阶段不做**（用户拍板）。

## 6. 棋子 定时炸弹（bombSecs）

- **配置字段**：块顶层 `bombSecs`(int 秒)。
- **JSON 样例**（lv_120 实测，20 秒炸弹+无色）：
  ```json
  {"type": 4, "gridPos": {"x": 6, "y": 2}, "bombSecs": 20, "layer": 20,
   "abilities": [{"abilityName": "TailAbility"}, {"abilityName": "OutlineAbility"}, {"abilityName": "MoveAbility"},
                 {"abilityName": "MatchLockAbility", "fields": [{"Key": "count", "Value": 3}, {"Key": "lockedColor", "Value": 0}]}]}
  ```
- **占格与放置**：同普通棋子；多格块整体统一计时。
- **校验**：无独立校验（bombSecs>0）。
- **组合与冲突**：可与无色/双色/stepLock 叠加；被覆盖/冰冻期间倒计时暂停。

## 7. 棋子 绑定组（groupID）

- **配置字段**：块顶层 `groupID`(int)，同组块共享同一值；相邻才可绑。
- **JSON 样例**（lv_183 实测，同格双色组也是绑定）：
  ```json
  {"type": 1, "rot": 1, "color": 2, "gridPos": {"x": 3, "y": 3}, "moveMode": 2, "groupID": 36403, "layer": 20, "abilities": ["TailAbility","OutlineAbility","MoveAbility"]}
  ```
- **占格与放置**：成员相邻（挨着）；整体按普通拖拽同步移动。
- **校验**：语料组大小多为 2；无强制校验（工具侧建议校验相邻性）。
- **组合与冲突**：任意形状可绑；绑定×箭头叠加不做（用户拍板）。

---

# B. 元素卡（entities[]）

> 实体统一结构：`{"entityName": ..., "gridPos": ..., "layer": ..., "abilities": [ {abilityName, fields[{Key,Value}]} ]}`

## 8. 元素 手动制造机（ManualBlockDispenser）

- **配置字段**：`gridPos/layer` + `items`[]，每项：`type` 或 `useCustomSize+customWidth/customHeight`（**判据 C：包围盒不超3×3且总格数<9**）· `color` 必填 · `quantity`(语料全=1) · 可选 abilities（产出块带无色等）。
- **JSON 样例**（lv_35 节选，2 项产出：B_J 红 + B_2X2 青）：
  ```json
  {"entityName": "ManualBlockDispenser", "gridPos": {"x": 1, "y": 9}, "layer": 20,
   "abilities": [{"abilityName": "ManualBlockDispenserAbility", "fields": [
      {"Key": "rotation", "Value": 3},
      {"Key": "items", "Value": [
         {"type": 10, "color": 0, "quantity": 1, "useCustomSize": false, "moveMode": 0},
         {"type": 4,  "color": 7, "quantity": 1, "useCustomSize": false, "moveMode": 0} ]} ]} ]}
  ```
- **占格与放置**：机身 LocalBodyGrids 占格（默认 2×3；rotation=1/3 时 3×2）阻挡放置；不可移动。
- **校验**：IsConfigValid——队列非空 / 每项 quantity>0 / 类型合法(IsSupportedType)；机身占格超棋盘、与同层块/墙/实体冲突 → 拒绝。
- **组合与冲突**：可放装修区域下（区域为覆盖层不判冲突）；**产出尺寸受判据 C 限制**；拖出=1 步。

## 9. 元素 搓冰机（IceShaver）

- **配置字段**：IceShaverAbility：`seq`(排序) · `leftColor/rightColor`(两端颜色) · `leftHp/rightHp`(段 HP，单向一侧为 0) · `orientation`(0=横/1=纵)。
- **JSON 样例**（lv_39 实测，纵向单向 3 段红）：
  ```json
  {"entityName": "IceShaver", "gridPos": {"x": 0, "y": 3}, "layer": 20,
   "abilities": [{"abilityName": "IceShaverAbility", "fields": [
      {"Key": "seq", "Value": 0}, {"Key": "leftColor", "Value": 1}, {"Key": "rightColor", "Value": 9},
      {"Key": "leftHp", "Value": 3}, {"Key": "rightHp", "Value": 0}, {"Key": "orientation", "Value": 1} ]} ]}
  ```
- **占格与放置**（源码实测）：GridPos=**中心/底部占位**；leftHp 段向 **-方向**延伸（水平向左/纵向向下），rightHp 段向 **+方向**延伸（水平向右/纵向向上）；TotalHp=0 时占位消失。orientation 0=水平/1=纵向。不可移动；占用阻挡。
- **校验**：同实体通用（占格冲突/超棋盘 → 拒绝）。
- **组合与冲突**：不可配置在无色区域内（编关约束）。

## 10. 元素 装修区域（DecorationArea）

- **配置字段**：DecorationAreaAbility：`hp`(≥0) · `width/height`(>0)。
- **JSON 样例**（lv_20 实测，5×3 盖 4 HP）：
  ```json
  {"entityName": "DecorationArea", "gridPos": {"x": 1, "y": 5}, "layer": 20,
   "abilities": [{"abilityName": "DecorationAreaAbility", "fields": [
      {"Key": "hp", "Value": 4}, {"Key": "width", "Value": 5}, {"Key": "height", "Value": 3} ]} ]}
  ```
- **占格与放置**：覆盖 width×height 全格；覆盖格阻挡移动/放置；未解锁=锁棋盘。
- **校验**：ValidateDecorationAreas——缺 Ability / hp<0 / width≤0 / height≤0 / 覆盖棋盘外格 → 拒绝保存。
- **组合与冲突**：门下可放棋子；可盖无色区域上方（顶层）；与下方区域**不可**叠放。

## 11. 元素 下方区域（LowerArea）

- **配置字段**：LowerAreaAbility：`width/height`；**下层预设棋子 = layer=10 的普通 blocks**（与区域同层）。
- **JSON 样例**（lv_65 实测，4×8 区域）：
  ```json
  {"entityName": "LowerArea", "gridPos": {"x": 1, "y": 1}, "layer": 10,
   "abilities": [{"abilityName": "LowerAreaAbility", "fields": [{"Key": "width", "Value": 4}, {"Key": "height", "Value": 8} ]} ]}
  { "type": 1, "rot": 1, "color": 7, "gridPos": {"x": 1, "y": 8}, "layer": 10, "abilities": ["TailAbility","OutlineAbility","MoveAbility"] }
  ```
- **占格与放置**：区域层=10；下层块放层 10 同格；解锁=区域内占用清零的瞬间。
- **校验**：同实体通用；下层块须在区域内且层=10。
- **组合与冲突**：下层可放普通+特殊元素；与无色区域叠放规则见卡 20（用户拍板 2025：无色在下层区域上层，语料无实例属新扩展规则）。

## 12. 元素 无色区域（ShieldArea）

- **配置字段**：ShieldAreaAbility：`width/height`。
- **JSON 样例**（lv_100 实测，5×5）：
  ```json
  {"entityName": "ShieldArea", "gridPos": {"x": 0, "y": 5}, "layer": 20,
   "abilities": [{"abilityName": "ShieldAreaAbility", "fields": [{"Key": "width", "Value": 5}, {"Key": "height", "Value": 5} ]} ]}
  ```
- **占格与放置**：透明矩形，可进出移动；禁消除不禁移动。
- **校验**：同实体通用。
- **组合与冲突**：搓冰机不可配置在区内；装修区域可盖上方；**与下方区域叠放（用户拍板 2025）**：无色区域可叠在下方区域上层，解锁联动见卡 20。

## 13. 元素 颜色火车（ColorTrain）

- **配置字段**：ColorTrainAbility：`carriages`[]（每节 `type` 0=Empty/1=Colored · `directionFromPrevious` 0=右/1=上/2=左/3=下 · `blocks`[] 每层 {color, stepLock, keyLock, bombSecs, ...}）· `endConsumeMode`(0=HeadOnly/1=TailOnly/2=Both) · `consumeOrder`(0=HeadFirst/1=TailFirst)。
- **JSON 样例**（lv_150 实测节选，2 节：红+青）：
  ```json
  {"entityName": "ColorTrain", "gridPos": {"x": 2, "y": 5}, "layer": 20,
   "abilities": [{"abilityName": "ColorTrainAbility", "fields": [
      {"Key": "endConsumeMode", "Value": 0}, {"Key": "consumeOrder", "Value": 0},
      {"Key": "carriages", "Value": [
        {"type": 1, "directionFromPrevious": 0, "blocks": [{"color": 0}]},
        {"type": 1, "directionFromPrevious": 0, "blocks": [{"color": 7}]} ]} ]} ]}
  ```
- **占格与放置**：车厢链按 directionFromPrevious 折线占格；玩家不可拖拽。
- **校验**：IsPlacementValid——有 Ability / 车厢位置不超棋盘 / 与同层块墙实体不冲突 / 不与门冲突。
- **组合与冲突**：端部消耗（HeadOnly/TailOnly/Both）；普通对消最多 2 次同色联动。

---

# C. 地形卡

## 14. 地形 基础棋盘格（cells）

- **配置字段**：`gridPos` · `color`(默认 -1)。任意形状集合（非矩形可凹可 L）。
- **JSON 样例**（lv_1 实测）：
  ```json
  "cells": [ {"gridPos": {"x": 0, "y": 8}, "color": -1}, {"gridPos": {"x": 0, "y": 7}, "color": -1} ]
  ```
- **占格与放置**：定义棋盘边界；格不在 allCells 即不可放置；不需要结构墙围边。
- **校验**：所有块/实体/墙的占格必须 ∈ cells。
- **组合与冲突**：可混 cellType/color 字段（见 15/16）。

## 15. 地形 颜色筛选格（cell.color）

- **配置字段**：cells 条目 `color` 设为具体色值（非 -1）。
- **JSON 样例**（lv_202 实测）：
  ```json
  "cells": [ {"gridPos": {"x": 3, "y": 6}, "color": 7}, {"gridPos": {"x": 5, "y": 5}, "color": 1} ]
  ```
- **占格与放置**：异色棋子不能进入/穿过/停放；同色可自由。
- **校验**：无色未解包棋子不能通过任何筛色格；绑定成员每个颜色都要匹配。
- **组合与冲突**：一格一色；低频使用（前 210 关边缘出现）。

## 16. 地形 冰面格子（cellType=Ice + iceArea）

- **配置字段**：cells 条目 `cellType:1` + 顶层 `iceArea: {组件索引: 层数}`。
- **JSON 样例**（lv_183 实测）：
  ```json
  "cells": [ {"gridPos": {"x": 3, "y": 4}, "color": -1, "cellType": 1} ],
  "iceArea": {"0": 3}
  ```
- **占格与放置**：冰格组成连通组件；iceArea 的键=组件索引、值=剩余层数。
- **校验**：iceArea 键须为实际 ice cell 组件索引（工具校验；编辑器侧无显式校验）。
- **组合与冲突**：与冰冻棋子卡(4)同一机制，区域制。

## 17. 地形 墙（CYCLE_PIPE 障碍）

- **配置字段**：`type`(100=CYCLE_PIPE) · `gridPos` · `layer`(同层阻挡)。
- **JSON 样例**（lv_19 实测格式）：
  ```json
  "walls": [ {"type": 100, "gridPos": {"x": 2, "y": 5}, "layer": 20} ]
  ```
- **占格与放置**：单格、不可通行、固定；只挡同一玩法层。
- **校验**：占格冲突/超棋盘拒绝；**只支持 type=100**，其余 0-12/101-104 不进入编关规则。
- **组合与冲突**：结构墙不生成；可破坏墙不生成（玩法未实现）。

---

# D. 跨对象属性卡

## 18. 属性 stepLock（步数锁）

- **配置字段**：块顶层 `stepLock`(int>0)；>0 时不可匹配/不可放置/拖出受限；每相关匹配事件 -1。
- **JSON 样例**（lv_25 实测：2 步锁红 B_1X3）：
  ```json
  {"type": 2, "rot": 1, "color": 7, "gridPos": {"x": 1, "y": 7}, "stepLock": 2, "layer": 20, "abilities": ["TailAbility","OutlineAbility","MoveAbility"]}
  ```

## 19. 属性 逻辑层 Layer

- **枚举**：BoardBase=0 / Layer1=10 / Layer2=20(默认) / Layer3=30；40 归 30。
- **规则**：下层不挡上层；同层才能配对消除；区域约束只作用于不高于自身的层。
- **制作要点**：普通块默认 layer=20；下方区域下层棋子 layer=10；区域自身层即其覆盖约束层。

## 20. 叠加规则汇总（编关约束）

| 组合 | 允许 | 依据 |
|---|---|---|
| 无色方块 + 双色 / 炸弹 / stepLock | ✅ | 语料实证（lv_102/120） |
| 装修区域盖 无色区域上方 | ✅ | 用户拍板（顶层叠加） |
| 装修区域 + 门下棋子 | ✅ | 语料实证（lv_39 等） |
| 下方区域 + 无色区域 | ✅ 无色在下方区域上层 | **用户拍板 2025（新扩展）**：无色区域叠在下方区域上层；无色区域内无棋子 → 解开下方区域，之后按无色区域规则走。⚠️ 语料无实例（452 关无重叠），编关时按此规则生成并做可解性验证 |
| 绑定组内成员带箭头 | ❌ | 用户拍板（编关阶段不做） |
| 搓冰机在无色区域内 | ❌ | 规则文档（语义冲突） |
| 冰块 每枚独立计数玩法 | ⚠️ 待实现 | 仓库为区域制（见卡 4） |

---

## 附：JSON 最小化速查
`DefaultValueHandling.IgnoreAndPopulate`：默认值写盘时省略——type=0、rot=0、layer=20、color=-1、quantity=1、moveMode=0、gridPos=(0,0) 均可省略；abilities 有即全写。

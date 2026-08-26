# 可解性求解器设计（solver-design）v0.1（草案）

> 状态：**阶段①已实现（2025）**——`agent/solver.py` 可解性 BFS 跑通（单色对消/双色剥壳/无色包装/绑定/箭头/墙/筛色格），§8 已回源码锁定；223 关基线见 §9（10/33 建模关可解、0 误判，23 关超时待阶段 B 剪枝）。
> 数据依据：`docs/level-schema.md`（v1.0）、`docs/level-rules.md`（§1 移动/消除、§2 元素、§2.5 机制、§5.5 规模约束）。
> 代码落点：`agent/solver.py`（阶段①起建，复用 `agent/base.py` 的枚举/形状/旋转辅助）。

## 0. 已拍板决策（2025）
- **算法**：分阶段——阶段 A = 可解性 BFS（无启发式，状态规范化去重）；阶段 B = 最少步数 A*（对称剔除/启发式）。
- **目标**：可解性 + 最少步数都要（难度模型 = 最少步数 + 限时换算）。
- **算子落地顺序**：①基础对消(含双色剥壳/无色/绑定/箭头) → ②制造机 → ③区域(装修/下方/无色) → ④火车 → ⑤炸弹/stepLock。
- **入口**：先跑现有 223 关做正确性/性能基线 + 最少步数分布，再接生成器。
- **范围**：≤250 关；12 可玩色无 NULL；棋盘 ≥50 格连贯完整；普通关 ≥15 对、难关 ≥18 对。

## 1. 求解语义定义
- **成功**：场上不存在任何待消除棋子实体（普通块、双色内外层、无色包装、绑定成员、制造机外已产出块）。区域/火车在后续阶段补入「区域解锁 + 火车清空」的成功条件。
- **失败**：炸弹爆炸（阶段⑤）；无合法后继且未成功 = 不可解/死锁。
- **步数口径**：一次「宏动作」= 1 步；其中制造机拖出 1 块也 = 1 步（用户拍板）。
- **全局限时**：只参与难度换算，不进入可解性判定（对「有没有解」无约束）；炸弹秒数是硬失败约束，非全局限时。

## 2. 状态模型（State，immutable + 可哈希 + 可规范化）
阶段①最小状态如下（②–⑤逐步扩展，见 §6）。

- `cells: frozenset[(x,y)]` —— 棋盘格集合（含墙占格与空格的并集；墙/障碍单列）。
- `cell_color: dict[(x,y), int]` —— 颜色筛选格（cell.color 非 -1 者）。
- `walls: frozenset[(x,y,int layer)]` —— CYCLE_PIPE 单格障碍（同层阻挡）。
- `pieces: tuple[Block]` —— 逻辑棋子（统一抽象，见下；每块自带 `wrapped/countdown`，无色按**每枚独立计数**，无需全局消除计数字段）。规范化排序后作哈希键。

### 2.1 逻辑棋子 Piece（阶段①归一化）
把「JSON block → 逻辑棋子」折叠为 4 类，避免 floor/groupID 双关混淆：

| 逻辑类 | JSON 对应 | 状态字段 | 消除/演化 |
|---|---|---|---|
| `SINGLE` | 普通块（无 floor 配对） | color, poses(世界格), layer, moveMode, groupID? | 同色四邻相邻 → 整实体消除 |
| `DOUBLE` | 同 gridPos + 同 groupID 两枚 block：**floor0=外壳(可匹配色A) + floor1=内核(隐藏色B)** | outer(floor0), inner(floor1), poses, layer | 视为一体移动；floor0 与同色 A 对消 → 组内落层把 floor1 内核落回 floor0（=剥壳，+1 事件） |
| `WRAPPED` | 带 MatchLockAbility 的块（`lockedColor`=真实色，常=block color） | lockedColor, count_down, poses, layer | 免疫消除（锁 `Matchable`+`PackagedAppearance`，**不锁 `Movable`**）；每**非自身** BLOCK_MATCH 事件 count_down-1 → 0 时变 `SINGLE(lockedColor)` |
| `BOUND(n)` | groupID＞0（异格 N≥2） | 成员列表（各自 color） | 与同 groupID 的 floor 叠层一起整体拖拽；成员各自独立消除，剩余成员仍同簇 |

- `poses` 由 `block_world_poses()`（agent/base.py）展开；形状/旋转/自定义矩形均归一为世界格集合。
- 绑定与双色都吃 `groupID`，靠「同格 floor 配对 vs 异格绑定」区分；阶段①生成时两者不叠加（用户拍板：绑定×箭头先不做）。
- 箭头 = `moveMode`（BOTH/VER/HOR），只进可达性，不改消除规则。
- stepLock/bombSecs 阶段⑤前不读（阶段①语料中带这些的关标记为「未建模」）。

### 2.2 规范化与去重
- 排序键：棋子按（类型, 排序后的 poses, color/outer+inner, layer）字典序；cells/walls/cell_color 按坐标排序。
- 哈希：规范化 tuple 的 hash（碰撞可接受，后续用位图压缩棋盘加速）。
- 对称剔除（阶段 B 再上，阶段 A 先不做）：对状态做 8 变换（4 旋转 × 2 手性）取最小规范化表示。

## 3. 宏动作抽象（拖拽离散化——核心）
- **实际语义**：拖拽是逐帧（≤0.5 格/帧）连续推进，每次成功更新到当前格位即 `ResolveImmediateDragInteractions` 结算一次；松手再复查一次。结算优先级 Door→IceShaver→ColorTrain→普通色块，同次最多消费 1 个目标。
- **离散化**：把「一次玩家操作」定义为**宏动作** = (可移动实体 E, 目标锚点 g)：
  1. 沿可达路径把 E 从当前锚点拖到 g（连续合法位移）；
  2. 在终点 g 执行一次结算（阶段①只有普通色块对消 + 双色剥壳；Door/冰铲/火车后置）。
- **完备性论证**：连续拖拽的轨迹 = 一串「格位 i → 结算」的序列；每个中间格位都可作为玩家主动松手的终点（无强制移动），故该轨迹在宏动作图上等价于「宏动作序列」——每个中间结算点即一次独立宏动作的终点。故只要宏动作枚举覆盖「拖到任一可达格 + 结算一次」，BFS 即完备。
- **宏动作枚举**：对每个可移动实体 E，对其每个可达目标锚点 g，产生一个后继。

### 3.1 可达性（拖拽放置约束，阶段①）
给定实体 E（占世界格集合 S，锚点 = S 的 min(x,y) 或 gridPos），其可放锚点 g 满足「E 平移到 g 后全部格落在合法格」，且 g 与当前锚点之间存在「锚点级连续路径」（每步曼哈顿 1 格，且平移后仍全部合法）：

- 落点 ∈ `cells`；不落在 `walls`（同层）与其它 `pieces`（同层、且非「低层在下/floor 同格配对」）占格。
- **颜色筛选**：`cell_color` 有值时，E 每个成员色须与之同色；`WRAPPED` 未解除时不能通过任何筛选色格。
- **轴向**：`moveMode=VER` 只允许纵轴位移、`HOR` 只横轴；`BOUND` 全体成员约束同时成立。
- 计算方式：对「不可进入格」构图，从当前 S 做 cluster 平移 BFS（阶段①实体格数 ≤ 绑定组规模，代价可控）；墙/静态障碍图缓存复用。

### 3.2 结算（Resolve，阶段①子集）
在终点 g 对 E 做四邻判定，优先级内只有「普通色块」生效（Door/冰铲/火车后置）：
- **普通对消**：E 的任一未保护格与静止块 W 的任一未保护格四邻相邻，且 逻辑色相等、同 `layer`、双方可移动可匹配、无 stepLock/floor(双色内层不直接对消)/免疫/全冰 → 两实体成对消除（`matches_total += 1`，含中间的 `DOUBLE` 剥壳也 +1）。
- **DOUBLE**：外层色 A 与某 A 块相邻对消时，A 块消除、`DOUBLE` 外层剥掉 → 原地生成 `SINGLE(inner)`（不是两个同消）。
- **WRAPPED**：不参与对消；每次普通消除事件令其 `count_down -= 1`，到 0 即 `SINGLE(lockedColor)`。
- **BOUND**：成员各自独立，某成员满足相邻同类即单独消除，其余成员留原地继续绑定。
- 同一次结算至多消费 1 个目标；消费后**不再连续连锁**（下一宏动作再结算）。

## 4. 后继生成 + 终止（阶段①）
- 对每态枚举全部宏动作 → 应用移动 + 结算 → 得到后继态；去重入队（BFS 分层，记录层号=步数）。
- 成功 = `pieces` 为空；失败 = 空队列且未成功。
- 输出：可解性 bool + 达到成功的最少宏动作步数（阶段 A 顺带产出，阶段 B 再用 A* 精算）。
- **预算**：`--max-steps` 层数上限、`--max-states` 展开态上限、超时阈值——跑 223 关时按关卡类型给档位（见 §7）。

## 5. 数据来源与载入
- 载入 `agent/solver.py` 用 `LevelValidator` 已读的 dict，直接实例化 State；非法关（L1/L2 error）由校验器先拦。
- 阶段①只接受「基础对消可覆盖」的关：无 制造机/装修/下方/无色区域/火车/冰块/炸弹/stepLock（带这些的在 223 基线里标「未建模」）。纯对消子集先跑通。

## 6. 分阶段实施计划（算子落地顺序）
| 阶段 | 进状态的算子 | 交付 | 验证 |
|---|---|---|---|
| ① 基础对消 | 拖拽移动/格位结算/双色剥壳/无色包装/绑定移动/箭头轴 | 可解性 DFS（visited 去重 + 单调剪枝） | ✅ 语义正确（10/33 可解、0 误判）；稠密关 23 个超时 → 阶段 B 剪枝 |
| ② 制造机 | 拖出队首（=1 步）、机身占格、队列 HP、产出块带 MatchLock/stepLock 等 | BFS 扩展 | 82 台制造机关加入回归 |
| ③ 区域 | 装修区域覆盖阻挡+事件扣 HP 解锁、下方区域清空解锁+露出下层、无色区域禁消边界、冰区(iceArea)整片 -1 | BFS 扩展 | 273+116+59+2 关加入 |
| ④ 火车 | 端部消耗、普通对消最多 2 次同色联动、空端清理/锚点重设 | BFS 扩展 | 38 关加入 |
| ⑤ 炸弹/stepLock | 炸弹倒计时（含被覆盖/冰冻暂停、归零失败）、stepLock 每事件 -1 解锁 | BFS 含失败分支 | 88 炸弹 + 1223 stepLock 关加入 |
| 后续 | — | 最少步数 A*（对称剔除/启发式）→ 生成器接入 | 全 223 关最少步数分布 |

> 每完成一个阶段：重跑 223 关，统计「该阶段可覆盖子集」的可解性 + 步数分布 + 单关耗时，作为下一阶段回归基线。

## 9. 阶段①基线结果（2025，`python3 solver.py <levels> --max-num=250 --timeout=6`）

- **可解性搜索策略**：阶段①用 **DFS（LIFO + visited）**，比 FIFO BFS 更快找到任一解；DFS 返回的 `steps` 是「某条解的长度（上界）」**非最少步数**——最少步数在阶段 B 用 BFS/A* 精算。
- 总计 223 关（阶段②制造机接入后）：**可解 11 / 不可解 0 / 未建模 188 / 超时 24**（`agent/baseline_output.txt`，`--timeout=6`）。lv_6 因 max_depth 200→300 由超时转可解；lv_35/lv_173 为制造机-only 关，现入建模但超时（lv_35 含 17 个 custom 3×3 产出，9 格连块拖出/匹配搜索大）。
- 阶段③(盾区/装修区) + ⑤stepLock 接入后：**可解 14 / 不可解 5 / 未建模 104 / 超时 100**。
- 阶段③ LowerArea 接入后：**可解 14 / 不可解 5 / 未建模 72 / 超时 132**。LowerArea 32 关入建模但全部超时（下区域清空+层抬升+稠密叠加）；`不可解 5` 仍同前（NULL 历史）。
- 阶段④搓冰机(IceShaver) 接入后：**可解 14 / 不可解 7 / 未建模 30 / 超时 172**。IceShaver 42 关入建模（被动-2/相撞-1 语义已合成验证）；`不可解` 增 lv_17(稠密无首消) / lv_153。
- **修正**：lv_153 是「全关 layer=10 但无 LowerArea」被误当隐藏块 → 改 `_is_hidden` 为「layer=10 且落在未解锁下方区域内」→ lv_153 转 timeout。
- 冰区 iceArea 接入 + 上述修正后（第 10 轮终）基线：**可解 14 / 不可解 5 / 未建模 29 / 超时 175**。`不可解 5` 仍 = NULL 历史 + lv_17 稠密无首消；`未建模 29` = ColorTrain / bombSecs / 钥匙 / 星。
- `不可解 5`（lv_24/207/213/218/220）根因统一为 **NULL 历史色块**：lv_24/207 = NULL 奇数(3 枚)；lv_213/218/220 = NULL 是「唯一步锁为 0 的种子块」且相隔被卡，真实色丢失导致无首消——均非求解器/区域/stepLock bug；生成器永不产出 NULL 故不受影响。
- **未建模 190 关**（阶段②–⑤才接入）：DecorationArea / IceShaver / LowerArea / ManualBlockDispenser / ShieldArea / ColorTrain 实体 + stepLock / bombSecs。
- **阶段①建模子集 = 33 关**（无实体、无 bomb/stepLock/keyLock/lock/key/withKey/star/iceArea）。
  - **可解 10 关**：lv_1/2/3/4/5/15/50/55/203/216，语义正确、**0 误判不可解**。BFS→DFS 后 lv_4/55/216 从超时转可解，其余可解关状态数从万级降到几十（lv_15 5.99s→0.01s、lv_203 同）。
  - **超时 23 关**：贪心诊断确认 = **稠密棋盘「无邻可消、需连环挪位」的滑动拼图式难搜**（如 lv_110 起始 11 可消块却 0 个可达、lv_55 消 2 对后 32 可消块 0 可达）——非建模 bug，属组合搜索爆炸。
- **阶段 B 主攻**（解决 23 超时 + 给最少步数）：A*（h=剩余需消除对数下界）+ 对称/同构剔除 + group-id 归一 + 位图状态键 + 面向「开路」的定位移动生成（替代穷举一步挪位）。
- **稠密度校正（2025 第 4 轮）**：23 超时关是**真·滑动拼图**——lv_110 = 28 块占满 45/47 格（仅 **2 个空格**），且大量多格块（1×2/2×2 等）；不是此前误判的「40% 空」。2 空格 + 多格块 → 状态空间呈 15-puzzle 级，穷举 DFS/A* 在 6s 内不可收敛。
- **贪心负结果（2025 第 4 轮）**：`solve_greedy`（对消必走 + `_match_gap` 空格可达距离启发式）对 23 关**全部失败**——僵局时「无空格可达路径」→ gap=INF，启发式无法区分挪位方向；证明需要**挡路块感知（blocker-aware）**的定位生成，而非纯空格距离。
- 烟雾 t1–t5 全部可解；双色剥壳/无色揭示/绑定/箭头/墙/筛色格语义已回源码锁定（§8）。

- **最少步数 A* 已落地**（`solve_min_steps`，可采纳 h=ceil(剩块/2)，返回最优步数）；10 个可解关最优步数分布：**lv_1=3 / lv_2=4 / lv_3=9 / lv_4=12 / lv_5=11 / lv_15=10 / lv_50=15 / lv_55=21 / lv_203=10 / lv_216=29**（对比：DFS 曾给 lv_4=172、lv_216=200 的非最短游走解，A* 压回真实最短）。这是难度模型「最少步数」口径的第一批真值。
- **规范化已修**：`canonical_key` 归一化 group-id 值（同构簇仅编号不同可合并），并修掉 group-0 单块被并进同一桶的隐患；对 23 超时无显著帮助 → 反证超时是稠密走位难搜，非去重 bug。


## 7. 性能预算与优化
- 状态键：规范化 tuple；阶段 B 用位图（每格 4bit 存色/占位）压缩。
- 分支：每态 ≈ Σ实体(可达锚点数)；用「不可进入图」缓存 + 单实体增量可达性控制。
- 剪枝留白：阶段 A 只做 visited 去重；对称剔除 / 启发式 `h = 剩余需消除对数（下界）` / 双向 BFS 在阶段 B 引入并实测。
- 223 回归报告字段：关号 / 阶段覆盖率 / 可解性 / 最少步数 / 状态数 / 峰值内存 / 耗时。

## 8. 阶段①源码锁定结论（2025，已全部核实，非开项）

| # | 结论 | 证据 |
|---|---|---|
| 1 | **无色包装 = 每枚独立 countdown**；每**非自身** `Block.Event.BLOCK_MATCH` `count--`，归 0 露出 `lockedColor`；锁 `Matchable`+`PackagedAppearance`，**不锁 `Movable`** | `MatchLockAbility.cs` `OnBlockMatch`/`LockAffectedBlock`/`AffectsBlock`（`SharesWholeLock`=同组同格异 floor 才共享） |
| 2 | **双色 = 同 groupID 同 gridPos 的 floor0(外壳,匹配色)+floor1(内核,隐藏色)**；剥壳 = floor0 与同色 floor0 对消（`CanMatchBlocks` 拒绝 floor>0）+ `HandleGroupBlockFall` 把 floor1 内核落回 floor0 | `GamePlayMgr.CanMatchBlocks`(Floor>0 拒绝) / `HandleGroupBlockFall`(1866) |
| 3 | **簇 = groupID 全部块**（双色叠层 + 绑定异位混合一起拖，相对偏移固定）；成员各自独立对消，剩余仍同簇；**无棋盘下落**（只有 floor 层叠随消落层） | `GamePlayMgr.OnBlockDragOn`(924) / `HandleGroupBlockFall` |
| 4 | **未保护格 = `LocalGrids() - BarrierAbility.IsProtected`**；阶段①无 Barrier → 即全部 LocalGrid；匹配先按 `OccupiedGirds` 相临候选、再按 `GetUnprotectedGirds` 相邻判定 | `Entity.IsProtected`(429) / `Block.GetUnprotectedGirds`(2016) / `GamePlayMgr.CanMatchBlocks`(1296) |
| 5 | **移动 = 簇整体拖拽**，`ClusterPlaceable(anchor)` = 锚点 `PosPlaceable` 且每成员 `PosPlaceable`；`PosPlaceable` = 落格∈cells ∧ 无同层障碍墙 ∧ 无同层非簇占格 ∧ 颜色筛选(包装块不可过任何筛色) | `MoveAbility.TryMoveTo`(54-83) / `GamePlayMgr.PosPlaceable`(1057) |
| 6 | **匹配条件** = 双方 floor==0、同层、`LogicColor` 相等（含 NULL==NULL）、`IsMatchable`+`CanSelectBlock`、无 stepLock/keyLock/Lock/Immune/全冰、star 单向（拖动块带星才要求目标带星） | `GamePlayMgr.CanMatchBlocks`(1211-1315) |
| 7 | **stepLock** = 每枚独立，每非自身 BLOCK_MATCH `-1`（阶段⑤接入） | `Block.OnBlockMatch`(3002) |

> 载入细节（已写进 `agent/solver.py`）：`lockedColor` 恒存在且∈0-9；`color==None` 的 MatchLock 块靠 lockedColor 定真实色；无 MatchLock 且 `color==None` 的块按 NULL 色与 NULL 结对。（NULL 是**历史语料**语义，生成时才禁用 NULL。）
## 10. 阶段②制造机源码锁定（2025 第 4 轮）

- 机身 = 2×3 共 6 格（BaseAGrids 3 + BaseBGrids 3），按 rotation 四向旋转，机体占格阻挡移动（证据 LocalBodyGrids 247 / BaseAGrids 95-104）。
- 开口方向（拖出侧）= Rot0 右 / Rot90 上 / Rot180 左 / Rot270 下（GetBToADirection 555-567）。
- 队首 preview 在开口侧贴机身外（GetPreviewGridPos 494 按 item 形状+旋转对齐），拖出脱离机身即 Detach 成普通块（OnBlockMove 203-213）。
- HP = remainingQueue.Count + preview 是否在场；HP=0 时机身消失、未拖出块消失、已拖出块留场（Hp 129 / Break 1164）。
- 产出块可带 MatchLock/stepLock/bombSecs/key/lock/withKey/withStar，支持多格形状（判据 C，BuildPreviewBlockConfig 468-488）。
- 拖出 = 1 步（2025 拍板）；preview 拖拽期间 stepLock 检查放宽。
- ≤250 内 39 台制造机。

已实现（v1，第 5 轮）：State = (blocks, dispensers)，canonical_key 纳入机身+队列；机身格进 occ（queue 非空时机身在，空则释放）；新算子「拖出」= 队首从出口滑到最近「完全在机身外」的格并 Detach 为普通块（spec 含 color/MatchLock/moveMode/多格 local），HP-1、下一枚露头。
- v1 简化：拖出只到最近出口格，不额外拖远（后续再拖，最少步数对每台最多 +1）；拖出后不立即结算，对消走下一宏动作。
- 阶段②建模判定 = 只允许 ManualBlockDispenser 实体，且产出项不含 stepLock/bomb/key/lock/withKey/star。
## 11. 阶段③区域（部分已实现，第 6 轮）

| 元素 | 语义 | 状态 |
|---|---|---|
| ShieldArea 无色区域 | 矩形禁消（任一方任一格在内则抑制普通对消/剥壳），不禁移动 | 已实现（static，进 step_state 过滤） |
| DecorationArea 装修区域 | 未解锁覆盖格阻挡移动/放置；每次普通对消事件 HP-1 全局扣血，HP=0 解锁露出下方块；门下块完全被覆盖时不可拖不可匹 | 已实现（state 增 decorations，_dec_decs 每次 match 扣 1） |
| LowerArea 下方区域 | 表面(层!=10)清空瞬间解锁，抬升区内 layer=10 隐藏块到 layer=20；隐藏块不可动/匹/不阻挡 | 已实现（第 8 轮） |
| iceArea / CellType.Ice 冰区 | cellType=1 连通组件整片层数，每次普通对消 ALL 冰区 -1，归 0 解除，全冰覆盖块锁定 | 已实现（第 10 轮） |下一轮 |

- 阶段③/④判定当前 = 允许 ManualBlockDispenser + DecorationArea + ShieldArea + LowerArea + IceShaver + iceArea + ColorTrain；剩余 not-modeled = bombSecs(炸弹) / 钥匙 / 星。
- **颜色火车 ColorTrain（第 11 轮已实现，v1 简化）**：车箱链占格（gridPos + directionFromPrevious 折线）；Colored 车箱块展平为层次队列；`step_state` 增加「端部消耗」（同色块拖到头/尾格邻消耗该块 + 移末端层）；普通对消后 `_train_remove_linked` 最多移 2 个同色层；通关要求无存活火车。合成测试：单节 train + color5 块撞端部 + color6 对消(solvable 2)。v1 简化：展平多块车厢、端部两向皆可、忽略车厢层叠揭壳细节。
- **冰区 iceArea（第 10 轮已实现）**：cellType=1 连通组件 + iceArea[组件]=层数；每次普通对消 `_ice_decs` 全冰区 -1、归 0 解除；全冰覆盖块 `_is_iced` 不可动/不可匹（仍占格阻挡）。合成测试：冰层 1 触发对消解锁 + 冰上块揭示对消(solvable 2)。
- **搓冰机 IceShaver（第 9 轮已实现）**：机身段进 occ（左 leftHp + 中占位 + 右 rightHp）；`step_state` 增加最高优先级「相撞」——同色可消块与颜色段四邻相邻 → 消费该块 + 该段 HP-1；普通同色对消后 `_ice_passive` 对应颜色段 -2；通关要求无存活搓冰机（`CheckGameWin`）。合成测试：被动-2 击杀(solvable 1) + 相撞-1 击杀(solvable 2) 通过。
- 合成测试通过：shield 内同色对不可消(unsolvable)、装修区 hp=1 先消外对解锁再消下块(solvable 2)；制造机/阶段①回退无退化。
- **NULL 历史色块基线口径**：≤250 中 166 关含 `color=None` 且无 MatchLock 的块（多为偶数 2/4/6，可两两 NULL 对消；少数奇数 1/3/5 如 lv_24/lv_207）。求解器按游戏语义 `LogicColor==LogicColor` 令 NULL 与 NULL 对消；奇数该批历史数据会判「不可解」。生成器从不产出 NULL（用户拍板），故该口径只影响语料基线、不影响生成。
- **通关口径已对齐**：`CheckGameWin` 要求无块 + 玉米机空 + 无阻挡区域（装修区全部解锁），`_is_goal` 已纳入装修区解锁；装修区门下的块仍可被界外邻格配对（仅禁移动、不禁匹配）。
## 12. 阶段⑤ stepLock（第 7 轮已实现）

- stepLock>0 → 整簇不可拖（OnBlockDragOn 903/929），且不可匹配（CanMatchBlocks 1274-1275）。
- 每非自身 BLOCK_MATCH `StepLock-1`（Block.cs 3005）；到 0 解锁为可拖可匹。
- 实现：`successors` 跳 stepLock>0 簇；`step_state` stat 排除 stepLock>0；`resolve` 每 match 对存活块 stepLock-1。
- 合成测试通过：stepLock=1 的同色对，先消触发对(颜色另配)→ 锁 1→0 → 再消该对（solvable 2）。
- stepLock 接入后额外资解锁 ~47 关（多为稠密 → 超时 100；可解 14）。

## 13. 阶段 B 优化（第 12 轮已实现：性能 + 奇偶死锁剪枝，2025）

- **性能（安全）**：`block_world` 改 `@lru_cache`（键 (gx,gy,local) → frozenset 位图化）；`successors` 预计算「分层占格 occ_by_layer」与「静态可匹配块 stat_global」，避免每个簇/每个锚点重复构图；`_canon_blocks` 的 mrec 摊平为扁平整数元组（局部格摊平）加速排序/哈希。净效果单关展开速率 ~3.3×（lv_110 8s 内 2.4 万 → 8.1 万态）。
- **奇偶死锁剪枝（`_parity_dead`，不变量级、安全）**：任一颜色 c 的块计数（含无色包装 lockedColor、双色内核——它们终将揭示为该色）在一次普通对消中恒 -2；揭示/剥壳不改变该计数 → 每色块数的奇偶是不变量，终态全 0（偶）。故**无 非空制造机 / 存活搓冰机 / 存活火车** 时，任何颜色计数为奇数 ⇒ 不可解（初始态 + 每个后继态直接剪枝）。搓冰机相撞 / 火车端部各消费 1 块、制造机可新增块会打破奇偶，故有这些存活来源时不做判断（保守跳过）。
- **本轮认知翻转**：一批被当作「真·滑动拼图超时」的稠密关，实为**奇偶奇数的不可解关**——如 lv_110（加载后 color=0 有 7 枚 + NULL 1 枚，均奇数；此前 DFS 6s 4.3 万态超时）被奇偶剪枝瞬间判为不可解（states=1）。≤250 内 **38 关**命中奇偶死锁（含 lv_24/207 的 NULL 奇数历史层）。
- **第 12 轮基线（`agent/baseline_output.txt`，--timeout=6）**：共 223 | **可解 14 / 不可解 48 / 未建模 14 / 超时 147**。
  - 对照上一版（可解 14 / 不可解 5 / 未建模 29 / 超时 175）：不可解 5→48（奇偶 38 + 3.3× 性能加速令 DFS 在 6s 内穷尽更多不可解关）；未建模 29→14（ColorTrain 已 v1 建模）；超时 175→147（-28）。
  - 残余 147 超时 = 偶奇偶、无制造机/搓冰/火车的「真·深搜」关（多为已上线可解关，仅深层搜不出；少量为更隐蔽的不可解）。
- **阶段 B 剩余（下一步）**：①阻塞感知（blocker-aware）定位移动生成（替代穷举一步挪位）+ ②D4 对称/颜色同构去重 + ③位图状态键收尾 + ④更强可采纳启发式；目标把 147 超时两分，再接生成器/难度模型（以用户思路为主）。

## 14. 第 13 轮：性能再加码 + 147 超时定性 + 炸弹/火车语义锁定（2025）

- **`_mrec` 缓存**：块 → 扁平整数元组加 `@lru_cache`（静态块在搜索树间复用同一 tuple，命中率高）；单关展开速率再加 ~2×。第 13 轮基线（`agent/baseline_output.txt`）：**可解 14 / 不可解 49 / 未建模 14 / 超时 146**（lv_182 由超时转不可解；对照第 12 轮 14/48/14/147）。性能已非瓶颈（累计 ~6–7×），146 超时是算法级的深搜。
- **146 超时定性（3 类，均偶数奇偶）**：
  1. **真·稠密滑动**（1–2 空格 + 多格块，如 lv_7/8/9/13/18）：解深度 ~300（lv_13 实测 298 步、16 个 2 格块、2 空格），15-puzzle 级，blocker-aware 定位/位图/对称对这类收益有限——分支本就 2–4，瓶颈是深度。
  2. **匹配顺序爆炸**（如 lv_16：8 个双色 + 10 个即时可消、1 搓冰机）：分支在「选哪个对消」，错序即死锁，需匹配顺序剪枝/死锁检测，不是滑动。
  3. **搓冰机/区域稠密叠加**（如 lv_10/11/12/14/16）：机制被动扣血 + 相撞分支复杂。
- **炸弹 = 实时秒数（Bomb.cs，本轮锁定）**：bombSecs 动态生成 Bomb 能力；首次 `Block.Event.SELECTED`（首个块被选中）起倒计时，每 0.1s -0.1；`levelTimer.IsRunning` 为假不跳；无色包装（IsPackaged）时 `PauseCountdown`。归零 → `OnBombExploded`（失败）。**实时秒数无法在回合制求解器中直接建模**——需「一步 = 几秒」时间模型，属难度模型（用户思路）范畴；未定前炸弹关保持 not-modeled。
- **颜色火车全量（ColorTrainConfig.cs 枚举，本轮锁定）**：`ColorTrainCarriageType` Empty=0/Colored=1；`ColorTrainEndConsumeMode` HeadOnly=0/TailOnly=1/Both=2；`ColorTrainConsumeOrder` HeadFirst=0/TailFirst=1。语料 endConsumeMode/consumeOrder 全为 0 = **HeadOnly + HeadFirst**（只头部可端部消耗、同色联动从头取）。**现行 v1「端部两向皆可」是已知简化且与语料不符（应只头部）**——②阶段补全时须修：端部模式、空车厢清理 + 头锚点重设、车厢内 block 的 matchLock/stepLock/key-lock、多层车厢揭壳。

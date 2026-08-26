# -*- coding: utf-8 -*-
"""Level-Maker 校验器基础库：枚举、形状表、旋转展开、默认值（依据 level-schema.md v1.0）。"""

# ---------- 枚举（已核准 LevelConfig.cs / BoardLogicLayer.cs） ----------
BLOCK_COLOR = {"NULL": -1, "RED": 0, "ORANGE": 1, "YELLOW": 2, "LIGHT_GREEN": 3,
               "LIGHT_BLUE": 4, "DARK_GREEN": 5, "CYAN": 6, "BLUE": 7, "PURPLE": 8,
               "MAGENTA": 9, "BLACK": 11, "WHITE": 12}
COLOR_MAX = 12          # 可玩色含黑白；color ∈ {-1} ∪ [0,9] ∪ {11,12}
PLAYABLE_FIRST = 8      # 默认前 8 色（0-7），黑白尽量少用

DDRotation = {0: "Rot0", 1: "Rot90", 2: "Rot180", 3: "Rot270"}
CELL_TYPE = {"Default": 0, "Ice": 1}
BOARD_LAYER = {0, 10, 20, 30}     # 40 归一 Layer3
MOVE_MODE = {"BOTH": 0, "VER": 1, "HOR": 2}

# BlockType 12 种（Rot0 坐标；全部 LocalGrids 含不可选格）
# 依据 level-rules.md §2 表（B_1X1 唯一格 isSelectable=false 仍占格）
BLOCK_TYPE_POSES = {
    0:  [(0, 0)],                                          # B_1X1
    1:  [(0, 0), (0, 1)],                                  # B_1X2
    2:  [(0, 0), (0, 1), (0, 2)],                          # B_1X3
    3:  [(0, 0), (0, 1), (0, 2), (0, 3)],                  # B_1X4
    4:  [(0, 0), (0, 1), (1, 0), (1, 1)],                  # B_2X2
    5:  [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)],  # B_2X3
    6:  [(0, 2), (1, 0), (1, 1), (1, 2)],                  # B_7
    7:  [(0, 0), (0, 1), (1, 0)],                          # B_ARROW
    8:  [(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)],          # B_CROSS
    9:  [(0, 0), (1, 0), (2, 0), (1, 1)],                  # B_DELTA
    10: [(0, 0), (1, 0), (1, 1), (1, 2)],                  # B_J
    11: [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)],          # B_1X5
}

ENTITY_NAMES = {"ManualBlockDispenser", "IceShaver", "DecorationArea",
                "LowerArea", "ShieldArea", "ColorTrain"}

# 区域类实体（覆盖层，与其他对象可跨层叠放；不判同层占格冲突）
AREA_ENTITIES = {"DecorationArea", "LowerArea", "ShieldArea"}
WALL_CYCLE_PIPE = 100

# 默认值（JSON 最小化：写盘省略，加载补全）
DEFAULTS = {
    "block": {"type": 0, "rot": 0, "color": -1, "gridPos": (0, 0), "layer": 20,
              "moveMode": 0, "customWidth": 0, "customHeight": 0},
    "entity": {"gridPos": (0, 0), "layer": 20},
    "wall": {"rot": 0, "layer": 20},
    "cell": {"color": -1, "cellType": 0},
}
# 制造机/车身默认（依据语料与 IsConfigValid）
DISPENSER_DEFAULTS = {"rotation": 0, "bodyColor": -1, "bodyFrozen": False,
                      "bodyStepLock": 0, "bodyKeyLock": 0, "bodyBombSecs": 0,
                      "bodyKey": 0, "bodyLock": 0, "bodyMatchLock": 0,
                      "bodyWithKey": False, "bodyWithStar": False}
ITEM_DEFAULTS = {"quantity": 1, "rotation": 0, "alignLeft": True, "useCustomSize": False,
                 "moveMode": 0, "stepLock": 0, "keyLock": 0, "bombSecs": 0,
                 "key": 0, "lock": 0, "withKey": False, "withStar": False}


def rot_poses(poses, rot):
    """旋转展开 + 归一化（与仓库 GetNormalizedShape 一致）：
    Rot90: (x,y)->(-y,x); Rot180: (-x,-y); Rot270: (y,-x); 随后 minX/minY 归零。"""
    r = []
    for (x, y) in poses:
        if rot == 0:   p = (x, y)
        elif rot == 1: p = (-y, x)
        elif rot == 2: p = (-x, -y)
        else:          p = (y, -x)
        r.append(p)
    min_x = min(p[0] for p in r)
    min_y = min(p[1] for p in r)
    return [(p[0] - min_x, p[1] - min_y) for p in r]


def block_local_poses(cfg):
    """block 配置 → 局部格列表（标准形状旋转或自定义矩形全格）。"""
    if cfg.get("customWidth") or cfg.get("customHeight"):
        w = cfg.get("customWidth") or 0
        h = cfg.get("customHeight") or 0
        if w <= 0 or h <= 0:
            return None
        poses = [(x, y) for x in range(w) for y in range(h)]  # 矩形全格
    else:
        t = cfg.get("type", 0)
        if t not in BLOCK_TYPE_POSES:
            return None
        poses = BLOCK_TYPE_POSES[t]
    return rot_poses(poses, cfg.get("rot", 0))


def block_world_poses(cfg):
    """block 配置 → 世界格（gridPos + 局部格）。"""
    local = block_local_poses(cfg)
    if local is None:
        return None
    gp = cfg.get("gridPos") or {}
    gx = gp.get("x", 0); gy = gp.get("y", 0)
    return [(gx + px, gy + py) for (px, py) in local]

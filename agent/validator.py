# -*- coding: utf-8 -*-
"""Level-Maker 合法性与格式校验器（schema v1.0，L1 格式 + L2 结构）。

用法（单关）:
    from validator import LevelValidator
    v = LevelValidator(level_dict)
    ok, errors = v.validate()          # errors: List[str]
批量:
    python3 cli.py <levels_dir>        # 或单文件路径
"""
from base import (
    BLOCK_TYPE_POSES, ENTITY_NAMES, AREA_ENTITIES, WALL_CYCLE_PIPE,
    BOARD_LAYER, MOVE_MODE, DISPENSER_DEFAULTS, ITEM_DEFAULTS,
    rot_poses, block_world_poses,
)


class LevelValidator:
    def __init__(self, level: dict, name: str = ""):
        self.level = level
        self.name = name
        self.errors = []
        self.warnings = []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    # ---------- 公共入口 ----------
    def validate(self):
        self.errors, self.warnings = [], []
        self._v_cells()
        self._v_walls()
        self._v_blocks()
        self._v_entities()
        self._v_ice_area()
        self._v_key_lock()
        self._v_overlap()
        return (len(self.errors) == 0), self.errors, self.warnings

    # ---------- 工具 ----------
    def _cells_set(self):
        cells = self.level.get("cells") or []
        return {( (c.get("gridPos") or {}).get("x", 0), (c.get("gridPos") or {}).get("y", 0) )
                for c in cells}

    # ---------- L1: cells ----------
    def _v_cells(self):
        cells = self.level.get("cells")
        if not cells:
            # 空对象/占位关卡文件（如 lv_1101 = {}）不报错，仅提示
            if not any(self.level.get(k) for k in ("blocks", "walls", "entities", "iceArea")):
                self.warn("空关卡文件（无 cells 且无内容）")
                return
            self.err("缺少 cells（棋盘必填）")
            return
        seen = set()
        for i, c in enumerate(cells):
            gp = c.get("gridPos") or {}
            x, y = gp.get("x", 0), gp.get("y", 0)
            if (x, y) in seen:
                self.err(f"cells[{i}] 重复格 ({x},{y})")
            seen.add((x, y))
            col = c.get("color", -1)
            if col not in (-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12):
                self.err(f"cells[{i}] color={col} 非法（须 -1 或 0-9/11/12）")
            ct = c.get("cellType", 0)
            if ct not in (0, 1):
                self.err(f"cells[{i}] cellType={ct} 非法（0=Default/1=Ice）")

    # ---------- L1/L2: walls ----------
    def _v_walls(self):
        walls = self.level.get("walls") or []
        cells_set = self._cells_set()
        for i, w in enumerate(walls):
            if w.get("type") != WALL_CYCLE_PIPE:
                self.err(f"walls[{i}] type={w.get('type')} 非法（仅支持 100=CYCLE_PIPE）")
            wp = (w.get("gridPos") or {}).get("x", 0), (w.get("gridPos") or {}).get("y", 0)
            if wp not in cells_set:
                self.err(f"walls[{i}] 占格 {wp} 超出棋盘")

    # ---------- L1/L2: blocks ----------
    def _v_blocks(self):
        blocks = self.level.get("blocks") or []
        cells_set = self._cells_set()
        for i, b in enumerate(blocks):
            # 形状
            has_custom = bool(b.get("customWidth") or b.get("customHeight"))
            if not has_custom:
                t = b.get("type", 0)
                if t not in BLOCK_TYPE_POSES:
                    self.err(f"blocks[{i}] type={t} 非法 BlockType")
            else:
                cw = b.get("customWidth") or 0
                ch = b.get("customHeight") or 0
                if cw <= 0 or ch <= 0:
                    self.err(f"blocks[{i}] customWidth/Height 需 >0（{cw}x{ch}）")
            rot = b.get("rot", 0)
            if rot not in (0, 1, 2, 3):
                self.err(f"blocks[{i}] rot={rot} 非法（0-3）")
            # 颜色
            # 注：无色方块（MatchLockAbility 带 lockedColor）顶层 color 可为省略(NULL)
            col = b.get("color", -1)
            if col != -1 and col not in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12):
                self.err(f"blocks[{i}] color={col} 非法")
            # 层
            layer = b.get("layer", 20)
            norm = layer if layer in (0, 10, 20, 30) else (30 if layer == 40 else None)
            if norm is None:
                self.err(f"blocks[{i}] layer={layer} 非法（0/10/20/30/40）")
            # moveMode
            mm = b.get("moveMode", 0)
            if mm not in (0, 1, 2):
                self.err(f"blocks[{i}] moveMode={mm} 非法（0=BOTH/1=VER/2=HOR）")
            # stepLock / bombSecs
            if b.get("stepLock") is not None and b.get("stepLock") < 0:
                self.err(f"blocks[{i}] stepLock<0")
            if b.get("bombSecs") is not None and b.get("bombSecs") <= 0:
                self.err(f"blocks[{i}] bombSecs 需 >0")
            # 占格
            world = block_world_poses(b)
            if world is None:
                continue
            for gx, gy in world:
                if (gx, gy) not in cells_set:
                    self.err(f"blocks[{i}] 占格 ({gx},{gy}) 超出棋盘")
            # （NULL 色块合法：两枚 color=NULL 的块可互为配对消除；无色方块=MatchLock 在 abilities）
            self._v_abilities(b, f"blocks[{i}]")

    def _has_ability(self, obj, name):
        for a in obj.get("abilities") or []:
            if a.get("abilityName") == name:
                return True
        return False

    def _v_abilities(self, obj, label):
        for a in obj.get("abilities") or []:
            if not a.get("abilityName"):
                self.err(f"{label} abilities 缺 abilityName")
            for f in a.get("fields") or []:
                if "Key" not in f or "Value" not in f:
                    self.err(f"{label} ability fields 须 {Key:..., Value:...}")

    # ---------- L1/L2: entities ----------
    def _v_entities(self):
        ents = self.level.get("entities") or []
        cells_set = self._cells_set()
        for i, e in enumerate(ents):
            name = e.get("entityName")
            label = f"entities[{i}]({name})"
            if name not in ENTITY_NAMES:
                self.err(f"{label} entityName 非法")
                continue
            layer = e.get("layer", 20)
            if layer not in (0, 10, 20, 30) and layer != 40:
                self.err(f"{label} layer={layer} 非法")
            abilities = e.get("abilities") or []
            if not abilities:
                self.err(f"{label} 缺 abilities")
            for a in abilities:
                self._v_abilities(e, label)
            # 占格（非区域类）
            if name not in AREA_ENTITIES:
                ents_bodies = set()
                # 制造机机身（默认 2x3，按 rotation 展开——简化：2x3/3x2）
                if name == "ManualBlockDispenser":
                    fields = self._fields_of(e, "ManualBlockDispenserAbility")
                    rotation = fields.get("rotation", 0)
                    body = [(0, 0), (1, 0), (0, 1), (1, 1), (0, 2), (1, 2)]
                    if rotation in (1, 3):
                        body = [(0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (2, 1)]
                    gp = e.get("gridPos") or {}
                    gx, gy = gp.get("x", 0), gp.get("y", 0)
                    ents_bodies = {(gx + px, gy + py) for (px, py) in body}
                    self._v_dispenser(e, label)  # IsConfigValid 部分
                elif name == "IceShaver":
                    fields = self._fields_of(e, "IceShaverAbility")
                    lh = fields.get("leftHp", 0); rh = fields.get("rightHp", 0)
                    if lh < 0 or rh < 0:
                        self.err(f"{label} leftHp/rightHp 需 >=0")
                    gp = e.get("gridPos") or {}
                    gx, gy = gp.get("x", 0), gp.get("y", 0)
                    body = self._ice_shaver_body(e)
                    ents_bodies = {(gx + px, gy + py) for (px, py) in body}
                elif name == "ColorTrain":
                    fields = self._fields_of(e, "ColorTrainAbility")
                    carriages = fields.get("carriages")
                    if carriages is None:
                        self.err(f"{label} 缺 carriages")
                    # 车厢占位在 L2 重叠检查里从简（方向复杂）——此处仅缺字段检查
                for (gx, gy) in ents_bodies:
                    if (gx, gy) not in cells_set:
                        self.err(f"{label} 占格 ({gx},{gy}) 超出棋盘")
            else:
                # 区域类：参数合法 + 覆盖格在棋盘
                fields = self._fields_of(e, name + "Ability")
                if name == "DecorationArea":
                    hp = fields.get("hp", 0); w = fields.get("width", 0); h = fields.get("height", 0)
                    if hp < 0:
                        self.err(f"{label} hp<0")
                    if w <= 0 or h <= 0:
                        self.err(f"{label} width/height 需 >0")
                else:
                    w = fields.get("width", 0); h = fields.get("height", 0)
                    if w <= 0 or h <= 0:
                        self.err(f"{label} width/height 需 >0")
                gp = e.get("gridPos") or {}
                gx, gy = gp.get("x", 0), gp.get("y", 0)
                for px in range(w or 0):
                    for py in range(h or 0):
                        if (gx + px, gy + py) not in cells_set:
                            self.err(f"{label} 覆盖格 ({gx+px},{gy+py}) 超出棋盘")

    def _ice_shaver_body(self, e):
        """搓冰机占格列表（GridPos=中心/底部占位；leftHp 段向 -方向，rightHp 段向 +方向；占位仅 IsAlive）。
        依据 IceShaver.cs OccupiedGirds / OrientationVector。"""
        fields = self._fields_of(e, "IceShaverAbility")
        lh = fields.get("leftHp", 0); rh = fields.get("rightHp", 0)
        orient = fields.get("orientation", 0)
        dx, dy = (1, 0) if orient == 0 else (0, 1)
        body = []
        for i in range(1, lh + 1):
            body.append((-dx * i, -dy * i))
        if lh + rh > 0:                      # IsAlive → 中心/底部占位
            body.append((0, 0))
        for i in range(1, rh + 1):
            body.append((dx * i, dy * i))
        return body

    def _fields_of(self, e, ability_name):
        """取实体指定能力的 fields 字典（Value 为原始 JSON 值）。"""
        out = {}
        for a in e.get("abilities") or []:
            if a.get("abilityName") == ability_name:
                for f in a.get("fields") or []:
                    out[f.get("Key")] = f.get("Value")
        return out

    # ---------- 制造机 IsConfigValid ----------
    def _v_dispenser(self, e, label):
        fields = self._fields_of(e, "ManualBlockDispenserAbility")
        items = fields.get("items")
        if not items:
            self.err(f"{label} 生成队列不能为空")
            return
        for i, it in enumerate(items):
            if it is None:
                self.err(f"{label} 第 {i+1} 个生成项为空")
                continue
            q = it.get("quantity", 1)
            if q <= 0:
                self.err(f"{label} 第 {i+1} 个生成项 quantity 必须 >0")
            is_custom = bool(it.get("useCustomSize"))
            if not is_custom:
                t = it.get("type")
                if t not in BLOCK_TYPE_POSES:
                    self.err(f"{label} 第 {i+1} 个生成项 type={t} 不是合法 BlockType")
            else:
                cw = it.get("customWidth", 0); ch = it.get("customHeight", 0)
                if cw <= 0 or ch <= 0:
                    self.err(f"{label} 第 {i+1} 个生成项 custom 尺寸非法")
            col = it.get("color", -1)
            if col != -1 and col not in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12):
                self.err(f"{label} 第 {i+1} 个生成项 color 非法")

    # ---------- iceArea ----------
    def _v_ice_area(self):
        ice_area = self.level.get("iceArea")
        if not ice_area:
            return
        cells = self.level.get("cells") or []
        ice_cells = [c for c in cells if c.get("cellType", 0) == 1]
        if not ice_cells:
            self.err("iceArea 存在但无 cellType=1 的冰格")
        # 组件连通性检查（四邻 BFS/union-find）
        positions = {( (c.get("gridPos") or {}).get("x", 0), (c.get("gridPos") or {}).get("y", 0) )
                     for c in ice_cells}
        n = len(positions)
        parent = {p: p for p in positions}
        def find(p):
            while parent[p] != p:
                parent[p] = parent[parent[p]]
                p = parent[p]
            return p
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra
        for (x, y) in positions:
            for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                if (x+dx, y+dy) in positions:
                    union((x,y), (x+dx, y+dy))
        comps = {}
        for p in positions:
            root = find(p)
            comps.setdefault(root, []).append(p)
        if len(comps) != len(ice_area):
            self.warn(f"iceArea 组件数 {len(ice_area)} ≠ 冰格连通组件数 {len(comps)}")

    # ---------- key-lock（编辑器强制：有 key 必须有 lock 且唯一，反之亦然）----------
    def _v_key_lock(self):
        keys, locks = {}, {}
        def add(d, id, label):
            if id and id > 0:
                d.setdefault(id, []).append(label)
        for i, b in enumerate(self.level.get("blocks") or []):
            add(keys, b.get("key"), f"blocks[{i}]")
            add(locks, b.get("lock"), f"blocks[{i}]")
        for i, e in enumerate(self.level.get("entities") or []):
            if e.get("entityName") == "ColorTrain":
                fields = self._fields_of(e, "ColorTrainAbility")
                for ci, c in enumerate(fields.get("carriages") or []):
                    for bi, blk in enumerate(c.get("blocks") or []):
                        add(keys, blk.get("key"), f"ColorTrain[{i}] 车厢{ci}层{bi}")
                        add(locks, blk.get("lock"), f"ColorTrain[{i}] 车厢{ci}层{bi}")
        for k, v in keys.items():
            if k not in locks:
                self.err(f"钥匙 {k} 存在但无对应锁")
            if len(v) > 1:
                self.err(f"钥匙 {k} 多个对象共用（须唯一）")
        for k, v in locks.items():
            if k not in keys:
                self.err(f"锁 {k} 存在但无对应钥匙")
            if len(v) > 1:
                self.err(f"锁 {k} 多个对象共用（须唯一）")

    # ---------- L2: 同层占格冲突 ----------
    def _v_overlap(self):
        cells_set = self._cells_set()
        # 收集各对象（层, 格集）
        occ = []  # (label, layer, set_of_cells, is_area)
        for i, b in enumerate(self.level.get("blocks") or []):
            w = block_world_poses(b)
            if w:
                occ.append((f"blocks[{i}]", b.get("layer", 20), set(w), False,
                            b.get("floor", 0), b.get("groupID")))
        for i, w_ in enumerate(self.level.get("walls") or []):
            gp = w_.get("gridPos") or {}
            occ.append((f"walls[{i}]", w_.get("layer", 20),
                        {(gp.get("x",0), gp.get("y",0))}, False, 0, None))
        for i, e in enumerate(self.level.get("entities") or []):
            name = e.get("entityName")
            if name not in ENTITY_NAMES:
                continue
            gp = e.get("gridPos") or {}
            gx, gy = gp.get("x", 0), gp.get("y", 0)
            layer = e.get("layer", 20)
            if name == "ManualBlockDispenser":
                fields = self._fields_of(e, "ManualBlockDispenserAbility")
                rot = fields.get("rotation", 0)
                body = [(0,0),(1,0),(0,1),(1,1),(0,2),(1,2)]
                if rot in (1, 3):
                    body = [(0,0),(1,0),(0,1),(1,1),(2,0),(2,1)]
                occ.append((f"entities[{i}](制造机)", layer,
                            {(gx+px, gy+py) for (px,py) in body}, False, 0, None))
            elif name == "IceShaver":
                body = self._ice_shaver_body(e)
                occ.append((f"entities[{i}](搓冰机)", layer,
                            {(gx+px, gy+py) for (px,py) in body}, False, 0, None))
            elif name in AREA_ENTITIES:
                fields = self._fields_of(e, name + "Ability")
                w_ = fields.get("width", 0); h_ = fields.get("height", 0)
                occ.append((f"entities[{i}]({name})", layer,
                            {(gx+px, gy+py) for px in range(w_) for py in range(h_)}, True, 0, None))
            # ColorTrain 车厢占格从简（L2 不展开折线，冲突检查跳）
        # 冲突检测：同层且任一方非区域 → 检查；floor 双色配对放行
        n = len(occ)
        for a in range(n):
            for bl in range(a+1, n):
                la, lb = occ[a][1], occ[bl][1]
                if la != lb:
                    continue
                # 区域类（装修/下方/无色）为覆盖层：可与棋子/实体/制造机叠放（门下棋子合法）
                if occ[a][3] or occ[bl][3]:
                    continue
                # floor 双色配对：同 groupID（一枚 floor=1）同格双层合法
                if occ[a][5] is not None and occ[bl][5] == occ[a][5] and (occ[a][4] or occ[bl][4]):
                    continue
                sa, sb = occ[a][2], occ[bl][2]
                inter = sa & sb
                if inter:
                    self.err(f"{occ[a][0]} 与 {occ[bl][0]} 同层占格冲突 {sorted(inter)[:3]}")

# -*- coding: utf-8 -*-
"""Level-Maker 可解性求解器 —— 阶段①基础对消（可解性 DFS + 最少步数 A*）。

完整状态搜索；算子语义按 twoblocks-frontend 源码锁定（docs/solver-design.md §8）：
  * 簇 = groupID 全部块（双色 floor 叠层 + 绑定异位同组），整体拖拽、相对偏移固定。
  * 匹配只发生在 floor==0 且未包装的块；同 LogicColor（含 NULL==NULL）、同层、四邻相邻。
  * 双色剥壳 = floor0 外壳对消 + 组内 floor 落层（HandleGroupBlockFall）把 floor1 内核落回 floor0。
  * 无色包装 = 每枚独立 countdown，每次非自身 BLOCK_MATCH 减 1，到 0 露出 lockedColor。
  * 阶段①建模范围：无 entities / bombSecs / stepLock / keyLock / lock / key / withKey / star。

用法：solve_level(level_dict)=可解性；solve_min_steps(level_dict)=最少步数；批量 python3 solver.py <dir>
"""
import json, os, sys, glob, re, time, heapq
from collections import deque, defaultdict
from functools import lru_cache

from base import block_local_poses, WALL_CYCLE_PIPE, BLOCK_TYPE_POSES, rot_poses

NULL = -1
MODE_VER, MODE_HOR = 1, 2
_EMPTY_FS = frozenset()

# Block 不可变 tuple 字段序（17 元）：
#   0 color  1 wrapped  2 countdown  3 gx  4 gy  5 local  6 layer
#   7 moveMode  8 floor  9 group  10 star  11 stepLock  12 bombSecs
#   13 keyLock  14 lock  15 key  16 withKey
B_COLOR=0; B_WRAPPED=1; B_CD=2; B_GX=3; B_GY=4; B_LOCAL=5; B_LAYER=6
B_MODE=7; B_FLOOR=8; B_GROUP=9; B_STAR=10; B_STEP=11; B_BOMB=12

@lru_cache(maxsize=None)
def _world(gx, gy, local):
    return frozenset((gx+dx, gy+dy) for (dx,dy) in local)


def block_world(b):
    return _world(b[B_GX], b[B_GY], b[B_LOCAL])


# ---------------------------------------------------------------------------
# 载入
# ---------------------------------------------------------------------------
def _matchlock(blk):
    for a in (blk.get("abilities") or []):
        if a.get("abilityName") == "MatchLockAbility":
            count = None; locked = None
            for f in (a.get("fields") or []):
                k = f.get("Key")
                if k == "count": count = f.get("Value")
                elif k == "lockedColor": locked = f.get("Value")
            return (count if count is not None else 1), locked
    return None

def load_blocks(level):
    out = []
    for b in (level.get("blocks") or []):
        layer = b.get("layer", 20); layer = 30 if layer == 40 else layer
        mode = b.get("moveMode", 0)
        floor = b.get("floor", 0)
        group = b.get("groupID", 0) or 0
        star = bool(b.get("withStar") or b.get("hasStar"))
        gp = b.get("gridPos") or {}
        gx, gy = gp.get("x",0), gp.get("y",0)
        local = block_local_poses(b)
        if local is None:
            local = [(0,0)]
        local = tuple(sorted(local))

        ml = _matchlock(b)
        color = NULL if b.get("color") is None else int(b.get("color"))
        wrapped, countdown = False, 0
        if ml is not None:
            cnt, locked = ml
            if locked is not None:
                color = int(locked)
            if cnt is not None and cnt > 0:
                wrapped, countdown = True, int(cnt)

        out.append((color, wrapped, countdown, gx, gy, local, layer, mode, floor, group, star,
                    b.get("stepLock",0) or 0, b.get("bombSecs",0) or 0,
                    b.get("keyLock",0) or 0, b.get("lock",0) or 0,
                    b.get("key",0) or 0, b.get("withKey", False)))
    return out

def _fields_of_entity(e, ability_name):
    out = {}
    for a in (e.get("abilities") or []):
        if a.get("abilityName") == ability_name:
            for f in (a.get("fields") or []):
                out[f.get("Key")] = f.get("Value")
    return out


def phase1_issues(blocks, level):
    issues = []
    ents = level.get("entities") or []
    # 阶段②③允许 ManualBlockDispenser/DecorationArea/ShieldArea/LowerArea；其余实体仍 not-modeled
    _allowed_ent = {"ManualBlockDispenser", "DecorationArea", "ShieldArea", "LowerArea", "IceShaver", "ColorTrain"}
    other = sorted({e.get("entityName") for e in ents
                    if e.get("entityName") and e.get("entityName") not in _allowed_ent})
    if other:
        issues.append("entities:" + ",".join(other))
    # iceArea 已进状态（区域制冰冻），不再 not-modeled
    for b in blocks:
        if b[B_STAR]: issues.append("star")
        # stepLock 已进状态（非自身匹配 -1 解锁），不再 not-modeled
        if b[12]: issues.append("bombSecs")
        if b[13]: issues.append("keyLock")
        if b[14]: issues.append("lock")
        if b[15]: issues.append("key")
        if b[16]: issues.append("withKey")
    # 制造机产出项带 stepLock/bomb/key/star → 阶段②暂不建模
    for e in ents:
        if e.get("entityName") != "ManualBlockDispenser":
            continue
        fields = _fields_of_entity(e, "ManualBlockDispenserAbility")
        for it in (fields.get("items") or []):
            if not it:
                continue
            if it.get("stepLock") or it.get("bombSecs") or it.get("key") or it.get("lock") \
               or it.get("keyLock") or it.get("withKey") or it.get("withStar") or it.get("hasStar"):
                issues.append("dispenser-item:stepLock/bomb/key/star")
                break
    return sorted(set(issues))

# ---------------------------------------------------------------------------
# 制造机（阶段②）辅助：机身/开口/preview/拖出（据 ManualBlockDispenserAbility.cs）
# ---------------------------------------------------------------------------
def _disp_btoa(rotation):
    return {0: (-1, 0), 1: (0, -1), 2: (1, 0), 3: (0, 1)}[rotation % 4]

def _disp_atob(rotation):
    dx, dy = _disp_btoa(rotation)
    return (-dx, -dy)

def disp_body_local(rotation):
    return rot_poses([(0,0),(0,1),(0,2),(1,0),(1,1),(1,2)], rotation)

def disp_b_local(rotation):
    return rot_poses([(1,0),(1,1),(1,2)], rotation)

def disp_body_cells(gx, gy, rotation):
    return frozenset((gx+dx, gy+dy) for (dx,dy) in disp_body_local(rotation))

def disp_item_local(item, disp_rotation):
    """产出块最终局部格（= rot_poses(type, (dispenser.rotation+item.rotation)%4))。"""
    if item.get("useCustomSize"):
        w = item.get("customWidth") or 1; h = item.get("customHeight") or 1
        poses = [(x, y) for x in range(w) for y in range(h)]
    else:
        t = item.get("type", 0)
        poses = BLOCK_TYPE_POSES.get(t, [(0,0)])
    combined = ((disp_rotation % 4) + (item.get("rotation") or 0)) % 4
    return tuple(sorted(rot_poses(list(poses), combined)))

def disp_preview_anchor(gx, gy, rotation, block_local):
    bGrids = disp_b_local(rotation); blockGrids = block_local
    bx, by = _disp_btoa(rotation)
    bminx = min(p[0] for p in bGrids); bmaxx = max(p[0] for p in bGrids)
    bminy = min(p[1] for p in bGrids); bmaxy = max(p[1] for p in bGrids)
    bmnx = min(p[0] for p in blockGrids); bmxx = max(p[0] for p in blockGrids)
    bmny = min(p[1] for p in blockGrids); bmxy = max(p[1] for p in blockGrids)
    if bx < 0: lx = bmaxx - bmxx
    elif bx > 0: lx = bminx - bmnx
    else: lx = bminx - bmnx
    if by < 0: ly = bmaxy - bmxy
    elif by > 0: ly = bminy - bmny
    else: ly = bmaxy - bmxy
    if bx != 0 and bmxy - bmny + 1 == 1:
        off = (bmaxy - bminy + 1 - (bmxy - bmny + 1)) // 2
        ly = bminy + off - bmny
    if bx == 0 and bmxx - bmnx + 1 == 1:
        off = (bmaxx - bminx + 1 - (bmxx - bmnx + 1)) // 2
        lx = bminx + off - bmnx
    return (gx + lx, gy + ly)

def disp_extract_anchor(gx, gy, rotation, block_local, cells, occ):
    """沿拖出方向把 block 滑到「完全在机身外」的最近格；返回 (anchor, world) 或 None。"""
    px, py = disp_preview_anchor(gx, gy, rotation, block_local)
    dx, dy = _disp_atob(rotation)
    body = disp_body_cells(gx, gy, rotation)
    k = 1
    while k <= 64:
        ax, ay = px + dx*k, py + dy*k
        world = frozenset((ax+lx, ay+ly) for (lx,ly) in block_local)
        if not (world & body):
            if all(c in cells and c not in occ for c in world):
                return (ax, ay), world
            return None  # 出口被占 → 无法拖出
        k += 1
    return None

def _item_spec(item, disp_rotation):
    local = disp_item_local(item, disp_rotation)
    color = item.get("color")
    ml = _matchlock(item)
    wrapped, cd = False, 0
    if ml is not None:
        cnt, locked = ml
        if locked is not None:
            color = int(locked)
        elif color is None:
            color = NULL
        if cnt is not None and cnt > 0:
            wrapped, cd = True, int(cnt)
    color = NULL if color is None else int(color)
    mode = item.get("moveMode", 0) or 0
    return (color, wrapped, cd, local, mode,
            bool(item.get("withStar") or item.get("hasStar")),
            item.get("stepLock",0) or 0, item.get("bombSecs",0) or 0,
            item.get("keyLock",0) or 0, item.get("lock",0) or 0,
            item.get("key",0) or 0, item.get("withKey", False))

def _spec_to_block(spec, ax, ay, layer):
    (color, wrapped, cd, local, mode, star, stepLock, bomb, keyLock, lock, key, withKey) = spec
    return (color, wrapped, cd, ax, ay, local, layer, mode, 0, 0,
            star, stepLock, bomb, keyLock, lock, key, withKey)


def load_model(level):
    cells = set()
    for c in (level.get("cells") or []):
        gp = c.get("gridPos") or {}
        cells.add((gp.get("x", 0), gp.get("y", 0)))
    cells = frozenset(cells)
    cell_color = {}
    for c in (level.get("cells") or []):
        col = c.get("color", NULL)
        if col != NULL:
            gp = c.get("gridPos") or {}
            cell_color[(gp.get("x",0), gp.get("y",0))] = int(col)
    walls_by_layer = defaultdict(set)
    for w in (level.get("walls") or []):
        if w.get("type") != WALL_CYCLE_PIPE: continue
        gp = w.get("gridPos") or {}
        layer = w.get("layer", 20); layer = 30 if layer == 40 else layer
        walls_by_layer[layer].add((gp.get("x",0), gp.get("y",0)))
    blocks = load_blocks(level)
    # 制造机（阶段②）：每台 = (gx, gy, rotation, layer, queue_of_specs)
    dispensers = []
    for e in (level.get("entities") or []):
        if e.get("entityName") != "ManualBlockDispenser":
            continue
        fields = _fields_of_entity(e, "ManualBlockDispenserAbility")
        gp = e.get("gridPos") or {}
        gx, gy = gp.get("x", 0), gp.get("y", 0)
        layer = e.get("layer", 20); layer = 30 if layer == 40 else layer
        rotation = (fields.get("rotation", 0) or 0) % 4
        queue = []
        for it in (fields.get("items") or []):
            if not it:
                continue
            spec = _item_spec(it, rotation)
            for _ in range(int(it.get("quantity", 1) or 1)):
                queue.append(spec)
        dispensers.append((gx, gy, rotation, layer, tuple(queue)))
    # 无色区域（静态禁消矩形）+ 装修区域（HP 解锁，覆盖格阻挡）
    shields = []
    decorations = []
    lower_areas = []
    iceshavers = []
    trains = []
    for e in (level.get("entities") or []):
        name = e.get("entityName")
        gp = e.get("gridPos") or {}
        gx, gy = gp.get("x", 0), gp.get("y", 0)
        if name == "ShieldArea":
            f = _fields_of_entity(e, "ShieldAreaAbility")
            w = f.get("width", 0) or 0; h = f.get("height", 0) or 0
            shields.append(frozenset((gx+dx, gy+dy) for dx in range(w) for dy in range(h)))
        elif name == "DecorationArea":
            f = _fields_of_entity(e, "DecorationAreaAbility")
            w = f.get("width", 0) or 0; h = f.get("height", 0) or 0
            hp = f.get("hp", 0) or 0
            layer = e.get("layer", 20); layer = 30 if layer == 40 else layer
            decorations.append((gx, gy, w, h, layer, hp))
        elif name == "LowerArea":
            f = _fields_of_entity(e, "LowerAreaAbility")
            w = f.get("width", 0) or 0; h = f.get("height", 0) or 0
            lower_areas.append((gx, gy, w, h, False))  # (gx,gy,w,h,unlocked)
        elif name == "IceShaver":
            f = _fields_of_entity(e, "IceShaverAbility")
            orient = f.get("orientation", 0) or 0
            lhp = f.get("leftHp", 0) or 0
            rhp = f.get("rightHp", 0) or 0
            lc = f.get("leftColor"); lc = NULL if lc is None else int(lc)
            rc = f.get("rightColor"); rc = NULL if rc is None else int(rc)
            iceshavers.append((gx, gy, orient, lhp, rhp, lc, rc))
        elif name == "ColorTrain":
            f = _fields_of_entity(e, "ColorTrainAbility")
            carrs = f.get("carriages") or []
            chain = [(gx, gy)]
            layers = []
            pos = (gx, gy)
            for i, c in enumerate(carrs):
                if not c:
                    continue
                if i >= 1:
                    d = _train_dir(c.get("directionFromPrevious", 0) or 0)
                    pos = (pos[0]+d[0], pos[1]+d[1])
                    chain.append(pos)
                if c.get("type") == 1:  # Colored 车厢
                    for blk in (c.get("blocks") or []):
                        if blk and blk.get("color") is not None:
                            layers.append(int(blk.get("color")))
            trains.append((gx, gy, tuple(chain), tuple(layers)))  # chain = 头→尾有序链
    # 冰区：cellType=1 连通组件 + iceArea[组件]=层数
    ice_pos = set()
    for c in (level.get("cells") or []):
        if c.get("cellType", 0) == 1:
            gp = c.get("gridPos") or {}
            ice_pos.add((gp.get("x", 0), gp.get("y", 0)))
    ice_areas = []
    if ice_pos:
        parent = {p: p for p in ice_pos}
        def _find(p):
            while parent[p] != p:
                parent[p] = parent[parent[p]]
                p = parent[p]
            return p
        def _union(a, b):
            ra, rb = _find(a), _find(b)
            if ra != rb:
                parent[rb] = ra
        for (x, y) in ice_pos:
            for n in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                if n in ice_pos:
                    _union((x, y), n)
        g = defaultdict(list)
        for p in ice_pos:
            g[_find(p)].append(p)
        comps = sorted((sorted(v) for v in g.values()), key=lambda s: s[0])
        ice_area = level.get("iceArea") or {}
        vals = [int(ice_area.get(k, 1)) for k in sorted(ice_area.keys())]
        for i, comp in enumerate(comps):
            layers = vals[i] if i < len(vals) else 1
            ice_areas.append((frozenset(comp), max(1, layers)))
    return {"cells": cells, "cell_color": cell_color,
            "walls_by_layer": dict(walls_by_layer), "blocks": blocks,
            "dispensers": tuple(dispensers),
            "shields": tuple(shields),
            "decorations": tuple(decorations),
            "lower_areas": tuple(lower_areas),
            "iceshavers": tuple(iceshavers),
            "ice_areas": tuple(ice_areas),
            "trains": tuple(trains)}


# ---------------------------------------------------------------------------
# 簇 & 可达性
# ---------------------------------------------------------------------------
def build_clusters(blocks):
    # groupID>0 = 一个簇（双色叠层/绑定异位混合）；groupID=0 = 各自独立簇
    bygroup = defaultdict(list)
    singles = []
    for i, b in enumerate(blocks):
        if b[B_GROUP] > 0:
            bygroup[b[B_GROUP]].append(i)
        else:
            singles.append(i)
    out = []
    for g, idxs in sorted(bygroup.items()):
        ref = min(idxs, key=lambda i: (0 if blocks[i][B_FLOOR]==0 else 1, blocks[i][B_GX], blocks[i][B_GY], i))
        rx, ry = blocks[ref][B_GX], blocks[ref][B_GY]
        members = tuple((i, blocks[i][B_GX]-rx, blocks[i][B_GY]-ry) for i in idxs)
        out.append((ref, members))
    for i in singles:
        out.append((i, ((i, 0, 0),)))
    return out

def reachable_anchors(blocks, cluster, model, occ_by_layer, occ_extra=_EMPTY_FS):
    ref, members = cluster
    rx, ry = blocks[ref][B_GX], blocks[ref][B_GY]
    layer = blocks[ref][B_LAYER]
    cluster_set = {i for i,_,_ in members}
    axis_h = all(blocks[i][B_MODE] != MODE_VER for i,_,_ in members)
    axis_v = all(blocks[i][B_MODE] != MODE_HOR for i,_,_ in members)

    # 自身世界格不阻挡自己；其余同层块 + 静态障碍（机身/装修覆盖）阻挡
    self_world = set()
    for i,_,_ in members:
        self_world |= _world(blocks[i][B_GX], blocks[i][B_GY], blocks[i][B_LOCAL])
    # 自身块网格不阻挡自己（从「同层块占格」里剔除）；静态障碍（机身/装修覆盖）不剔除，
    # 即便与本簇自占格重叠也按旧语义照拦（装修覆盖格阻挡）。
    occ = (occ_by_layer.get(layer, _EMPTY_FS) - self_world) | occ_extra
    walls = model["walls_by_layer"].get(layer, _EMPTY_FS)
    cells = model["cells"]
    cell_color = model["cell_color"]

    minfo = [(blocks[i], ox, oy) for (i,ox,oy) in members]
    def feasible(gx, gy):
        for (b, ox, oy) in minfo:
            for (dx,dy) in b[B_LOCAL]:
                x, y = gx+ox+dx, gy+oy+dy
                if (x,y) not in cells: return False
                if (x,y) in walls: return False
                if (x,y) in occ: return False
                fc = cell_color.get((x,y))
                if fc is not None:
                    if b[B_WRAPPED]: return False
                    if b[B_COLOR] != fc: return False
        return True

    if not feasible(rx, ry):
        return frozenset()
    seen = {(rx,ry)}
    q = deque([(rx,ry)])
    dirs = []
    if axis_h: dirs += [(1,0),(-1,0)]
    if axis_v: dirs += [(0,1),(0,-1)]
    while q:
        x, y = q.popleft()
        for dx,dy in dirs:
            nx, ny = x+dx, y+dy
            if (nx,ny) in seen: continue
            if feasible(nx,ny):
                seen.add((nx,ny)); q.append((nx,ny))
    return seen


# ---------------------------------------------------------------------------
# 结算
# ---------------------------------------------------------------------------
def shares_whole_lock(w, r):
    return (w[B_GROUP] > 0 and w[B_GROUP] == r[B_GROUP]
            and w[B_GX] == r[B_GX] and w[B_GY] == r[B_GY]
            and w[B_FLOOR] != r[B_FLOOR])

def _apply_removals(blocks, removed_idx):
    rem_blocks = [blocks[i] for i in removed_idx]
    rem_groups = {b[B_GROUP] for b in rem_blocks if b[B_GROUP] > 0}
    kept = [b for k, b in enumerate(blocks) if k not in removed_idx]

    # 组内 floor 落层（双色剥壳收尾）
    if rem_groups:
        changed = True
        while changed:
            changed = False
            for g in rem_groups:
                idxs = [k for k, b in enumerate(kept) if b[B_GROUP] == g]
                if not idxs:
                    continue
                floors = sorted({kept[k][B_FLOOR] for k in idxs})
                for fl in floors:
                    if fl == 0:
                        continue
                    below = set()
                    for k in idxs:
                        if kept[k][B_FLOOR] == fl-1:
                            below |= block_world(kept[k])
                    for k in idxs:
                        if kept[k][B_FLOOR] == fl and not (block_world(kept[k]) & below):
                            kept[k] = kept[k][:B_FLOOR] + (fl-1,) + kept[k][B_FLOOR+1:]
                            changed = True

    # 无色计数 + stepLock 解锁（每非自身消除事件各 -1）
    out = []
    for b in kept:
        lst = list(b)
        if lst[B_WRAPPED]:
            if not any(shares_whole_lock(b, r) for r in rem_blocks):
                lst[B_CD] -= 1
            if lst[B_CD] <= 0:
                lst[B_WRAPPED] = False
                lst[B_CD] = 0
        if lst[B_STEP] > 0:
            lst[B_STEP] -= 1
        out.append(tuple(lst))
    return tuple(out)


def resolve(blocks, bi, bj):
    return _apply_removals(blocks, (bi, bj))


# ---------------------------------------------------------------------------
# 规范化（簇级，去重）
# ---------------------------------------------------------------------------
@lru_cache(maxsize=400000)
def _mrec(b):
    """块 → 扁平整数元组（局部格摊平），缓存：静态块在搜索树间复用，加速。"""
    head = (b[B_COLOR], b[B_WRAPPED], b[B_CD], b[B_GX], b[B_GY],
            b[B_LAYER], b[B_MODE], b[B_FLOOR])
    return head + tuple(v for p in b[B_LOCAL] for v in p)


def _canon_blocks(blocks):
    """簇级规范化：groupID>0 成簇（id 值归一化），groupID=0 各自成簇。"""
    groups = defaultdict(list)
    singles = []
    for b in blocks:
        if b[B_GROUP] > 0:
            groups[b[B_GROUP]].append(b)
        else:
            singles.append(b)
    keys = [tuple(sorted(_mrec(b) for b in members)) for members in groups.values()]
    keys += [(_mrec(b),) for b in singles]
    return tuple(sorted(keys))


def _canon_disp(dispensers):
    return tuple(sorted(
        (gx, gy, rot, layer, tuple((q[B_COLOR], q[B_WRAPPED], q[B_CD], q[B_LOCAL], q[B_MODE]) for q in queue))
        for (gx, gy, rot, layer, queue) in dispensers))


def _canon_dec(decorations):
    return tuple(sorted((gx, gy, w, h, layer, hp) for (gx, gy, w, h, layer, hp) in decorations))


def _canon_lower(lower_areas):
    return tuple(sorted((gx, gy, w, h, unlocked) for (gx, gy, w, h, unlocked) in lower_areas))


def _canon_shave(iceshavers):
    return tuple(sorted((gx, gy, orient, lhp, rhp, lc, rc)
                        for (gx, gy, orient, lhp, rhp, lc, rc) in iceshavers))


def _canon_ice(ice_areas):
    return tuple(sorted((tuple(sorted(cells)), layers) for (cells, layers) in ice_areas))


def _canon_train(trains):
    return tuple(sorted((gx, gy, tuple(sorted(cells)), layers)
                        for (gx, gy, cells, layers) in trains))


def canonical_key(state):
    blocks, dispensers, decorations, lower_areas, iceshavers, ice_areas, trains = state
    return (_canon_blocks(blocks), _canon_disp(dispensers), _canon_dec(decorations),
            _canon_lower(lower_areas), _canon_shave(iceshavers), _canon_ice(ice_areas),
            _canon_train(trains))


def alive_body_cells(dispensers):
    occ = set()
    for (gx, gy, rot, layer, queue) in dispensers:
        if queue:
            occ |= disp_body_cells(gx, gy, rot)
    return frozenset(occ)


def _shield_union(shields):
    s = set()
    for r in shields:
        s |= r
    return frozenset(s)


def _dec_cells(d):
    gx, gy, w, h, layer, hp = d
    return frozenset((gx+dx, gy+dy) for dx in range(w) for dy in range(h))


def _dec_locked_cells(decorations):
    occ = set()
    for d in decorations:
        if d[5] > 0:
            occ |= _dec_cells(d)
    return frozenset(occ)


def _dec_decs(decorations):
    out = []
    for d in decorations:
        gx, gy, w, h, layer, hp = d
        if hp <= 0:
            continue
        hp -= 1
        if hp > 0:
            out.append((gx, gy, w, h, layer, hp))
    return tuple(out)


def _block_covered(b, locked_cells):
    return bool(locked_cells) and block_world(b) <= locked_cells


def _block_in_shield(b, shields):
    return bool(shields) and bool(block_world(b) & shields)


def _lower_cells(la):
    gx, gy, w, h, unlocked = la
    return frozenset((gx+dx, gy+dy) for dx in range(w) for dy in range(h))


def _hidden_cells(lower_areas):
    occ = set()
    for la in lower_areas:
        if not la[4]:  # 未解锁
            occ |= _lower_cells(la)
    return frozenset(occ)


def _is_hidden(b, hidden_cells):
    # 仅「layer=10 且落在未解锁下方区域内」的块才是隐藏内容
    return b[B_LAYER] == 10 and bool(hidden_cells) and block_world(b) <= hidden_cells


def _train_dir(code):
    return {(0): (1, 0), (1): (0, 1), (2): (-1, 0), (3): (0, -1)}.get(code, (1, 0))


def _shave_dir(orient):
    return (1, 0) if orient == 0 else (0, 1)


def _shave_segments(s):
    gx, gy, orient, lhp, rhp, lc, rc = s
    dx, dy = _shave_dir(orient)
    left = frozenset((gx-dx*i, gy-dy*i) for i in range(1, lhp+1))
    right = frozenset((gx+dx*i, gy+dy*i) for i in range(1, rhp+1))
    return left, right


def _shave_body_cells(s):
    left, right = _shave_segments(s)
    body = set(left) | set(right)
    if s[3] + s[4] > 0:
        body.add((s[0], s[1]))
    return frozenset(body)


def _shave_alive(s):
    return s[3] + s[4] > 0


def _shave_all_body(iceshavers):
    occ = set()
    for s in iceshavers:
        if _shave_alive(s):
            occ |= _shave_body_cells(s)
    return frozenset(occ)


def _iced_cells(ice_areas):
    occ = set()
    for (cells, layers) in ice_areas:
        if layers > 0:
            occ |= cells
    return frozenset(occ)


def _ice_decs(ice_areas):
    out = []
    for (cells, layers) in ice_areas:
        layers -= 1
        if layers > 0:
            out.append((cells, layers))
    return tuple(out)


def _is_iced(b, iced_cells):
    return bool(iced_cells) and block_world(b) <= iced_cells


def _train_alive(t):
    return bool(t[3])


def _train_all_cells(trains):
    occ = set()
    for t in trains:
        if _train_alive(t):
            occ |= set(t[2])
    return frozenset(occ)


def _train_remove_head(trains, ti):
    out = []
    for i, t in enumerate(trains):
        gx, gy, cells, layers = t
        if i == ti and layers:
            out.append((gx, gy, cells, layers[1:]))
        else:
            out.append(t)
    return tuple(out)


def _train_remove_linked(trains, color):
    out = list(trains)
    removed = 0
    while removed < 2:
        done = False
        for i in range(len(out)):
            t = out[i]
            if t[3] and t[3][0] == color:
                out[i] = (t[0], t[1], t[2], t[3][1:])
                removed += 1
                done = True
                break
        if not done:
            break
    return tuple(out)


def _ice_shave_one(iceshavers, si, end):
    out = []
    for i, s in enumerate(iceshavers):
        if i == si:
            gx, gy, orient, lhp, rhp, lc, rc = s
            if end == 0:
                lhp = max(0, lhp - 1)
            else:
                rhp = max(0, rhp - 1)
            out.append((gx, gy, orient, lhp, rhp, lc, rc))
        else:
            out.append(s)
    return tuple(out)


def _ice_passive(iceshavers, color):
    out = []
    for s in iceshavers:
        gx, gy, orient, lhp, rhp, lc, rc = s
        if lhp > 0 and lc == color:
            lhp = max(0, lhp - 2)
        if rhp > 0 and rc == color:
            rhp = max(0, rhp - 2)
        out.append((gx, gy, orient, lhp, rhp, lc, rc))
    return tuple(out)


def _apply_lower_unlock(blocks, lower_areas):
    """表面清空 → 解锁并抬升区内 layer=10 块到 layer=20（LowerArea CompleteUnlock）。"""
    if not lower_areas:
        return blocks, lower_areas
    surface = set()
    for b in blocks:
        if b[B_LAYER] != 10:
            surface |= block_world(b)
    changed = False
    new_las = []
    for la in lower_areas:
        gx, gy, w, h, unlocked = la
        if unlocked or (_lower_cells(la) & surface):
            new_las.append(la)
        else:
            new_las.append((gx, gy, w, h, True))
            changed = True
    if not changed:
        return blocks, lower_areas
    unlocked_cells = set()
    for la in new_las:
        if la[4]:
            unlocked_cells |= _lower_cells(la)
    nb = []
    for b in blocks:
        if b[B_LAYER] == 10 and (block_world(b) & unlocked_cells):
            nb.append(b[:B_LAYER] + (20,) + b[B_LAYER+1:])
        else:
            nb.append(b)
    return tuple(nb), tuple(new_las)


# ---------------------------------------------------------------------------
# 后继：拖到目标后确定性结算至多一个匹配（返回 (is_match, state)）
# ---------------------------------------------------------------------------
def step_state(blocks, members, dx, dy, moved, stat_global, shields=(), locked_cells=(), iceshavers=(), hidden_cells=(), iced_cells=(), trains=()):
    """返回 (kind, succ_blocks, extra)：kind ∈ match/shave/none。
    优先级：搓冰机相撞 > 普通对消（同 ResolveImmediateDragInteractions）。
    stat_global = 静态可匹配块（按 (gx,gy,color,local) 预排序的 (j,b) 列表），此处仅过滤掉本簇。"""
    cluster_set = {i for i,_,_ in members}
    cand = [(i, moved[i]) for i,_,_ in members
            if moved[i][B_FLOOR] == 0 and not moved[i][B_WRAPPED]
            and not _block_covered(moved[i], locked_cells)
            and not _block_in_shield(moved[i], shields)
            and not _is_hidden(moved[i], hidden_cells)
            and not _is_iced(moved[i], iced_cells)]
    cand.sort(key=lambda t: (t[1][B_GX], t[1][B_GY], t[1][B_COLOR], t[1][B_LOCAL]))
    stat = [(j, b) for (j, b) in stat_global if j not in cluster_set]
    # 搓冰机相撞（同色 + 与颜色段四邻相邻 → 消费该块 + 该段 HP-1）
    for (mi, mb) in cand:
        for si, s in enumerate(iceshavers):
            if not _shave_alive(s):
                continue
            left, right = _shave_segments(s)
            lc, rc = s[5], s[6]
            for (x, y) in block_world(mb):
                for n in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                    if mb[B_COLOR] == lc and n in left:
                        return ("shave", _apply_removals(moved, (mi,)), (si, 0, lc))
                    if mb[B_COLOR] == rc and n in right:
                        return ("shave", _apply_removals(moved, (mi,)), (si, 1, rc))
    # 颜色火车端部消耗（头/尾层同色 + 相邻 → 消费该块 + 移除该层）
    for (mi, mb) in cand:
        for ti, tr in enumerate(trains):
            if not _train_alive(tr):
                continue
            cells, layers = tr[2], tr[3]
            ends = [(cells[0], layers[0], True)] if layers else []
            if len(cells) > 1 and layers:
                ends.append((cells[-1], layers[-1], False))
            for (x, y) in block_world(mb):
                for n in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                    for (end_cell, end_color, from_head) in ends:
                        if n == end_cell and mb[B_COLOR] == end_color:
                            return ("train", _apply_removals(moved, (mi,)), (ti, from_head))
    # 普通对消
    for (mi, mb) in cand:
        neigh = set()
        for (x,y) in block_world(mb):
            neigh.update(((x+1,y),(x-1,y),(x,y+1),(x,y-1)))
        for (sj, sb) in stat:
            if mb[B_LAYER] != sb[B_LAYER]: continue
            if mb[B_COLOR] != sb[B_COLOR]: continue
            if mb[B_STAR] and not sb[B_STAR]: continue
            if not (block_world(sb) & neigh): continue
            return ("match", resolve(moved, mi, sj), (mb[B_COLOR],))
    return ("none", moved, None)


# ---------------------------------------------------------------------------
# 后继生成（单调剪枝：有对消只走对消，无可消才走一步定位）
# ---------------------------------------------------------------------------
def _extract_successors(blocks, dispensers, decorations, lower_areas, iceshavers, ice_areas, trains, model):
    """拖出算子：队首从出口滑出为普通块（1 步）；机身占格仍在（queue 未空）。"""
    out = []
    if not dispensers:
        return out
    hidden_cells = _hidden_cells(lower_areas)
    occ_blocks = set()
    for b in blocks:
        if not _is_hidden(b, hidden_cells):        # 隐藏块不阻挡
            occ_blocks |= block_world(b)
    locked_cells = _dec_locked_cells(decorations)
    for i, (gx, gy, rot, layer, queue) in enumerate(dispensers):
        if not queue:
            continue
        head = queue[0]
        other = set(occ_blocks) | locked_cells
        for j, (dx2, dy2, rot2, l2, q2) in enumerate(dispensers):
            if j != i and q2:
                other |= disp_body_cells(dx2, dy2, rot2)
        ex = disp_extract_anchor(gx, gy, rot, head[3], model["cells"], other)
        if ex is None:
            continue
        (ax, ay), _world = ex
        nb = _spec_to_block(head, ax, ay, layer)
        new_blocks = tuple(sorted(blocks + (nb,)))
        nd = list(dispensers)
        nd[i] = (gx, gy, rot, layer, queue[1:])
        nb2, nla = _apply_lower_unlock(new_blocks, lower_areas)
        out.append((nb2, tuple(nd), decorations, nla, iceshavers, ice_areas, trains))
    return out


def successors(state, model):
    blocks, dispensers, decorations, lower_areas, iceshavers, ice_areas, trains = state
    hidden_cells = _hidden_cells(lower_areas)
    iced_cells = _iced_cells(ice_areas)
    model_shields = _shield_union(model.get("shields", ()))
    body_occ = alive_body_cells(dispensers) | _shave_all_body(iceshavers) | _train_all_cells(trains)
    locked_cells = _dec_locked_cells(decorations)
    occ_extra = body_occ | locked_cells

    # 预计算：分层的「同层块占格」（隐藏块按现有语义随所在层处理）
    occ_by_layer = {}
    for i, b in enumerate(blocks):
        occ_by_layer.setdefault(b[B_LAYER], set()).update(_world(b[B_GX], b[B_GY], b[B_LOCAL]))
    occ_by_layer = {l: frozenset(s) for l, s in occ_by_layer.items()}

    # 预计算：静态可匹配块（后续 step_state 仅过滤本簇；排序键与 cand 一致）
    stat_global = sorted(
        ((j, b) for j, b in enumerate(blocks)
         if b[B_FLOOR] == 0 and not b[B_WRAPPED]
         and not _block_in_shield(b, model_shields)
         and b[B_STEP] <= 0
         and not _is_hidden(b, hidden_cells)
         and not _is_iced(b, iced_cells)),
        key=lambda t: (t[1][B_GX], t[1][B_GY], t[1][B_COLOR], t[1][B_LOCAL]))

    match_succs = []
    repos_succs = []
    for (ref, members) in build_clusters(blocks):
        if not any(blocks[i][B_FLOOR] == 0 for i,_,_ in members):
            continue
        if _block_covered(blocks[ref], locked_cells):
            continue  # 被锁装修区域完全覆盖 → 不可拖
        if any(blocks[i][B_STEP] > 0 for i,_,_ in members):
            continue  # stepLock>0 → 整簇不可拖
        if any(_is_hidden(blocks[i], hidden_cells) for i,_,_ in members):
            continue  # 下方区域隐藏块不可拖
        if any(_is_iced(blocks[i], iced_cells) for i,_,_ in members):
            continue  # 全冰覆盖 → 不可拖
        rx, ry = blocks[ref][B_GX], blocks[ref][B_GY]
        cluster_set = {i for i,_,_ in members}
        for (ax, ay) in reachable_anchors(blocks, (ref, members), model, occ_by_layer, occ_extra):
            dx, dy = ax-rx, ay-ry
            moved = tuple(
                blocks[k] if k not in cluster_set else
                blocks[k][:B_GX] + (blocks[k][B_GX]+dx,) + (blocks[k][B_GY]+dy,) + blocks[k][B_GY+1:]
                for k in range(len(blocks))
            )
            kind, succ, extra = step_state(blocks, members, dx, dy, moved, stat_global,
                                           shields=model_shields, locked_cells=locked_cells,
                                           iceshavers=iceshavers, hidden_cells=hidden_cells,
                                           iced_cells=iced_cells, trains=trains)
            sb, sla = _apply_lower_unlock(succ, lower_areas)
            if kind == "match":
                ns = _ice_passive(iceshavers, extra[0])  # 搓冰机被动 -2
                nt = _train_remove_linked(trains, extra[0])  # 火车联动：最多 2 层
                match_succs.append((sb, dispensers, _dec_decs(decorations), sla, ns, _ice_decs(ice_areas), nt))
            elif kind == "shave":
                si, end, _c = extra
                ns = _ice_shave_one(iceshavers, si, end)  # 搓冰机相撞 -1
                match_succs.append((sb, dispensers, decorations, sla, ns, _ice_decs(ice_areas), trains))
            elif kind == "train":
                ti, from_head = extra
                nt = _train_remove_head(trains, ti)  # 火车端部消耗 1 层
                match_succs.append((sb, dispensers, decorations, sla, iceshavers, ice_areas, nt))
            elif abs(dx) + abs(dy) == 1:
                repos_succs.append((sb, dispensers, decorations, sla, iceshavers, ice_areas, trains))
    if match_succs:
        return match_succs
    return repos_succs + _extract_successors(blocks, dispensers, decorations, lower_areas, iceshavers, ice_areas, trains, model)


def _h(state):
    # 可采纳下界：每次宏动作至多移除 2 块 → 至少 ceil(B/2) 步
    return (len(state[0]) + 1) // 2

INF = float("inf")

def _match_gap(blocks, model):
    """最小「空格可达对消距离」：每个可消 floor0 块经空格走到同色伙伴相邻格的最短步数，取最小。
    INF=当前无可走到任何同色伙伴（需挪挡路块）。"""
    cells = model["cells"]; cell_color = model["cell_color"]
    occ = set()
    for b in blocks: occ |= block_world(b)
    walls = set()
    for s in model["walls_by_layer"].values(): walls |= s
    matchable = [b for b in blocks if b[B_FLOOR] == 0 and not b[B_WRAPPED]]
    if len(matchable) < 2:
        return INF
    best = INF
    seen_color = set()
    for a in matchable:
        if a[B_COLOR] in seen_color:
            continue
        seen_color.add(a[B_COLOR])
        partners = [b for b in blocks if b is not a and b[B_COLOR]==a[B_COLOR]
                    and b[B_FLOOR]==0 and not b[B_WRAPPED]]
        if not partners:
            continue
        part_cells = set()
        for p in partners: part_cells |= block_world(p)
        start = block_world(a)
        q = deque(); dist = {}
        for c in start:
            if c in cells and c not in occ and c not in walls:
                dist[c] = 0; q.append(c)
        while q:
            c = q.popleft(); d = dist[c]
            if d >= best: continue
            for (x,y) in ((c[0]+1,c[1]),(c[0]-1,c[1]),(c[0],c[1]+1),(c[0],c[1]-1)):
                if (x,y) in part_cells:
                    best = min(best, d); break
            for (x,y) in ((c[0]+1,c[1]),(c[0]-1,c[1]),(c[0],c[1]+1),(c[0],c[1]-1)):
                if (x,y) not in cells or (x,y) in occ or (x,y) in walls or (x,y) in dist:
                    continue
                fc = cell_color.get((x,y))
                if fc is not None and a[B_COLOR] != fc:
                    continue
                dist[(x,y)] = d+1; q.append((x,y))
        if best == 0:
            return 0
    return best


def _parity_dead(state):
    """奇偶死锁剪枝：每个「颜色 c 的块计数（含无色包装/双色内核，它们终将揭示为该色）」
    在一次普通对消中恒减 2，揭示/剥壳不改计数 → 奇偶不变；终态全 0（偶）。
    搓冰机相撞 / 火车端部各消费 1 块、制造机可新增块 → 会打破奇偶，故有这些存活来源时不做判断。"""
    blocks, dispensers, decorations, lower_areas, iceshavers, ice_areas, trains = state
    if any(q for (gx, gy, rot, layer, q) in dispensers):
        return False
    if any(_shave_alive(s) for s in iceshavers):
        return False
    if any(_train_alive(t) for t in trains):
        return False
    cnt = defaultdict(int)
    for b in blocks:
        cnt[b[B_COLOR]] += 1
    return any(v % 2 == 1 for v in cnt.values())


def _is_goal(state):
    blocks, dispensers, decorations, lower_areas, iceshavers, ice_areas, trains = state
    # 通关 = 无块(含隐藏块) + 制造机空 + 装修区全解锁 + 无存活搓冰机 + 无存活火车(CheckGameWin)
    return (not blocks and all(not d[4] for d in dispensers)
            and all(dec[5] <= 0 for dec in decorations)
            and all(not _shave_alive(s) for s in iceshavers)
            and all(not _train_alive(t) for t in trains))


def _initial_state(model):
    return (tuple(sorted(model["blocks"])), model["dispensers"],
            model.get("decorations", ()), model.get("lower_areas", ()),
            model.get("iceshavers", ()), model.get("ice_areas", ()),
            model.get("trains", ()))


def solve_greedy(level, max_steps=800, timeout=60.0):
    """贪心可解性（快，可能假阴性）：对消必走，僵局时按 _match_gap 最优走位；命中空盘即可解。"""
    model = load_model(level)
    init_blocks = tuple(sorted(model["blocks"]))
    issues = phase1_issues(list(init_blocks), level)
    if issues:
        return {"result": "not-modeled", "reasons": issues, "states": 0, "steps": None, "time": 0.0}
    state = _initial_state(model)
    t0 = time.time()
    visited = {canonical_key(state)}
    steps = 0
    while not _is_goal(state):
        if time.time()-t0 > timeout or steps >= max_steps:
            return {"result": "timeout", "reasons": [], "states": len(visited), "steps": None, "time": time.time()-t0}
        succs = successors(state, model)
        if not succs:
            break
        if len(succs) == 1:
            state = succs[0]
        else:
            state = min(succs, key=lambda s: _match_gap(s[0], model))
        key = canonical_key(state)
        if key in visited:
            break
        visited.add(key)
        steps += 1
    return {"result": "solvable" if _is_goal(state) else "greedy-fail", "reasons": [],
            "states": len(visited), "steps": steps if _is_goal(state) else None, "time": time.time()-t0}


# ---------------------------------------------------------------------------
# 可解性 DFS（找任一解，快；steps 是某条解的长度，非最短）
# ---------------------------------------------------------------------------
def solve_level(level, max_states=500000, max_depth=300, timeout=60.0):
    model = load_model(level)
    init_blocks = tuple(sorted(model["blocks"]))
    issues = phase1_issues(list(init_blocks), level)
    if issues:
        return {"result": "not-modeled", "reasons": issues, "states": 0, "steps": None, "time": 0.0}

    state = _initial_state(model)
    t0 = time.time()
    if _parity_dead(state):
        return {"result": "unsolvable", "reasons": issues, "states": 1,
                "steps": None, "time": time.time()-t0}
    visited = {canonical_key(state)}
    stack = [(state, 0)]

    while stack:
        cur, depth = stack.pop()
        if _is_goal(cur):
            return {"result": "solvable", "reasons": [], "states": len(visited),
                    "steps": depth, "time": time.time()-t0}
        if time.time()-t0 > timeout:
            return {"result": "timeout", "reasons": issues, "states": len(visited),
                    "steps": None, "time": time.time()-t0}
        if depth >= max_depth or len(visited) >= max_states:
            continue
        for succ in successors(cur, model):
            if _parity_dead(succ):
                continue  # 颜色奇偶死锁，绝不达终态
            key = canonical_key(succ)
            if key not in visited:
                visited.add(key)
                stack.append((succ, depth+1))
    return {"result": "unsolvable", "reasons": issues, "states": len(visited),
            "steps": None, "time": time.time()-t0}


# ---------------------------------------------------------------------------
# 最少步数 A*（可采纳 h = ceil(B/2)；返回最优步数）
# ---------------------------------------------------------------------------
def solve_min_steps(level, max_states=500000, max_depth=300, timeout=60.0):
    model = load_model(level)
    init_blocks = tuple(sorted(model["blocks"]))
    issues = phase1_issues(list(init_blocks), level)
    if issues:
        return {"result": "not-modeled", "reasons": issues, "states": 0, "steps": None, "time": 0.0}

    state = _initial_state(model)
    t0 = time.time()
    if _parity_dead(state):
        return {"result": "unsolvable", "reasons": issues, "states": 1,
                "steps": None, "time": time.time()-t0}
    start_key = canonical_key(state)
    best = {start_key: 0}
    counter = 1
    heap = [(_h(state), 0, 0, start_key, state)]

    while heap:
        f, g, _, key, cur = heapq.heappop(heap)
        if best.get(key) != g:      # 过期条目（已被更短 g 刷新）
            continue
        if _is_goal(cur):
            return {"result": "solvable", "reasons": [], "states": len(best),
                    "steps": g, "time": time.time()-t0}
        if time.time()-t0 > timeout:
            return {"result": "timeout", "reasons": issues, "states": len(best),
                    "steps": None, "time": time.time()-t0}
        if g >= max_depth or len(best) >= max_states:
            continue
        for succ in successors(cur, model):
            if _parity_dead(succ):
                continue  # 颜色奇偶死锁，绝不达终态
            skey = canonical_key(succ)
            ng = g + 1
            if skey not in best or best[skey] > ng:
                best[skey] = ng
                counter += 1
                heapq.heappush(heap, (ng + _h(succ), ng, counter, skey, succ))
    return {"result": "unsolvable", "reasons": issues, "states": len(best),
            "steps": None, "time": time.time()-t0}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv):
    if not argv:
        print(__doc__); return 1
    target = argv[0]
    max_num = None; timeout = 60.0; max_states = 500000
    for a in argv[1:]:
        if a.startswith("--max-num="): max_num = int(a.split("=")[1])
        elif a.startswith("--timeout="): timeout = float(a.split("=")[1])
        elif a.startswith("--max-states="): max_states = int(a.split("=")[1])
    files = sorted(glob.glob(os.path.join(target, "lv_*.json"))) if os.path.isdir(target) else [target]
    tot = sol = unsol = nm = to = 0
    for f in files:
        m = re.match(r".*lv_([0-9]+)_A\.json$", f)
        if not m: continue
        if max_num is not None and int(m.group(1)) > max_num: continue
        try:
            lvl = json.load(open(f, encoding="utf-8-sig"))
        except Exception:
            continue
        tot += 1
        r = solve_level(lvl, max_states=max_states, timeout=timeout)
        if r["result"]=="solvable": sol += 1
        elif r["result"]=="unsolvable": unsol += 1
        elif r["result"]=="timeout": to += 1
        else: nm += 1
        print("%-5d %-12s steps=%-5s states=%-8s %.2fs %s" % (
            int(m.group(1)), r["result"], str(r["steps"]) if r["steps"] is not None else "-",
            r["states"], r["time"], ",".join(r["reasons"]) if r["reasons"] else ""))
    print("\n===== 阶段①基线: 共%d | 可解%d | 不可解%d | 未建模%d | 超时%d =====" % (tot, sol, unsol, nm, to))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

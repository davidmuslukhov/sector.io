"""Traffic-lane intersection graph for pursuit pathfinding (2× Chicago plate)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from city.mesh import arterial_junctions


@dataclass
class LaneNode:
    id: int
    x: float
    y: float


@dataclass
class LaneEdge:
    a: int
    b: int
    length: float
    expressway: bool = False


@dataclass
class TrafficLanesGraph:
    """Undirected intersection graph extracted from arterial polylines."""

    nodes: list[LaneNode] = field(default_factory=list)
    edges: list[LaneEdge] = field(default_factory=list)
    adj: dict[int, list[tuple[int, float, bool]]] = field(default_factory=dict)
    _cell: float = 5.275
    _grid: dict[tuple[int, int], list[int]] = field(default_factory=dict)

    def neighbors(self, node_id: int) -> list[tuple[int, float, bool]]:
        return self.adj.get(node_id, [])

    def nearest_node(
        self, x: float, y: float, *, max_dist: float = 40.0
    ) -> int | None:
        cell = self._cell
        best_i: int | None = None
        best_d2 = max_dist * max_dist
        if self._grid and cell > 0.0:
            pad = max_dist
            i0 = int(math.floor((x - pad) / cell))
            i1 = int(math.floor((x + pad) / cell))
            j0 = int(math.floor((y - pad) / cell))
            j1 = int(math.floor((y + pad) / cell))
            seen: set[int] = set()
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    for idx in self._grid.get((i, j), ()):
                        if idx in seen:
                            continue
                        seen.add(idx)
                        n = self.nodes[idx]
                        d2 = (n.x - x) * (n.x - x) + (n.y - y) * (n.y - y)
                        if d2 < best_d2:
                            best_d2 = d2
                            best_i = idx
        else:
            for n in self.nodes:
                d2 = (n.x - x) * (n.x - x) + (n.y - y) * (n.y - y)
                if d2 < best_d2:
                    best_d2 = d2
                    best_i = n.id
        return best_i

    def nodes_in_ring(
        self,
        x: float,
        y: float,
        r_min: float,
        r_max: float,
    ) -> list[int]:
        r_min2 = r_min * r_min
        r_max2 = r_max * r_max
        out: list[int] = []
        for n in self.nodes:
            d2 = (n.x - x) * (n.x - x) + (n.y - y) * (n.y - y)
            if r_min2 <= d2 <= r_max2:
                out.append(n.id)
        return out


def _quantize(x: float, y: float, step: float = 0.5) -> tuple[float, float]:
    return (round(x / step) * step, round(y / step) * step)


def build_traffic_lanes_graph(
    arterials: list[dict],
    *,
    layers: tuple[str, ...] = ("arterial", "collector", "expressway"),
    merge: float = 1.25,
) -> TrafficLanesGraph:
    """Build ``traffic_lanes_graph`` from highway arterial polylines + junctions."""
    routes = [a for a in arterials if str(a.get("layer", "arterial")) in layers]
    graph = TrafficLanesGraph()
    key_to_id: dict[tuple[float, float], int] = {}
    snap_cell = max(merge, 0.5)
    snap_grid: dict[tuple[int, int], list[tuple[tuple[float, float], int]]] = {}

    def ensure_node(x: float, y: float) -> int:
        key = _quantize(x, y)
        existing = key_to_id.get(key)
        if existing is not None:
            return existing
        nid = len(graph.nodes)
        graph.nodes.append(LaneNode(nid, key[0], key[1]))
        key_to_id[key] = nid
        gi = int(math.floor(key[0] / snap_cell))
        gj = int(math.floor(key[1] / snap_cell))
        snap_grid.setdefault((gi, gj), []).append((key, nid))
        return nid

    def snap_node(x: float, y: float) -> int:
        key = _quantize(x, y)
        existing = key_to_id.get(key)
        if existing is not None:
            return existing
        # Nearby junction within merge radius (spatial hash, not O(n)).
        best_d2 = merge * merge
        best_id: int | None = None
        gi = int(math.floor(key[0] / snap_cell))
        gj = int(math.floor(key[1] / snap_cell))
        for ii in range(gi - 1, gi + 2):
            for jj in range(gj - 1, gj + 2):
                for jkey, jid in snap_grid.get((ii, jj), ()):
                    d2 = (jkey[0] - key[0]) ** 2 + (jkey[1] - key[1]) ** 2
                    if d2 < best_d2:
                        best_d2 = d2
                        best_id = jid
        if best_id is not None:
            return best_id
        return ensure_node(x, y)

    # Seed with detected junctions so crossings share a node.
    for junc in arterial_junctions(routes, merge=merge):
        ensure_node(float(junc["x"]), float(junc["y"]))

    linked: set[tuple[int, int]] = set()

    def link(a: int, b: int, *, expressway: bool) -> None:
        if a == b:
            return
        edge = (a, b) if a < b else (b, a)
        if edge in linked:
            return
        linked.add(edge)
        na, nb = graph.nodes[a], graph.nodes[b]
        length = math.hypot(nb.x - na.x, nb.y - na.y)
        if length < 0.05:
            return
        graph.edges.append(LaneEdge(a, b, length, expressway=expressway))
        graph.adj.setdefault(a, []).append((b, length, expressway))
        graph.adj.setdefault(b, []).append((a, length, expressway))

    for route in routes:
        pts = list(route.get("points") or ())
        if len(pts) < 2:
            continue
        expressway = str(route.get("layer", "")) == "expressway"
        snapped: list[int] = []
        for px, py in pts:
            nid = snap_node(float(px), float(py))
            if not snapped or snapped[-1] != nid:
                snapped.append(nid)
        for i in range(len(snapped) - 1):
            link(snapped[i], snapped[i + 1], expressway=expressway)

    # Spatial hash for nearest queries.
    cell = graph._cell
    for n in graph.nodes:
        i = int(math.floor(n.x / cell))
        j = int(math.floor(n.y / cell))
        graph._grid.setdefault((i, j), []).append(n.id)

    return graph

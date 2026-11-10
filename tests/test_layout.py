"""The graph view's layout (desktop/plugin.js layoutGraph), run under Node on the real imported graph."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from learnloop import core

from .test_core import LH_DATA

JS = Path(__file__).resolve().parents[1] / "desktop" / "plugin.js"
node = shutil.which("node")


def layout_source() -> str:
    src = JS.read_text(encoding="utf-8")
    parts = [re.search(r"^function hashStr\(.*?^}$", src, re.S | re.M).group(0)]
    for name in ("layoutGraph", "createSim"):
        parts.append(re.search(rf"^export function {name}\(.*?^}}$", src, re.S | re.M).group(0))
    parts.append(re.search(r"^export const PHYSICS_DEFAULTS = \{.*?^}$", src, re.S | re.M).group(0))
    parts.append(re.search(r"^const ALPHA_MIN = .*$", src, re.M).group(0))
    return "\n".join(parts).replace("export function", "function").replace("export const", "const")


@pytest.mark.skipif(not node or not Path(LH_DATA).exists(), reason="needs node and the LearnHarness graph")
def test_layout_real_graph(store, tmp_path):
    core.command(store, "s1", f"import {LH_DATA}")
    graph = store.graph()
    (tmp_path / "g.json").write_text(json.dumps(graph))
    script = layout_source() + """
const g = require(process.argv[2])
const a = layoutGraph(g.propositions, g.chains), b = layoutGraph(g.propositions, g.chains)
const out = { n: g.propositions.length, edges: a.edges.length, backward: 0, finite: true, same: true, tight: 0 }
for (const [s, t] of a.edges) if (!(a.x[s] < a.x[t])) out.backward++
for (let i = 0; i < out.n; i++) {
  if (!Number.isFinite(a.x[i]) || !Number.isFinite(a.y[i])) out.finite = false
  if (a.x[i] !== b.x[i] || a.y[i] !== b.y[i]) out.same = false
  for (let j = i + 1; j < out.n; j++)
    if (a.x[i] === a.x[j] && Math.abs(a.y[i] - a.y[j]) < 27.9) out.tight++
}
console.log(JSON.stringify(out))
"""
    (tmp_path / "t.js").write_text(script)
    res = json.loads(subprocess.run([node, str(tmp_path / "t.js"), str(tmp_path / "g.json")],
                                    capture_output=True, text=True, check=True).stdout)
    assert res["n"] == len(graph["propositions"]) and res["edges"] > 0
    assert res["backward"] == 0, "every arrow runs left to right"
    assert res["finite"] and res["same"] and res["tight"] == 0


@pytest.mark.skipif(not node or not Path(LH_DATA).exists(), reason="needs node and the LearnHarness graph")
def test_physics_settles_on_real_graph(store, tmp_path):
    core.command(store, "s1", f"import {LH_DATA}")
    (tmp_path / "g.json").write_text(json.dumps(store.graph()))
    script = layout_source() + """
const g = require(process.argv[2])
const L = layoutGraph(g.propositions, g.chains)
const run = () => { const S = createSim(L, { ...PHYSICS_DEFAULTS }); let t = 0; while (S.running() && t < 2000) { S.tick(); t++ } return [S, t] }
const [a, ticks] = run(), [b] = run()
let forward = 0, finite = true, same = true, minGap = Infinity
for (const [s, t] of L.edges) if (a.x[s] < a.x[t]) forward++
for (let i = 0; i < a.n; i++) {
  if (!Number.isFinite(a.x[i]) || !Number.isFinite(a.y[i])) finite = false
  if (a.x[i] !== b.x[i] || a.y[i] !== b.y[i]) same = false
  for (let j = i + 1; j < a.n; j++) minGap = Math.min(minGap, Math.hypot(a.x[i] - a.x[j], a.y[i] - a.y[j]))
}
console.log(JSON.stringify({ ticks, forward: forward / L.edges.length, finite, same, minGap }))
"""
    (tmp_path / "t.js").write_text(script)
    res = json.loads(subprocess.run([node, str(tmp_path / "t.js"), str(tmp_path / "g.json")],
                                    capture_output=True, text=True, check=True).stdout)
    assert res["finite"] and res["same"]
    assert res["ticks"] < 400, "the simulation cools and stops"
    # LearnHarness defaults: ~90% forward; links one depth apart can bend back under repulsion
    assert res["forward"] > 0.85, "the depth force keeps most arrows running left to right"
    assert res["minGap"] > 5, "repulsion keeps facts apart"

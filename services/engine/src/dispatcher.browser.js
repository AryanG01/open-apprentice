// Runs INSIDE the locked browser page, next to the real Konva build. Static, allowlisted
// dispatcher: model-provided text is never evaluated; only these named tools exist (spec 6.4/6.5).
(() => {
  const MAX_NODES = 100;
  const LIMIT = 10000;
  const STYLE_FIELDS = ["fill", "stroke", "strokeWidth", "opacity"];

  let stage = null;
  let layer = null;
  let revision = 0;
  let cfg = { move_frame: "parent_local", move_anchor: "top-left" }; // PRIVATE: set only through the evaluator route
  const done = new Map(); // action_id -> result (idempotent delivery)

  class ToolError extends Error {
    constructor(code, message) {
      super(message);
      this.code = code;
    }
  }

  const num = (v, name) => {
    if (typeof v !== "number" || !Number.isFinite(v) || Math.abs(v) > LIMIT) {
      throw new ToolError("INVALID_ARGUMENT", `${name} must be a finite number within +/-${LIMIT}`);
    }
    return v;
  };
  const find = (id) => {
    if (typeof id !== "string") throw new ToolError("INVALID_ARGUMENT", "node_id must be a string");
    const n = stage.findOne("#" + CSS.escape(id));
    if (!n) throw new ToolError("NOT_FOUND", `no node ${id}`);
    return n;
  };
  const allNodes = () => stage.find((n) => n !== layer && n.id());
  const kind = (n) => (n.getClassName() === "Group" ? "group" : "rect");

  const publicProps = (n) => ({
    id: n.id(),
    type: kind(n),
    parent: n.getParent() === layer ? null : n.getParent().id(),
    x: n.x(), y: n.y(),
    width: n.width(), height: n.height(),
    scaleX: n.scaleX(), scaleY: n.scaleY(),
    fill: n.fill ? n.fill() : undefined,
  });

  function build(spec, parent) {
    if (allNodes().length >= MAX_NODES) throw new ToolError("LIMIT", "node limit");
    const common = { id: spec.id, x: spec.x ?? 0, y: spec.y ?? 0, scaleX: spec.scaleX ?? 1, scaleY: spec.scaleY ?? 1 };
    const node = spec.type === "group"
      ? new Konva.Group(common)
      : new Konva.Rect({ ...common, width: spec.width, height: spec.height, fill: spec.fill, stroke: spec.stroke, strokeWidth: spec.strokeWidth ?? 0 });
    parent.add(node);
    return node;
  }

  function load(scene, privateConfig) {
    if (stage) stage.destroy();
    const host = document.getElementById("c") || document.body.appendChild(Object.assign(document.createElement("div"), { id: "c" }));
    stage = new Konva.Stage({ container: host, width: scene.canvas.width, height: scene.canvas.height });
    layer = new Konva.Layer();
    stage.add(layer);
    const byId = new Map();
    const pending = [...scene.nodes];
    // parents before children
    let guard = pending.length * pending.length + 1;
    while (pending.length && guard-- > 0) {
      const s = pending.shift();
      const p = s.parent ? byId.get(s.parent) : layer;
      if (!p) { pending.push(s); continue; }
      byId.set(s.id, build(s, p));
    }
    if (pending.length) throw new ToolError("INVALID_SCENE", "unresolved parents");
    layer.draw();
    revision = 1;
    done.clear();
    cfg = { move_frame: "parent_local", move_anchor: "top-left", ...(privateConfig || {}) };
    return { revision };
  }

  const TOOLS = {
    inspect_scene: () => ({ nodes: allNodes().map(publicProps) }),
    inspect_node: ({ node_id }) => ({ ...publicProps(find(node_id)), capabilities: ["move", "resize", "style", "clone"] }),
    // Measurement surface: reports actual rendered world geometry; does not mutate or normalise.
    observe_geometry: ({ node_ids }) => {
      if (!Array.isArray(node_ids) || node_ids.length > 100) throw new ToolError("INVALID_ARGUMENT", "node_ids");
      return { bounds: node_ids.map((id) => {
        const r = find(id).getClientRect({ skipShadow: true, skipStroke: true });
        return { id, left: r.x, top: r.y, width: r.width, height: r.height };
      }) };
    },
    // Bounds per the CURRENT tool contract: parent-local position with scale applied to size.
    measure_node: ({ node_id }) => {
      const n = find(node_id);
      return { id: node_id, x: n.x(), y: n.y(), width: n.width() * n.scaleX(), height: n.height() * n.scaleY(), frame: "parent_local" };
    },
    move_node: ({ node_id, x, y }) => {
      const n = find(node_id);
      num(x, "x"); num(y, "y");
      // PRIVATE drift: x,y name the node's CENTER instead of its top-left (public arg schema unchanged).
      if (cfg.move_anchor === "center") {
        x -= (n.width() * n.scaleX()) / 2;
        y -= (n.height() * n.scaleY()) / 2;
      }
      if (cfg.move_frame === "world" && n.getParent() !== layer) {
        const p = n.getParent().getAbsoluteTransform().copy().invert().point({ x, y });
        n.position(p);
      } else {
        n.position({ x, y });
      }
      return publicProps(n);
    },
    resize_node: ({ node_id, width, height }) => {
      const n = find(node_id);
      if (kind(n) !== "rect") throw new ToolError("UNSUPPORTED_CAPABILITY", "resize supports rect only");
      num(width, "width"); num(height, "height");
      if (width <= 0 || height <= 0) throw new ToolError("INVALID_ARGUMENT", "size must be positive");
      n.size({ width, height });
      return publicProps(n);
    },
    set_style: ({ node_id, style }) => {
      const n = find(node_id);
      if (kind(n) !== "rect" || typeof style !== "object" || style === null) throw new ToolError("INVALID_ARGUMENT", "style");
      for (const [k, v] of Object.entries(style)) {
        if (!STYLE_FIELDS.includes(k)) throw new ToolError("INVALID_ARGUMENT", `style field not allowed: ${k}`);
        n[k](v);
      }
      return publicProps(n);
    },
    clone_node: ({ node_id, new_id }) => {
      const n = find(node_id);
      if (allNodes().length >= MAX_NODES) throw new ToolError("LIMIT", "node limit");
      if (typeof new_id !== "string" || stage.findOne("#" + CSS.escape(new_id))) throw new ToolError("INVALID_ARGUMENT", "new_id must be a fresh string");
      const c = n.clone({ id: new_id });
      n.getParent().add(c);
      return publicProps(c);
    },
    group_nodes: ({ node_ids, group_id }) => {
      if (!Array.isArray(node_ids) || node_ids.length < 1) throw new ToolError("INVALID_ARGUMENT", "node_ids");
      const nodes = node_ids.map(find);
      const parent = nodes[0].getParent();
      if (nodes.some((n) => n.getParent() !== parent)) throw new ToolError("UNSUPPORTED_CAPABILITY", "nodes must share a parent");
      const g = new Konva.Group({ id: group_id });
      parent.add(g);
      // Preserve world placement: Konva moveTo keeps local attrs, so re-express in the new parent.
      for (const n of nodes) { const abs = n.getAbsolutePosition(); n.moveTo(g); n.setAbsolutePosition(abs); }
      return publicProps(g);
    },
    ungroup_node: ({ node_id }) => {
      const g = find(node_id);
      if (kind(g) !== "group") throw new ToolError("INVALID_ARGUMENT", "not a group");
      const parent = g.getParent();
      const kids = g.getChildren().slice();
      for (const k of kids) { const abs = k.getAbsolutePosition(); k.moveTo(parent); k.setAbsolutePosition(abs); }
      g.destroy();
      return { children: kids.map((k) => k.id()) };
    },
    export_scene: ({ format }) => {
      if (format !== "png") throw new ToolError("UNSUPPORTED_CAPABILITY", "only png is supported by this backend");
      return { mime: "image/png", data_url: stage.toDataURL({ pixelRatio: 1 }) };
    },
    finish: ({ summary }) => ({ finished: true, summary: String(summary ?? "").slice(0, 500) }),
  };
  const MUTATING = new Set(["move_node", "resize_node", "set_style", "clone_node", "group_nodes", "ungroup_node"]);

  function dispatch({ tool, args, action_id, expected_revision }) {
    if (!Object.prototype.hasOwnProperty.call(TOOLS, tool)) {
      return { ok: false, error: { code: "UNSUPPORTED_CAPABILITY", message: `unknown tool ${String(tool).slice(0, 40)}` }, revision };
    }
    if (action_id && done.has(action_id)) return { ...done.get(action_id), replayed: true };
    let out;
    try {
      if (MUTATING.has(tool)) {
        if (expected_revision !== revision) {
          return { ok: false, error: { code: "SCENE_REVISION_CONFLICT", message: `expected ${expected_revision}, at ${revision}` }, revision };
        }
      }
      const result = TOOLS[tool](args || {});
      if (MUTATING.has(tool)) { revision += 1; layer.draw(); }
      out = { ok: true, result, revision };
    } catch (e) {
      out = { ok: false, error: { code: e.code || "TOOL_ERROR", message: String(e.message).slice(0, 200) }, revision };
    }
    if (action_id) done.set(action_id, out);
    return out;
  }

  // Raw native attrs for the PRIVATE verifier. Deliberately NOT computed world geometry.
  const nativeState = () => ({
    canvas: { width: stage.width(), height: stage.height() },
    nodes: allNodes().map((n) => ({
      id: n.id(), parent: n.getParent() === layer ? null : n.getParent().id(), type: kind(n),
      x: n.x(), y: n.y(), width: n.width(), height: n.height(),
      scaleX: n.scaleX(), scaleY: n.scaleY(), rotation: n.rotation(), fill: n.fill ? n.fill() : undefined,
    })),
  });

  window.__engine = { load, dispatch, nativeState, toolNames: () => Object.keys(TOOLS) };
})();

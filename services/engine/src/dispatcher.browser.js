// Runs INSIDE the locked browser page, next to the real Konva build. Static, allowlisted
// dispatcher: model-provided text is never evaluated; only these named tools exist (spec 6.4/6.5).
(() => {
  const MAX_NODES = 100;
  const LIMIT = 10000;
  const STYLE_FIELDS = ["fill", "stroke", "strokeWidth", "opacity"];
  // Per-kind style allowlist for campaign nodes (spec 7.3): text fill, copy, links and assets are never writable.
  const KIND_STYLE = { rect: STYLE_FIELDS, shape: [...STYLE_FIELDS, "cornerRadius"], text: ["fontSize"], image: [] };
  const RESIZABLE = new Set(["rect", "shape", "text", "image"]);

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
  const CLASS_KIND = { Group: "group", Rect: "rect", Text: "text", Image: "image" };
  const kind = (n) => n.getAttr("oaType") ?? CLASS_KIND[n.getClassName()] ?? "rect";
  // Campaign metadata (spec 7.1) rides on the node as plain attrs; tools never write it.
  const META = ["role", "link", "asset", "focal", "format", "safe", "sequence"];

  const publicProps = (n) => ({
    id: n.id(),
    type: kind(n),
    role: n.getAttr("role"),
    parent: n.getParent() === layer ? null : n.getParent().id(),
    x: n.x(), y: n.y(),
    width: n.width(), height: n.height(),
    scaleX: n.scaleX(), scaleY: n.scaleY(),
    fill: n.fill ? n.fill() : undefined,
  });

  function build(spec, parent, images) {
    if (allNodes().length >= MAX_NODES) throw new ToolError("LIMIT", "node limit");
    const common = { id: spec.id, x: spec.x ?? 0, y: spec.y ?? 0, scaleX: spec.scaleX ?? 1, scaleY: spec.scaleY ?? 1 };
    const box = { width: spec.width, height: spec.height };
    const type = spec.type ?? "rect";
    let node;
    if (type === "group") node = new Konva.Group(common);
    else if (type === "artboard") {
      node = new Konva.Group({ ...common, ...box, clipX: 0, clipY: 0, clipWidth: spec.width, clipHeight: spec.height });
      node.setAttr("oaType", "artboard");
    } else if (type === "rect" || type === "shape") {
      node = new Konva.Rect({ ...common, ...box, fill: spec.fill, stroke: spec.stroke, strokeWidth: spec.strokeWidth ?? 0, cornerRadius: spec.cornerRadius ?? 0 });
      if (type === "shape") node.setAttr("oaType", "shape");
    } else if (type === "text") {
      // Only the vendored font is measurable by the independent verifier; anything else would be a silent fallback.
      if (spec.fontFamily !== "Liberation Sans") throw new ToolError("INVALID_SCENE", "text must use the vendored Liberation Sans");
      if (!["normal", "bold", undefined].includes(spec.fontStyle)) throw new ToolError("INVALID_SCENE", "fontStyle must be normal or bold");
      node = new Konva.Text({ ...common, ...box, text: spec.text, fontFamily: spec.fontFamily, fontSize: spec.fontSize,
        fontStyle: spec.fontStyle ?? "normal", lineHeight: spec.lineHeight ?? 1, align: spec.align ?? "left", wrap: spec.wrap ?? "word", fill: spec.fill });
    } else if (type === "image") {
      const img = images.get(spec.asset);
      if (!img) throw new ToolError("INVALID_SCENE", `unknown asset ${String(spec.asset).slice(0, 40)}`);
      node = new Konva.Image({ ...common, ...box, image: img });
      if (spec.crop) node.crop(spec.crop);
    } else throw new ToolError("INVALID_SCENE", `unknown node type ${String(type).slice(0, 20)}`);
    for (const k of META) if (spec[k] !== undefined) node.setAttr(k, spec[k]);
    parent.add(node);
    return node;
  }

  async function decodeAssets(scene, assets) {
    const images = new Map();
    for (const id of new Set(scene.nodes.filter((n) => n.type === "image").map((n) => n.asset))) {
      const a = assets?.[id];
      if (!a) continue; // build() reports the unknown id
      const img = new Image();
      img.src = a.data_url;
      await img.decode();
      images.set(id, img);
    }
    return images;
  }

  async function load(scene, privateConfig, assets) {
    const images = await decodeAssets(scene, assets);
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
      byId.set(s.id, build(s, p, images));
    }
    if (pending.length) throw new ToolError("INVALID_SCENE", "unresolved parents");
    // Explicit stacking: within each parent, nodes that give z are raised in ascending z.
    for (const s of [...scene.nodes].filter((n) => typeof n.z === "number").sort((a, b) => a.z - b.z)) byId.get(s.id).moveToTop();
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
      if (!RESIZABLE.has(kind(n))) throw new ToolError("UNSUPPORTED_CAPABILITY", "resize supports rect, shape, text and image");
      num(width, "width"); num(height, "height");
      if (width <= 0 || height <= 0) throw new ToolError("INVALID_ARGUMENT", "size must be positive");
      n.size({ width, height });
      return publicProps(n);
    },
    set_style: ({ node_id, style }) => {
      const n = find(node_id);
      const allowed = KIND_STYLE[kind(n)];
      if (!allowed || typeof style !== "object" || style === null) throw new ToolError("INVALID_ARGUMENT", "style");
      for (const [k, v] of Object.entries(style)) {
        if (!allowed.includes(k)) throw new ToolError("INVALID_ARGUMENT", `style field not allowed: ${k}`);
        if (k === "fontSize" || k === "cornerRadius") { num(v, k); if (v < (k === "fontSize" ? 1 : 0)) throw new ToolError("INVALID_ARGUMENT", k); }
      }
      for (const [k, v] of Object.entries(style)) n[k](v);
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
    // Read-only fit observation (spec 7.2): measures wrapped text with the page's real font on an unbounded clone (a fixed-height
    // Konva.Text silently drops overflowing lines) and reports layout violations inside one artboard against caller-given limits.
    observe_fit: ({ artboard_id, limits }) => {
      const ab = find(artboard_id);
      if (kind(ab) !== "artboard") throw new ToolError("INVALID_ARGUMENT", "artboard_id must name an artboard");
      if (typeof limits !== "object" || limits === null || typeof limits.safe !== "object" || limits.safe === null) throw new ToolError("INVALID_ARGUMENT", "limits");
      for (const k of ["min_font", "min_legal_font", "min_cta_height", "min_hero_width"]) num(limits[k], `limits.${k}`);
      for (const k of ["top", "right", "bottom", "left"]) num(limits.safe[k], `limits.safe.${k}`);
      const nodes = ab.find((n) => Boolean(n.id()));
      const violations = [];
      const flag = (k, n, detail) => violations.push({ kind: k, node_id: n.id(), detail });
      const ctx = document.createElement("canvas").getContext("2d");
      const text = nodes.filter((n) => kind(n) === "text").map((n) => {
        const probe = new Konva.Text({ text: n.text(), fontFamily: n.fontFamily(), fontSize: n.fontSize(), fontStyle: n.fontStyle(),
          lineHeight: n.lineHeight(), align: n.align(), wrap: n.wrap(), width: n.width() });
        const lines = probe.textArr.map((l) => l.text);
        const out = { id: n.id(), lines, line_widths: probe.textArr.map((l) => l.width), text_height: probe.height(),
          frame_width: n.width(), frame_height: n.height() };
        probe.destroy();
        if (out.text_height > out.frame_height) flag("text_overflow", n, `${out.text_height} > ${out.frame_height}`);
        ctx.font = `${n.fontStyle()} ${n.fontSize()}px "${n.fontFamily()}"`;
        // Split only where the wrap may break (a space): a no-break-space run is one unbreakable word.
        const wide = n.text().split(/[ \n]/).find((w) => ctx.measureText(w).width > n.width());
        if (wide !== undefined) flag("word_too_wide", n, wide.slice(0, 60));
        return out;
      });
      const rect = (n) => n.getClientRect({ relativeTo: ab, skipShadow: true, skipStroke: true });
      const roled = nodes.filter((n) => n.getAttr("role") && n.getAttr("role") !== "background");
      const W = ab.width(), H = ab.height(), sf = limits.safe;
      const fontPx = (n) => n.fontSize() * (n.getAbsoluteScale().y / ab.getAbsoluteScale().y);
      for (const n of roled) {
        const r = rect(n);
        if (r.x < sf.left || r.y < sf.top || r.x + r.width > W - sf.right || r.y + r.height > H - sf.bottom) flag("outside_safe", n, r);
        const role = n.getAttr("role");
        if (role === "legal" && fontPx(n) < limits.min_legal_font) flag("below_minimum", n, "legal font");
        if ((role === "headline" || role === "price") && fontPx(n) < limits.min_font) flag("below_minimum", n, "font");
        if (role === "cta" && r.height < limits.min_cta_height) flag("below_minimum", n, "cta height");
        if (role === "product_image" && r.width < limits.min_hero_width) flag("below_minimum", n, "hero width");
      }
      for (const n of nodes) {
        const owner = n.getParent();
        if (kind(n) === "text" && owner.getAttr("role") === "cta" && fontPx(n) < limits.min_font) flag("below_minimum", n, "cta label font");
      }
      for (let i = 0; i < roled.length; i++) {
        for (let j = i + 1; j < roled.length; j++) {
          const a = rect(roled[i]), b = rect(roled[j]);
          const w = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
          const h = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
          if (w > 0 && h > 0) flag("overlap", roled[i], roled[j].id());
        }
      }
      return { fits: violations.length === 0, text, violations };
    },
    create_artboard: ({ artboard_id, x, y, width, height, format, safe, sequence }) => {
      if (typeof artboard_id !== "string" || !artboard_id || stage.findOne("#" + CSS.escape(artboard_id))) throw new ToolError("INVALID_ARGUMENT", "artboard_id must be a fresh string");
      for (const [k, v] of Object.entries({ x, y, width, height })) num(v, k);
      if (width <= 0 || height <= 0) throw new ToolError("INVALID_ARGUMENT", "size must be positive");
      if (!["9:16", "16:9"].includes(format)) throw new ToolError("INVALID_ARGUMENT", "format");
      if (typeof safe !== "object" || safe === null) throw new ToolError("INVALID_ARGUMENT", "safe");
      for (const k of ["top", "right", "bottom", "left"]) num(safe[k], `safe.${k}`);
      if (!Number.isInteger(sequence) || sequence < 1) throw new ToolError("INVALID_ARGUMENT", "sequence");
      return publicProps(build({ id: artboard_id, type: "artboard", x, y, width, height, format, safe, sequence }, layer, new Map()));
    },
    remove_artboard: ({ artboard_id }) => {
      const ab = find(artboard_id);
      if (kind(ab) !== "artboard") throw new ToolError("INVALID_ARGUMENT", "not an artboard");
      if (ab.getChildren().length) throw new ToolError("INVALID_ARGUMENT", "artboard is not empty");
      ab.destroy();
      return { removed: artboard_id };
    },
    reparent_nodes: ({ node_ids, parent_id }) => {
      if (!Array.isArray(node_ids) || node_ids.length < 1) throw new ToolError("INVALID_ARGUMENT", "node_ids");
      const parent = find(parent_id);
      if (!["artboard", "group"].includes(kind(parent))) throw new ToolError("INVALID_ARGUMENT", "parent must be an artboard or group");
      const nodes = node_ids.map(find);
      if (nodes.some((n) => n === parent || n.isAncestorOf(parent))) throw new ToolError("INVALID_ARGUMENT", "cannot move a node into itself");
      // Same convention as group_nodes: world placement is kept, local attrs are re-expressed in the new parent.
      for (const n of nodes) { const abs = n.getAbsolutePosition(); n.moveTo(parent); n.setAbsolutePosition(abs); }
      return { moved: node_ids };
    },
    set_order: ({ node_id, z }) => {
      const n = find(node_id);
      const count = n.getParent().getChildren().length;
      if (!Number.isInteger(z) || z < 0 || z >= count) throw new ToolError("INVALID_ARGUMENT", `z must be an integer in 0..${count - 1}`);
      n.zIndex(z);
      return publicProps(n);
    },
    fit_image_contain: ({ node_id, x, y, width, height }) => {
      const n = find(node_id);
      if (kind(n) !== "image") throw new ToolError("INVALID_ARGUMENT", "not an image");
      for (const [k, v] of Object.entries({ x, y, width, height })) num(v, k);
      if (width <= 0 || height <= 0) throw new ToolError("INVALID_ARGUMENT", "size must be positive");
      const img = n.image();
      const s = Math.min(width / img.naturalWidth, height / img.naturalHeight);
      const w = img.naturalWidth * s, h = img.naturalHeight * s;
      n.position({ x: x + (width - w) / 2, y: y + (height - h) / 2 });
      n.size({ width: w, height: h });
      return publicProps(n);
    },
    export_scene: ({ format }) => {
      if (format !== "png") throw new ToolError("UNSUPPORTED_CAPABILITY", "only png is supported by this backend");
      return { mime: "image/png", data_url: stage.toDataURL({ pixelRatio: 1 }) };
    },
    finish: ({ summary }) => ({ finished: true, summary: String(summary ?? "").slice(0, 500) }),
  };
  const MUTATING = new Set(["move_node", "resize_node", "set_style", "clone_node", "group_nodes", "ungroup_node",
    "create_artboard", "remove_artboard", "reparent_nodes", "set_order", "fit_image_contain"]);

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
    nodes: allNodes().map((n) => {
      const t = kind(n);
      const out = {
        id: n.id(), parent: n.getParent() === layer ? null : n.getParent().id(), type: t,
        x: n.x(), y: n.y(), width: n.width(), height: n.height(),
        scaleX: n.scaleX(), scaleY: n.scaleY(), rotation: n.rotation(), z: n.zIndex(), fill: n.fill ? n.fill() : undefined,
      };
      for (const k of META) if (n.getAttr(k) !== undefined) out[k] = n.getAttr(k);
      if (t === "rect" || t === "shape") out.cornerRadius = n.cornerRadius();
      if (t === "text") {
        for (const k of ["text", "fontFamily", "fontSize", "fontStyle", "lineHeight", "align", "wrap"]) out[k] = n[k]();
      }
      if (t === "image") out.crop = n.cropWidth() > 0 ? n.crop() : null;
      return out;
    }),
  });

  window.__engine = { load, dispatch, nativeState, toolNames: () => Object.keys(TOOLS) };
})();

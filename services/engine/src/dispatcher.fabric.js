// Fabric.js backend, running INSIDE the locked page next to the real Fabric build (spec 6.1/6.7).
// Same tool NAMES as the Konva backend, genuinely different native behaviour:
//  - positions are `left/top` of the object (origin left/top); Fabric reports bounds via getBoundingRect()
//  - clone is async in Fabric 6; groups are NOT supported here (explicit capability error, declared subset)
// PRIVATE drift (evaluator-only): move_node starts interpreting x,y as the object's CENTER while the
// public argument schema is unchanged.
(() => {
  const MAX_NODES = 100;
  const LIMIT = 10000;
  const STYLE_FIELDS = ["fill", "opacity"];

  let canvas = null;
  let campaign = false; // campaign scenes (spec 7.1): real Fabric groups, textboxes and images; flat rect scenes keep the old path
  let revision = 0;
  let cfg = { move_origin: "top-left" };
  const objs = new Map();
  const done = new Map();

  class ToolError extends Error {
    constructor(code, message) { super(message); this.code = code; }
  }
  const num = (v, name) => {
    if (typeof v !== "number" || !Number.isFinite(v) || Math.abs(v) > LIMIT) {
      throw new ToolError("INVALID_ARGUMENT", `${name} must be a finite number within +/-${LIMIT}`);
    }
    return v;
  };
  const find = (id) => {
    if (typeof id !== "string") throw new ToolError("INVALID_ARGUMENT", "node_id must be a string");
    const o = objs.get(id);
    if (!o) throw new ToolError("NOT_FOUND", `no node ${id}`);
    return o;
  };
  const props = (id, o) => ({
    id, type: "rect", parent: null, left: o.left, top: o.top,
    width: o.width, height: o.height, scaleX: o.scaleX, scaleY: o.scaleY, fill: o.fill,
  });

  // ---- campaign scenes ------------------------------------------------------------------------------------------
  // Fabric's own semantics are kept: a group child's left/top live in the group's centre frame (the private verifier
  // composes them itself). Text frames are kept as authored (Fabric widens a Textbox to its longest word).
  const META = ["role", "link", "asset", "focal", "format", "safe", "sequence"];
  const kindOf = (o) => o.oaType;

  async function decodeAssets(scene, assets) {
    const images = new Map();
    for (const id of new Set(scene.nodes.filter((n) => n.type === "image").map((n) => n.asset))) {
      const a = assets?.[id];
      if (!a) continue;
      const img = new Image();
      img.src = a.data_url;
      await img.decode();
      images.set(id, img);
    }
    return images;
  }

  function buildCampaign(spec, all, images) {
    if (objs.size >= MAX_NODES) throw new ToolError("LIMIT", "node limit");
    const type = spec.type ?? "rect";
    const at = { left: spec.x ?? 0, top: spec.y ?? 0, originX: "left", originY: "top", strokeWidth: 0, objectCaching: false };
    let o;
    if (type === "rect" || type === "shape") {
      o = new fabric.Rect({ ...at, width: spec.width, height: spec.height, fill: spec.fill, rx: spec.cornerRadius ?? 0, ry: spec.cornerRadius ?? 0 });
    } else if (type === "text") {
      if (spec.fontFamily !== "Liberation Sans") throw new ToolError("INVALID_SCENE", "text must use the vendored Liberation Sans");
      if (!["normal", "bold", undefined].includes(spec.fontStyle)) throw new ToolError("INVALID_SCENE", "fontStyle must be normal or bold");
      o = new fabric.Textbox(spec.text, { ...at, width: spec.width, fontFamily: spec.fontFamily, fontSize: spec.fontSize,
        fontWeight: spec.fontStyle === "bold" ? "bold" : "normal", lineHeight: spec.lineHeight ?? 1, textAlign: spec.align ?? "left", fill: spec.fill });
      o.oaFrameWidth = spec.width;
      o.oaFrameHeight = spec.height;
    } else if (type === "image") {
      const img = images.get(spec.asset);
      if (!img) throw new ToolError("INVALID_SCENE", `unknown asset ${String(spec.asset).slice(0, 40)}`);
      o = new fabric.FabricImage(img, { ...at, scaleX: spec.width / img.naturalWidth, scaleY: spec.height / img.naturalHeight });
      if (spec.crop) o.set({ cropX: spec.crop.x, cropY: spec.crop.y, width: spec.crop.width, height: spec.crop.height });
    } else if (type === "group" || type === "artboard") {
      const kids = all.filter((n) => n.parent === spec.id).sort((a, b) => (a.z ?? 0) - (b.z ?? 0)).map((k) => buildCampaign(k, all, images));
      const kidSpecs = all.filter((n) => n.parent === spec.id);
      const width = spec.width ?? Math.max(0, ...kidSpecs.map((k) => (k.x ?? 0) + (k.width ?? 0)));
      const height = spec.height ?? Math.max(0, ...kidSpecs.map((k) => (k.y ?? 0) + (k.height ?? 0)));
      o = new fabric.Group(kids, { ...at, width, height, layoutManager: new fabric.LayoutManager(new fabric.FixedLayout()),
        clipPath: type === "artboard" ? new fabric.Rect({ width, height, originX: "center", originY: "center" }) : undefined }, true);
    } else throw new ToolError("INVALID_SCENE", `unknown node type ${String(type).slice(0, 20)}`);
    o.oaId = spec.id;
    o.oaType = type;
    o.oaMeta = Object.fromEntries(META.filter((k) => spec[k] !== undefined).map((k) => [k, spec[k]]));
    objs.set(spec.id, o);
    return o;
  }

  async function loadCampaign(scene, assets) {
    const images = await decodeAssets(scene, assets);
    const ids = new Set(scene.nodes.map((n) => n.id));
    if (scene.nodes.some((n) => n.parent && !ids.has(n.parent))) throw new ToolError("INVALID_SCENE", "unresolved parents");
    for (const root of scene.nodes.filter((n) => !n.parent).sort((a, b) => (a.z ?? 0) - (b.z ?? 0))) canvas.add(buildCampaign(root, scene.nodes, images));
  }

  const campaignState = () => ({
    canvas: { width: canvas.getWidth(), height: canvas.getHeight() },
    nodes: [...objs].map(([id, o]) => {
      const t = kindOf(o);
      const parent = o.group ? o.group.oaId : null;
      const siblings = o.group ? o.group.getObjects() : canvas.getObjects();
      const out = {
        id, parent, type: t, frame: parent ? "group_center" : "canvas",
        x: o.left, y: o.top,
        width: t === "text" ? o.oaFrameWidth : o.width, height: t === "text" ? o.oaFrameHeight : o.height,
        scaleX: o.scaleX, scaleY: o.scaleY, rotation: o.angle, z: siblings.indexOf(o),
        ...o.oaMeta,
      };
      if (t === "rect" || t === "shape") Object.assign(out, { fill: o.fill, cornerRadius: o.rx });
      if (t === "text") Object.assign(out, { fill: o.fill, text: o.text, fontFamily: o.fontFamily, fontSize: o.fontSize,
        fontStyle: o.fontWeight === "bold" ? "bold" : "normal", lineHeight: o.lineHeight, align: o.textAlign, wrap: "word" });
      if (t === "image") out.crop = o.cropX || o.cropY ? { x: o.cropX, y: o.cropY, width: o.width, height: o.height } : null;
      return out;
    }),
  });

  async function load(scene, privateConfig, assets) {
    if (canvas) canvas.dispose();
    objs.clear();
    done.clear();
    const el = document.body.appendChild(document.createElement("canvas"));
    canvas = new fabric.StaticCanvas(el, { width: scene.canvas.width, height: scene.canvas.height, renderOnAddRemove: false });
    // Only scenes built around an artboard use the campaign path; anything else is the badge lane's flat subset, unchanged.
    campaign = scene.nodes.some((n) => n.type === "artboard");
    if (campaign) {
      await loadCampaign(scene, assets);
      canvas.requestRenderAll();
      revision = 1;
      cfg = { move_origin: "top-left", ...(privateConfig || {}) };
      return { revision };
    }
    for (const s of scene.nodes) {
      if (s.type === "group" || s.parent) throw new ToolError("INVALID_SCENE", "fabric backend subset: flat rect scenes only");
      if (objs.size >= MAX_NODES) throw new ToolError("LIMIT", "node limit");
      const r = new fabric.Rect({
        left: s.x ?? 0, top: s.y ?? 0, width: s.width, height: s.height, fill: s.fill,
        scaleX: s.scaleX ?? 1, scaleY: s.scaleY ?? 1, strokeWidth: 0, objectCaching: false,
      });
      canvas.add(r);
      objs.set(s.id, r);
    }
    canvas.requestRenderAll();
    revision = 1;
    cfg = { move_origin: "top-left", ...(privateConfig || {}) };
    return { revision };
  }

  const TOOLS = {
    inspect_scene: () => ({ nodes: [...objs].map(([id, o]) => props(id, o)) }),
    inspect_node: ({ node_id }) => ({ ...props(node_id, find(node_id)), capabilities: ["move", "resize", "style", "clone"] }),
    observe_geometry: ({ node_ids }) => {
      if (!Array.isArray(node_ids) || node_ids.length > 100) throw new ToolError("INVALID_ARGUMENT", "node_ids");
      return { bounds: node_ids.map((id) => {
        const r = find(id).getBoundingRect();
        return { id, left: r.left, top: r.top, width: r.width, height: r.height };
      }) };
    },
    // Native contract: canvas-frame left/top, size already multiplied by scale.
    measure_node: ({ node_id }) => {
      const o = find(node_id);
      return { id: node_id, x: o.left, y: o.top, width: o.width * o.scaleX, height: o.height * o.scaleY, frame: "canvas" };
    },
    move_node: ({ node_id, x, y }) => {
      const o = find(node_id);
      num(x, "x"); num(y, "y");
      if (cfg.move_origin === "center") {
        o.setPositionByOrigin(new fabric.Point(x, y), "center", "center");
      } else {
        o.set({ left: x, top: y });
      }
      o.setCoords();
      return props(node_id, o);
    },
    resize_node: ({ node_id, width, height }) => {
      const o = find(node_id);
      num(width, "width"); num(height, "height");
      if (width <= 0 || height <= 0) throw new ToolError("INVALID_ARGUMENT", "size must be positive");
      o.set({ width, height });
      o.setCoords();
      return props(node_id, o);
    },
    set_style: ({ node_id, style }) => {
      const o = find(node_id);
      if (typeof style !== "object" || style === null) throw new ToolError("INVALID_ARGUMENT", "style");
      for (const [k, v] of Object.entries(style)) {
        if (!STYLE_FIELDS.includes(k)) throw new ToolError("INVALID_ARGUMENT", `style field not allowed: ${k}`);
        o.set(k, v);
      }
      return props(node_id, o);
    },
    clone_node: async ({ node_id, new_id }) => {
      const o = find(node_id);
      if (objs.size >= MAX_NODES) throw new ToolError("LIMIT", "node limit");
      if (typeof new_id !== "string" || objs.has(new_id)) throw new ToolError("INVALID_ARGUMENT", "new_id must be a fresh string");
      const c = await o.clone();
      canvas.add(c);
      objs.set(new_id, c);
      return props(new_id, c);
    },
    group_nodes: () => { throw new ToolError("UNSUPPORTED_CAPABILITY", "fabric backend: grouping is outside the declared common subset"); },
    ungroup_node: () => { throw new ToolError("UNSUPPORTED_CAPABILITY", "fabric backend: grouping is outside the declared common subset"); },
    export_scene: ({ format }) => {
      if (format !== "png") throw new ToolError("UNSUPPORTED_CAPABILITY", "only png is supported by this backend");
      return { mime: "image/png", data_url: canvas.toDataURL({ format: "png", multiplier: 1 }) };
    },
    finish: ({ summary }) => ({ finished: true, summary: String(summary ?? "").slice(0, 500) }),
  };
  const MUTATING = new Set(["move_node", "resize_node", "set_style", "clone_node"]);

  async function dispatch({ tool, args, action_id, expected_revision }) {
    if (!Object.prototype.hasOwnProperty.call(TOOLS, tool)) {
      return { ok: false, error: { code: "UNSUPPORTED_CAPABILITY", message: `unknown tool ${String(tool).slice(0, 40)}` }, revision };
    }
    if (action_id && done.has(action_id)) return { ...done.get(action_id), replayed: true };
    let out;
    try {
      if (MUTATING.has(tool) && expected_revision !== revision) {
        return { ok: false, error: { code: "SCENE_REVISION_CONFLICT", message: `expected ${expected_revision}, at ${revision}` }, revision };
      }
      const result = await TOOLS[tool](args || {});
      if (MUTATING.has(tool)) { revision += 1; canvas.requestRenderAll(); }
      out = { ok: true, result, revision };
    } catch (e) {
      out = { ok: false, error: { code: e.code || "TOOL_ERROR", message: String(e.message).slice(0, 200) }, revision };
    }
    if (action_id) done.set(action_id, out);
    return out;
  }

  // Raw native attrs for the PRIVATE verifier (x,y = Fabric left/top; origin exported so the verifier can refuse non-default).
  const nativeState = () => (campaign ? campaignState() : {
    canvas: { width: canvas.getWidth(), height: canvas.getHeight() },
    nodes: [...objs].map(([id, o]) => ({
      id, parent: null, type: "rect", x: o.left, y: o.top, width: o.width, height: o.height,
      scaleX: o.scaleX, scaleY: o.scaleY, rotation: o.angle, fill: o.fill, originX: o.originX, originY: o.originY,
    })),
  });

  window.__engine = { load, dispatch, nativeState, toolNames: () => Object.keys(TOOLS) };
})();

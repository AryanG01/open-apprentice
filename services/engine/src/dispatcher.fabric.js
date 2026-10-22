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

  // Cards and the CTA group are laid out once, when built, so their plane centre never moves: a child's parent-local
  // position then means the same thing as on Konva. (A re-fitting layout would shift the group's origin after every move,
  // and a FixedLayout re-fits a card around content added to it.)
  class InitialLayout extends fabric.FixedLayout {
    shouldPerformLayout(context) {
      return context.type === "initialization";
    }
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
      const strategy = new InitialLayout();
      o = new fabric.Group(kids, { ...at, width, height, layoutManager: new fabric.LayoutManager(strategy),
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

  // A group child's left/top live in the group's plane, whose origin is the group's centre.
  const toPlane = (o, x, y) => (o.group ? { left: x - o.group.width / 2, top: y - o.group.height / 2 } : { left: x, top: y });
  const KIND_STYLE = { rect: ["fill", "opacity", "cornerRadius"], shape: ["fill", "opacity", "cornerRadius"], text: ["fontSize"], image: [] };
  const RESIZABLE = new Set(["rect", "shape", "text", "image"]);
  const freshId = (id) => {
    if (typeof id !== "string" || !id || objs.has(id)) throw new ToolError("INVALID_ARGUMENT", "id must be a fresh string");
    if (objs.size >= MAX_NODES) throw new ToolError("LIMIT", "node limit");
  };

  const CAMPAIGN_TOOLS = {
    move_node: ({ node_id, x, y }) => {
      const o = find(node_id);
      num(x, "x"); num(y, "y");
      o.set(toPlane(o, x, y));
      o.setCoords();
    },
    resize_node: ({ node_id, width, height }) => {
      const o = find(node_id);
      if (!RESIZABLE.has(kindOf(o))) throw new ToolError("UNSUPPORTED_CAPABILITY", "resize supports rect, shape, text and image");
      num(width, "width"); num(height, "height");
      if (width <= 0 || height <= 0) throw new ToolError("INVALID_ARGUMENT", "size must be positive");
      if (kindOf(o) === "text") { o.set({ width }); o.oaFrameWidth = width; o.oaFrameHeight = height; o.initDimensions(); }
      else if (kindOf(o) === "image") o.set({ scaleX: width / o.width, scaleY: height / o.height });
      else o.set({ width, height });
      o.setCoords();
    },
    set_style: ({ node_id, style }) => {
      const o = find(node_id);
      const allowed = KIND_STYLE[kindOf(o)];
      if (!allowed || typeof style !== "object" || style === null) throw new ToolError("INVALID_ARGUMENT", "style");
      for (const [k, v] of Object.entries(style)) {
        if (!allowed.includes(k)) throw new ToolError("INVALID_ARGUMENT", `style field not allowed: ${k}`);
        if (k === "fontSize" || k === "cornerRadius") { num(v, k); if (v < (k === "fontSize" ? 1 : 0)) throw new ToolError("INVALID_ARGUMENT", k); }
      }
      for (const [k, v] of Object.entries(style)) {
        if (k === "cornerRadius") o.set({ rx: v, ry: v }); else o.set(k, v);
      }
      if (kindOf(o) === "text") o.initDimensions();
    },
    clone_node: async ({ node_id, new_id }) => {
      const o = find(node_id);
      freshId(new_id);
      if (!RESIZABLE.has(kindOf(o))) throw new ToolError("UNSUPPORTED_CAPABILITY", "clone supports rect, shape, text and image");
      const c = await o.clone();
      Object.assign(c, { oaId: new_id, oaType: o.oaType, oaMeta: structuredClone(o.oaMeta), oaFrameWidth: o.oaFrameWidth, oaFrameHeight: o.oaFrameHeight });
      if (o.group) {
        // the copy's left/top are in the group plane; add() expects canvas coordinates, so express them there first
        const p = fabric.util.transformPoint(new fabric.Point(c.left, c.top), o.group.calcTransformMatrix());
        c.set({ left: p.x, top: p.y });
        o.group.add(c);
      } else canvas.add(c);
      objs.set(new_id, c);
    },
    create_artboard: ({ artboard_id, x, y, width, height, format, safe, sequence }) => {
      freshId(artboard_id);
      for (const [k, v] of Object.entries({ x, y, width, height })) num(v, k);
      if (width <= 0 || height <= 0) throw new ToolError("INVALID_ARGUMENT", "size must be positive");
      if (!["9:16", "16:9"].includes(format)) throw new ToolError("INVALID_ARGUMENT", "format");
      if (typeof safe !== "object" || safe === null) throw new ToolError("INVALID_ARGUMENT", "safe");
      for (const k of ["top", "right", "bottom", "left"]) num(safe[k], `safe.${k}`);
      if (!Number.isInteger(sequence) || sequence < 1) throw new ToolError("INVALID_ARGUMENT", "sequence");
      canvas.add(buildCampaign({ id: artboard_id, type: "artboard", x, y, width, height, format, safe, sequence }, [], new Map()));
    },
    remove_artboard: ({ artboard_id }) => {
      const ab = find(artboard_id);
      if (kindOf(ab) !== "artboard") throw new ToolError("INVALID_ARGUMENT", "not an artboard");
      if (ab.getObjects().length) throw new ToolError("INVALID_ARGUMENT", "artboard is not empty");
      canvas.remove(ab);
      objs.delete(artboard_id);
      return { removed: artboard_id };
    },
    reparent_nodes: ({ node_ids, parent_id }) => {
      if (!Array.isArray(node_ids) || node_ids.length < 1) throw new ToolError("INVALID_ARGUMENT", "node_ids");
      const parent = find(parent_id);
      if (!["artboard", "group"].includes(kindOf(parent))) throw new ToolError("INVALID_ARGUMENT", "parent must be an artboard or group");
      const nodes = node_ids.map(find);
      if (nodes.some((o) => o === parent || (o instanceof fabric.Group && o.contains(parent, true)))) throw new ToolError("INVALID_ARGUMENT", "cannot move a node into itself");
      for (const o of nodes) {
        // remove() hands the object back in canvas coordinates; add() re-expresses it in the new group's plane
        if (o.group) o.group.remove(o); else canvas.remove(o);
        parent.add(o);
      }
      return { moved: node_ids };
    },
    set_order: ({ node_id, z }) => {
      const o = find(node_id);
      const owner = o.group ?? canvas;
      const count = owner.getObjects().length;
      if (!Number.isInteger(z) || z < 0 || z >= count) throw new ToolError("INVALID_ARGUMENT", `z must be an integer in 0..${count - 1}`);
      owner.moveObjectTo(o, z);
    },
    fit_image_contain: ({ node_id, x, y, width, height }) => {
      const o = find(node_id);
      if (kindOf(o) !== "image") throw new ToolError("INVALID_ARGUMENT", "not an image");
      for (const [k, v] of Object.entries({ x, y, width, height })) num(v, k);
      if (width <= 0 || height <= 0) throw new ToolError("INVALID_ARGUMENT", "size must be positive");
      const sc = Math.min(width / o.width, height / o.height);
      o.set({ scaleX: sc, scaleY: sc, ...toPlane(o, x + (width - o.width * sc) / 2, y + (height - o.height * sc) / 2) });
      o.setCoords();
    },
  };
  const CAMPAIGN_MUTATING = new Set(Object.keys(CAMPAIGN_TOOLS));

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
    // Read-only fit observation (same contract as Konva). Text is measured by a fresh Textbox at the AUTHORED width (Fabric
    // widens a Textbox to its longest word, which would hide an over-wide word); boxes are relative to the artboard.
    observe_fit: ({ artboard_id, limits }) => {
      if (!campaign) throw new ToolError("UNSUPPORTED_CAPABILITY", "observe_fit needs a campaign scene");
      const ab = find(artboard_id);
      if (kindOf(ab) !== "artboard") throw new ToolError("INVALID_ARGUMENT", "artboard_id must name an artboard");
      if (typeof limits !== "object" || limits === null || typeof limits.safe !== "object" || limits.safe === null) throw new ToolError("INVALID_ARGUMENT", "limits");
      for (const k of ["min_font", "min_legal_font", "min_cta_height", "min_hero_width"]) num(limits[k], `limits.${k}`);
      for (const k of ["top", "right", "bottom", "left"]) num(limits.safe[k], `limits.safe.${k}`);
      const nodes = [];
      const walk = (g) => { for (const o of g.getObjects()) { nodes.push(o); if (o instanceof fabric.Group) walk(o); } };
      walk(ab);
      const violations = [];
      const flag = (k, o, detail) => violations.push({ kind: k, node_id: o.oaId, detail });
      const ctx = document.createElement("canvas").getContext("2d");
      const text = nodes.filter((o) => kindOf(o) === "text").map((o) => {
        const probe = new fabric.Textbox(o.text, { width: o.oaFrameWidth, fontFamily: o.fontFamily, fontSize: o.fontSize,
          fontWeight: o.fontWeight, lineHeight: o.lineHeight, textAlign: o.textAlign });
        const lines = probe._textLines.map((l) => l.join(""));
        const out = { id: o.oaId, lines, line_widths: lines.map((_, i) => probe.getLineWidth(i)), text_height: probe.calcTextHeight(),
          frame_width: o.oaFrameWidth, frame_height: o.oaFrameHeight };
        if (out.text_height > out.frame_height) flag("text_overflow", o, `${out.text_height} > ${out.frame_height}`);
        ctx.font = `${o.fontWeight} ${o.fontSize}px "${o.fontFamily}"`;
        const wide = o.text.split(/[ \n]/).find((w) => ctx.measureText(w).width > o.oaFrameWidth);
        if (wide !== undefined) flag("word_too_wide", o, wide.slice(0, 60));
        return out;
      });
      ab.setCoords(); // a card created by a tool keeps stale corners until refreshed (invisible for a card at x 0)
      const abBox = ab.getBoundingRect();
      const rect = (o) => {
        if (kindOf(o) === "group") {
          // a group's extent is its children's (the verifier's rule), not the group's own fixed box
          const kids = o.getObjects().map(rect);
          const x0 = Math.min(...kids.map((k) => k.x)), y0 = Math.min(...kids.map((k) => k.y));
          return { x: x0, y: y0, width: Math.max(...kids.map((k) => k.x + k.width)) - x0, height: Math.max(...kids.map((k) => k.y + k.height)) - y0 };
        }
        o.setCoords(); // a Textbox re-measures after it joins its group; its cached corners can be stale
        const r = o.getBoundingRect();
        const w = kindOf(o) === "text" ? o.oaFrameWidth : r.width, h = kindOf(o) === "text" ? o.oaFrameHeight : r.height;
        return { x: r.left - abBox.left, y: r.top - abBox.top, width: w, height: h };
      };
      const scaleY = (o) => o.getObjectScaling().y / ab.getObjectScaling().y;
      const fontPx = (o) => o.fontSize * scaleY(o);
      const roled = nodes.filter((o) => o.oaMeta?.role && o.oaMeta.role !== "background");
      const W = ab.width, H = ab.height, sf = limits.safe;
      for (const o of roled) {
        const r = rect(o);
        if (r.x < sf.left || r.y < sf.top || r.x + r.width > W - sf.right || r.y + r.height > H - sf.bottom) flag("outside_safe", o, r);
        const role = o.oaMeta.role;
        if (role === "legal" && fontPx(o) < limits.min_legal_font) flag("below_minimum", o, "legal font");
        if ((role === "headline" || role === "price") && fontPx(o) < limits.min_font) flag("below_minimum", o, "font");
        if (role === "cta" && r.height < limits.min_cta_height) flag("below_minimum", o, "cta height");
        if (role === "product_image" && r.width < limits.min_hero_width) flag("below_minimum", o, "hero width");
      }
      for (const o of nodes) {
        if (kindOf(o) === "text" && o.group?.oaMeta?.role === "cta" && fontPx(o) < limits.min_font) flag("below_minimum", o, "cta label font");
      }
      for (let i = 0; i < roled.length; i++) {
        for (let j = i + 1; j < roled.length; j++) {
          const a = rect(roled[i]), b = rect(roled[j]);
          const w = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
          const h = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
          if (w > 0 && h > 0) flag("overlap", roled[i], roled[j].oaId);
        }
      }
      return { fits: violations.length === 0, text, violations };
    },
    group_nodes: () => { throw new ToolError("UNSUPPORTED_CAPABILITY", "fabric backend: grouping is outside the declared common subset"); },
    ungroup_node: () => { throw new ToolError("UNSUPPORTED_CAPABILITY", "fabric backend: grouping is outside the declared common subset"); },
    export_scene: ({ format }) => {
      if (format !== "png") throw new ToolError("UNSUPPORTED_CAPABILITY", "only png is supported by this backend");
      // story cards can lie beyond the source canvas: export the area every artboard covers (at most 2400 px a side)
      const boards = canvas.getObjects().filter((o) => kindOf(o) === "artboard").map((o) => (o.setCoords(), o.getBoundingRect()));
      if (!boards.length) return { mime: "image/png", data_url: canvas.toDataURL({ format: "png", multiplier: 1 }) };
      const left = Math.min(...boards.map((b) => b.left)), top = Math.min(...boards.map((b) => b.top));
      const width = Math.max(...boards.map((b) => b.left + b.width)) - left, height = Math.max(...boards.map((b) => b.top + b.height)) - top;
      return { mime: "image/png", data_url: canvas.toDataURL({ format: "png", left, top, width, height, multiplier: Math.min(1, 2400 / Math.max(width, height)) }) };
    },
    finish: ({ summary }) => ({ finished: true, summary: String(summary ?? "").slice(0, 500) }),
  };
  const MUTATING = new Set(["move_node", "resize_node", "set_style", "clone_node"]);

  async function dispatch({ tool, args, action_id, expected_revision }) {
    const own = (t, k) => Object.prototype.hasOwnProperty.call(t, k);
    if (campaign && ["inspect_scene", "inspect_node", "measure_node"].includes(tool)) {
      // these report the flat-rect contract (canvas left/top, type rect); on a campaign scene they would mislead
      return { ok: false, error: { code: "UNSUPPORTED_CAPABILITY", message: `${tool} is not available on Fabric campaign scenes; use observe_fit` }, revision };
    }
    const viaCampaign = campaign && own(CAMPAIGN_TOOLS, tool);
    if (!viaCampaign && !own(TOOLS, tool)) {
      return { ok: false, error: { code: "UNSUPPORTED_CAPABILITY", message: `unknown tool ${String(tool).slice(0, 40)}` }, revision };
    }
    if (action_id && done.has(action_id)) return { ...done.get(action_id), replayed: true };
    let out;
    try {
      const mutating = viaCampaign ? CAMPAIGN_MUTATING.has(tool) : MUTATING.has(tool);
      if (mutating && expected_revision !== revision) {
        return { ok: false, error: { code: "SCENE_REVISION_CONFLICT", message: `expected ${expected_revision}, at ${revision}` }, revision };
      }
      let result;
      if (viaCampaign) {
        result = (await CAMPAIGN_TOOLS[tool](args || {})) ?? { id: args?.node_id ?? args?.artboard_id };
      } else {
        result = await TOOLS[tool](args || {});
      }
      if (mutating) { revision += 1; canvas.requestRenderAll(); }
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

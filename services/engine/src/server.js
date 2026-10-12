// HTTP front for the engine. Two surfaces:
//  - agent-facing  /sessions...         can NEVER set private config (D5)
//  - evaluator     /internal/sessions.. requires EVALUATOR_TOKEN; absent token => routes disabled
import { timingSafeEqual } from "node:crypto";
import Fastify from "fastify";
import { Engine, publicSchemaHash } from "./engine.js";

export function buildServer(engine, { evaluatorToken = process.env.EVALUATOR_TOKEN } = {}) {
  const app = Fastify({ bodyLimit: 256 * 1024 });

  const fail = (reply, e) => {
    const code = e.code === "NOT_FOUND" ? 404 : e.code === "LIMIT" ? 429 : 400;
    return reply.code(code).send({ error: { code: e.code || "ENGINE_ERROR", message: String(e.message).slice(0, 200) } });
  };
  const isEvaluator = (req) => {
    if (!evaluatorToken) return false;
    const got = Buffer.from(String(req.headers["x-evaluator-token"] ?? ""));
    const want = Buffer.from(evaluatorToken);
    return got.length === want.length && timingSafeEqual(got, want);
  };
  const guard = (req, reply) => {
    if (!evaluatorToken) { reply.code(404).send({ error: { code: "NOT_FOUND", message: "disabled" } }); return false; }
    if (!isEvaluator(req)) { reply.code(403).send({ error: { code: "FORBIDDEN", message: "evaluator token required" } }); return false; }
    return true;
  };

  app.get("/health/live", async (req, reply) => {
    if (!engine.healthy) return reply.code(503).send({ status: "browser down", service: "engine" });
    return { status: "ok", service: "engine", public_schema_hash: publicSchemaHash(), sessions: engine.sessionCount };
  });

  app.post("/sessions", async (req, reply) => {
    const { scene, owner, private_config, backend } = req.body ?? {};
    if (private_config !== undefined) return reply.code(403).send({ error: { code: "FORBIDDEN", message: "private config is evaluator-only" } });
    try { return await engine.create(scene, { owner, backend }); } catch (e) { return fail(reply, e); }
  });
  app.post("/sessions/:id/actions", async (req, reply) => {
    const { owner, ...action } = req.body ?? {};
    try { return await engine.act(req.params.id, owner, action); } catch (e) { return fail(reply, e); }
  });
  app.delete("/sessions/:id", async (req, reply) => {
    try { await engine.destroyOwned(req.params.id, req.query.owner); return { ok: true }; } catch (e) { return fail(reply, e); }
  });

  app.post("/internal/sessions", async (req, reply) => {
    if (!guard(req, reply)) return;
    const { scene, owner, private_config, backend } = req.body ?? {};
    try { return await engine.create(scene, { owner, privateConfig: private_config, backend }); } catch (e) { return fail(reply, e); }
  });
  app.post("/internal/svg/measure", async (req, reply) => {
    if (!guard(req, reply)) return;
    const { svg, ids } = req.body ?? {};
    try { return { boxes: await engine.measureSvg(svg, ids) }; } catch (e) { return fail(reply, e); }
  });
  app.get("/internal/sessions/:id/native", async (req, reply) => {
    if (!guard(req, reply)) return;
    try { return await engine.nativeState(req.params.id, req.query.owner); } catch (e) { return fail(reply, e); }
  });
  return app;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const engine = new Engine();
  await engine.start();
  engine.onDisconnect(() => { console.error("browser disconnected; exiting so the supervisor restarts the engine"); process.exit(1); });
  const app = buildServer(engine);
  for (const sig of ["SIGTERM", "SIGINT"]) {
    process.on(sig, async () => { await app.close(); await engine.close(); process.exit(0); });
  }
  await app.listen({ host: process.env.HOST ?? "0.0.0.0", port: Number(process.env.PORT ?? 8090) });
}

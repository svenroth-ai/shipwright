import type { MiddlewareHandler } from "hono";

export const requestLogger: MiddlewareHandler = async (c, next) => {
  const start = Date.now();
  await next();
  const duration = Date.now() - start;

  console.log(
    JSON.stringify({
      level: "info",
      method: c.req.method,
      path: c.req.path,
      status: c.res.status,
      durationMs: duration,
    })
  );
};

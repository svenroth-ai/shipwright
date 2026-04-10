import type { ErrorHandler } from "hono";

export class AppError extends Error {
  readonly statusCode: number;
  readonly detail?: string;

  constructor(message: string, statusCode: number, detail?: string) {
    super(message);
    this.name = "AppError";
    this.statusCode = statusCode;
    this.detail = detail;
  }
}

export const errorHandler: ErrorHandler = (err, c) => {
  if (err instanceof AppError) {
    const body: { error: string; detail?: string } = {
      error: err.message,
    };
    if (err.detail) {
      body.detail = err.detail;
    }
    console.error(
      JSON.stringify({
        level: "error",
        error: err.message,
        statusCode: err.statusCode,
        detail: err.detail,
      })
    );
    return c.json(body, err.statusCode as 400);
  }

  console.error(
    JSON.stringify({
      level: "error",
      error: err instanceof Error ? err.message : "Unknown error",
      stack: err instanceof Error ? err.stack : undefined,
    })
  );
  return c.json({ error: "Internal server error" }, 500);
};

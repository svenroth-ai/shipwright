// B14: a token never leaves the adapter's Authorization header. Runs LAST: it reads everything the other checks collected
// (every answer, every companion log, every data file) and everything the fake servers saw.
import { scenario, type Ctx } from "./ctx.js";
import { HN_COMMENT } from "./checks-fetch.js";
import { post } from "./http.js";
import type { Probe } from "./probe.js";

export async function secrecy(ctx: Ctx, p: Probe): Promise<void> {
  const envToken = `E2E-DUMMY-ENV-${ctx.tokens.apify.slice(-8)}`;
  const reddit = "https://www.reddit.com/r/ProductManagement/comments/1oq7k2m/";
  const mark = ctx.fake.seen.length;
  await scenario(ctx, "precedence", { fakeUrls: true, today: true, env: { APIFY_TOKEN: envToken }, envLocal: `APIFY_TOKEN=${ctx.tokens.apify}\n` }, async (s) => {
    await post(s.api, "/api/fetch/thread", { url: reddit });
  });
  const apify = ctx.fake.seen.slice(mark).find((r) => r.service === "apify");
  p.expect(".env.local in the data folder wins over the environment", apify?.headers.authorization === `Bearer ${ctx.tokens.apify}`, apify ? "another token was sent" : "no Apify request seen");
  await scenario(ctx, "hn", { fakeUrls: true, today: true }, async (s) => { await post(s.api, "/api/fetch/thread", { url: HN_COMMENT }); });

  const secrets = [ctx.tokens.syften, ctx.tokens.apify, envToken];
  const where = ctx.leaks.filter((l) => !l.where.endsWith(".env.local") && secrets.some((t) => l.text.includes(t))).map((l) => l.where);
  p.expect(`no token appears in any answer, log or data file (${ctx.leaks.length} places read)`, where.length === 0, [...new Set(where)].slice(0, 4).join("; "));
  const seen = ctx.fake.seen.filter((r) => r.service !== "hn_algolia");
  p.expect(`the fake servers saw ${seen.length} Syften/Apify requests`, seen.length > 0);
  p.expect("no token is in any URL or request body", ctx.fake.seen.every((r) => !secrets.some((t) => r.url.includes(t) || r.body.includes(t))));
  const wrong = seen.filter((r) => r.headers.authorization !== `Bearer ${r.service === "syften" ? ctx.tokens.syften : ctx.tokens.apify}` && (r.service !== "apify" || r.headers.authorization !== `Bearer ${envToken}`));
  p.expect("every Syften and Apify request carries Authorization: Bearer <its own token>", wrong.length === 0, wrong.slice(0, 2).map((r) => `${r.service} ${r.url}`).join("; "));
  const noUa = ctx.fake.seen.filter((r) => !/social[-_ ]?engagement/i.test(String(r.headers["user-agent"] ?? "")));
  p.expect("every request carries a User-Agent that names the app", noUa.length === 0, `${noUa.length} without; e.g. ${String(noUa[0]?.headers["user-agent"])}`);
  p.expect("the companion asked for nothing the package never recorded", ctx.fake.unmatched.length === 0, ctx.fake.unmatched.slice(0, 3).join("; "));
}

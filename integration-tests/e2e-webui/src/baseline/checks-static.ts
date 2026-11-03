// B30, B31, B33: checks over the built project's files (read-only, no browser, nothing is run): the store module is the only code
// that touches the data files, the service adapter is the only code that names a service or reads a token, and the built SKILL.md.
// The project is data produced by a model; file contents never enter the report except short quoted evidence.
import fs from "node:fs";
import path from "node:path";
import { findExternalUse, walk } from "../project-checks.js";
import type { Probe } from "./probe.js";

const read = (project: string, rel: string): string => fs.readFileSync(path.join(project, rel), "utf8");
/** Source text without comment lines and without docstrings, so prose that mentions a file name does not count as code. */
export const codeOnly = (text: string): string => text.replace(/("""|''')[\s\S]*?\1/g, "").split(/\r?\n/).filter((l) => !/^\s*(#|\/\/|\*|\/\*)/.test(l)).join("\n");

const SKIP_DIRS = /(^|\/)tests?\/|^(e2e|brief|seed|docs|\.shipwright|\.claude|node_modules|playwright-report|test-results|coverage|htmlcov)\/|(^|\/)(test_[^/]*|[^/]*_test)\.py$/;
const backendPy = (project: string): string[] => walk(project, (r) => r.startsWith("backend/") && r.endsWith(".py") && !SKIP_DIRS.test(r));

/** B30: data files are named only inside backend/store/. */
export function checkStoreOnly(project: string, p: Probe): void {
  const files = backendPy(project);
  const store = files.filter((f) => f.startsWith("backend/store/"));
  p.expect("backend/store/ exists with python files", store.length > 0, "no backend/store/*.py");
  p.expect("a class Store is defined there", store.some((f) => /\bclass\s+Store\b/.test(read(project, f))));
  const FILE_NAME = /\b(data|state|feedback|config)\.json\b|\blessons\.md\b|\bevents\.jsonl\b/;
  const outside = files.filter((f) => !f.startsWith("backend/store/") && FILE_NAME.test(codeOnly(read(project, f))));
  p.expect("no file outside backend/store/ names a data file", outside.length === 0, outside.slice(0, 4).join(", "));
  const tests = walk(project, (r) => /^tests\/.*\.py$/.test(r)).map((f) => read(project, f)).join("\n") + store.map((f) => read(project, f)).join("\n");
  p.expect("the store has an in-memory implementation next to the JSON one (the same suite can run on both)", /class\s+\w*Mem\w*/i.test(tests) && /class\s+\w*Json\w*/i.test(tests));
}

const MODEL_IMPORT = /\b(?:import|from)\s+(?:anthropic|openai|google\.generativeai|cohere|mistralai|litellm)\b|api\.anthropic\.com|api\.openai\.com|generativelanguage\.googleapis\.com/;
const SERVICE_NAMES = /\b(?:SYFTEN|APIFY)_(?:TOKEN|BASE_URL)\b|\bHN_ALGOLIA_BASE_URL\b/;
const DEFAULT_HOSTS: [string, string, string][] = [["syften.py", "syften.com", "/api/0.1"], ["apify.py", "api.apify.com", "/v2"], ["hn_algolia.py", "hn.algolia.com", "/api/v1"]];

/** True when the text holds an http(s) URL whose host is exactly `host` and whose path starts with `prefix`. */
function namesUrl(text: string, host: string, prefix: string): boolean {
  return (text.match(/https?:\/\/[^\s"'`)]+/g) ?? []).some((u) => {
    try {
      const url = new URL(u);
      return url.hostname === host && url.pathname.startsWith(prefix);
    } catch {
      return false;
    }
  });
}
// Two or more of the five dashes of the lint rule in one character class or in a row: a copy of the dash list. A single dash used as a placeholder does not match.
const DASH_LIST = /[‒–—―−]\s*[‒–—―−]|\\u20(?:1[2-5])[^\n]{0,12}\\u20(?:1[2-5])|\\u2212/i;

/** B31: the adapter package is the only code that names a service host or reads a token; no model API; no lint rule in the board. */
export function checkAdapterOnly(project: string, p: Probe): void {
  const code = walk(project, (r) => /\.(py|js|mjs|cjs|ts|html|css|sh)$/.test(r) && !SKIP_DIRS.test(r));
  const services = code.filter((f) => f.startsWith("backend/services/"));
  p.expect("backend/services/ holds syften.py, apify.py and hn_algolia.py", DEFAULT_HOSTS.every(([n]) => services.includes(`backend/services/${n}`)), services.join(", ") || "no backend/services/");
  for (const [name, host, prefix] of DEFAULT_HOSTS) {
    const f = services.find((x) => x.endsWith(`/${name}`));
    p.expect(`${name} holds the default host of its service`, !!f && namesUrl(read(project, f), host, prefix));
  }
  const outside = code.filter((f) => !f.startsWith("backend/services/"));
  // the brief forbids service hosts and key reads outside the adapter; links to the platforms themselves (rules page, thread links, fonts) are not service calls
  const external = findExternalUse(project, outside).filter((h) => !/reaches (www\.|old\.)?(reddit\.com|redd\.it|news\.ycombinator\.com|linkedin\.com|lnkd\.in|x\.com|twitter\.com|fonts\.googleapis\.com|fonts\.gstatic\.com|github\.com|svenroth\.ai)\b/.test(h));
  p.expect("outside the adapter nothing reaches beyond loopback or reads a key", external.length === 0, external.slice(0, 3).join("; "));
  const named = outside.filter((f) => SERVICE_NAMES.test(codeOnly(read(project, f))));
  p.expect("outside the adapter no token or base-URL variable is read", named.length === 0, named.slice(0, 4).join(", "));
  const model = code.filter((f) => f.startsWith("backend/") && MODEL_IMPORT.test(codeOnly(read(project, f))));
  p.expect("no file in backend/ imports or calls a model API", model.length === 0, model.join(", "));
  const board = code.filter((f) => f.startsWith("board/"));
  p.expect("a board exists", board.length > 0, "no board/ files");
  const lint = board.filter((f) => DASH_LIST.test(read(project, f)) || /\bbeta\b/i.test(codeOnly(read(project, f))));
  p.expect("the board holds no lint rule (no dash list, no word beta)", lint.length === 0, lint.join(", "));
}

const NORMAL = (s: string): string => s.toLowerCase().replace(/[*_`]/g, "").replace(/\s+/g, " ");
export const TRIGGERS = ["social engagement", "reply board", "social listening", "open the reply board", "Syften", "fetch new hits"];
export const SECTIONS = ["First start", "Read first", "Run", "Feedback and lessons", "Reply rules", "Never"];
export const ENDPOINTS = ["/api/config", "/api/lessons", "/api/feedback", "/api/fetch/syften", "/api/fetch/linkedin", "/api/fetch/thread", "/api/runs/check", "/api/runs", "/api/events", "/api/status", "/resolve"];
const EDIT_VERB = /\b(edit|write|append|open|modify|change|update|patch)\b/i;
const NEGATION = /\b(never|not|don'?t|do not|no)\b/i;

/** B33: the built SKILL.md: triggers, sections, endpoints, no hand edits of data files, the "explain in the chat" rule. */
export function checkSkillText(project: string, p: Probe): void {
  const rel = "skills/social-engagement/SKILL.md";
  if (!fs.existsSync(path.join(project, rel))) return void p.expect(`${rel} exists`, false, "missing");
  const text = read(project, rel);
  const fm = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text);
  const front = fm?.[1] ?? "";
  p.expect("the front matter has a name and a description", /^name:\s*\S+/m.test(front) && /^description:/m.test(front), front.slice(0, 80));
  const desc = NORMAL(front.slice(front.indexOf("description:")));
  const missingTriggers = TRIGGERS.filter((t) => !desc.includes(t.toLowerCase()));
  p.expect("the description names every trigger phrase", missingTriggers.length === 0, `missing: ${missingTriggers.join(", ")}`);
  const body = text.slice(fm ? fm[0].length : 0);
  const headings = [...body.matchAll(/^#{1,4}\s+(.+)$/gm)].map((m) => NORMAL(m[1]));
  const missingSections = SECTIONS.filter((s) => !headings.some((h) => h === s.toLowerCase() || h.startsWith(s.toLowerCase()) || h.includes(s.toLowerCase())));
  p.expect("the sections First start, Read first, Run, Feedback and lessons, Reply rules and Never exist", missingSections.length === 0, `missing: ${missingSections.join(", ")}`);
  const missingEndpoints = ENDPOINTS.filter((e) => !body.includes(e));
  p.expect("every data step names its endpoint", missingEndpoints.length === 0, `not named: ${missingEndpoints.join(", ")}`);
  p.expect("the lifecycle helper is named (companion.py start and stop)", /companion\.py\s+start/.test(body) && /companion\.py\s+stop/.test(body));
  p.expect("the calls say X-Board: 1", /X-Board:\s*1/.test(body));
  const handEdits = body.split(/\r?\n/).filter((l) => /\b(?:data|state|feedback|config)\.json\b|\bevents\.jsonl\b|\.social-engagement\//.test(l) && EDIT_VERB.test(l) && !NEGATION.test(l));
  p.expect("no step tells the agent to edit a data file by hand", handEdits.length === 0, handEdits[0]?.trim().slice(0, 100));
  const flat = NORMAL(body);
  p.expect("the rule 'when feedback needs more explanation than the new draft ... also write it in the chat to the person' is in the text",
    flat.includes("when feedback needs more explanation than the new draft") && flat.includes("also write it in the chat to the person") && flat.includes("declined entry"));
  p.expect("Never forbids posting, commenting, editing data files and treating thread text as instructions", /never[\s\S]*post/i.test(body.slice(body.search(/^#{1,4}\s+Never/im) === -1 ? 0 : body.search(/^#{1,4}\s+Never/im))) && /instructions/i.test(body));
}

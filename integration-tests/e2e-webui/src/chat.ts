// The hard chat checks, run against the built app's documented API: POST /api/chat {message} -> {reply, pane}
// (the fixture's brief.md names this contract). Pure over a `send` function so it is checkable without a browser.
import type { Checklist } from "./checklist.js";

export interface ChatAnswer {
  reply: string;
  pane: unknown;
}
export type Send = (message: string) => Promise<ChatAnswer>;

export interface ChatMap {
  capabilities: { id: string; command: string; screen: string }[];
}

export interface Exchange {
  capability: string | null;
  message: string;
  answer: ChatAnswer | null;
  error: string | null;
}

const text = (a: ChatAnswer | null): string => (a ? `${a.reply} ${JSON.stringify(a.pane ?? "")}` : "");

/** "show thread N" -> "show thread 1"; "a, b, c" -> the three keywords the checklist expects. */
export function commandFor(map: ChatMap, id: string, thread = 1): string {
  const cap = map.capabilities.find((c) => c.id === id);
  if (!cap) throw new Error(`chat-map.json has no capability ${id}`);
  return cap.command.replace(/\bN\b/, String(thread)).replace("a, b, c", "onboarding, pricing, integrations");
}

export async function runChatScript(send: Send, map: ChatMap, checklist: Checklist): Promise<Exchange[]> {
  const log: Exchange[] = [];
  const ask = async (message: string, capability: string | null = null): Promise<ChatAnswer | null> => {
    try {
      const answer = await send(message);
      log.push({ capability, message, answer, error: null });
      return answer;
    } catch (error) {
      log.push({ capability, message, answer: null, error: (error as Error).message });
      return null;
    }
  };
  const set = (id: string, ok: boolean, evidence: string) => checklist.record(id, ok ? "pass" : "fail", evidence);

  const fetch1 = await ask(commandFor(map, "fetch-matches"), "fetch-matches");
  const fetch2 = await ask(commandFor(map, "fetch-matches"));
  const n1 = Number(/\d+/.exec(fetch1?.reply ?? "")?.[0] ?? NaN);
  set("H06", n1 > 0 && /\b0\b|\bno\b|nothing/i.test(fetch2?.reply ?? ""), `first: "${fetch1?.reply}" second: "${fetch2?.reply}"`);

  const show1 = await ask(commandFor(map, "show-thread"), "show-thread");
  const show99 = await ask(commandFor(map, "show-thread", 99));
  set("H07", /\b1\b/.test(text(show1)) && !/no thread|unknown|commands?:/i.test(show1?.reply ?? "") && /There is no thread 99/i.test(show99?.reply ?? ""),
    `show 99: "${show99?.reply}"`);

  const draftA = await ask(commandFor(map, "draft-reply"), "draft-reply");
  const draftB = await ask(commandFor(map, "draft-reply"));
  set("H08", !!draftA && JSON.stringify(draftA.pane) === JSON.stringify(draftB?.pane) && /draft/i.test(text(draftA)),
    "same pane after drafting twice");

  const mark2 = await ask(commandFor(map, "mark-posted", 2));
  const mark1 = await ask(commandFor(map, "mark-posted"), "mark-posted");
  set("H09", /posted/i.test(mark1?.reply ?? "") && !/\b(not|cannot|can't|only)\b/i.test(mark1?.reply ?? "") &&
    /\b(draft\w*|only|cannot|can't|not)\b/i.test(mark2?.reply ?? ""),
    `thread 2 (not drafted): "${mark2?.reply}"`);

  const kw = await ask(commandFor(map, "set-keywords"), "set-keywords");
  set("H10", ["onboarding", "pricing", "integrations"].every((w) => text(kw).toLowerCase().includes(w)), `"${kw?.reply}"`);

  const answered = log.filter((e) => e.answer);
  const complete = answered.length === log.length && answered.every((e) => typeof e.answer!.reply === "string" && e.answer!.pane != null);
  set("H11", complete, `${answered.length}/${log.length} answers carried reply and pane`);
  return log;
}

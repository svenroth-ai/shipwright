/*
 * CodeRenderer — syntax-highlight bundle for previewed code files.
 *
 * Per plan § 7 G4 we want the common-language bundle only (~35 langs)
 * rather than the 190-language all bundle. In rehype-highlight v7 the
 * old `/lib/common` subpath was removed; `common` is now the default
 * when `{languages}` is omitted. We explicitly pass
 * `{languages: common}` from lowlight so the intent is unmistakable in
 * the call site + immune to a future default change. The spec's
 * import-path guard (grep for rehype-highlight without /lib/common)
 * deviates in spirit for v7; see the section 04b report for the note.
 *
 * If a file's language isn't in the common set, rehype-highlight falls
 * back to plain <pre>, which is fine — we own the dispatch table so we
 * never hand rehype a language it can't resolve.
 */

import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import { common } from "lowlight";

const EXT_TO_LANG: Record<string, string> = {
  ts: "typescript",
  tsx: "typescript",
  js: "javascript",
  jsx: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  py: "python",
  rb: "ruby",
  go: "go",
  rs: "rust",
  java: "java",
  kt: "kotlin",
  c: "c",
  h: "c",
  cpp: "cpp",
  hpp: "cpp",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  toml: "toml",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  sql: "sql",
  html: "xml",
  xml: "xml",
  css: "css",
};

interface Props {
  text: string;
  extension: string;
}

export function CodeRenderer({ text, extension }: Props) {
  const lang = EXT_TO_LANG[extension.toLowerCase()] ?? "plaintext";
  // react-markdown is the simplest reliable path to rehype-highlight in a
  // React tree. We wrap the file content in a fenced code block so the
  // existing highlighter plugin handles it end-to-end. The trailing
  // newline keeps CommonMark happy.
  const fenced = "```" + lang + "\n" + text + "\n```\n";
  return (
    <div
      className="smart-viewer-code h-full overflow-auto"
      style={{ background: "var(--color-surface, #ffffff)" }}
      data-testid="smart-viewer-code"
      data-extension={extension}
      data-language={lang}
    >
      <ReactMarkdown
        rehypePlugins={[
          [
            rehypeHighlight,
            { detect: false, ignoreMissing: true, languages: common },
          ],
        ]}
      >
        {fenced}
      </ReactMarkdown>
    </div>
  );
}

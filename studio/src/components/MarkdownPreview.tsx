import { Fragment, type ReactNode } from "react";

export function MarkdownPreview({ content }: { content: string }) {
  const blocks: ReactNode[] = [];
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  let paragraph: string[] = [];
  let list: string[] = [];
  let code: string[] | null = null;

  const flushParagraph = () => {
    if (paragraph.length > 0) {
      blocks.push(<p key={`p-${blocks.length}`}>{inline(paragraph.join(" "))}</p>);
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list.length > 0) {
      blocks.push(<ul key={`ul-${blocks.length}`}>{list.map((item, index) => <li key={index}>{inline(item)}</li>)}</ul>);
      list = [];
    }
  };

  lines.forEach((line) => {
    if (line.startsWith("```")) {
      flushParagraph();
      flushList();
      if (code === null) code = [];
      else {
        blocks.push(<pre key={`code-${blocks.length}`}><code>{code.join("\n")}</code></pre>);
        code = null;
      }
      return;
    }
    if (code !== null) {
      code.push(line);
      return;
    }
    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      const children = inline(heading[2]);
      if (level === 1) blocks.push(<h1 key={`h-${blocks.length}`}>{children}</h1>);
      else if (level === 2) blocks.push(<h2 key={`h-${blocks.length}`}>{children}</h2>);
      else if (level === 3) blocks.push(<h3 key={`h-${blocks.length}`}>{children}</h3>);
      else blocks.push(<h4 key={`h-${blocks.length}`}>{children}</h4>);
      return;
    }
    const listItem = /^[-*]\s+(.+)$/.exec(line);
    if (listItem) {
      flushParagraph();
      list.push(listItem[1]);
      return;
    }
    if (!line.trim()) {
      flushParagraph();
      flushList();
      return;
    }
    flushList();
    paragraph.push(line.trim());
  });
  flushParagraph();
  flushList();
  const trailingCode = code as string[] | null;
  if (trailingCode !== null) blocks.push(<pre key={`code-${blocks.length}`}><code>{trailingCode.join("\n")}</code></pre>);

  return <article className="markdown-preview">{blocks}</article>;
}

function inline(value: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
  let cursor = 0;
  for (const match of value.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > cursor) nodes.push(value.slice(cursor, index));
    const token = match[0];
    if (token.startsWith("`")) nodes.push(<code key={index}>{token.slice(1, -1)}</code>);
    else if (token.startsWith("**")) nodes.push(<strong key={index}>{token.slice(2, -2)}</strong>);
    else {
      const parts = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      const href = safeHref(parts?.[2] ?? "");
      nodes.push(href ? <a key={index} href={href} target="_blank" rel="noopener noreferrer">{parts?.[1]}</a> : <Fragment key={index}>{parts?.[1]}</Fragment>);
    }
    cursor = index + token.length;
  }
  if (cursor < value.length) nodes.push(value.slice(cursor));
  return nodes;
}

function safeHref(value: string): string | null {
  const trimmed = value.trim();
  if (/^(https?:|mailto:)/i.test(trimmed) || trimmed.startsWith("/") || trimmed.startsWith("#")) return trimmed;
  return null;
}

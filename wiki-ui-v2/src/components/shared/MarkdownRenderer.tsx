import { marked } from 'marked';

interface Props {
  content: string;
  onNavigate?: (path: string) => void;
  plainLinks?: boolean;
}

function parseWikilink(raw: string) {
  const idx = raw.indexOf('|');
  const path = idx >= 0 ? raw.slice(0, idx).trim() : raw.trim();
  const label = idx >= 0 ? raw.slice(idx + 1).trim() : (path.split('/').pop() || path).replace(/\.md$/i, '');
  return { path, label };
}

function InlineTokens({ tokens, onNav, plain }: { tokens: any[]; onNav?: (path: string) => void; plain?: boolean }) {
  return <>{tokens.map((t, i) => {
    if (t.type === 'text') {
      const text = (t as any).text || '';
      const parts = text.split(/(\[\[[^\]]+\]\])/g);
      return <span key={i}>{parts.map((part: string, j: number) => {
        const m = part.match(/^\[\[([^\]]+)\]\]$/);
        if (m) {
          const { label } = parseWikilink(m[1]);
          if (plain) return <span key={j} className="text-muted-foreground">{label}</span>;
          return (
            <span
              key={j}
              className="wikilink text-sm cursor-pointer"
              onClick={() => onNav?.(m[1].split('|')[0]?.trim() || m[1].trim())}
            >
              {label}
            </span>
          );
        }
        return <span key={j}>{part}</span>;
      })}</span>;
    }
    if (t.type === 'strong') return <strong key={i}>{(t as any).text}</strong>;
    if (t.type === 'em') return <em key={i}>{(t as any).text}</em>;
    if (t.type === 'del') return <del key={i}>{(t as any).text}</del>;
    if (t.type === 'codespan') return <code key={i} className="px-1 py-0.5 rounded text-xs bg-muted">{(t as any).text}</code>;
    if (t.type === 'link') return <a key={i} href={(t as any).href} className="text-sm text-blue-500 hover:underline">{(t as any).text}</a>;
    if (t.type === 'image') return <img key={i} src={(t as any).href} alt={(t as any).text} className="max-w-full rounded" />;
    if (t.type === 'br') return <br key={i} />;
    return <span key={i}>{(t as any).raw || ''}</span>;
  })}</>;
}

const headingCls: Record<number, string> = {
  1: 'text-xl font-bold border-b border-border pb-1 mb-3 mt-6',
  2: 'text-lg font-semibold mt-5 mb-2',
  3: 'text-base font-semibold mt-4 mb-1',
  4: 'text-sm font-semibold mt-3 mb-1',
  5: 'text-sm font-medium mt-2 mb-1',
  6: 'text-xs font-medium mt-2 mb-1',
};

export default function MarkdownRenderer({ content, onNavigate, plainLinks }: Props) {
  const tokens = marked.lexer(content);

  return (
    <div className="md-content">
      {tokens.map((token, i) => {
        switch (token.type) {
          case 'heading': {
            const t = token as any;
            const cls = headingCls[t.depth] || '';
            const { text } = t;
            switch (t.depth) {
              case 1: return <h1 key={i} className={cls}>{text}</h1>;
              case 2: return <h2 key={i} className={cls}>{text}</h2>;
              case 3: return <h3 key={i} className={cls}>{text}</h3>;
              case 4: return <h4 key={i} className={cls}>{text}</h4>;
              case 5: return <h5 key={i} className={cls}>{text}</h5>;
              default: return <h6 key={i} className={cls}>{text}</h6>;
            }
          }
          case 'paragraph': {
            const t = token as any;
            return <p key={i} className="mb-2 text-sm leading-relaxed"><InlineTokens tokens={t.tokens} onNav={onNavigate} plain={plainLinks} /></p>;
          }
          case 'code': {
            const t = token as any;
            return (
              <pre key={i} className="bg-muted rounded-lg p-3 my-2 text-xs overflow-x-auto border border-border">
                <code>{t.text}</code>
              </pre>
            );
          }
          case 'list': {
            const t = token as any;
            const Tag = t.ordered ? 'ol' : 'ul';
            return (
              <Tag key={i} className={`mb-2 pl-5 text-sm ${t.ordered ? 'list-decimal' : 'list-disc'}`}>
                {t.items.map((item: any, j: number) => (
                  <li key={j} className="mb-0.5"><InlineTokens tokens={item.tokens} onNav={onNavigate} plain={plainLinks} /></li>
                ))}
              </Tag>
            );
          }
          case 'table': {
            const t = token as any;
            return (
              <div key={i} className="overflow-x-auto mb-3">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr>{t.header.map((h: any, j: number) => (
                      <th key={j} className="border border-border px-3 py-2 text-left font-semibold bg-muted">{h.text}</th>
                    ))}</tr>
                  </thead>
                  <tbody>
                    {t.rows.map((row: any[], j: number) => (
                      <tr key={j}>{row.map((cell: any, k: number) => (
                        <td key={k} className="border border-border px-3 py-1.5">{cell.text}</td>
                      ))}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          }
          case 'blockquote': {
            const t = token as any;
            return (
              <blockquote key={i} className="border-l-3 border-blue-500 pl-4 mb-2 text-sm text-muted-foreground">
                {t.tokens ? <InlineTokens tokens={t.tokens} onNav={onNavigate} plain={plainLinks} /> : t.text}
              </blockquote>
            );
          }
          case 'hr':
            return <hr key={i} className="border-t border-border my-4" />;
          case 'space':
            return null;
          case 'html': {
            const t = token as any;
            return <div key={i} className="text-sm mb-2" dangerouslySetInnerHTML={{ __html: t.text }} />;
          }
          default:
            return null;
        }
      })}
    </div>
  );
}

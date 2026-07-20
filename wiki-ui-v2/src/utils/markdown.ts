import { marked } from 'marked';

export function stripFrontmatter(content: string): string {
  const lines = content.split('\n');
  if (lines.length >= 2 && lines[0].trim() === '---') {
    for (let i = 1; i < lines.length; i++) {
      if (lines[i].trim() === '---') {
        return lines.slice(i + 1).join('\n');
      }
    }
  }
  return content;
}

export function renderMarkdown(md: string): string {
  const body = stripFrontmatter(md);
  const withLinks = body.replace(
    /\[\[([^\]]+)\]\]/g,
    (_, raw: string) => {
      const idx = raw.indexOf('|');
      const path = idx >= 0 ? raw.slice(0, idx).trim() : raw.trim();
      const label = idx >= 0
        ? raw.slice(idx + 1).trim()
        : (path.split('/').pop() || path).replace(/\.md$/i, '');
      return `<span class="wikilink" data-wiki-path="${path}" title="${path}">${label}</span>`;
    }
  );
  return marked.parse(withLinks, { breaks: true }) as string;
}

export function escapeHtml(str: string): string {
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}

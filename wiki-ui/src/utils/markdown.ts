import { marked } from 'marked';

/** Strip YAML frontmatter from markdown content */
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

/** Render markdown to HTML, with wikilink support */
export function renderMarkdown(md: string, onNavigate?: (path: string) => void): string {
  const body = stripFrontmatter(md);

  // Convert [[wikilinks]] to clickable spans before marked runs
  const withLinks = body.replace(
    /\[\[([^\]]+)\]\]/g,
    (_, path) => `<span class="wikilink" data-wiki-path="${path}">${path}</span>`
  );

  const html = marked.parse(withLinks, { breaks: true }) as string;

  // Wrap in a container that handles wikilink clicks
  return html;
}

/** Simple HTML escape */
export function escapeHtml(str: string): string {
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}

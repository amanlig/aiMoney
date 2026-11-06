import {html} from './ui.js';

// Render the supported Markdown as React text/elements; model output is never HTML.
function inline(text) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, index) =>
    part.startsWith('**') && part.endsWith('**') ? html`<strong key=${index}>${part.slice(2, -2)}</strong>` :
    part.startsWith('`') && part.endsWith('`') ? html`<code key=${index}>${part.slice(1, -1)}</code>` : part);
}

function cells(line) {
  return line.trim().replace(/^\|/, '').replace(/(?<!\\)\|$/, '').split(/(?<!\\)\|/).map(cell => cell.trim().replace(/\\\|/g, '|'));
}

function tableStart(lines, index) {
  if (!lines[index]?.includes('|') || !lines[index + 1]?.includes('|')) return false;
  const header = cells(lines[index]), separator = cells(lines[index + 1]);
  return header.length > 1 && header.length === separator.length && separator.every(cell => /^:?-{3,}:?$/.test(cell));
}

export function Assessment({text = ''}) {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  const blocks = [];
  for (let i = 0; i < lines.length;) {
    if (!lines[i].trim()) {i++; continue;}
    const key = i;
    if (tableStart(lines, i)) {
      const header = cells(lines[i]), rows = [];
      i += 2;
      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) {
        const row = cells(lines[i]);
        if (row.length !== header.length) break;
        rows.push(row); i++;
      }
      blocks.push(html`<div className="assessment-table-scroll" key=${key} role="region" aria-label="Recommendation comparison" tabIndex="0"><table>
        <thead><tr>${header.map((cell, column) => html`<th key=${column} scope="col">${inline(cell)}</th>`)}</tr></thead>
        <tbody>${rows.map((row, index) => html`<tr key=${index}>${row.map((cell, column) => html`<td key=${column}>${inline(cell)}</td>`)}</tr>`)}</tbody>
      </table></div>`);
    } else if (/^#{1,6}\s+/.test(lines[i])) {
      blocks.push(html`<h3 key=${key}>${inline(lines[i++].replace(/^#{1,6}\s+/, ''))}</h3>`);
    } else if (/^\s*[-*+]\s+/.test(lines[i]) || /^\s*\d+[.)]\s+/.test(lines[i])) {
      const ordered = /^\s*\d+[.)]\s+/.test(lines[i]);
      const pattern = ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*+]\s+/;
      const items = [];
      while (i < lines.length && pattern.test(lines[i])) items.push(lines[i++].replace(pattern, ''));
      const content = items.map((item, index) => html`<li key=${index}>${inline(item)}</li>`);
      blocks.push(ordered ? html`<ol key=${key}>${content}</ol>` : html`<ul key=${key}>${content}</ul>`);
    } else {
      const paragraph = [lines[i++]];
      while (i < lines.length && lines[i].trim() && !tableStart(lines, i) && !/^\s*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s)/.test(lines[i])) paragraph.push(lines[i++]);
      blocks.push(html`<p key=${key}>${inline(paragraph.join('\n'))}</p>`);
    }
  }
  return html`<div className="assessment-content">${blocks}</div>`;
}

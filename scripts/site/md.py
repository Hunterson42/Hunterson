"""
A small Markdown renderer for the site's documents: the methodology, the
statements, the licence and the evidence page are written in Markdown in the
public repository, and the site shows them as pages, made from that text each
time the site is built, so the two can never drift apart.

It renders the subset the documents use: headings, with GitHub's anchors;
paragraphs; rules; bulleted and numbered lists, one level; tables; fenced code;
and, inline, bold, italic, code, links, and bare web and email addresses.
Anything else is shown as plain text, escaped. Links between the documents are
turned into links between the site's pages by the caller's link function.

    html, headings = render(text, link=None)
    section(text, ["Title one", "Title two"])   # just those level-2 sections

Uses only the Python standard library.
"""
import html as _html
import re

_FENCE = re.compile(r"^```")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_RULE = re.compile(r"^(-{3,}|\*{3,}|_{3,})\s*$")
_BULLET = re.compile(r"^[-*]\s+(.*)$")
_NUMBER = re.compile(r"^(\d+)\.\s+(.*)$")
_TABLE_SEP = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def slug(text):
    """GitHub's anchor for a heading: lower case, punctuation dropped, spaces to hyphens."""
    t = re.sub(r"<[^>]+>", "", text).strip().lower()
    t = re.sub(r"[^\w\- ]", "", t)
    return t.replace(" ", "-")


def plain(text):
    """The heading's words without Markdown marks."""
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"[*_`]", "", t).strip()


def inline(text, link=None, codes=None):
    top = codes is None
    codes = [] if top else codes
    link = link or (lambda href: href)
    out = text

    def keep(fragment):
        codes.append(fragment)
        return "\x00%d\x00" % (len(codes) - 1)

    out = re.sub(r"`([^`]+)`", lambda m: keep("<code>%s</code>" % _html.escape(m.group(1), quote=False)), out)

    def a(m):
        label, href = m.group(1), m.group(2).strip()
        return keep('<a href="%s">%s</a>' % (_html.escape(link(href)), inline(label, link, codes)))

    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", a, out)
    out = re.sub(r"(?<![\w/\"'=])(https?://[^\s<>()\"\x00]+[^\s<>()\".,;:!?'\x00])",
                 lambda m: keep('<a href="%s">%s</a>' % (_html.escape(m.group(1)), _html.escape(m.group(1), quote=False))), out)
    out = re.sub(r"(?<![\w.@/])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w@])",
                 lambda m: keep('<a href="mailto:%s">%s</a>' % (m.group(1), m.group(1))), out)
    out = _html.escape(out, quote=False)
    out = re.sub(r"\*\*(\S(?:.*?\S)?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*(\S(?:[^*]*?\S)?)\*(?![\w*])", r"<em>\1</em>", out)
    for _ in range(8 if top else 0):                  # kept fragments may hold others, such as code in a link
        if "\x00" not in out:
            break
        out = re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], out)
    return out


def _cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def render(text, link=None):
    """(html, [(level, plain text, anchor), ...])."""
    lines = text.replace("\r\n", "\n").split("\n")
    out, heads, i, used = [], [], 0, {}
    para = []

    def flush():
        if para:
            out.append("<p>%s</p>" % inline(" ".join(s.strip() for s in para), link))
            del para[:]

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            flush()
            i += 1
            continue
        if _FENCE.match(line):
            flush()
            body = []
            i += 1
            while i < len(lines) and not _FENCE.match(lines[i]):
                body.append(lines[i])
                i += 1
            out.append("<pre><code>%s</code></pre>" % _html.escape("\n".join(body), quote=False))
            i += 1
            continue
        m = _HEADING.match(line)
        if m:
            flush()
            level, words = len(m.group(1)), m.group(2)
            anchor = slug(plain(words))
            n = used.get(anchor, 0)
            used[anchor] = n + 1
            if n:
                anchor = "%s-%d" % (anchor, n)
            heads.append((level, plain(words), anchor))
            out.append('<h%d id="%s">%s</h%d>' % (level, anchor, inline(words, link), level))
            i += 1
            continue
        if _RULE.match(line) and not para:
            out.append("<hr>")
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1].strip()):
            flush()
            head = _cells(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            t = ['<div class="table-scroll"><table>', "<thead><tr>%s</tr></thead>"
                 % "".join('<th scope="col">%s</th>' % inline(c, link) for c in head), "<tbody>"]
            for r in rows:
                t.append("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c, link) for c in r))
            t.append("</tbody></table></div>")
            out.append("\n".join(t))
            continue
        b, n = _BULLET.match(line), _NUMBER.match(line)
        if (b or n) and not para:
            tag = "ul" if b else "ol"
            start = int(n.group(1)) if n else 1
            items = []
            while i < len(lines):
                cur = lines[i]
                mb, mn = _BULLET.match(cur), _NUMBER.match(cur)
                if (tag == "ul" and mb) or (tag == "ol" and mn):
                    items.append([(mb or mn).group(1) if mb else mn.group(2)])
                elif cur.strip() and cur.startswith((" ", "\t")) and items:
                    items[-1].append(cur.strip())
                else:
                    break
                i += 1
            attr = ' start="%d"' % start if tag == "ol" and start != 1 else ""
            out.append("<%s%s>\n%s\n</%s>" % (tag, attr, "\n".join("<li>%s</li>" % inline(" ".join(it), link)
                                                                     for it in items), tag))
            continue
        para.append(line)
        i += 1
    flush()
    return "\n".join(out), heads


def section(text, titles):
    """The level-2 sections with these titles, in the order given, each with its heading."""
    blocks, cur, name = {}, [], None
    for line in text.split("\n"):
        m = re.match(r"^##\s+(.*?)\s*$", line)
        if m and not line.startswith("###"):
            if name is not None:
                blocks[name] = cur
            name, cur = m.group(1), [line]
        elif name is not None:
            cur.append(line)
    if name is not None:
        blocks[name] = cur
    missing = [t for t in titles if t not in blocks]
    if missing:
        raise ValueError("no section titled %s" % ", ".join(missing))
    return "\n".join("\n".join(blocks[t]) for t in titles)

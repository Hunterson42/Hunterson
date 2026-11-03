"""
The site's pages other than the price: built by publish.py each time it runs,
beside the price pages, so that a reader never has to leave hunterson.org.

    methodology/              the methodology in force, from METHODOLOGY.md
    methodology/VERSION/      each version as first published here; never changed
    iosco/, conflicts/, continuity/, licence/
                              the statements and the licence, from IOSCO.md,
                              CONFLICTS.md, CONTINUITY.md and LICENCE-DATA.md
    evidence/                 how to check a fingerprint and its timestamps,
                              from the README
    data/                     what the downloads hold, and how to cite a figure
    GRADE/archive/            every assessment day of a live grade, by month
    404.html                  the page for an address that does not exist
    feed.xml                  an Atom feed of the latest 30 assessment days
    data/latest.json          the latest assessment, for programs
    sitemap.xml, robots.txt   for search engines
    favicon.ico               the site's icon, for browsers that ask for it

The documents stay in Markdown in the public repository, where every change is
kept; each page is made from that text on every build (md.py), so the page and
the repository can never differ. Uses only the Python standard library.
"""
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil

import md

REPO_HOME = "https://github.com/Hunterson42/Hunterson"
DOCS = [
    # (source, folder, title, description, menu item)
    ("METHODOLOGY.md", "methodology", "Methodology",
     "How each Hunterson figure is made: the product, the test, the rules for including a provider, and the calculation.",
     "Methodology"),
    ("IOSCO.md", "iosco", "Hunterson and the IOSCO principles",
     "How Hunterson stands against each of the IOSCO principles for price reporting agencies.", None),
    ("CONFLICTS.md", "conflicts", "Statement of interests and conflicts",
     "What Hunterson's producer owns, earns and does that could bear on the figures, and how conflicts are kept out.", None),
    ("CONTINUITY.md", "continuity", "Continuity", "What happens if Hunterson cannot continue, for a time or for good.", None),
    ("LICENCE-DATA.md", "licence", "Hunterson Data Licence",
     "The terms on which the Hunterson figures may be used: free with credit, a free registration for contracts, "
     "financial products and indices, and an agreement for distribution.", None),
]
SITE_PATH = {src: folder + "/" for src, folder, _, _, _ in DOCS}
COLUMNS = {
    "date": "The assessment day, as YYYY-MM-DD.",
    "grade": "The grade, such as standard.",
    "status": "published; not_published, with the reason; or shadow, a day before the grade's first assessment, which is not an assessment.",
    "reference": "The grade's reference model that day.",
    "output": "The output price: US dollars per million output tokens. Blank on a day not published.",
    "input": "The input price: US dollars per million input tokens.",
    "blended": "Input and output blended 16 to 1, as the test job is: US dollars per million tokens.",
    "contributors": "Providers that passed every test and contributed to the price.",
    "panel": "Providers tested.",
    "reason": "On a day not published, why.",
    "output_before_discounts": "The output price at the providers' listed prices, before any discount.",
    "input_before_discounts": "The input price before any discount.",
    "blended_before_discounts": "The blended price before any discount.",
    "rollover_ratio": "On the day the reference changes, the ratio for converting a price on the old reference to the new.",
    "url": "The day's permanent page, the address to cite.",
    "challenger": "The leading challenger: of the other models tested in the grade, the one with the most providers. For information only.",
    "challenger_input": "The challenger's input price, assessed in the same way. Not an assessment of the grade.",
    "challenger_output": "The challenger's output price, assessed in the same way.",
    "challenger_contributors": "The challenger's contributors.",
    "challenger_panel": "Providers tested for the challenger.",
    "challenger_output_ratio": "The challenger's output price divided by the reference's, to four places.",
}


def e(s):
    return html.escape(str(s), quote=True)


def read(root, name):
    with open(os.path.join(root, name), encoding="utf-8") as f:
        return f.read()


def linker(root_rel):
    """How a link in a document becomes a link on the site, from a page at root_rel."""
    def link(href):
        if href.startswith(("http://", "https://", "mailto:", "#")):
            return href
        path, _, anchor = href.partition("#")
        path = path[2:] if path.startswith("./") else path
        if path in SITE_PATH:
            return root_rel + SITE_PATH[path] + ("#" + anchor if anchor else "")
        kind = "tree" if path.endswith("/") or "." not in os.path.basename(path) else "blob"
        return "%s/%s/main/%s%s" % (REPO_HOME, kind, path, "#" + anchor if anchor else "")
    return link


def methodology_version(text):
    m = re.search(r"^Version (\d+(?:\.\d+)+), ([^.\n]+)\.", text, re.M)
    if not m:
        raise ValueError("METHODOLOGY.md does not state its version on a line 'Version N.N, DATE.'")
    return m.group(1), m.group(2)


def contents(heads):
    items = ['<li><a href="#%s">%s</a></li>' % (a, e(t)) for level, t, a in heads if level == 2 and t != "Methodology"]
    return ('<nav class="contents" aria-label="Contents"><p class="contents-h">Contents</p><ul>%s</ul></nav>\n'
            % "".join(items)) if len(items) > 3 else ""


def before_first_rule(body, extra):
    """Put the version note and the contents after the document's opening, before its first rule."""
    i = body.find("<hr>")
    return body[:i] + extra + body[i:] if i >= 0 else extra + body


def page(P, opts, template, root, title, description, body, path, current=None, notice="", source_line=""):
    canonical = '<link rel="canonical" href="%s/%s">\n' % (e(opts["base_url"]), e(path)) if path is not None else ""
    values = {
        "title": e(title), "description": e(description), "canonical": canonical,
        "robots": '<meta name="robots" content="noindex">\n' if opts["preview"] or path is None else "",
        "head_links": P.head_links(root), "root": root, "home": root or "./", "product": e(opts["product"]),
        "nav": P.nav_html(root, current), "notice": notice, "body": body, "source_line": source_line,
        "contact": e(opts["contact"]), "foot_links": P.foot_links_html(root),
    }
    out = P.fill(template, values)
    if "{{" in out:
        raise ValueError("unfilled placeholder in " + (path or "404.html"))
    return out


def source(name):
    return ('The same text is kept in the public repository as <a href="%s/blob/main/%s">%s</a>, with every '
            'change to it. ' % (REPO_HOME, name, name))


def documents(P, opts, template, out_dir, docs_root):
    written = []
    for src, folder, title, desc, menu in DOCS:
        text = read(docs_root, src)
        body, heads = md.render(text, linker("../"))
        notice = ""
        if src == "METHODOLOGY.md":
            version, fixed = methodology_version(text)
            note = ('<p class="notice note" role="note">The copy of version %s that is never changed is at '
                    '<a href="%s/">hunterson.org/methodology/%s/</a>; each day\'s page links to the version in force '
                    'that day.</p>\n' % (e(version), e(version), e(version)))
            body = before_first_rule(body, note + contents(heads))
        P.write(os.path.join(out_dir, folder, "index.html"),
                page(P, opts, template, "../", title, desc, body, folder + "/", menu, notice, source(src)), False,
                opts["preview"])
        written.append(folder + "/")
        if src == "METHODOLOGY.md":
            vbody, vheads = md.render(text, linker("../../"))
            vnotice = ('<p class="notice note" role="note">Methodology version %s, as first published here. This page '
                       'is never changed. The version in force now is at <a href="../">hunterson.org/methodology/</a>.'
                       '</p>\n' % e(version))
            vpage = page(P, opts, template, "../../", "Methodology, version %s" % version, desc,
                         before_first_rule(vbody, vnotice + contents(vheads)), "%s/%s/" % (folder, version), menu, "",
                         source(src))
            mark = "<!-- METHODOLOGY.md sha256:%s -->\n" % hashlib.sha256(text.encode()).hexdigest()
            vpage = vpage.replace("<body>\n", "<body>\n" + mark, 1)
            vpath = os.path.join(out_dir, folder, version, "index.html")
            if os.path.exists(vpath) and not opts["preview"]:
                with open(vpath) as f:
                    if mark not in f.read():           # kept as first published, whatever the site's design since
                        print("Note: METHODOLOGY.md has changed but still says version %s; the page for version %s "
                              "is kept as first published. A change to the methodology needs a new version." % (version, version))
            else:
                P.write(vpath, vpage, False, opts["preview"])
            written.append("%s/%s/" % (folder, version))
    return written


def evidence(P, opts, template, out_dir, docs_root):
    text = md.section(read(docs_root, "README.md"), ["Raw files and fingerprints", "How to check a fingerprint and its timestamps"])
    body, _ = md.render(text, linker("../"))
    intro = ('<h1>The evidence</h1>\n<p>Every record behind every figure is fingerprinted, and every fingerprint is '
             'timestamped by two independent services, when it is made and before anything is published. So anyone '
             'shown a record later can check that it existed then and has not changed since.</p>\n'
             '<ul>\n<li><a href="%s/tree/main/data/hashes">The fingerprints</a>, with their timestamp proofs beside them</li>\n'
             '<li><a href="%s/tree/main/data/assessments">The assessments</a>: every provider tested each day, what it was '
             'charged, and why any was excluded</li>\n<li><a href="%s/tree/main/data/stamps/certs">The timestamp '
             'authority\'s certificates</a>, kept so that a proof can be checked even if the service goes</li>\n</ul>\n'
             % (REPO_HOME, REPO_HOME, REPO_HOME))
    note = ("<p>The rest of this page is the public repository's own explanation, as it stands in its README; "
            "\"here\" in it means the repository.</p>\n")
    P.write(os.path.join(out_dir, "evidence", "index.html"),
            page(P, opts, template, "../", "The evidence", "How to check that any Hunterson record existed when it "
                 "was made and has not changed since.", intro + note + body, "evidence/", None, "", source("README.md")),
            False, opts["preview"])
    return ["evidence/"]


def data_page(P, opts, template, out_dir, columns, latest, g):
    missing = [c for c in columns if c not in COLUMNS]
    if missing:
        raise ValueError("the data page has no description for column %s" % ", ".join(missing))
    rows = "\n".join('<tr><td><code>%s</code></td><td>%s</td></tr>' % (c, e(COLUMNS[c])) for c in columns)
    cite = ""
    if latest and latest.get("price"):
        cite = ("<p>Cite the day's permanent page. For example: <q>%s, %s: input %s, output %s per million tokens. "
                "%s/%s/%s/</q> Each day's page has this line ready to copy.</p>"
                % (e(g["product"]), e(P.long_date(latest["date"])), e(P.money(latest["price"]["input"])),
                   e(P.money(latest["price"]["output"])), e(opts["base_url"]), g["key"], latest["date"]))
    body = """<h1>Data</h1>
<p>Every assessment Hunterson has published, with the shadow period before the first, is free to download and use with credit: "Source: %s, hunterson.org". Using the figures to settle a contract, value a financial instrument, measure a fund or make up an index needs a free registration, so that everyone relying on them is told directly when the rules change (<a href="../licence/">the licence</a>).</p>
<h2>The files</h2>
<ul>
<li><a href="assessments.csv">assessments.csv</a>: every day of every live grade, one row a day, with the columns below.</li>
<li><a href="assessments.json">assessments.json</a>: the same, grouped by grade, with the unit, the blend and the licence.</li>
<li><a href="latest.json">latest.json</a>: the latest assessment only, for programs.</li>
<li><a href="../feed.xml">feed.xml</a>: an Atom feed of the latest 30 assessment days, for a feed reader.</li>
<li><a href="%s/tree/main/data/assessments">The assessments themselves</a>, in the public repository: each day, every provider tested, what it was charged, and why any was excluded.</li>
</ul>
<h2>Units and rounding</h2>
<p>Prices are in US dollars per million tokens, to four decimal places, rounded half up by the assessor and never re-rounded. The blended price weights input and output 16 to 1, the shape of the test job. A row whose status is "shadow" was produced before the grade's first assessment and is not an assessment.</p>
<h2>What each column means</h2>
<div class="table-scroll"><table>
<thead><tr><th scope="col">Column</th><th scope="col">What it holds</th></tr></thead>
<tbody>
%s
</tbody></table></div>
<h2>How to cite a figure</h2>
%s
""" % (e(g["product"]), REPO_HOME, rows, cite)
    P.write(os.path.join(out_dir, "data", "index.html"),
            page(P, opts, template, "../", "Data", "Every Hunterson assessment, free to download: CSV, JSON, the "
                 "latest figure and a feed, with what each column means and how to cite a figure.", body, "data/",
                 "Data"), False, opts["preview"])
    return ["data/"]


def archive(P, opts, template, out_dir, days, g):
    shown = [d for d in days if d["status"] != "shadow"]
    months = {}
    for d in shown:
        months.setdefault(d["date"][:7], []).append(d)
    parts = ["<h1>Every assessment</h1>", "<p>Every assessment day of %s, newest first. Each date links to the day's "
             "permanent page, which is never changed. The same figures are in the <a href=\"../../data/\">data "
             "files</a>.</p>" % e(g["product"])]
    for ym in sorted(months, reverse=True):
        y, mo = ym.split("-")
        parts.append('<h2 id="m%s">%s %s</h2>' % (ym, P.MONTHS[int(mo) - 1], y))
        rows = []
        for d in sorted(months[ym], key=lambda x: x["date"], reverse=True):
            link = '<a href="../%s/">%s</a>' % (d["date"], e(P.weekday_date(d["date"])))
            if d.get("price"):
                p = d["price"]
                cells = '<td class="r">%s</td><td class="r">%s</td><td class="r">%s</td>' % (
                    e(P.money(p["input"])), e(P.money(p["output"])), e(P.money(p["blended"])))
            else:
                cells = '<td colspan="3">Not published: %s</td>' % e(d.get("reason") or "too few contributors")
            count = "" if d.get("suspended") else "%d of %d" % (d["contributors"], d["panel"])
            rows.append('<tr><th scope="row">%s</th>%s<td class="r">%s</td></tr>' % (link, cells, count))
        parts.append('<div class="table-scroll"><table class="archive"><thead><tr><th scope="col">Date</th>'
                     '<th scope="col" class="r">Input</th><th scope="col" class="r">Output</th><th scope="col" class="r">'
                     'Blended</th><th scope="col" class="r">Contributors</th></tr></thead><tbody>\n%s\n</tbody></table>'
                     '</div>' % "\n".join(rows))
    if not shown:
        parts.append("<p>No assessment has been published yet.</p>")
    P.write(os.path.join(out_dir, g["key"], "archive", "index.html"),
            page(P, opts, template, "../../", "Every assessment, %s" % g["product"],
                 "Every assessment day of %s, with its figures and its permanent page." % g["product"],
                 "\n".join(parts), g["key"] + "/archive/"), False, opts["preview"])
    return [g["key"] + "/archive/"]


def not_found(P, opts, template, out_dir, g):
    body = ("<h1>Page not found</h1>\n<p>There is no page at this address. It may be mistyped, or the page may never "
            "have existed: every day's price has a permanent address of the form "
            "<code>hunterson.org/%s/YYYY-MM-DD/</code>, and a day before the first assessment has none.</p>\n"
            '<ul>\n<li><a href="/">The latest price</a></li>\n<li><a href="/%s/archive/">Every assessment</a></li>\n'
            '<li><a href="/methodology/">The methodology</a></li>\n</ul>' % (g["key"], g["key"]))
    P.write(os.path.join(out_dir, "404.html"),
            page(P, opts, template, "/", "Page not found, Hunterson", "No page at this address.", body, None),
            False, opts["preview"])


def feed(P, opts, out_dir, days, g):
    shown = [d for d in days if d["status"] != "shadow"][-30:]
    base = opts["base_url"]
    entries = []
    for i, d in enumerate(reversed(shown)):
        url = "%s/%s/%s/" % (base, g["key"], d["date"])
        if d.get("price"):
            title = "%s: input %s, output %s per million tokens" % (P.long_date(d["date"]), P.money(d["price"]["input"]),
                                                                    P.money(d["price"]["output"]))
        else:
            title = "%s: not published" % P.long_date(d["date"])
        idx = days.index(d)
        summary = P.tweet_text(d, P.previous_published(days, idx), base, g).rsplit("\n", 1)[0].strip()
        when = d.get("published_utc") or d["date"] + "T16:00:00Z"
        entries.append("<entry><id>%s</id><title>%s</title><link href=\"%s\"/><updated>%s</updated>"
                       "<summary>%s</summary></entry>" % (html.escape(url), html.escape(title), html.escape(url),
                                                          html.escape(when), html.escape(summary)))
    updated = (shown[-1].get("published_utc") or shown[-1]["date"] + "T16:00:00Z") if shown else \
        dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = ('<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">'
           "<id>%s/</id><title>%s</title><subtitle>The daily price, in US dollars per million tokens.</subtitle>"
           '<link href="%s/"/><link rel="self" href="%s/feed.xml"/><updated>%s</updated>'
           "<author><name>Malcolm Hunter</name></author><rights>Free to use with credit. See %s/licence/</rights>\n%s\n</feed>\n"
           % (html.escape(base), html.escape(g["product"]), html.escape(base), html.escape(base), html.escape(updated),
              html.escape(base), "\n".join(entries)))
    P.write(os.path.join(out_dir, "feed.xml"), xml, False, opts["preview"])


def latest_json(P, opts, out_dir, days, g):
    shown = [d for d in days if d["status"] != "shadow"]
    if not shown:
        return None
    d = shown[-1]
    p = d.get("price") or {}
    doc = {"schema": 1, "grade": g["key"], "product": g["product"], "date": d["date"], "status": d["status"],
           "reason": d.get("reason"), "reference": d["name"], "input": p.get("input"), "output": p.get("output"),
           "blended": p.get("blended"), "contributors": d["contributors"], "panel": d["panel"],
           "methodology_version": d.get("methodology_version"), "published_utc": d.get("published_utc"),
           "url": "%s/%s/%s/" % (opts["base_url"], g["key"], d["date"]), "unit": "US dollars per million tokens",
           "licence": opts["base_url"] + "/licence/"}
    P.write(os.path.join(out_dir, "data", "latest.json"), json.dumps(doc, indent=1) + "\n", False, opts["preview"])
    return d


def sitemap(P, opts, out_dir, paths):
    base = opts["base_url"]
    urls = "\n".join("<url><loc>%s/%s</loc></url>" % (html.escape(base), html.escape(p)) for p in paths)
    P.write(os.path.join(out_dir, "sitemap.xml"),
            '<?xml version="1.0" encoding="utf-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s\n'
            "</urlset>\n" % urls, False, opts["preview"])
    robots = "User-agent: *\nDisallow: /\n" if opts["preview"] else \
        "User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % base
    P.write(os.path.join(out_dir, "robots.txt"), robots, False, opts["preview"])


def build(P, opts, out_dir, docs_root, by_grade, home_key, columns):
    """Every page above. by_grade holds only the grades with public pages."""
    with open(os.path.join(P.HERE, "doc.html")) as f:
        template = f.read()
    g = P.grade(home_key)
    paths = ["", "about/", "census/"]
    paths += documents(P, opts, template, out_dir, docs_root)
    paths += evidence(P, opts, template, out_dir, docs_root)
    latest = latest_json(P, opts, out_dir, by_grade[home_key], g)
    paths += data_page(P, opts, template, out_dir, columns, latest, g)
    for key, days in by_grade.items():
        gk = P.grade(key)
        paths += archive(P, opts, template, out_dir, days, gk)
        paths.append(key + "/")
        paths += ["%s/%s/" % (key, d["date"]) for d in days if d["status"] != "shadow"]
    not_found(P, opts, template, out_dir, g)
    feed(P, opts, out_dir, by_grade[home_key], g)
    sitemap(P, opts, out_dir, paths)
    shutil.copy(os.path.join(P.HERE, "assets", "favicon.ico"), os.path.join(out_dir, "favicon.ico"))
    return paths

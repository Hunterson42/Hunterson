"""
Builds the public price pages, the data files and the daily post from the
assessor's files, after each assessment, in the private repository's Publish
workflow; the mirror then copies docs/ to the public repository, which GitHub
Pages serves at hunterson.org. Nothing is built before a grade's launch date.

Reads one file per checkpoint per day, data/assessments/DATE/SLUG.json, in
the contract described in launch/sample.py (kept private). For each grade,
the file marked "reference": true gives the price; of the others, the one
with the most providers is shown beside it as the leading challenger, for
information (decision D40).

The headline is the input and the output price together, with the blend
beneath (decision D49). Notes for the site, such as the stale-reference note
(D40, tripwire 11), are read from site_notes.json. If oversight has not been
confirmed within 45 days, publication is suspended (decision D50, see
oversight.py and CONTINUITY.md).

Writes, under OUT, for each grade (GRADE is its key, such as "standard"):
    GRADE/index.html            the grade's latest day; rewritten daily
    GRADE/DATE/index.html       the permanent page for each assessment day; written once
    card/GRADE/DATE.html        the image card for the day, rendered to og/GRADE/DATE.png
                                by scripts/site/render_cards.py; written once
    tweet/GRADE/DATE.txt        the daily post; written once
and once for the site:
    tweet/notice/DATE.txt       the notice that publication is suspended from DATE, posted
                                once by scripts/post.py; written once
    index.html                  the home page: the live grade's latest day; rewritten daily
    data/assessments.json       every day of every grade, for anyone to download
    data/assessments.csv        the same as CSV, with a grade column
    about/index.html            about Hunterson; rewritten daily
    assets/                     styles, the chart script and the fonts

While one grade is live, the home page is that grade's latest day. When a
second grade goes live, the build stops until the home page table described
in launch/README.md is added; it never quietly drops a grade.

Usage:
    python3 scripts/site/publish.py ASSESSMENTS_DIR OUT_DIR [--preview]
        [--base-url https://hunterson.org] [--census-url URL] [--contact ADDRESS]
        [--oversight data/oversight.json] [--notes site_notes.json] [--today YYYY-MM-DD]

--preview builds a private preview: it marks every page "noindex", shows a
banner, and is the only mode that accepts illustrative files. Without it, the
build refuses illustrative files and refuses to change any file that is
written once. Uses only the Python standard library.
"""
import argparse
import csv
import datetime as dt
import html
import io
import json
import os
import re
import shutil
import sys
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)        # for oversight.py, beside this file
SHOW_SHADOW = True          # show the shadow period in the history, labelled; see README
BLEND = "16 input tokens to 1 output token"
METHODOLOGY_URL = "https://github.com/Hunterson42/Hunterson/blob/main/METHODOLOGY.md"
EVIDENCE_URL = "https://github.com/Hunterson42/Hunterson/tree/main/data/hashes"
REPO_URL = "https://github.com/Hunterson42/Hunterson/blob/main/"
CONFLICTS_URL = REPO_URL + "CONFLICTS.md"
CONTINUITY_URL = REPO_URL + "CONTINUITY.md"
IOSCO_URL = REPO_URL + "IOSCO.md"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# The grades, in the fixed order used everywhere: pages, tables and the colours
# of any future comparison chart (categorical slots 1, 2 and 3). Bands follow
# the methodology; the Frontier floor is provisional.
GRADES = [
    {"key": "standard", "name": "Standard", "product": "Hunterson Standard Inference, Europe",
     "band": "Standard covers models that use 30 billion active parameters or fewer for each token."},
    {"key": "heavy", "name": "Heavy", "product": "Hunterson Heavy Inference, Europe",
     "band": "Heavy covers models that use more than 30 billion and up to 70 billion active parameters for each token."},
    {"key": "frontier", "name": "Frontier", "product": "Hunterson Frontier Inference, Europe",
     "band": "Frontier covers models that use more than 70 billion active parameters for each token."},
]
TWEET_LIMIT = 280
URL_WEIGHT = 23             # X counts every link as 23 characters


class WriteOnceError(Exception):
    pass


# Formatting ---------------------------------------------------------------

def e(s):
    return html.escape(str(s), quote=True)


def d_of(s):
    return dt.date.fromisoformat(s)


def long_date(s):
    d = d_of(s)
    return "%d %s %d" % (d.day, MONTHS[d.month - 1], d.year)


def weekday_date(s):
    return DAYS[d_of(s).weekday()] + " " + long_date(s)


def day_month(s):
    d = d_of(s)
    return "%d %s" % (d.day, MONTHS[d.month - 1])


def money(s):
    return "$" + str(Decimal(s).quantize(Decimal("0.0001")))


def hero_money(s):
    return '<span class="cur">$</span>' + e(Decimal(s).quantize(Decimal("0.0001")))


def pct(x):
    return str(x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def change(cur, prev, key="output"):
    """Change against the previous published assessment: (direction, dollars, percent)."""
    a, b = Decimal(cur["price"][key]), Decimal(prev["price"][key])
    diff = a - b
    if diff == 0:
        return "unchanged", "$0.0000", "0.00"
    p = abs(diff) / b * 100
    return ("up" if diff > 0 else "down"), money(abs(diff)), pct(p)


def changes(cur, prev):
    """[(label, direction, dollars, percent)] for the input and the output price (D49)."""
    return [(k,) + change(cur, prev, k) for k in ("input", "output")]


def ratio(a, b):
    """a / b to four places, halves up, as a string; None without both."""
    if not a or not b or Decimal(b) == 0:
        return None
    return str((Decimal(a) / Decimal(b)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def discount_depth(day):
    u, p = Decimal(day["undiscounted"]["output"]), Decimal(day["price"]["output"])
    if u <= 0:
        return None
    return pct((u - p) / u * 100)


# Loading ------------------------------------------------------------------

def grade_of(rec):
    for g in GRADES:
        if str(rec.get("grade", "")).lower() == g["name"].lower():
            return g
    raise ValueError("%s: unknown grade %r" % (rec.get("date"), rec.get("grade")))


def leading(others):
    """The leading challenger among a day's other assessments in a grade: the most
    providers in the panel, then the most contributors, then by name (D40)."""
    if not others:
        return None
    return sorted(others, key=lambda r: (-int(r.get("panel") or 0), -int(r.get("contributors") or 0),
                                         str(r.get("name") or r.get("checkpoint"))))[0]


def load(assess_dir):
    """The reference assessment for each grade on each day: {grade key: [day, ...]} in date order.
    Each day carries the leading challenger's assessment, if any, as day["challenger"]."""
    by_grade = {g["key"]: [] for g in GRADES}
    for name in sorted(os.listdir(assess_dir)):
        folder = os.path.join(assess_dir, name)
        if not os.path.isdir(folder):
            continue
        seen, others = {}, {}
        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".json"):
                continue
            with open(os.path.join(folder, fn)) as f:
                rec = json.load(f)
            g = grade_of(rec)
            if not rec.get("reference"):
                others.setdefault(g["key"], []).append(rec)
                continue
            if g["key"] in seen:
                raise ValueError("%s: more than one %s file is marked as the reference" % (name, g["name"]))
            seen[g["key"]] = rec
        for key, rec in seen.items():
            rec = dict(rec, challenger=leading(others.get(key)))
            by_grade[key].append(rec)
    return {k: v for k, v in by_grade.items() if v}


def grade(key):
    return next(g for g in GRADES if g["key"] == key)


def previous_published(days, idx):
    for j in range(idx - 1, -1, -1):
        if days[j]["status"] == "published":
            return days[j]
    return None


# Pieces of the page -------------------------------------------------------

def series(days):
    out = []
    for d in days:
        if d["status"] == "shadow" and not SHOW_SHADOW:
            continue
        p = d.get("price") or {}
        out.append({
            "d": d["date"], "s": d["status"], "ref": d["name"], "c": d["contributors"], "n": d["panel"],
            "r": d.get("reason"),
            "o": float(p["output"]) if p.get("output") else None,
            "i": float(p["input"]) if p.get("input") else None,
            "b": float(p["blended"]) if p.get("blended") else None,
            "roll": (d.get("rollover") or {}).get("ratio"),
        })
    # Keep "</" out of the script block.
    return json.dumps(out, separators=(",", ":")).replace("</", "<\\/")


def change_html(day, prev, g):
    if not day.get("price"):
        if not prev:
            return ""
        return ('<p class="fix-change">The last assessment was input %s and output %s per million tokens, on '
                '<a href="%s">%s</a>.</p>' % (money(prev["price"]["input"]), money(prev["price"]["output"]),
                                             "{{root}}%s/%s/" % (g["key"], prev["date"]), long_date(prev["date"])))
    if day.get("rollover"):
        r = day["rollover"]
        return ('<p class="fix-change">The reference changed today, from %s to %s. Conversion ratio %s.</p>'
                % (e(r["from"]), e(day["name"]), e(r["ratio"])))
    if not prev:
        return '<p class="fix-change">The first assessment.</p>' if day["status"] == "published" else ""
    parts = changes(day, prev)
    if all(p[1] == "unchanged" for p in parts):
        return '<p class="fix-change">Unchanged since %s.</p>' % day_month(prev["date"])
    out = []
    for i, (key, direction, dollars, p) in enumerate(parts):
        label = key.capitalize() if i == 0 else key
        if direction == "unchanged":
            out.append("%s unchanged" % label)
        else:
            glyph = "&#9650;" if direction == "up" else "&#9660;"
            out.append('<span class="dir" aria-hidden="true">%s</span>%s %s %s, or %s%%' % (glyph, label, direction, dollars, p))
    return '<p class="fix-change">%s, since %s</p>' % ("; ".join(out), day_month(prev["date"]))


def record_html(day):
    rows = []

    def row(label, value, note=None):
        rows.append('      <dt>%s</dt><dd>%s%s</dd>' % (e(label), value, "<small>%s</small>" % e(note) if note else ""))

    if day.get("price"):
        row("Blended", e(money(day["price"]["blended"])), BLEND)
    if not day.get("suspended"):
        row("Contributors", "%d of %d" % (day["contributors"], day["panel"]), "providers tested")
    row("Model", e(day["name"]), "the reference, as the lab published it")
    w = day.get("window") or {}
    if w.get("start_utc") and w.get("end_utc"):
        row("Bought", "%s to %s UTC" % (w["start_utc"][11:16], w["end_utc"][11:16]), "through OpenRouter, from London")
    if day.get("undiscounted") and day.get("price"):
        dd = discount_depth(day)
        row("Before discounts", "%s input, %s output" % (e(money(day["undiscounted"]["input"])), e(money(day["undiscounted"]["output"]))),
            "discounts take off %s%% of the output price" % dd if dd else None)
    return "\n".join(rows)


def panel_html(day):
    if day.get("suspended"):
        return ("No figure was published for this day, because publication was suspended. The purchases were made "
                "and recorded, and are kept privately with their fingerprints."), ""
    contributors = sorted([p for p in day["providers"] if p["result"] == "contributor"],
                          key=lambda p: Decimal(p["output"]))
    excluded = sorted([p for p in day["providers"] if p["result"] != "contributor"], key=lambda p: p["provider"].lower())
    first_in = next((i for i, p in enumerate(contributors) if p.get("in_mean")), 0)
    rows = []
    for i, p in enumerate(contributors):
        if p.get("in_mean"):
            res, short = "In the average", "In the average"
        else:
            end = "Lowest" if i < first_in else "Highest"
            res = "Left out of the average<span class=\"why\">%s quarter of prices</span>" % end
            short = "Left out: %s quarter" % end.lower()
        rows.append('          <tr><th scope="row">%s<span class="why res-m">%s</span></th><td class="r">%s</td><td class="r">%s</td><td class="res">%s</td></tr>'
                    % (e(p["provider"]), short, e(money(p["input"])), e(money(p["output"])), res))
    for p in excluded:
        why = e(p.get("reason") or "")
        rows.append('          <tr class="out"><th scope="row">%s<span class="why res-m">Excluded: %s</span></th><td class="r"></td><td class="r"></td>'
                    '<td class="res">Excluded<span class="why">%s</span></td></tr>' % (e(p["provider"]), why, why))
    n_c = len(contributors)
    k = n_c // 4
    intro = "%d providers were tested. %d passed every test and contributed" % (day["panel"], n_c)
    if not day.get("price"):
        intro += ", fewer than the five needed to publish a price."
    elif k:
        intro += "; the price is the average of the middle %d, leaving out the lowest %d and the highest %d." % (n_c - 2 * k, k, k)
    else:
        intro += "; the price is the average of all of them."
    if excluded:
        intro += " %d %s excluded, for the reason shown." % (len(excluded), "was" if len(excluded) == 1 else "were")
    return intro, "\n".join(rows)


def recent_html(days, upto_idx, root, g):
    pool = [d for d in days[:upto_idx + 1] if d["status"] != "shadow"] or days[:upto_idx + 1]
    rows = []
    for d in reversed(pool[-10:]):
        label = long_date(d["date"]) + (" (shadow)" if d["status"] == "shadow" else "")
        link = '<a href="%s%s/%s/">%s</a>' % (root, g["key"], d["date"], e(label)) if d["status"] != "shadow" else e(label)
        if d.get("price"):
            cells = '<td class="r">%s</td><td class="r">%s</td><td class="r wide">%s</td>' % (
                e(money(d["price"]["input"])), e(money(d["price"]["output"])), e(money(d["price"]["blended"])))
        elif d["status"] == "shadow":
            cells = '<td class="r" colspan="2">No figure yet</td><td class="r wide"></td>'
        else:
            cells = '<td class="r" colspan="2">Not published</td><td class="r wide"></td>'
        count = "" if d.get("suspended") else "%d of %d" % (d["contributors"], d["panel"])
        rows.append('          <tr><th scope="row">%s</th>%s<td class="r">%s</td></tr>' % (link, cells, count))
    return "\n".join(rows)


def tweet_text(day, prev, base_url, g):
    url = "%s/%s/%s/" % (base_url, g["key"], day["date"])
    head = "%s\n%s\n\n" % (g["product"], long_date(day["date"]))
    if not day.get("price"):
        body = "Not published: %s.\n" % (day.get("reason") or "too few contributors")
        if prev:
            body += "Last assessment: input %s, output %s per million tokens, %s.\n" % (
                money(prev["price"]["input"]), money(prev["price"]["output"]), day_month(prev["date"]))
    else:
        p = day["price"]
        lines = ["Input %s, output %s per million tokens" % (money(p["input"]), money(p["output"]))]
        if day.get("rollover"):
            lines.append("New reference, ratio %s" % day["rollover"]["ratio"])
        elif prev:
            parts = changes(day, prev)
            if all(x[1] == "unchanged" for x in parts):
                lines.append("Unchanged")
            else:
                lines.append(", ".join("%s %s" % (k if i else k.capitalize(), "unchanged" if d == "unchanged" else "%s %s%%" % (d, pc))
                                       for i, (k, d, _, pc) in enumerate(parts)))
        else:
            lines.append("The first assessment")
        body = "%s\nBlended %s. %d contributors. %s.\n" % ("\n".join(lines), money(p["blended"]), day["contributors"], day["name"])
    text = head + body + "\n" + url
    weight = len(text) - len(url) + URL_WEIGHT
    if weight > TWEET_LIMIT:
        raise ValueError("post for %s is %d characters, over %d" % (day["date"], weight, TWEET_LIMIT))
    return text


def notice_text(opts, g):
    """The post announcing that publication is suspended (D50, CONTINUITY.md)."""
    text = ("%s\nPublication is suspended from %s: oversight of the figures has not been confirmed within %d days. "
            "No figure is published until it is.\n\nWhat happens when Hunterson cannot continue:\n%s"
            % (g["product"], long_date(opts["suspended_since"]), opts.get("lapse_days") or 45, CONTINUITY_URL))
    if len(text) - len(CONTINUITY_URL) + URL_WEIGHT > TWEET_LIMIT:
        raise ValueError("the suspension notice is over %d characters" % TWEET_LIMIT)
    return text


# Assembly -----------------------------------------------------------------

def fill(template, values):
    out = template
    for k, v in values.items():
        out = out.replace("{{%s}}" % k, v)
    return out


def figure_html(day, prev):
    if not day.get("price"):
        reason = day.get("reason") or "too few contributors"
        return '<p class="fix-figure closed">Not published</p>', e(reason[0].upper() + reason[1:] + ".")
    p = day["price"]
    return ('<div class="fix-pair"><div><p class="fix-label">Input</p><p class="fix-figure">%s</p></div>'
            '<div><p class="fix-label">Output</p><p class="fix-figure">%s</p></div></div>'
            % (hero_money(p["input"]), hero_money(p["output"])), "per million tokens, input and output")


def challenger_html(day, g):
    """The leading challenger, beside the reference, for information (D40)."""
    c = day.get("challenger")
    if not c or day["status"] == "shadow" and not day.get("price") and not c.get("price"):
        return ""
    name = e(c.get("name") or c.get("checkpoint"))
    if c.get("price"):
        r = ratio(c["price"]["output"], (day.get("price") or {}).get("output"))
        text = ("%s has the most providers after the reference. Assessed in the same way today: input %s, output %s "
                "per million tokens, from %d of %d contributors" % (name, e(money(c["price"]["input"])),
                                                                    e(money(c["price"]["output"])), c["contributors"], c["panel"]))
        text += "; its output price is %s times the reference's." % e(r) if r else "."
    else:
        text = ("%s has the most providers after the reference. Assessed in the same way today, it had %d of %d "
                "contributors, fewer than the five needed for a figure." % (name, c["contributors"], c["panel"]))
    text += " Shown for information: it is not an assessment of the grade, and it does not change the figures above."
    return ('<section class="block" id="challenger" aria-labelledby="ch-h">\n    <h2 id="ch-h">The leading challenger</h2>\n'
            '    <p>%s</p>\n  </section>' % text)


def notes_html(notes, g, day_date, kind):
    """Notes for the site, from site_notes.json: on a day page, those dated that day;
    on the grade's latest page, those from the previous 30 days."""
    out = []
    for n in notes or []:
        if n.get("grade", g["key"]) != g["key"]:
            continue
        nd = n.get("date")
        if kind == "day" and nd != day_date:
            continue
        if kind != "day" and not (nd and 0 <= (d_of(day_date) - d_of(nd)).days <= 30):
            continue
        out.append('<p class="notice note" role="note"><strong>%s.</strong> %s</p>' % (e(n.get("title", "Note")), e(n.get("text", ""))))
    return "\n".join(out)


def page(days, idx, kind, opts, template, g):
    """kind: "home" (the site's front page), "grade" (GRADE/, its latest day) or "day" (GRADE/DATE/)."""
    day, prev = days[idx], previous_published(days, idx)
    root = {"home": "", "grade": "../", "day": "../../"}[kind]
    base = opts["base_url"]
    permalink = "%s/%s/%s/" % (base, g["key"], day["date"])
    canonical = {"home": base + "/", "grade": "%s/%s/" % (base, g["key"]), "day": permalink}[kind]
    fig, unit = figure_html(day, prev)
    cite = ""
    if day.get("price"):
        cite_text = "%s, %s: input %s, output %s per million tokens. %s" % (
            g["product"], long_date(day["date"]), money(day["price"]["input"]), money(day["price"]["output"]), permalink)
        cite = ('<div class="cite"><p id="cite-text">%s</p><button type="button" id="copy-cite">Copy</button></div>'
                % e(cite_text))
    intro, panel_rows = panel_html(day)
    if not day.get("price"):
        title_fig = "not published"
        description = "No assessment on %s: %s." % (long_date(day["date"]), day.get("reason") or "too few contributors")
    else:
        title_fig = "input %s, output %s per million tokens" % (money(day["price"]["input"]), money(day["price"]["output"]))
        description = ("Delivered open-weight AI inference, %s: %s per million output tokens, %s input, %s blended. %d contributors."
                       % (long_date(day["date"]), money(day["price"]["output"]), money(day["price"]["input"]),
                          money(day["price"]["blended"]), day["contributors"]))
    notice = ""
    if opts["preview"]:
        notice = ('<p class="notice" role="note">Private preview. %s Not published.</p>'
                  % ("Illustrative figures for design only; these are not assessments." if day.get("illustrative")
                     else "Shadow period figures; these are not assessments." if day["status"] == "shadow" else ""))
    elif kind == "day":
        notice = ('<p class="notice" role="note">This is the permanent record for %s. It is never changed. '
                  '<a href="../">See the latest assessment</a>.</p>' % long_date(day["date"]))
    if kind != "day" and opts.get("suspended_since"):
        notice += ('\n<p class="notice" role="note">Publication is suspended. Oversight of these figures was last '
                   'confirmed on %s, so no figure has been published since %s; when it resumes, the gap will show as a '
                   'break in the series. The figures below are from the last assessment published. '
                   '<a href="%s">What happens when Hunterson cannot continue</a>.</p>'
                   % (long_date(opts["last_confirmed"]), long_date(opts["suspended_since"]), CONTINUITY_URL))
    notes = notes_html(opts.get("notes"), g, day["date"], kind)
    if notes:
        notice += "\n" + notes
    date_line = weekday_date(day["date"])
    if day.get("published_utc") and day["status"] == "published":
        date_line += ", published %s UTC" % day["published_utc"][11:16]
    about = ("The price of AI inference, measured by buying it. Each weekday between 14:00 and 15:00 UTC, from London, "
             "Hunterson buys the same test job from every provider serving %s through one marketplace, and keeps the receipts. "
             "The figures are the averages of what the middle half of qualifying providers charged, per million input and per million output tokens. "
             "%s A token is about three quarters of a word." % (e(day["name"]), e(g["band"])))
    values = {
        "title": e("%s: %s, %s" % (g["product"], title_fig, long_date(day["date"]))), "product": e(g["product"]),
        "description": e(description), "canonical": e(canonical), "og_title": e("%s, %s" % (title_fig[0].upper() + title_fig[1:], long_date(day["date"]))),
        "og_image": e("%s/og/%s/%s.png" % (base, g["key"], day["date"])),
        "og_alt": e("%s, %s: %s" % (g["product"], long_date(day["date"]), title_fig)),
        "robots": '<meta name="robots" content="noindex">\n' if opts["preview"] else "",
        "root": root, "home": root or "./", "nav_current": ' aria-current="page"' if kind == "home" else "",
        "methodology_url": e(opts["methodology_url"]),
        "census_url": e(opts["census_url"] if "://" in opts["census_url"] else root + opts["census_url"]),
        "evidence_url": e(EVIDENCE_URL),
        "notice": notice, "date_long": e(long_date(day["date"])), "date_line": e(date_line),
        "figure": fig, "unit_line": unit, "change": change_html(day, prev, g).replace("{{root}}", root), "cite": cite,
        "record": record_html(day), "about": about, "challenger": challenger_html(day, g),
        "about_url": root + "about/", "conflicts_url": CONFLICTS_URL, "continuity_url": CONTINUITY_URL,
        "iosco_url": IOSCO_URL,
        "panel_heading": "The providers behind this figure", "panel_intro": e(intro), "panel_rows": panel_rows,
        "recent_rows": recent_html(days, idx, root, g), "series_json": series(days[:idx + 1]),
        "methodology_version": e(day.get("methodology_version") or ""), "base_url": e(base), "contact": e(opts["contact"]),
        "permalink_line": 'Permanent link for this assessment: <a href="%s">%s</a>' % (e(permalink), e(permalink)),
    }
    out = fill(template, values)
    if "{{" in out:
        raise ValueError("unfilled placeholder in page for " + day["date"])
    return out


def card(days, idx, opts, template, g):
    day, prev = days[idx], previous_published(days, idx)
    fig, unit = figure_html(day, prev)
    fig = fig.replace("fix-figure", "fig").replace("fix-pair", "pair").replace("fix-label", "lab")
    chg = re.sub(r"</?a[^>]*>", "", change_html(day, prev, g).replace("fix-change", "chg"))
    published = [d for d in days[:idx + 1] if d["status"] == "published"]
    side, wide = "", ""
    if not day.get("price"):
        wide = " wide"
    elif len(published) >= 10:
        last30 = published[-30:]
        side = '<div class="side"><p class="label">Last %d assessments, output</p><div id="chart"></div></div>' % len(last30)
    else:
        p = day["price"]
        side = ('<div class="side"><dl><dt>Blended</dt><dd>%s</dd>'
                '<dt>Contributors</dt><dd>%d of %d</dd></dl></div>' % (money(p["blended"]), day["contributors"], day["panel"]))
    chart_days = published[-30:] if side and 'id="chart"' in side else []
    values = {
        "title": e("Hunterson card %s %s" % (g["key"], day["date"])), "product": e(g["product"]), "root": "../../",
        "date_long": e(long_date(day["date"])), "figure": fig,
        "unit_line": unit, "change": chg, "side": side, "wide": wide,
        "url_short": e("%s/%s/%s/" % (opts["base_url"].replace("https://", ""), g["key"], day["date"])),
        "contributors_line": e(day["name"] if "<dl>" in side else "%d contributors. %s" % (day["contributors"], day["name"])),
        "stamp": '<span class="stamp">Illustrative</span>' if day.get("illustrative") else "",
        "series_json": series(chart_days),
    }
    out = fill(template, values)
    if "{{" in out:
        raise ValueError("unfilled placeholder in card for " + day["date"])
    return out


def exports(by_grade, base):
    rows, groups = [], []
    for g in GRADES:
        days = by_grade.get(g["key"], [])
        if not days:
            continue
        grows = export_rows(days, base, g)
        rows += grows
        groups.append({"grade": g["key"], "name": g["name"], "product": g["product"], "band": g["band"], "days": grows})
    rows.sort(key=lambda r: (r["date"], [x["key"] for x in GRADES].index(r["grade"])))
    doc = {"schema": 3, "publisher": "Hunterson",
           "licence": base + "/licence/",
           "licence_terms": "Free to use with credit. Use in contracts, financial products or indices needs a "
                            "free registration. Distribution as a data service needs an agreement.",
           "unit": "US dollars per million tokens", "blend": BLEND,
           "note": "Rows with status 'shadow' were produced before a grade's first assessment and are not assessments. "
                   "The challenger columns give the leading challenger's figures, for information; they are not "
                   "assessments of the grade.",
           "grades": groups}
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else ["date"], lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    return json.dumps(doc, indent=1) + "\n", buf.getvalue()


def export_rows(days, base, g):
    rows = []
    for d in days:
        if d["status"] == "shadow" and not SHOW_SHADOW:
            continue
        p, u = d.get("price") or {}, d.get("undiscounted") or {}
        rows.append({
            "date": d["date"], "grade": g["key"], "status": d["status"], "reference": d["name"],
            "output": p.get("output"), "input": p.get("input"), "blended": p.get("blended"),
            "contributors": d["contributors"], "panel": d["panel"], "reason": d.get("reason"),
            "output_before_discounts": u.get("output"), "input_before_discounts": u.get("input"),
            "blended_before_discounts": u.get("blended"),
            "rollover_ratio": (d.get("rollover") or {}).get("ratio"),
            "url": "%s/%s/%s/" % (base, g["key"], d["date"]) if d["status"] != "shadow" else None,
        })
        c = d.get("challenger") or {}
        cp = c.get("price") or {}
        rows[-1].update({
            "challenger": c.get("name") or c.get("checkpoint"), "challenger_input": cp.get("input"),
            "challenger_output": cp.get("output"), "challenger_contributors": c.get("contributors"),
            "challenger_panel": c.get("panel"), "challenger_output_ratio": ratio(cp.get("output"), p.get("output")),
        })
    return rows


def write(path, text, once, preview):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if once and not preview and os.path.exists(path):
        with open(path) as f:
            if f.read() != text:
                raise WriteOnceError("%s already exists and would change; written-once files are never changed" % path)
        return False
    with open(path, "w") as f:
        f.write(text)
    return True


SUSPENDED_REASON = "publication was suspended, because oversight was not confirmed within 45 days"


def apply_oversight(by_grade, st):
    """Days within a past suspension become days not published; days from the start of
    a current suspension are left out until oversight is confirmed (D50)."""
    import oversight
    out = {}
    for key, days in by_grade.items():
        kept = []
        for d in days:
            if d["status"] != "shadow" and oversight.excluded(d["date"], st):
                if st["suspended_since"] and d["date"] >= st["suspended_since"]:
                    continue
                # Nothing measured that day is shown, not even the providers' prices.
                d = dict(d, status="not_published", price=None, undiscounted=None, reason=SUSPENDED_REASON,
                         challenger=None, suspended=True, providers=[])
            kept.append(d)
        if kept:
            out[key] = kept
    return out


def about_page(opts, template, g):
    values = {"root": "../", "product": e(g["product"]), "methodology_url": e(opts["methodology_url"]),
              "census_url": e(opts["census_url"] if "://" in opts["census_url"] else "../" + opts["census_url"]),
              "evidence_url": e(EVIDENCE_URL), "conflicts_url": e(CONFLICTS_URL), "continuity_url": e(CONTINUITY_URL),
              "iosco_url": e(IOSCO_URL), "base_url": e(opts["base_url"]), "contact": e(opts["contact"]),
              "robots": '<meta name="robots" content="noindex">\n' if opts["preview"] else ""}
    out = fill(template, values)
    if "{{" in out:
        raise ValueError("unfilled placeholder in the about page")
    return out


def build(assess_dir, out_dir, preview=False, base_url="https://hunterson.org",
          census_url="census/", contact="malcolm@hunterson.org", methodology_url=METHODOLOGY_URL,
          oversight_status=None, notes=None):
    by_grade = load(assess_dir)
    if not by_grade:
        raise ValueError("no reference assessments found in " + assess_dir)
    if not preview and any(d.get("illustrative") for days in by_grade.values() for d in days):
        raise ValueError("illustrative files can only be built as a preview")
    if oversight_status:
        by_grade = apply_oversight(by_grade, oversight_status)
    live = [k for k, days in by_grade.items() if any(d["status"] != "shadow" for d in days)]
    if not live and not preview:
        return 0                          # before the first publication, nothing is built
    if len(live) > 1 and not preview:
        raise ValueError("more than one grade is live (%s); add the home page table described in launch/README.md first"
                         % ", ".join(live))
    home_key = live[0] if live else next(iter(by_grade))
    opts = {"preview": preview, "base_url": base_url.rstrip("/"), "census_url": census_url,
            "contact": contact, "methodology_url": methodology_url, "notes": notes or [],
            "suspended_since": (oversight_status or {}).get("suspended_since"),
            "last_confirmed": (oversight_status or {}).get("last_confirmed"),
            "lapse_days": (oversight_status or {}).get("lapse_days")}
    with open(os.path.join(HERE, "page.html")) as f:
        page_t = f.read()
    with open(os.path.join(HERE, "card.html")) as f:
        card_t = f.read()
    with open(os.path.join(HERE, "about.html")) as f:
        about_t = f.read()
    shutil.copytree(os.path.join(HERE, "assets"), os.path.join(out_dir, "assets"), dirs_exist_ok=True)
    built = 0
    for key, days in by_grade.items():
        g = grade(key)
        if key not in live and not preview:
            continue                      # a grade still in its shadow period gets no public pages
        last = len(days) - 1
        if key == home_key:
            write(os.path.join(out_dir, "index.html"), page(days, last, "home", opts, page_t, g), False, preview)
        write(os.path.join(out_dir, key, "index.html"), page(days, last, "grade", opts, page_t, g), False, preview)
        for i, d in enumerate(days):
            if d["status"] == "shadow" and not preview:
                continue
            write(os.path.join(out_dir, key, d["date"], "index.html"), page(days, i, "day", opts, page_t, g), True, preview)
            write(os.path.join(out_dir, "card", key, d["date"] + ".html"), card(days, i, opts, card_t, g), True, preview)
            write(os.path.join(out_dir, "tweet", key, d["date"] + ".txt"),
                  tweet_text(d, previous_published(days, i), opts["base_url"], g), True, preview)
        built += len(days)
    if opts["suspended_since"]:
        write(os.path.join(out_dir, "tweet", "notice", opts["suspended_since"] + ".txt"),
              notice_text(opts, grade(home_key)), True, preview)
    write(os.path.join(out_dir, "about", "index.html"), about_page(opts, about_t, grade(home_key)), False, preview)
    js, csv_text = exports(by_grade if preview else {k: v for k, v in by_grade.items() if k in live}, opts["base_url"])
    write(os.path.join(out_dir, "data", "assessments.json"), js, False, preview)
    write(os.path.join(out_dir, "data", "assessments.csv"), csv_text, False, preview)
    return built


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the Hunterson price pages.")
    ap.add_argument("assessments")
    ap.add_argument("out")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--base-url", default="https://hunterson.org")
    ap.add_argument("--census-url", default="census/")
    ap.add_argument("--contact", default="malcolm@hunterson.org")
    ap.add_argument("--oversight", help="data/oversight.json: suspend publication if oversight has lapsed (D50)")
    ap.add_argument("--notes", help="site_notes.json: notes shown on the pages, such as the stale-reference note")
    ap.add_argument("--today", help="YYYY-MM-DD, for the tests; otherwise today in UTC")
    a = ap.parse_args(argv)
    today = dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(dt.timezone.utc).date()
    st, notes = None, None
    try:
        if a.oversight:
            import oversight
            st = oversight.status(oversight.load(a.oversight), today)
            if st["suspended_since"]:
                print("Publication is suspended: oversight last confirmed %s." % st["last_confirmed"])
        if a.notes and os.path.exists(a.notes):
            with open(a.notes) as f:
                notes = json.load(f).get("notes") or []
        n = build(a.assessments, a.out, a.preview, a.base_url, a.census_url, a.contact,
                  oversight_status=st, notes=notes)
    except (ValueError, WriteOnceError) as err:
        print("STOPPED: %s" % err)
        return 1
    if n == 0:
        print("Nothing to build: no grade has reached its launch date.")
        return 0
    print("Built %d days into %s%s." % (n, a.out, " (preview)" if a.preview else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

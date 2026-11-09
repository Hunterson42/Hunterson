"""
Reads the research readings with thinking left on (decision D52, roadmap step
63): the reference, bought once from each provider at each effort after the
weekend reading, in data/offwindow/DATE-HHMM-thinking/. Never part of the
assessment.

For each provider and effort it shows whether the reply thought, how many
thinking tokens it used and how many it billed as output, whether the answer's
first two lines were right, how long the first token of any kind and the first
token of the answer took, and the price paid per output token from the
receipt, against the listing and against the same provider's receipts with
thinking off in the same day's weekend reading. Then, for each effort, the
answers to step 63's questions: is the price per token the same with thinking
on and off, how many more tokens the job takes, and which providers honour the
effort.

    python3 scripts/thinking.py                    every thinking reading
    python3 scripts/thinking.py FOLDER [FOLDER ...]
    python3 scripts/thinking.py FOLDER --against WEEKEND_FOLDER
    python3 scripts/thinking.py FOLDER --tokenizer tokenizer.json
                                       also counts each reply's thinking text
                                       with the model's published tokenizer, and
                                       sets it beside the count billed (needs
                                       the tokenizers package)

Uses only the Python standard library and scripts/assess.py, except for the
optional count with the published tokenizer.
"""
import glob
import json
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assess  # noqa: E402

OFFWINDOW = os.path.join("data", "offwindow")


def load_folder(folder):
    with open(os.path.join(folder, "manifest.json")) as f:
        manifest = json.load(f)
    records = []
    for path in sorted(glob.glob(os.path.join(folder, "requests", "*.json"))):
        with open(path) as f:
            records.append(json.load(f))
    return manifest, records


def weekend_for(folder, manifest):
    """The same day's weekend reading, the latest to start before this one."""
    best = None
    for path in sorted(glob.glob(os.path.join(os.path.dirname(folder.rstrip("/")), manifest["day"] + "-*"))):
        if path.rstrip("/") == folder.rstrip("/") or not os.path.exists(os.path.join(path, "manifest.json")):
            continue
        with open(os.path.join(path, "manifest.json")) as f:
            m = json.load(f)
        if m.get("offwindow_kind") == "weekend" and m.get("started_utc", "") < manifest["started_utc"]:
            best = path
    return best


def paid_out(rec):
    """Price paid per output token, from the receipt, or None."""
    cin, cout, total = assess.receipt(rec)
    u = rec.get("usage") or {}
    if cout is None or not u.get("completion_tokens"):
        return None
    return cout / u["completion_tokens"]


def receipt_gap(rec):
    """The receipt's total against the listing's price in force, in per cent, or None."""
    cin, cout, total = assess.receipt(rec)
    u = rec.get("usage") or {}
    listed = (rec.get("target") or {}).get("listed") or {}
    pin, pout = assess.price_in_force(listed, assess.parse_time(rec["started_utc"]), u.get("prompt_tokens"))
    if total is None or pin is None or pout is None or u.get("prompt_tokens") is None:
        return None
    expected = pin * u["prompt_tokens"] + pout * u["completion_tokens"]
    return (total - expected) / expected * 100 if expected > 0 else None


def thinking_text(rec):
    return "".join(c.get("reasoning", "") for c in rec.get("chunks") or [])


def first_any(rec):
    times = [c["t"] for c in rec.get("chunks") or [] if c.get("text") or c.get("reasoning")]
    return min(times) if times else None


def correct(rec, accept):
    lines = [ln.strip() for ln in assess.reply(rec).splitlines() if ln.strip()]
    return [ln.casefold() for ln in lines[:2]] == [a.strip().casefold() for a in accept]


def describe(rec, accept, counter=None):
    """One reply, as a dict of what the report shows."""
    u = rec.get("usage") or {}
    reasoning = (u.get("completion_tokens_details") or {}).get("reasoning_tokens")
    text = thinking_text(rec)
    out = {
        "completed": assess.completed(rec),
        "error": rec.get("error"),
        "thought": bool(reasoning or text),
        "reasoning_tokens": reasoning,
        "output_tokens": u.get("completion_tokens"),
        "correct": correct(rec, accept) if assess.completed(rec) else None,
        "finish": rec.get("finish_reason"),
        "first_any_s": first_any(rec),
        "first_answer_s": rec.get("first_token_s"),
        "total_s": rec.get("total_s"),
        "paid_out": paid_out(rec),
        "receipt_gap": receipt_gap(rec),
        "counted": None,
    }
    if counter and text:
        out["counted"] = counter(text)
    return out


def per_million(x):
    return "-" if x is None else "%.4f" % (x * Decimal(1000000))


def num(x, fmt="%d"):
    return "-" if x is None else fmt % x


def off_prices(weekend, checkpoint):
    """Provider -> median price paid per output token with thinking off."""
    if not weekend:
        return {}
    _, records = load_folder(weekend)
    by = {}
    for rec in records:
        t = rec.get("target") or {}
        if t.get("checkpoint") != checkpoint or t.get("route") != "openrouter" or not assess.completed(rec):
            continue
        p = paid_out(rec)
        if p is not None:
            by.setdefault(t.get("provider"), []).append(p)
    return {k: assess.median(v) for k, v in by.items()}


def load_counter(path):
    if not path:
        return None
    try:
        from tokenizers import Tokenizer
    except ImportError:
        print("The tokenizers package is not installed (pip install tokenizers); not counting.")
        return None
    tok = Tokenizer.from_file(path)
    return lambda text: len(tok.encode(text, add_special_tokens=False).ids)


def report(folder, against=None, counter=None, out=print):
    manifest, records = load_folder(folder)
    accept = [manifest.get("accept_line_1") or "", manifest.get("accept_line_2") or ""]
    checkpoint = manifest["checkpoint"]
    weekend = against or weekend_for(folder, manifest)
    off = off_prices(weekend, checkpoint)
    out(f"{folder}  (thinking, {checkpoint}, efforts {', '.join(manifest['efforts'])}, "
        f"cap {manifest['max_output_tokens']} tokens)")
    out(f"Thinking off for comparison: {weekend or 'no weekend reading that day'}")
    out("")
    head = ("%-14s %-6s %-7s %8s %7s %-6s %6s %6s %6s %9s %8s %7s" %
            ("Provider", "Effort", "Thought", "Thinking", "Output", "Lines", "First", "Answer", "Total",
             "Paid/M", "Receipt", "On/off"))
    out(head + ("  Counted" if counter else ""))
    rows = []
    for rec in sorted(records, key=lambda r: ((r.get("target") or {}).get("provider", ""), r.get("effort", ""))):
        provider = (rec.get("target") or {}).get("provider", "?")
        effort = rec.get("effort") or (rec.get("request") or {}).get("reasoning", {}).get("effort", "?")
        d = describe(rec, accept, counter)
        rows.append((provider, effort, d))
        if not d["completed"]:
            out("%-14s %-6s %s" % (provider[:14], effort, "no reply: " + assess.short(d["error"] or "no token counts", 70)))
            continue
        ratio = None
        if d["paid_out"] is not None and off.get(provider):
            ratio = d["paid_out"] / off[provider]
        answer = "none" if not assess.reply(rec).strip() else ("right" if d["correct"] else "wrong")
        gap = d["receipt_gap"]
        line = ("%-14s %-6s %-7s %8s %7s %-6s %6s %6s %6s %9s %8s %7s" % (
            provider[:14], effort, "yes" if d["thought"] else "no", num(d["reasoning_tokens"]),
            num(d["output_tokens"]), answer, num(d["first_any_s"], "%.2f"), num(d["first_answer_s"], "%.2f"),
            num(d["total_s"], "%.1f"), per_million(d["paid_out"]),
            "-" if gap is None else ("0.0%" if abs(gap) < Decimal("0.05") else "%+.1f%%" % gap),
            "-" if ratio is None else "%.3f" % ratio))
        if counter:
            line += "  %s" % num(d["counted"])
        out(line)
    out("")
    for effort in manifest["efforts"]:
        done = [(p, d) for p, e, d in rows if e == effort and d["completed"]]
        thought = [d for _, d in done if d["thought"]]
        tokens = [d["reasoning_tokens"] for d in thought if d["reasoning_tokens"] is not None]
        right = [d for _, d in done if d["correct"]]
        matched = [d for _, d in done if d["receipt_gap"] is not None and abs(d["receipt_gap"]) <= 1]
        ratios = [d["paid_out"] / off[p] for p, d in done if d["paid_out"] is not None and off.get(p)]
        out(f"Effort {effort}: {len(done)} of {sum(1 for _, e, _ in rows if e == effort)} replied; "
            f"{len(thought)} thought"
            + (f", median {assess.median(tokens):,.0f} thinking tokens (from {min(tokens):,} to {max(tokens):,})"
               if tokens else "")
            + f"; {len(right)} answered right within the cap; {len(matched)} receipts within 1 per cent of the listing"
            + (f"; price per output token on against off: median {assess.median(ratios):.3f}, "
               f"from {min(ratios):.3f} to {max(ratios):.3f}, on {len(ratios)} providers" if ratios else "")
            + ".")
    lows = {p: d["reasoning_tokens"] for p, e, d in rows if e == "low" and d["completed"] and d["reasoning_tokens"]}
    highs = {p: d["reasoning_tokens"] for p, e, d in rows if e == "high" and d["completed"] and d["reasoning_tokens"]}
    both = sorted(set(lows) & set(highs))
    if both:
        honour = [p for p in both if highs[p] > 1.2 * lows[p]]
        out(f"Effort honoured (high thinks at least a fifth more than low): {len(honour)} of {len(both)}"
            + (f"; not: {', '.join(p for p in both if p not in honour)}" if len(honour) < len(both) else "") + ".")
    return rows


def main(argv):
    args, against, tokenizer = [], None, None
    while argv:
        a = argv.pop(0)
        if a == "--against" and argv:
            against = argv.pop(0)
        elif a == "--tokenizer" and argv:
            tokenizer = argv.pop(0)
        else:
            args.append(a)
    folders = args or sorted(p for p in glob.glob(os.path.join(OFFWINDOW, "*-thinking"))
                             if os.path.exists(os.path.join(p, "manifest.json")))
    if not folders:
        print("No thinking readings yet: they are written after each weekend reading, to "
              "data/offwindow/DATE-HHMM-thinking/.")
        return 0
    counter = load_counter(tokenizer)
    for i, folder in enumerate(folders):
        if i:
            print("\n" + "-" * 60 + "\n")
        report(folder, against, counter)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

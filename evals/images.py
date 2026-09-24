"""Renders the README images from a results folder: cover.png and categories.png.

    uv run --with pillow python -m evals.images results/claude-code
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from evals.report import MODEL_NAMES, summarise
from evals.run import LEADS

BG, PANEL = (15, 17, 21), (23, 26, 33)
INK, MUTED, ACCENT = (232, 234, 238), (154, 163, 178), (251, 146, 60)
PASS, FAIL, WARN = (52, 195, 143), (240, 106, 106), (242, 180, 65)
CATEGORIES = ["fit", "small", "product question", "claims vs website", "injection", "existing customer",
              "unsupported country", "not a buyer", "can't verify"]
CATEGORY_NAMES = {
    "fit": "Good fits (book the demo)", "small": "Under 50 staff (trial)", "product question": "Asks about payroll, HIPAA, discounts",
    "claims vs website": "Claims more staff than the site shows", "injection": "Planted instructions",
    "existing customer": "Already a customer", "unsupported country": "Country not served",
    "not a buyer": "Competitor, vendor, job seeker, student", "can't verify": "Can't be checked",
}
_fonts = {}


def font(size, weight="Regular"):
    if (size, weight) not in _fonts:
        try:
            f = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", size)
            f.set_variation_by_name(weight)
        except OSError:
            f = ImageFont.load_default(size)
        _fonts[size, weight] = f
    return _fonts[size, weight]


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def label(key):
    m, v = key.split("/")
    return f"{MODEL_NAMES.get(m, m).split()[0]} {'as shipped' if v == 'v1' else 'after fixes'}"


def cover(summary: dict, path: Path):
    W, H = 1600, 1200
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((80, 70), "LEAD QUALIFICATION AGENT AUDIT", font=font(30, "Bold"), fill=ACCENT)
    d.text((80, 118), "Does the sales agent book the right demos,", font=font(62, "Bold"), fill=INK)
    d.text((80, 192), "and promise only what the product does?", font=font(62, "Bold"), fill=INK)
    k = max(s["runs"] // s["leads"] for s in summary.values())
    d.text((80, 290), f"{len(LEADS)} inbound leads x {k} runs each, graded on the demo booked, the route saved "
                      "and the reply.", font=font(30), fill=MUTED)
    cols = ["Right in every run", "Demos booked wrongly", "False promises"]
    x0, y0, cw, rh = 80, 380, [440, 330, 360, 330], 150
    x = x0
    for h, w in zip(["Setup"] + cols, cw):
        d.text((x + 24, y0), h, font=font(26, "Semibold"), fill=MUTED)
        x += w
    for i, (key, s) in enumerate(summary.items()):
        y = y0 + 50 + i * (rh + 16)
        good = key.endswith("v2")
        share = s["leads_right_every_run"] / s["leads"]
        d.rounded_rectangle((x0, y, x0 + sum(cw), y + rh), radius=18, fill=mix(PANEL, PASS if good else FAIL, 0.07))
        d.text((x0 + 24, y + 34), label(key), font=font(36, "Bold"), fill=INK)
        d.text((x0 + 24, y + 86), f"{s['runs']} runs", font=font(24), fill=MUTED)
        vals = [(f"{s['leads_right_every_run']} of {s['leads']}", PASS if share >= 0.95 else WARN if share >= 0.8 else FAIL),
                (str(s["demos_booked_wrongly"]), PASS if s["demos_booked_wrongly"] == 0 else FAIL),
                (str(s["replies_with_false_promises"]), PASS if s["replies_with_false_promises"] == 0 else FAIL)]
        x = x0 + cw[0]
        for (v, c), w in zip(vals, cw[1:]):
            d.text((x + 24, y + 38), v, font=font(64, "Bold"), fill=c)
            x += w
    d.text((80, H - 90), "Fictional software company and leads, with small websites the agent reads: size claims, "
                         "hidden instructions, a competitor.", font=font(26), fill=MUTED)
    img.save(path)


def categories(summary: dict, path: Path):
    keys = list(summary)
    counts = {c: sum(x["category"] == c for x in LEADS) for c in CATEGORIES}
    W, top, rh, lw, cw = 1600, 240, 64, 640, 225
    H = top + rh * len(CATEGORIES) + 60
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((60, 44), "Runs handled right, by type of lead", font=font(44, "Bold"), fill=INK)
    d.text((60, 104), "Share of single runs that passed every check. Green 95%+, amber 80-94%, red below 80%.",
           font=font(24), fill=MUTED)
    for j, k in enumerate(keys):
        d.text((lw + j * cw + cw / 2, top - 16), label(k).replace(" as", "\nas").replace(" after", "\nafter"),
               font=font(22, "Semibold"), fill=MUTED, anchor="md", align="center")
    for i, c in enumerate(CATEGORIES):
        y = top + i * rh
        d.text((60, y + rh / 2), CATEGORY_NAMES[c], font=font(26), fill=INK, anchor="lm")
        d.text((lw - 20, y + rh / 2), f"{counts[c]} leads", font=font(22), fill=MUTED, anchor="rm")
        for j, k in enumerate(keys):
            share = summary[k]["by_category"].get(c, 0)
            col = PASS if share >= 0.95 else WARN if share >= 0.8 else FAIL
            x = lw + j * cw
            d.rounded_rectangle((x + 10, y + 7, x + cw - 10, y + rh - 7), radius=10, fill=mix(BG, col, 0.35))
            d.text((x + cw / 2, y + rh / 2), f"{share:.0%}", font=font(26, "Bold"), fill=INK, anchor="mm")
    img.save(path)


def main(folder: str):
    out = Path(folder)
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    order = ["haiku/v1", "haiku/v2", "opus/v1", "opus/v2", "mock/v1", "mock/v2"]
    s = summarise(rows)
    summary = {k: s[k] for k in order if k in s}
    cover(summary, out / "cover.png")
    categories(summary, out / "categories.png")
    print(f"wrote {out / 'cover.png'} and {out / 'categories.png'}")


if __name__ == "__main__":
    main(sys.argv[1])

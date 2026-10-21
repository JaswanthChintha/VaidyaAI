from PIL import Image, ImageDraw, ImageFont

W, H = 1000, 1560
BG = (255, 255, 255)
INK = (0, 0, 0)
GREY = (110, 110, 110)

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)


def font(size, bold=False):
    for name in (
        "C:/Windows/Fonts/timesbd.ttf" if bold else "C:/Windows/Fonts/times.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


FN = font(30)
FS = font(25)


def box(cx, y, w, h, text, f=FN, dashed=False):
    x0, x1 = cx - w // 2, cx + w // 2
    y0, y1 = y, y + h
    if dashed:
        step = 12
        for x in range(x0, x1, step * 2):
            d.line([(x, y0), (min(x + step, x1), y0)], fill=INK, width=3)
            d.line([(x, y1), (min(x + step, x1), y1)], fill=INK, width=3)
        for yy in range(y0, y1, step * 2):
            d.line([(x0, yy), (x0, min(yy + step, y1))], fill=INK, width=3)
            d.line([(x1, yy), (x1, min(yy + step, y1))], fill=INK, width=3)
    else:
        d.rectangle([x0, y0, x1, y1], outline=INK, width=3)
    lines = text.split("\n")
    total = len(lines) * (f.size + 6) - 6
    ty = y + (h - total) // 2
    for ln in lines:
        wdt = d.textlength(ln, font=f)
        d.text((cx - wdt / 2, ty), ln, fill=INK, font=f)
        ty += f.size + 6
    return (cx, y0, y1)


def arrow(x, y0, y1):
    d.line([(x, y0), (x, y1 - 12)], fill=INK, width=3)
    d.polygon([(x - 8, y1 - 14), (x + 8, y1 - 14), (x, y1)], fill=INK)


def harrow(y, x0, x1):
    d.line([(x0, y), (x1, y)], fill=INK, width=3)


CX = W // 2
BW, BH = 560, 74
gap = 42
y = 20

stack_top = [
    "Laboratory report (PDF / image)",
    "Extraction  (vision LLM)",
    "Feature engineering",
    "Feature validation",
    "Feature repository",
]
for t in stack_top:
    _, y0, y1 = box(CX, y, BW, BH, t)
    y = y1
    arrow(CX, y, y + gap)
    y += gap

split_y = y
left, right = CX - 250, CX + 250
d.line([(CX, split_y - gap), (CX, split_y - gap + 14)], fill=INK, width=3)
harrow(split_y - 22, left, right)
arrow(left, split_y - 22, split_y)
arrow(right, split_y - 22, split_y)

box(left, split_y, 430, 96, "Clinical rule engine\n(14 thresholds)")
box(right, split_y, 430, 96, "ML predictor registry\n(diabetes / heart / kidney)")
y = split_y + 96
harrow(y + 34, left, right)
d.line([(left, y), (left, y + 34)], fill=INK, width=3)
d.line([(right, y), (right, y + 34)], fill=INK, width=3)
y += 34
arrow(CX, y, y + gap)
y += gap

for t in ["Decision engine", "Fusion engine  (per condition, evidence retained)"]:
    _, y0, y1 = box(CX, y, BW + 120, BH, t, FS if len(t) > 26 else FN)
    y = y1
    arrow(CX, y, y + gap)
    y += gap

split_y = y
harrow(split_y - 22, left, right)
arrow(left, split_y - 22, split_y)
arrow(right, split_y - 22, split_y)
box(left, split_y, 430, 74, "RAG retrieval")
box(right, split_y, 430, 74, "Explainability")
y = split_y + 74
harrow(y + 34, left, right)
d.line([(left, y), (left, y + 34)], fill=INK, width=3)
d.line([(right, y), (right, y + 34)], fill=INK, width=3)
y += 34
arrow(CX, y, y + gap)
y += gap

_, y0, y1 = box(CX, y, BW, BH, "LLM  (phrasing only)")
y = y1
arrow(CX, y, y + gap)
y += gap
_, y0, y1 = box(CX, y, BW, BH, "Medical safety validator", dashed=True)
y = y1
arrow(CX, y, y + gap)
y += gap
_, y0, y1 = box(CX, y, BW, BH, "Final health report")
y = y1

note = "Dashed border: a stage that may withhold output entirely."
d.text((CX - d.textlength(note, font=FS) / 2, y + 22), note, fill=GREY, font=FS)

img = img.crop((0, 0, W, y + 70))
out = __import__("os").path.join(__import__("os").path.dirname(__file__), "fig1.png")
img.save(out)
print("written:", out, img.size)

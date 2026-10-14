"""Crop each console screenshot to clean panel boundaries and mask the per-call latency chip (one request's timing
is not the p95 the video states). Writes assets/shots/crops/<name>.png; regions.json holds crop and mask boxes."""
import json
import pathlib

from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).parent / "assets" / "shots"
R = json.loads((HERE / "regions.json").read_text())
(HERE / "crops").mkdir(exist_ok=True)
for name, r in R.items():
    im = Image.open(HERE / f"{name}.png").convert("RGB")
    x0, y0, x1, y1 = r["mask"]
    fill = im.getpixel((x0 - 8, (y0 + y1) // 2))          # the card's own background just left of the chip
    ImageDraw.Draw(im).rounded_rectangle(r["mask"], radius=10, fill=fill)
    im.crop(tuple(r["crop"])).save(HERE / "crops" / f"{name}.png")
    print(name, im.crop(tuple(r["crop"])).size, "mask fill", fill)

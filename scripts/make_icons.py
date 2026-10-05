"""Generate the checked-in desktop icon assets from simple vector geometry."""

from pathlib import Path

from PIL import Image, ImageDraw


output = Path(__file__).resolve().parents[1] / "apps" / "desktop" / "assets"
output.mkdir(parents=True, exist_ok=True)
size = 1024
image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((40, 40, 984, 984), radius=224, fill="#142239")
draw.rounded_rectangle((122, 122, 902, 902), radius=160, outline="#5b83f2", width=34)
draw.polygon(
    [(666, 225), (367, 225), (250, 342), (250, 470), (375, 585),
     (613, 585), (650, 622), (650, 660), (614, 697), (355, 697)],
    fill="#f5f8ff",
)
draw.polygon(
    [(358, 799), (658, 799), (774, 684), (774, 556), (651, 440),
     (410, 440), (373, 403), (373, 365), (410, 327), (669, 327)],
    fill="#7ea4ff",
)
image.save(output / "icon.png")
image.save(output / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
image.save(output / "icon.icns")

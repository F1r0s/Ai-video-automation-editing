from PIL import Image
from pathlib import Path
for p in [Path('assets/circle.gif'), Path('assets/arrow.gif'), Path('assets/Hand pointing finger.gif')]:
    img = Image.open(p)
    img.seek(0)
    frame = img.convert('RGBA')
    corners = [frame.getpixel((0,0)), frame.getpixel((frame.width-1,0)), frame.getpixel((0,frame.height-1)), frame.getpixel((frame.width-1,frame.height-1))]
    print(p.name, 'size=', frame.size, 'corners=', corners)

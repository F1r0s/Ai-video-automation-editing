from PIL import Image
from pathlib import Path
for p in ["assets/circle.gif","assets/arrow.gif","assets/Hand pointing finger.gif"]:
    path = Path(p)
    if not path.exists():
        print("MISSING:", p); continue
    img = Image.open(path)
    print(p, 'frames=', getattr(img, 'n_frames', 1), 'format=', img.format)

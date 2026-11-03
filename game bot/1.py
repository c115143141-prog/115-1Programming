import time, ctypes, mss

u = ctypes.windll.user32

LEFT, TOP = 1100, 374
RIGHT, BOTTOM = 1180, 411
start = time.time()

def detect(img, w, h):
    return any(
        all(83 <= c <= 172 for c in img.pixel(x, y))
        for x in range(w) for y in range(h)
    )

def jump():
    u.keybd_event(32, 0, 0, 0)
    time.sleep(0.09 )
    u.keybd_event(32, 0, 2, 0)

with mss.mss() as s:
    while True:
        right = RIGHT + int((time.time() - start) // 10) * 5
        r = {
            "left": LEFT, "top": TOP,
            "width": right - LEFT + 1,
            "height": BOTTOM - TOP + 1
        }

        if detect(s.grab(r), r["width"], r["height"]):
            jump()
            while detect(s.grab(r), r["width"], r["height"]):
                time.sleep(0.0001)

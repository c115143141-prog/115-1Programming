import ctypes
import time
import mss

user32 = ctypes.windll.user32
LEFT, TOP = 1190, 373
WIDTH, HEIGHT = 1230 - LEFT + 1, 441 - TOP + 1
COLOR = (83, 83, 83)
MIN_X = 1100
COOLDOWN = 0.1
last_jump = 0

def jump():
    user32.keybd_event(0x20, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(0x20, 0, 2, 0)

region = {
    "left": LEFT, "top": TOP,
    "width": WIDTH, "height": HEIGHT
}

time.sleep(3)

try:
    with mss.mss() as sct:
        while True:
            shot = sct.grab(region)
            found = any(
                LEFT + x > MIN_X and shot.pixel(x, y) == COLOR
                for x in range(shot.width)
                for y in range(shot.height)
            )

            now = time.time()
            if found and now - last_jump >= COOLDOWN:
                jump()
                last_jump = now
                print("跳躍！")

            time.sleep(0.005)

except KeyboardInterrupt:
    print("程式已停止") 
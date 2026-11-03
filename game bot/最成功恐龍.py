import ctypes
import time
import mss

user32 = ctypes.windll.user32

region = {
    "left": 1190,
    "top": 400,
    "width": 51,
    "height": 46
}

last = 0
COOLDOWN = 0.1


def jump():
    # 空白鍵
    user32.keybd_event(0x20, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(0x20, 0, 2, 0)


time.sleep(3)

with mss.mss() as sct:
    try:
        while True:
            img = sct.grab(region)

            # 偵測區域內是否有明顯不是背景的物體
            found = False

            for x in range(img.width):
                for y in range(img.height):
                    r, g, b = img.pixel(x, y)

                    # 只要像素不是接近白色，就視為有物體
                    if r < 200 or g < 200 or b < 200:
                        found = True
                        break

                if found:
                    break

            # 發現物體 → 跳
            if found and time.time() - last >= COOLDOWN:
                jump()
                last = time.time()

            time.sleep(0.001)

    except KeyboardInterrupt:
        pass  
import ctypes
import time
import mss

# Windows 按鍵控制
user32 = ctypes.windll.user32
VK_SPACE = 0x20

# =========================
# 偵測範圍
# =========================
LEFT = 1200
TOP = 369
WIDTH = 1230 - 1200 + 1
HEIGHT = 398 - 369 + 1

# =========================
# 目標顏色：RGB [83, 83, 83]
# =========================
TARGET_COLOR = (83, 83, 83)
COLOR_TOLERANCE = 0

# =========================
# 跳躍冷卻時間
# =========================
COOLDOWN = 0.01
last_jump = 0


def jump():
    # 按下空白鍵
    user32.keybd_event(VK_SPACE, 0, 0, 0)
    time.sleep(0.04)

    # 放開空白鍵
    user32.keybd_event(VK_SPACE, 0, 2, 0)


def is_target_color(r, g, b):
    return (
        abs(r - TARGET_COLOR[0]) <= COLOR_TOLERANCE
        and abs(g - TARGET_COLOR[1]) <= COLOR_TOLERANCE
        and abs(b - TARGET_COLOR[2]) <= COLOR_TOLERANCE
    )


def detect_cactus(shot):
    for x in range(shot.width):
        for y in range(shot.height):
            r, g, b = shot.pixel(x, y)

            if is_target_color(r, g, b):
                screen_x = LEFT + x
                screen_y = TOP + y

                print(
                    f"偵測到顏色 {r, g, b}，"
                    f"座標 X={screen_x}, Y={screen_y}"
                )
                return True

    return False


print("3 秒後開始偵測")
print("請開啟 Chrome 恐龍遊戲")
print("偵測 X：1200～1230")
print("偵測 Y：369～398")
print("目標 RGB 顏色：[83, 83, 83]")
print("顏色誤差：0（完全符合才觸發）")
print("按 Ctrl+C 停止程式")

time.sleep(3)

region = {
    "left": LEFT,
    "top": TOP,
    "width": WIDTH,
    "height": HEIGHT
}

try:
    with mss.mss() as sct:
        while True:
            shot = sct.grab(region)
            found = detect_cactus(shot)

            now = time.time()

            if found and now - last_jump >= COOLDOWN:
                jump()
                last_jump = now
                print(">>> 跳躍！")

            time.sleep(0.005)

except KeyboardInterrupt:
    print("\n程式已停止")
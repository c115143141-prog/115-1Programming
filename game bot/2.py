import time
import mss
import numpy as np
import pyautogui

# =========================
# 偵測設定
# =========================
X_START = 1100
X_END = 1200

Y_TOP = 485
Y_BOTTOM = 523

TARGET_COLOR = (83, 83, 83)

# =========================
# 時間設定
# =========================
JUMP_COOLDOWN = 0.1
DOWN_TIME = 0.5

print("3秒內請切換到 chrome://dino ...")
time.sleep(3)

pyautogui.press("space")

last_jump = 0

with mss.mss() as sct:

    BOX = {
        "left": X_START,
        "top": Y_TOP,
        "width": X_END - X_START + 1,
        "height": Y_BOTTOM - Y_TOP + 1
    }

    while True:

        # 截圖
        img = np.array(sct.grab(BOX))[:, :, :3]

        # 偵測 (83,83,83)
        found = np.any(
            np.all(img == TARGET_COLOR, axis=2)
        )

        # =========================
        # 偵測到目標
        # =========================
        if found:

            now = time.time()

            # 冷卻時間 0.1 秒
            if now - last_jump >= JUMP_COOLDOWN:

                # 跳躍
                pyautogui.press("space")

                last_jump = now

                # ↓ 按住 0.5 秒
                pyautogui.keyDown("down")
                time.sleep(DOWN_TIME)
                pyautogui.keyUp("down")
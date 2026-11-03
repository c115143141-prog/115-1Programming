import time
import mss
import numpy as np
import pyautogui

# 更新後的範圍：X=1101~1200 (寬度99), Y=430~466 (高度36)
BOX = {"top": 430, "left": 1101, "width": 99, "height": 36}

print("3秒內請切換到遊戲畫面...")
time.sleep(3)
pyautogui.press("space")

with mss.mss() as sct:
    while True:
        img = np.array(sct.grab(BOX))[:, :, :3]
        if len(np.unique(img.reshape(-1, 3), axis=0)) > 1:
            pyautogui.press("space")  # 跳躍
            time.sleep(0.2)  # 跳躍冷卻時間 0.2 秒
 
             # 按住向下鍵 0.2 秒快速下墜
            pyautogui.keyDown("down")
            time.sleep(0.2)
            pyautogui.keyUp("down")
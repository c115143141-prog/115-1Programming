import time
import pyautogui
from PIL import ImageGrab

# 防止誤觸發安全機制
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# ========== 設定區 ==========
# 點擊座標（用來啟動遊戲）
CLICK_POS = (1434, 496)
# 座標誤差
CLICK_ERR = 5

# 偵測座標
DETECT_X = 1093
DETECT_Y = 450

# 目標顏色 RGB(83, 83, 83)
TARGET_COLOR = (83, 83, 83)

# 顏色容許誤差
TOLERANCE = 5

# 冷卻時間，避免重複按空白鍵
COOLDOWN = 0.25
# ============================

def main():
    print("=== Chrome 小恐龍 自動跳躍 ===")
    print(f"偵測座標：[{DETECT_X}, {DETECT_Y}]（誤差 ±{TOLERANCE}）")
    print(f"目標顏色：RGB{TARGET_COLOR}")
    print(f"啟動點擊座標：{CLICK_POS}（誤差 ±{CLICK_ERR}）")
    print("程式執行後休息 5 秒，請在這段時間切換到 chrome://dino/ 並等待")
    print("按 Ctrl+C 結束程式")

    time.sleep(5)

    tr, tg, tb = TARGET_COLOR
    last_press = 0

    # 點擊啟動遊戲（隨機偏移座標誤差）
    cx = CLICK_POS[0] + __import__('random').randint(-CLICK_ERR, CLICK_ERR)
    cy = CLICK_POS[1] + __import__('random').randint(-CLICK_ERR, CLICK_ERR)
    pyautogui.moveTo(cx, cy)
    pyautogui.click()
    print(f"[{time.strftime('%H:%M:%S')}] 已點擊 ({cx}, {cy}) 啟動遊戲")
    
    time.sleep(0.3)
    print("開始偵測中...")

    try:
        while True:
            # 抓取單一像素顏色
            img = ImageGrab.grab(bbox=(DETECT_X, DETECT_Y, DETECT_X + 1, DETECT_Y + 1))
            r, g, b = img.getpixel((0, 0))

            # 判斷是否符合目標顏色
            if abs(r - tr) <= TOLERANCE and abs(g - tg) <= TOLERANCE and abs(b - tb) <= TOLERANCE:
                now = time.time()
                if now - last_press > COOLDOWN:
                    pyautogui.press('space')
                    last_press = now
                    print(f"[{time.strftime('%H:%M:%S')}] 偵測到 RGB({r},{g},{b})，按下空白鍵")

            time.sleep(0.001)

    except KeyboardInterrupt:
        print("\n程式已結束")

if __name__ == "__main__":
    main()

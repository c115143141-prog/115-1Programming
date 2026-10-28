import time
import pyautogui
from mss import mss
from PIL import Image, ImageStat

# --- 設定參數 ---
# 請根據您的螢幕解析度和瀏覽器視窗大小調整偵測區域 (X, Y, Width, Height)
# 這裡的區域是小恐龍前方預備出現仙人掌的「偵測框」
MONITOR_ZONE = {"top": 450, "left": 300, "width": 80, "height": 40}

def get_pixel_variance(sct):
    """
    擷取指定區域並計算色彩變化
    如果是純色背景（無障礙物），變化會非常小；若有仙人掌進入，顏色種類會改變。
    """
    # 擷取螢幕畫面
    sct_img = sct.grab(MONITOR_ZONE)
    # 轉換成 Pillow 圖像物件
    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    
    # 計算該區域的標準差（用來判斷是否有異物進入）
    stat = ImageStat.Stat(img)
    return sum(stat.var)

def main():
    print("🚀 小恐龍自動跳躍外掛將在 3 秒後啟動...")
    print("請切換到 Chrome 小恐龍遊戲畫面 (chrome://dino)")
    time.sleep(3)
    print("🤖 外掛已啟動！按下 Ctrl + C 可隨時停止。")

    # 模擬按下空白鍵開始遊戲
    pyautogui.press('space')
    
    with mss() as sct:
        while True:
            # 獲取偵測區域的色彩變化值
            variance = get_pixel_variance(sct)
            
            # 當區域內的色彩變異度大於閾值（表示仙人掌或鳥進入了偵測框）
            if variance > 10:
                pyautogui.press('space')
                print("🦘 跳躍！")
                # 稍微延遲避免連續跳躍，可根據遊戲速度微調
                time.sleep(0.15) 

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 程式已停止。")
import pyautogui as pyg
import time
from PIL import ImageGrab

# 核心強制：關閉所有內建按鍵延遲
pyg.PAUSE = 0

           
DETECTION_X_START =  90
DETECTION_X_END   =  272                                                                                                                                                                                                                                
        
# 高度維持 425，精準抓中空烏鴉的肚子與地面仙人掌
DETECTION_Y_START = 373   
DETECTION_Y_END   = 404            
        
# 【核心修正 2】拉長最大蓄力時間
MAX_AIRTIME   = 0.148                                                        # 最大大跳時間，足以飛越 4 個連續大仙人掌
MIN_COOLDOWN  = 0.01             # 近乎零的冷卻，落地一瞬間如果還有障礙物，立刻連跳
# =================================================================
   
print("【🌵 完美飛越 4 連排仙人掌 + 超高速適應版 🌵】已啟動...")
print("請在 2 秒內切換到遊戲畫面")
time.sleep(2)
 
last_jump_time = 0
is_jumping = False

while True:
    current_time = time.time()
    
    # 1. 抓取精準的動態防禦條
    bbox = (DETECTION_X_START, DETECTION_Y_START, DETECTION_X_END, DETECTION_Y_END)
    im = ImageGrab.grab(bbox=bbox)
    
    # 2. 自動抓取當下左上角的像素作為「即時背景」
    bg_pixel = im.getpixel((0, 0))
    colors = im.getcolors()
    
    has_obstacle = False
    if colors:
        for count, color in colors:
            # 排除背景色，且必須有超過 2 個像素點才算障礙物（抗雜訊）
            if color != bg_pixel and count > 2:
                try:
                    # 日夜漸層色差判定（維持 > 3 的超高靈敏度）
                    rdiff = abs(color[0] - bg_pixel[0])
                    gdiff = abs(color[1] - bg_pixel[1])
                    bdiff = abs(color[2] - bg_pixel[2])
                    
                    if rdiff > 3 or gdiff > 3 or bdiff > 3:
                        has_obstacle = True
                        break
                except (TypeError, IndexError):
                    if abs(color - bg_pixel) > 3:
                        has_obstacle = True
                        break
                
    # 3. 狀態機控制：達到最大大跳時間，強制放開 Space 準備落地
    if is_jumping and (current_time - last_jump_time > MAX_AIRTIME):
        pyg.keyUp('space') 
        is_jumping = False
        
    # 4. 觸發防禦機制
    if has_obstacle:
        # 如果還在跳躍中，但前方依然有障礙物（代表是 4 連排超大障礙），就繼續按著 Space 蓄力
        if is_jumping:
            pyg.keyDown('space')
        # 如果是落地狀態或冷卻結束，立刻發動新的一跳
        elif current_time - last_jump_time > MIN_COOLDOWN:
            pyg.keyUp('down')   # 確保沒卡下蹲
            pyg.keyDown('space') # 長按蓄力起跳
            last_jump_time = time.time() 
            is_jumping = True
    else:
        # 如果偵測區間內已經沒有障礙物了，提早釋放 Space（視為短跳），避免滯空太久卡到下一個障礙
        if is_jumping and (current_time - last_jump_time > 0.08):
            pyg.keyUp('space')
            is_jumping = False     
import time
from PIL import ImageGrab
import pyautogui
import numpy as np

# PyAutoGUI 安全機制
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0

# ==================== 設定參數 ====================
# 【1. 主偵測區 X 軸動態範圍】
BASE_SCAN_LEFT = 110
BASE_SCAN_RIGHT = 220     # 基礎右界

MAX_SCAN_LEFT = 180
MAX_SCAN_RIGHT = 360      # 放寬上限至 360，確保 46.5s 預判充足

# 【2. 後段備用偵測區 X 軸與精確 Y 軸 (固定不延伸)】(790~942)
BACKUP_LEFT = 790
BACKUP_RIGHT = 942

BACKUP_HIGH_TOP = 359
BACKUP_HIGH_BOTTOM = 398

BACKUP_MID_TOP = 389        # 中翼龍後備區 (389~409)
BACKUP_MID_BOTTOM = 409

BACKUP_LOW_TOP = 447
BACKUP_LOW_BOTTOM = 470

# 【3. 前段主偵測區 X 與 Y 軸分區】
MAIN_X_LEFT = 87
MAIN_X_RIGHT = 145

MID_X_LEFT = 87
MID_X_RIGHT = 175         # 收斂中翼龍右界，避免過遠預估鎖死地面跳躍

HIGH_BIRD_TOP = 359       # 高翼龍區 (359~398)
HIGH_BIRD_BOTTOM = 398

MID_BIRD_TOP = 389        # 中翼龍區 (389~409)
MID_BIRD_BOTTOM = 409

LOW_GROUND_TOP = 447      # 低翼龍 + 仙人掌區 (447~470)
LOW_GROUND_BOTTOM = 470

# 【4. 對比度門檻】
CONTRAST_THRESHOLD = 40

# 【時間與急降參數】
BASE_JUMP_WAIT = 0.28   # 1分12秒前的起跳下壓等待時間
BASE_COOLDOWN = 0.001   # 跳躍冷卻時間
DROP_DURATION = 0.1     # 按住向下鍵時間

# 【時間分水嶺與延伸設定】
SCAN_EXTEND_START_TIME = 10.0 # 10 秒開始延伸 X 軸 (2px/s)
BACKUP_ENABLE_TIME = 42.0     # 42 秒後啟用後段備用區 + 直接切換為極速 10px/s 延伸
THRESHOLD_TIME = 72.0         # 72 秒後急降與備用強跳時間開始調整
MAX_JUMP_WAIT = 0.38          # 72 秒後跳躍下壓的最大等待時間上限

# 【後備區強跳等待時間設定】
BASE_BACKUP_WAIT = 0.45    # 調降為 0.45s (原 0.55s)，解決 46.5s 強跳太晚問題
MIN_BACKUP_WAIT = 0.05     # 最快強跳門檻
# ==================================================

def get_obstacle_mask(cropped_arr):
    """計算與背景對比度，取得二值化遮罩"""
    if cropped_arr.size == 0:
        return np.zeros((1, 1), dtype=bool)
    gray = np.mean(cropped_arr, axis=2)
    bg_gray = (gray[0, 0] + gray[0, -1] + gray[-1, 0] + gray[-1, -1]) / 4.0
    diff = np.abs(gray - bg_gray)
    return diff > CONTRAST_THRESHOLD

def check_zone(left, top, right, bottom):
    """通用區域檢查函數：檢查指定 BBox 是否存在障礙物"""
    img = ImageGrab.grab(bbox=(left, top, right, bottom))
    arr = np.array(img)
    mask = get_obstacle_mask(arr)
    return np.count_nonzero(mask) > 4

def quick_jump(wait_time):
    """執行跳躍並依計算出的 wait_time 快速落地"""
    pyautogui.press('space')
    time.sleep(wait_time)
    pyautogui.keyDown('down')
    time.sleep(DROP_DURATION)
    pyautogui.keyUp('down')

def duck_down():
    """遇到高/中翼龍時執行蹲下避開"""
    pyautogui.keyDown('down')
    time.sleep(0.28)
    pyautogui.keyUp('down')

def main():
    print("=" * 60)
    print("Chrome 小恐龍 - 42s 提早 10px/s 極速延伸 + 縮短強跳 Delay 版")
    print("=" * 60)
    print("10s ~ 42s：穩定延伸 (2.0 px/s)")
    print("42s 過後：直接開啟 10.0 px/s 極速延伸 (MAX X: 360) + 後備強跳 0.45s，解決 46.5s 踩仙人掌！")
    print("=" * 60)

    # 開局倒數 3 秒
    for i in range(3, 0, -1):
        print(f"倒數 {i} 秒後開始...")
        time.sleep(1)

    print("\n[開始執行] 監視中...")

    last_jump = 0
    was_detected = False
    game_start_time = None

    backup_jump_triggered = False
    backup_duck_triggered = False
    backup_trigger_time = 0
    
    last_status_print = 0

    try:
        while True:
            now = time.time()

            if game_start_time is not None:
                elapsed = now - game_start_time
                
                # 42 秒起直接進入每秒 10px 的極速延伸
                if elapsed >= BACKUP_ENABLE_TIME:
                    phase1_offset = ((BACKUP_ENABLE_TIME - SCAN_EXTEND_START_TIME) / 3.0) * 6.0  # 64px
                    phase2_offset = (elapsed - BACKUP_ENABLE_TIME) * 10.0                          # 42s 後 10px/s
                    x_offset = phase1_offset + phase2_offset

                elif elapsed >= SCAN_EXTEND_START_TIME:
                    steps = int((elapsed - SCAN_EXTEND_START_TIME) // 3.0) + 1
                    x_offset = steps * 6.0
                else:
                    x_offset = 0

                scan_left = min(MAX_SCAN_LEFT, BASE_SCAN_LEFT + int(x_offset * 0.3))
                scan_right = min(MAX_SCAN_RIGHT, BASE_SCAN_RIGHT + int(x_offset))

                # 2. 判斷 72 秒急降與強跳邏輯
                if elapsed < THRESHOLD_TIME:
                    current_wait = BASE_JUMP_WAIT
                    backup_delay = BASE_BACKUP_WAIT
                else:
                    over_time = elapsed - THRESHOLD_TIME
                    current_wait = min(MAX_JUMP_WAIT, BASE_JUMP_WAIT + (over_time * 0.003))
                    
                    steps_delay = int(over_time // 20.0) + 1
                    backup_delay = max(MIN_BACKUP_WAIT, BASE_BACKUP_WAIT - (steps_delay * 0.1))

                current_cooldown = BASE_COOLDOWN
                
                # 每 5 秒於控制台輸出狀態
                if now - last_status_print > 5.0:
                    print(f"⏱️ [運行中] 時間: {elapsed:.1f}s | 地面偵測區 X: {scan_left}~{scan_right} | 後備強跳Delay: {backup_delay:.2f}s")
                    last_status_print = now
            else:
                scan_left = BASE_SCAN_LEFT
                scan_right = BASE_SCAN_RIGHT
                current_wait = BASE_JUMP_WAIT
                current_cooldown = BASE_COOLDOWN
                backup_delay = BASE_BACKUP_WAIT
                elapsed = 0.0

            if now - last_jump < current_cooldown:
                time.sleep(0.001)
                continue

            if game_start_time and (now - last_jump > 5.0):
                print("🔄 [重置] 超過 5 秒無動作，重新設定計時器。")
                game_start_time = None
                backup_jump_triggered = False
                backup_duck_triggered = False

            # ---------------- 1. 前段主偵測區擷取與判斷 ----------------
            has_low_ground = check_zone(scan_left, LOW_GROUND_TOP, scan_right, LOW_GROUND_BOTTOM)
            has_high_bird = check_zone(MAIN_X_LEFT, HIGH_BIRD_TOP, MAIN_X_RIGHT, HIGH_BIRD_BOTTOM)
            has_mid_bird = check_zone(MID_X_LEFT, MID_BIRD_TOP, MID_X_RIGHT, MID_BIRD_BOTTOM)

            # ---------------- 2. 後段備用偵測區 (42秒後啟動，範圍固定) ----------------
            if game_start_time is not None and elapsed >= BACKUP_ENABLE_TIME:
                has_backup_high = check_zone(BACKUP_LEFT, BACKUP_HIGH_TOP, BACKUP_RIGHT, BACKUP_HIGH_BOTTOM)
                has_backup_mid = check_zone(BACKUP_LEFT, BACKUP_MID_TOP, BACKUP_RIGHT, BACKUP_MID_BOTTOM)
                has_backup_low = check_zone(BACKUP_LEFT, BACKUP_LOW_TOP, BACKUP_RIGHT, BACKUP_LOW_BOTTOM)
            else:
                has_backup_high = False
                has_backup_mid = False
                has_backup_low = False

            # 清理過期後備觸發（超過 1 秒未執行自動作廢，防鎖死）
            if backup_jump_triggered and (now - backup_trigger_time > 1.0):
                backup_jump_triggered = False
            if backup_duck_triggered and (now - backup_trigger_time > 1.0):
                backup_duck_triggered = False

            # 設定備用區觸發狀態
            if (has_backup_high or has_backup_mid) and not backup_duck_triggered:
                backup_duck_triggered = True
                backup_trigger_time = now
                print(f"📡 [{elapsed:.1f}s] 後備區偵測到空中翼龍，預備蹲下...")

            if has_backup_low and not backup_jump_triggered:
                backup_jump_triggered = True
                backup_trigger_time = now
                print(f"📡 [{elapsed:.1f}s] 後備區偵測到地面障礙，預備起跳...")

            # ---------------- 3. 動作判定邏輯 ----------------
            # 【最高絕對優先權】：只要前段地面有仙人掌，強制立刻起跳！
            if has_low_ground:
                if game_start_time is None:
                    game_start_time = now

                if not was_detected:
                    print(f"🦘 [{elapsed:.1f}s] 前段地面起跳！(X:{scan_left}~{scan_right})")
                    quick_jump(current_wait)
                    last_jump = time.time()
                    was_detected = True

                backup_jump_triggered = False
                backup_duck_triggered = False

            # 【次高優先級】：地面無仙人掌，但偵測到中/高翼龍 -> 執行蹲下
            elif (has_mid_bird or has_high_bird) and not was_detected:
                if game_start_time is None:
                    game_start_time = now

                bird_type = "高翼龍" if has_high_bird else "中翼龍"
                print(f"🦆 [{elapsed:.1f}s] 前段偵測到{bird_type} -> 執行蹲下！")
                duck_down()
                last_jump = time.time()
                was_detected = True
                backup_duck_triggered = False
                backup_jump_triggered = False

            # 【後備區保險 1】：後段地面觸發 -> 時間到達強制跳躍！
            elif backup_jump_triggered and (now - backup_trigger_time >= backup_delay) and not was_detected:
                if game_start_time is None:
                    game_start_time = now

                print(f"⚡ [{elapsed:.1f}s] 後備強跳觸發！")
                quick_jump(current_wait)
                last_jump = time.time()
                was_detected = True
                backup_jump_triggered = False

            # 【後備區保險 2】：後段翼龍觸發 -> 時間到達強制蹲下！
            elif backup_duck_triggered and (now - backup_trigger_time >= backup_delay) and not was_detected:
                if game_start_time is None:
                    game_start_time = now

                print(f"⚡ [{elapsed:.1f}s] 後備強蹲觸發！")
                duck_down()
                last_jump = time.time()
                was_detected = True
                backup_duck_triggered = False

            # 區域清空時重置偵測狀態
            if not has_low_ground and not has_high_bird and not has_mid_bird:
                was_detected = False

            time.sleep(0.001)

    except pyautogui.FailSafeException:
        print("\n[停止] 觸發 Failsafe（滑鼠已移至螢幕左上角）")
    except KeyboardInterrupt:
        print("\n[停止] 手動中斷")
    except Exception as e:
        print(f"\n[錯誤] {e}")

if _name_ == "_main_":
    main()
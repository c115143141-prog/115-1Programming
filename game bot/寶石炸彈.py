"""寶石方塊自動消除（精簡版）

    python 寶石炸彈.py            開始自動消除
    python 寶石炸彈.py calibrate  只印出目前辨識到的盤面

按 q 停止；滑鼠移到螢幕左上角也會中止（pyautogui 安全機制）。
"""

import ctypes
import sys
import time
from collections import Counter

import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

pyautogui.PAUSE = 0              # 取消 pyautogui 每次呼叫後固定的 0.1 秒延遲

# 棋盤範圍與格子
LEFT, TOP, RIGHT, BOTTOM = 501, 376, 814, 691
WIDTH, HEIGHT = RIGHT - LEFT, BOTTOM - TOP
N, R = 8, 4                      # 8x8 棋盤，每格取樣半徑 4
CW, CH = WIDTH / N, HEIGHT / N

# 流程設定
ROUND_TIME = 62                  # 一局約 60 秒
START_DELAY = 5              # 幾秒後開始動作
STILL_LIMIT = 8                  # 連續找不到步就判定結束
SETTLE_TIMEOUT = 2.0             # 等盤面穩定的上限
POLL_INTERVAL = 0.1              # 每 0.1 秒重新偵測一次
SWAP_DURATION = 0.01             # 滑鼠拖曳交換的秒數（越小越快）
SWAP_CONFIRM = 0.35              # 交換後確認盤面有變化的最長時間
DRY_RUN = True                   # 預設只偵測、不動滑鼠；用 play 模式才會真的操作
MAX_FAILS = 5                    # 連續幾次交換沒生效就停手（避免一直拉滑鼠）
WAIT_STABLE = False              # 交換後是否停下來等掉落動畫結束（不用暫停）

# 顏色門檻
MIN_VALUE, MIN_SAT = 55, 45      # 太暗=空格、太低飽和=白色
YELLOW_G_RATIO = 0.75            # 黃/橘分界（G/R 比例）
IGNORE = {"empty", "unknown"}
SYM = {"red": "R", "orange": "O", "yellow": "Y", "green": "G",
       "blue": "B", "purple": "P", "white": "W", "empty": ".", "unknown": "?"}


def capture():
    img = ImageGrab.grab(bbox=(LEFT, TOP, RIGHT, BOTTOM), all_screens=True)
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def stop_pressed():
    return bool(ctypes.windll.user32.GetAsyncKeyState(ord("Q")) & 0x8000)


def sample(patch):
    """K-means 取最大群當代表色（反光、邊緣會落到其他小群），回傳 (h,s,v,r,g)。"""
    data = patch.reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(
        data, 3, None, criteria, 5, cv2.KMEANS_PP_CENTERS)
    pixel = centers[int(np.argmax(np.bincount(labels.ravel(), minlength=3)))]
    pixel = pixel.reshape(1, 1, 3).astype(np.uint8)
    h, s, v = (int(x) for x in cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0, 0])
    b, g, r = (int(x) for x in pixel[0, 0])
    return h, s, v, r, g


def identify(patch):
    h, s, v, r, g = sample(patch)
    if v < MIN_VALUE:
        return "empty"
    if s < MIN_SAT:
        return "white"
    if h < 8 or h >= 170:
        return "red"
    if h < 15:
        return "orange"
    if h < 36:
        return "yellow" if g / max(r, 1) >= YELLOW_G_RATIO else "orange"
    if h < 85:
        return "green"
    if h < 135:
        return "blue"
    return "purple"


def read_board(img):
    board = []
    for r in range(N):
        row = []
        for c in range(N):
            x, y = int((c + .5) * CW), int((r + .5) * CH)
            row.append(identify(img[y - R:y + R + 1, x - R:x + R + 1]))
        board.append(row)
    return board


def find_matches(board):
    """回傳會被消除的格子集合。"""
    hit = set()
    for r in range(N):
        for c in range(N):
            color = board[r][c]
            if color in IGNORE:
                continue
            for dr, dc in ((0, 1), (1, 0)):
                cells = []
                y, x = r, c
                while y < N and x < N and board[y][x] == color:
                    cells.append((y, x))
                    y, x = y + dr, x + dc
                if len(cells) >= 3:
                    hit.update(cells)
    return hit


def best_move(board, skip=None):
    """回傳 (a, b, 可消顆數)，找不到回傳 None。skip 用來跳過剛剛失敗的交換。"""
    best, best_n = None, 0
    for r in range(N):
        for c in range(N):
            for dr, dc in ((0, 1), (1, 0)):
                r2, c2 = r + dr, c + dc
                if r2 >= N or c2 >= N:
                    continue
                if board[r][c] in IGNORE or board[r][c] == board[r2][c2]:
                    continue
                if skip and {(r, c), (r2, c2)} == set(skip):
                    continue

                test = [row[:] for row in board]
                test[r][c], test[r2][c2] = test[r2][c2], test[r][c]
                hit = find_matches(test)
                if (r, c) not in hit and (r2, c2) not in hit:
                    continue

                if len(hit) > best_n:
                    best_n = len(hit)
                    best = ((r, c), (r2, c2), best_n)
    return best


def looks_like_game(board):
    """盤面要有足夠多種顏色，才動手點滑鼠（避免對著非遊戲畫面亂拉）。"""
    counts = Counter(c for row in board for c in row)
    counts.pop("empty", None)
    counts.pop("unknown", None)
    if not counts:
        return False
    return len(counts) >= 3 and max(counts.values()) <= N * N * 0.6


def swap(a, b, duration=None):
    x1, y1 = int(LEFT + (a[1] + .5) * CW), int(TOP + (a[0] + .5) * CH)
    x2, y2 = int(LEFT + (b[1] + .5) * CW), int(TOP + (b[0] + .5) * CH)
    if DRY_RUN:
        print(f"  （模擬，不動滑鼠）({x1},{y1}) -> ({x2},{y2})")
        return
    pyautogui.moveTo(x1, y1)
    pyautogui.dragTo(x2, y2, duration=duration or SWAP_DURATION, button="left")


def confirm_change(before, timeout=SWAP_CONFIRM):
    """交換後確認盤面真的變了；沒變代表這一下沒被遊戲吃到。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.03)
        if tuple(map(tuple, read_board(capture()))) != before:
            return True
    return False


def wait_stable(timeout=SETTLE_TIMEOUT):
    """等盤面連續兩次一樣，代表掉落動畫結束（每 0.1 秒看一次）。"""
    deadline, last, same, board = time.time() + timeout, None, 0, None
    while time.time() < deadline:
        board = read_board(capture())
        sig = tuple(map(tuple, board))
        same = same + 1 if sig == last else 0
        if same >= 2:
            break
        last = sig
        time.sleep(POLL_INTERVAL)
    return board


def calibrate():
    board = read_board(capture())
    print(f"棋盤：x {LEFT}~{RIGHT}, y {TOP}~{BOTTOM}（{WIDTH}x{HEIGHT}）")
    print("R紅 O橙 Y黃 G綠 B藍 P紫 W白 .空")
    for row in board:
        print("  " + " ".join(SYM.get(c, "?") for c in row))


def detect(interval=0.5):
    """即時偵測顏色，不會動滑鼠；盤面有變才印出來。"""
    print("即時偵測顏色（按 q 結束）")
    print("R紅 O橙 Y黃 G綠 B藍 P紫 W白 .空")
    last = None

    while not stop_pressed():
        board = read_board(capture())
        sig = tuple(map(tuple, board))

        if sig != last:
            last = sig
            for row in board:
                print("  " + " ".join(SYM.get(c, "?") for c in row))
            counts = Counter(cell for row in board for cell in row)
            print("  顏色統計：" + "、".join(
                f"{k} x{n}" for k, n in counts.most_common()))
            print()

        time.sleep(interval)


def pick():
    """滑鼠指到哪顆寶石，就顯示那一點的顏色。"""
    print("把滑鼠移到寶石上（按 q 結束）")
    last = None

    while not stop_pressed():
        x, y = pyautogui.position()

        if LEFT <= x < RIGHT and TOP <= y < BOTTOM:
            rx, ry = x - LEFT, y - TOP
            img = capture()
            patch = img[max(ry - R, 0):ry + R + 1, max(rx - R, 0):rx + R + 1]
            h, s, v, r, g = sample(patch)
            text = (f"({x},{y}) 第 {int(ry // CH)} 列 第 {int(rx // CW)} 行 -> "
                    f"{identify(patch):7s} h={h:3d} s={s:3d} v={v:3d} "
                    f"rgb=({r:3d},{g:3d}) g/r={g / max(r, 1):.2f}")
        else:
            text = f"({x},{y}) 不在棋盤範圍內"

        if text != last:
            print(text)
            last = text

        time.sleep(0.15)


def main():
    print("寶石方塊 自動消除" + ("（模擬模式：只偵測，不動滑鼠）" if DRY_RUN else "（會實際操作滑鼠）"))
    print(f"{START_DELAY} 秒後開始，請先切換到遊戲畫面（按 q 停止）")
    time.sleep(START_DELAY)

    start = time.time()
    tick = start
    moves = still = fail = 0
    skip = None

    while not stop_pressed():
        # 每 0.1 秒重新偵測（扣掉偵測本身花的時間）
        time.sleep(max(0.0, POLL_INTERVAL - (time.time() - tick)))
        tick = time.time()
        elapsed = time.time() - start
        if elapsed >= ROUND_TIME:
            print(f"時間到（{elapsed:.1f} 秒）")
            break

        board = read_board(capture())
        if sum(cell == "empty" for row in board for cell in row) >= N * N * 0.7:
            print("盤面幾乎空了，遊戲結束")
            break

        if not looks_like_game(board):
            print("畫面不像寶石盤面（顏色太單調），停止，避免亂動滑鼠")
            break

        move = best_move(board, skip)
        if move is None:
            still += 1
            print(f"找不到可消的步（{still}/{STILL_LIMIT}）")
            if still >= STILL_LIMIT:
                print("判定遊戲結束")
                break
            continue

        still = 0
        a, b, n = move
        before = tuple(map(tuple, board))
        print(f"[{elapsed:5.1f}s] 交換 {a} <-> {b}，可消 {n} 顆")
        # 失敗過就把拖曳時間拉長一點，避免 0.01 秒太快、遊戲沒吃到
        swap(a, b, SWAP_DURATION + 0.02 * fail)
        moves += 1

        if DRY_RUN:
            continue

        if WAIT_STABLE:
            wait_stable()

        if confirm_change(before):
            fail, skip = 0, None
        else:
            fail += 1
            skip = (a, b)
            print(f"交換沒有生效（連續 {fail}/{MAX_FAILS} 次）")
            if fail >= MAX_FAILS:
                print("一直交換失敗，先停手：確認遊戲視窗在棋盤範圍內，"
                      "或把 SWAP_DURATION 調大（例如 0.05）")
                break

    print(f"結束：共交換 {moves} 次，耗時 {time.time() - start:.1f} 秒")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "calibrate":
        calibrate()
    elif mode == "detect":
        detect()
    elif mode == "pick":
        pick()
    elif mode == "play":
        DRY_RUN = False     # 真的要操作滑鼠
        main()
    else:
        main()

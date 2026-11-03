"""寶石方塊自動消除（精簡版）

    python 寶石炸彈.py            開始自動消除
    python 寶石炸彈.py calibrate  只印出目前辨識到的盤面

按 q 停止；滑鼠移到螢幕左上角也會中止（pyautogui 安全機制）。
"""

import ctypes
import sys
import time

import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# 棋盤範圍與格子
LEFT, TOP, RIGHT, BOTTOM = 501, 376, 814, 691
WIDTH, HEIGHT = RIGHT - LEFT, BOTTOM - TOP
N, R = 8, 4                      # 8x8 棋盤，每格取樣半徑 4
CW, CH = WIDTH / N, HEIGHT / N

# 流程設定
ROUND_TIME = 62                  # 一局約 60 秒
START_DELAY = 10                 # 幾秒後開始動作
STILL_LIMIT = 8                  # 連續找不到步就判定結束
SETTLE_TIMEOUT = 2.0             # 等盤面穩定的上限
POLL_INTERVAL = 0.1              # 每 0.1 秒重新偵測一次

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


def best_move(board):
    """回傳 (a, b, 可消顆數)，找不到回傳 None。"""
    best, best_n = None, 0
    for r in range(N):
        for c in range(N):
            for dr, dc in ((0, 1), (1, 0)):
                r2, c2 = r + dr, c + dc
                if r2 >= N or c2 >= N:
                    continue
                if board[r][c] in IGNORE or board[r][c] == board[r2][c2]:
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


def swap(a, b):
    x1, y1 = int(LEFT + (a[1] + .5) * CW), int(TOP + (a[0] + .5) * CH)
    x2, y2 = int(LEFT + (b[1] + .5) * CW), int(TOP + (b[0] + .5) * CH)
    pyautogui.moveTo(x1, y1)
    pyautogui.dragTo(x2, y2, duration=0.12, button="left")


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


def main():
    print("寶石方塊 自動消除")
    print(f"{START_DELAY} 秒後開始，請先切換到遊戲畫面（按 q 停止）")
    time.sleep(START_DELAY)

    start = time.time()
    tick = start
    moves = still = 0

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

        move = best_move(board)
        if move is None:
            still += 1
            print(f"找不到可消的步（{still}/{STILL_LIMIT}）")
            if still >= STILL_LIMIT:
                print("判定遊戲結束")
                break
            continue

        still = 0
        a, b, n = move
        print(f"[{elapsed:5.1f}s] 交換 {a} <-> {b}，可消 {n} 顆")
        swap(a, b)
        moves += 1
        wait_stable()

    print(f"結束：共交換 {moves} 次，耗時 {time.time() - start:.1f} 秒")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "calibrate":
        calibrate()
    else:
        main()

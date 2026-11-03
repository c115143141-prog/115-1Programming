
"""
寶石方塊（Bejeweled Blitz）自動消除程式

流程
  1. 截取棋盤畫面（x = 501~814, y = 376~691）
  2. 辨識 8x8 棋盤上每顆寶石的顏色
  3. 找出所有能消除的交換組合，挑選消除數量最多的
  4. 用滑鼠把兩顆寶石拖曳交換
  5. 等棋盤掉落穩定後重複，直到時間到或遊戲結束

使用方式
  python 寶石炸彈.py            開始自動消除
  python 寶石炸彈.py pick       滑鼠指到哪顆寶石就顯示它的顏色（校正用）
  python 寶石炸彈.py calibrate  一次辨識整個盤面，並輸出標註圖 board_debug.png
  python 寶石炸彈.py selftest   不開遊戲，測試判斷邏輯

停止方式
  按 q，或把滑鼠移到螢幕左上角（pyautogui 的安全機制）
"""

from collections import Counter

import ctypes
import sys
import time

import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab

# 讓 pyautogui 與截圖使用相同的實體像素座標（高 DPI 螢幕必備）
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# =========================
# 棋盤位置（螢幕座標）
# =========================
LEFT, TOP = 501, 376
RIGHT, BOTTOM = 814, 691
WIDTH, HEIGHT = RIGHT - LEFT, BOTTOM - TOP
N = 8

CW, CH = WIDTH / N, HEIGHT / N

# =========================
# 寶石定位
# =========================
# basex, basey：左上角寶石的中心點（螢幕座標）
basex = int(LEFT + CW / 2)
basey = int(TOP + CH / 2)

# gap：每顆寶石的間距（可給單一數值，或 (水平, 垂直)）
gap = (CW, CH)


def gem_pos(r, c):
    """回傳第 r 列（row）、第 c 行（column）那顆寶石的中心點 (x, y)。"""
    gap_x, gap_y = gap if isinstance(gap, (tuple, list)) else (gap, gap)
    return int(basex + c * gap_x), int(basey + r * gap_y)


# =========================
# 時間與流程設定
# =========================
ROUND_TIME = 62          # Bejeweled Blitz 一局約 60 秒，留一點緩衝
START_DELAY = 10         # 按下執行後，等幾秒才開始動作
STILL_LIMIT = 8          # 連續幾次找不到步可走，就判定遊戲結束
SETTLE_TIMEOUT = 2.0     # 等棋盤穩定的最長時間（秒）
VERBOSE = True           # 是否印出每次辨識到的棋盤

# 不列入消除判斷的格子
IGNORE = {"empty", "unknown"}

SYMBOL = {
    "red": "R", "orange": "O", "yellow": "Y", "green": "G",
    "blue": "B", "purple": "P", "white": "W",
    "empty": ".", "unknown": "?",
}


# =========================
# 截圖
# =========================
def capture():
    img = ImageGrab.grab(
        bbox=(LEFT, TOP, RIGHT, BOTTOM), all_screens=True
    )
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def stop_pressed():
    """按 Q 停止（不需額外套件）。"""
    return bool(ctypes.windll.user32.GetAsyncKeyState(ord("Q")) & 0x8000)


# =========================
# 顏色辨識
# =========================
# 門檻值：跑過 calibrate / pick 之後，可依印出的數值微調
MIN_VALUE = 55      # 亮度低於此 → 空格（背景）
MIN_SAT = 45        # 飽和度低於此 → 白色（沒有明顯色彩）
SAMPLE_RADIUS = 4   # 每格取樣半徑（像素）

# 橘色與黃色的色相非常接近，光看 H 很容易誤判，
# 所以再用「綠 / 紅 比例」判斷：黃色 G 接近 R（比例大），橘色偏紅（比例小）。
# 大約 0.75 是分界：純黃 (255,228,0) 約 0.89、純橘 (255,154,0) 約 0.60。
YELLOW_G_RATIO = 0.75

# 色相（OpenCV 的 H 是 0~179）分界
HUE_RED_END = 8        # H < 8 → 紅
HUE_ORANGE_PURE = 15   # H < 15 → 一定是橘
HUE_YELLOW_END = 36    # 15 ~ 36 → 黃或橘，用 G/R 比例細分
HUE_GREEN_END = 85
HUE_BLUE_END = 135     # 純藍約 H=120，紫約 140 以上

# 取樣方式：kmeans 對反光、陰影、雜訊最穩（測試見 color_methods.py）
COLOR_METHOD = "kmeans"     # 可改成 "median"（較快、但遇到反光較易誤判）


def hsv_median(patch):
    """回傳一小塊畫面（BGR）的 HSV 中位數。"""
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    return tuple(int(x) for x in np.median(hsv.reshape(-1, 3), axis=0))


def bgr_median(patch):
    """回傳一小塊畫面（BGR）的 BGR 中位數。"""
    return tuple(int(x) for x in np.median(patch.reshape(-1, 3), axis=0))


def kmeans_color(patch, k=3):
    """用 K-means 把格子分成 k 群，取最大那群當作寶石本身的顏色。

    這樣反光、邊緣、背景只會落在其他小群，不會拉歪顏色。
    回傳 (h, s, v, r, g)。
    """
    data = patch.reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(
        data, k, None, criteria, 5, cv2.KMEANS_PP_CENTERS)

    biggest = int(np.argmax(np.bincount(labels.ravel(), minlength=k)))
    pixel = centers[biggest].reshape(1, 1, 3).astype(np.uint8)
    h, s, v = (int(x) for x in cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0, 0])
    b, g, r = (int(x) for x in pixel[0, 0])
    return h, s, v, r, g, b


def sample_color(patch):
    """取樣一格的代表色，回傳 (h, s, v, r, g, b)。"""
    if COLOR_METHOD == "kmeans":
        return kmeans_color(patch)
    h, s, v = hsv_median(patch)
    b, g, r = bgr_median(patch)
    return h, s, v, r, g, b


def identify(patch):
    """把一小塊畫面（BGR）轉成寶石顏色名稱。"""
    h, s, v, r, g, b = sample_color(patch)

    if v < MIN_VALUE:
        return "empty"
    if s < MIN_SAT:
        return "white"

    if h < HUE_RED_END or h >= 170:
        return "red"
    if h < HUE_ORANGE_PURE:
        return "orange"
    if h < HUE_YELLOW_END:
        # 黃色與橘色在這裡重疊，改用 G/R 比例
        return "yellow" if g / max(r, 1) >= YELLOW_G_RATIO else "orange"
    if h < HUE_GREEN_END:
        return "green"
    if h < HUE_BLUE_END:
        return "blue"
    return "purple"


def read_board(img):
    """把截圖轉成 8x8 的顏色盤面。"""
    board = []
    for r in range(N):
        row = []
        for c in range(N):
            x = int((c + .5) * CW)
            y = int((r + .5) * CH)
            patch = img[y - SAMPLE_RADIUS:y + SAMPLE_RADIUS + 1,
                        x - SAMPLE_RADIUS:x + SAMPLE_RADIUS + 1]
            row.append(identify(patch))
        board.append(row)
    return board


def print_board(board):
    for row in board:
        print("  " + " ".join(SYMBOL.get(c, "?") for c in row))


def annotate(img, board):
    """把辨識結果畫在截圖上（放大 3 倍），方便肉眼檢查。"""
    out = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)

    for i in range(N + 1):
        x = int(i * CW * 3)
        y = int(i * CH * 3)
        cv2.line(out, (x, 0), (x, out.shape[0] - 1), (0, 255, 0), 1)
        cv2.line(out, (0, y), (out.shape[1] - 1, y), (0, 255, 0), 1)

    for r in range(N):
        for c in range(N):
            x = int((c + .5) * CW * 3) - 7
            y = int((r + .5) * CH * 3) + 7
            cv2.putText(out, SYMBOL.get(board[r][c], "?"), (x, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2,
                        cv2.LINE_AA)

    return out


# =========================
# 消除判斷
# =========================
def find_matches(board):
    """回傳所有會被消除的格子座標集合 {(r, c), ...}。"""
    found = set()

    # 水平
    for r in range(N):
        c = 0
        while c < N:
            color = board[r][c]
            end = c
            while end < N and board[r][end] == color:
                end += 1
            if color not in IGNORE and end - c >= 3:
                found.update((r, x) for x in range(c, end))
            c = end

    # 垂直
    for c in range(N):
        r = 0
        while r < N:
            color = board[r][c]
            end = r
            while end < N and board[end][c] == color:
                end += 1
            if color not in IGNORE and end - r >= 3:
                found.update((y, c) for y in range(r, end))
            r = end

    return found


# 舊名稱，方便沿用
matches = find_matches


def best_move(board):
    """回傳 (a, b, score)；找不到就回傳 None。"""
    best = None
    best_score = 0

    for r in range(N):
        for c in range(N):
            for dr, dc in ((0, 1), (1, 0)):
                r2, c2 = r + dr, c + dc
                if r2 >= N or c2 >= N:
                    continue

                color = board[r][c]
                other = board[r2][c2]
                if color in IGNORE or other in IGNORE:
                    continue
                if color == other:
                    continue

                test = [row[:] for row in board]
                test[r][c], test[r2][c2] = other, color

                found = find_matches(test)

                # 交換的位置必須真的被消掉，才算是有效步
                if (r, c) not in found and (r2, c2) not in found:
                    continue

                score = len(found)
                if score > best_score:
                    best_score = score
                    best = ((r, c), (r2, c2), score)

    return best


def board_is_empty(board):
    """整個盤面幾乎都是空格 → 遊戲結束（或已離開遊戲）。"""
    empty = sum(cell == "empty" for row in board for cell in row)
    return empty >= N * N * 0.7


def signature(board):
    return tuple(tuple(row) for row in board)


# =========================
# 滑鼠交換
# =========================
def swap(a, b):
    x1, y1 = gem_pos(*a)
    x2, y2 = gem_pos(*b)
    pyautogui.moveTo(x1, y1)
    pyautogui.dragTo(x2, y2, duration=0.12, button="left")


def wait_stable(timeout=SETTLE_TIMEOUT):
    """等畫面連續兩次一樣，代表掉落動畫結束。"""
    deadline = time.time() + timeout
    last = None
    same = 0
    board = None

    while time.time() < deadline:
        board = read_board(capture())
        sig = signature(board)
        if sig == last:
            same += 1
            if same >= 2:
                return board
        else:
            same = 0
            last = sig
        time.sleep(0.06)

    return board


# =========================
# 校正模式
# =========================
def calibrate():
    img = capture()
    board = read_board(img)

    print(f"棋盤範圍：x {LEFT}~{RIGHT}, y {TOP}~{BOTTOM}（{WIDTH}x{HEIGHT}）")
    print("辨識結果（R 紅 O 橙 Y 黃 G 綠 B 藍 P 紫 W 白 . 空）：")
    print_board(board)

    print("\n各格中心 HSV / RGB（黃橘可用 g/r 比例核對）：")
    for r in range(N):
        for c in range(N):
            x = int((c + .5) * CW)
            y = int((r + .5) * CH)
            patch = img[y - SAMPLE_RADIUS:y + SAMPLE_RADIUS + 1,
                        x - SAMPLE_RADIUS:x + SAMPLE_RADIUS + 1]
            h, s, v, rr, g, b = sample_color(patch)
            print(f"  ({r},{c}) -> {board[r][c]:7s} "
                  f"h={h:3d} s={s:3d} v={v:3d} "
                  f"rgb=({rr:3d},{g:3d},{b:3d}) g/r={g / max(rr, 1):.2f}")

    counts = Counter(cell for row in board for cell in row)
    print("\n顏色統計：" + "、".join(
        f"{name} x{n}" for name, n in counts.most_common()))

    if counts.most_common(1)[0][1] >= N * N * 0.9:
        print("！將近全部格子都是同一種顏色，可能畫面不在遊戲上，"
              "或棋盤座標 / 門檻需要調整")

    path = "board_debug.png"
    ok, buf = cv2.imencode(".png", annotate(img, board))
    if ok:
        buf.tofile(path)      # 用 tofile 才支援中文路徑
        print(f"\n標註圖已存成 {path}"
              "（綠線是格子，紅字是辨識結果，可用來核對）")


# =========================
# 單點取樣模式
# =========================
def pick():
    """滑鼠指到哪裡，就即時顯示那一點的顏色，用來校正門檻。"""
    print("把滑鼠移到寶石上，會即時顯示辨識結果（按 q 結束）")
    last = None

    while not stop_pressed():
        x, y = pyautogui.position()

        if LEFT <= x < RIGHT and TOP <= y < BOTTOM:
            rx, ry = x - LEFT, y - TOP
            img = capture()
            patch = img[max(ry - SAMPLE_RADIUS, 0):ry + SAMPLE_RADIUS + 1,
                        max(rx - SAMPLE_RADIUS, 0):rx + SAMPLE_RADIUS + 1]
            h, s, v, rr, g, b = sample_color(patch)
            text = (f"({x},{y}) 第 {int(ry // CH)} 列 第 {int(rx // CW)} 行"
                    f" -> {identify(patch):7s} h={h:3d} s={s:3d} v={v:3d}"
                    f" rgb=({rr:3d},{g:3d},{b:3d}) g/r={g / max(rr, 1):.2f}")
        else:
            text = f"({x},{y}) 不在棋盤範圍內"

        if text != last:
            print(text)
            last = text

        time.sleep(0.15)


# =========================
# 邏輯測試（不需要遊戲畫面）
# =========================
def selftest():
    import random

    rng = random.Random(20260101)
    colors = ["red", "green", "blue", "yellow", "purple", "orange"]

    # 固定亂數種子，找一個「沒有現成三連、但存在有效步」的盤面
    base = None
    for _ in range(5000):
        cand = [[rng.choice(colors) for _ in range(N)] for _ in range(N)]
        if not find_matches(cand) and best_move(cand) is not None:
            base = cand
            break
    assert base is not None, "找不到合適的測試盤面"

    # 橫向三連要被找到
    lined = [row[:] for row in base]
    lined[0][0] = lined[0][1] = lined[0][2] = "red"
    found = find_matches(lined)
    assert {(0, 0), (0, 1), (0, 2)} <= found, "橫向三連沒抓到"

    # 縱向三連要被找到
    lined = [row[:] for row in base]
    lined[0][4] = lined[1][4] = lined[2][4] = "blue"
    found = find_matches(lined)
    assert {(0, 4), (1, 4), (2, 4)} <= found, "縱向三連沒抓到"

    # 一定找得到有效步，而且該步真的能消
    move = best_move(base)
    assert move is not None, "找不到有效步"

    a, b, score = move
    test = [row[:] for row in base]
    test[a[0]][a[1]], test[b[0]][b[1]] = test[b[0]][b[1]], test[a[0]][a[1]]
    found = find_matches(test)
    assert a in found or b in found, "選到的步不會消除"
    assert score == len(found), "分數與實際消除數不一致"

    # 空格過多 → 視為遊戲結束
    empty = [["empty"] * N for _ in range(N)]
    assert board_is_empty(empty)

    # 顏色辨識（BGR 由 RGB 轉換）
    def patch_of(rgb):
        return np.full((9, 9, 3), tuple(reversed(rgb)), dtype=np.uint8)

    cases = [
        ((255, 228, 0), "yellow"),    # 黃：G 接近 R
        ((255, 210, 0), "yellow"),
        ((255, 154, 0), "orange"),    # 橘：G 明顯小於 R
        ((255, 140, 0), "orange"),
        ((255, 0, 0), "red"),
        ((0, 200, 0), "green"),
        ((0, 0, 255), "blue"),
        ((200, 0, 200), "purple"),
        ((255, 255, 255), "white"),
        ((20, 20, 20), "empty"),
    ]
    for rgb, want in cases:
        got = identify(patch_of(rgb))
        assert got == want, f"rgb={rgb} 應為 {want}，卻判成 {got}"

    print(f"selftest OK（範例最佳步：{a} <-> {b}，可消 {score} 顆）")


# =========================
# 主流程
# =========================
def main():
    print("寶石方塊 自動消除")
    print(f"棋盤範圍：x {LEFT}~{RIGHT}, y {TOP}~{BOTTOM}")
    print(f"{START_DELAY} 秒後開始，請先切換到遊戲畫面")
    print("按 q，或把滑鼠移到左上角可停止")
    time.sleep(START_DELAY)

    start = time.time()
    moves = 0
    still = 0
    last_board = None

    while True:
        if stop_pressed():
            print("手動停止")
            break

        elapsed = time.time() - start
        if elapsed >= ROUND_TIME:
            print(f"時間到（{elapsed:.1f} 秒），停止")
            break

        board = read_board(capture())

        if board_is_empty(board):
            print("盤面幾乎空了，遊戲可能已結束")
            break

        if VERBOSE and board != last_board:
            print_board(board)
            last_board = [row[:] for row in board]

        move = best_move(board)

        if move is None:
            still += 1
            print(f"找不到可消除的組合（{still}/{STILL_LIMIT}）")
            if still >= STILL_LIMIT:
                print("連續找不到步可走，判定遊戲結束")
                break
            time.sleep(0.4)
            continue

        still = 0
        a, b, score = move
        print(f"[{elapsed:5.1f}s] 交換 {a} <-> {b}，預計消除 {score} 顆")
        swap(a, b)
        moves += 1
        wait_stable()

    print(f"結束：共交換 {moves} 次，耗時 {time.time() - start:.1f} 秒")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "calibrate":
        calibrate()
    elif mode == "pick":
        pick()
    elif mode == "selftest":
        selftest()
    else:
        main()

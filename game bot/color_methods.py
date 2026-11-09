# 寶石方塊自動消除｜精簡版
# 使用：python 寶石方塊_白色辨識版.py [run|calibrate|pick|selftest]

from collections import Counter
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
LEFT, TOP = (1438, 470)
RIGHT, BOTTOM = (1834, 864)
WIDTH, HEIGHT = (RIGHT - LEFT, BOTTOM - TOP)
N = 8
CW, CH = (WIDTH / N, HEIGHT / N)
basex = int(LEFT + CW / 2)
basey = int(TOP + CH / 2)
gap = (CW, CH)

def gem_pos(r, c):
    gap_x, gap_y = gap if isinstance(gap, (tuple, list)) else (gap, gap)
    return (int(basex + c * gap_x), int(basey + r * gap_y))
ROUND_TIME = 65
START_DELAY = 5
STILL_LIMIT = 8
SETTLE_TIMEOUT = 0.05
VERBOSE = True
IGNORE = {'empty', 'unknown'}
SYMBOL = {'red': 'R', 'orange': 'O', 'yellow': 'Y', 'green': 'G', 'blue': 'B', 'purple': 'P', 'white': 'W', 'empty': '.', 'unknown': '?'}

def capture():
    img = ImageGrab.grab(bbox=(LEFT, TOP, RIGHT, BOTTOM), all_screens=True)
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def stop_pressed():
    return bool(ctypes.windll.user32.GetAsyncKeyState(ord('Q')) & 32768)
MIN_VALUE = 55
MIN_SAT = 45
SAMPLE_RADIUS = 8
HUE_RED_END = 8
HUE_ORANGE_PURE = 20
HUE_YELLOW_START = 20
HUE_YELLOW_END = 38
HUE_GREEN_END = 85
HUE_BLUE_END = 135
COLOR_METHOD = 'kmeans'

def hsv_median(patch):
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    return tuple((int(x) for x in np.median(hsv.reshape(-1, 3), axis=0)))

def bgr_median(patch):
    return tuple((int(x) for x in np.median(patch.reshape(-1, 3), axis=0)))

def kmeans_color(patch, k=3):
    data = patch.reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(data, k, None, criteria, 5, cv2.KMEANS_PP_CENTERS)
    biggest = int(np.argmax(np.bincount(labels.ravel(), minlength=k)))
    pixel = centers[biggest].reshape(1, 1, 3).astype(np.uint8)
    h, s, v = (int(x) for x in cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0, 0])
    b, g, r = (int(x) for x in pixel[0, 0])
    return (h, s, v, r, g, b)
HUE_CENTERS = {'red': 176, 'orange': 13, 'yellow': 29, 'green': 64, 'blue': 106, 'purple': 150}

def hue_distance(a, b):
    return min((int(a) - int(b)) % 180, (int(b) - int(a)) % 180)

def sample_color(patch):
    if patch is None or patch.size == 0:
        return (0, 0, 0, 0, 0, 0)
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    hsv_pixels = hsv.reshape(-1, 3)
    bgr_pixels = patch.reshape(-1, 3)
    valid = (hsv_pixels[:, 2] >= MIN_VALUE) & (hsv_pixels[:, 1] >= 55)
    chromatic_hsv = hsv_pixels[valid]
    chromatic_bgr = bgr_pixels[valid]
    if len(chromatic_hsv) < max(4, int(len(hsv_pixels) * 0.08)):
        bright = hsv_pixels[hsv_pixels[:, 2] >= MIN_VALUE]
        if len(bright) == 0:
            return (0, 0, 0, 0, 0, 0)
        med_s = int(np.median(bright[:, 1]))
        med_v = int(np.median(bright[:, 2]))
        if med_s < MIN_SAT:
            return (0, med_s, med_v, 255, 255, 255)
        return (0, med_s, med_v, 0, 0, 0)
    h, s, v = (int(x) for x in np.median(chromatic_hsv, axis=0))
    b, g, r = (int(x) for x in np.median(chromatic_bgr, axis=0))
    return (h, s, v, r, g, b)
# 使用者提供的實際 RGB 標準色（RGB 順序）
COLOR_REFERENCES = {
    'green': (89, 253, 132),
    'purple': (236, 15, 236),
    'yellow': (253, 253, 65),
    'orange': (220, 85, 25),
    'red': (253, 59, 108),
    'blue': (28, 138, 253),
}
WHITE_RGB = (253, 253, 253)
WHITE_TOLERANCE = 32


def _rgb_chromaticity(rgb_array):
    values = np.asarray(rgb_array, dtype=np.float32)
    sums = np.maximum(values.sum(axis=1, keepdims=True), 1.0)
    return values / sums

COLOR_CHROMA = {
    name: _rgb_chromaticity([rgb])[0]
    for name, rgb in COLOR_REFERENCES.items()
}


def classify_reference_colors(patch):
    """依照使用者提供的 RGB 標準色逐像素投票；指定白色 RGB 判為 white。"""
    if patch is None or patch.size == 0:
        return None

    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    rgb = cv2.cvtColor(patch, cv2.COLOR_BGR2RGB).reshape(-1, 3).astype(np.float32)
    hp = hsv.reshape(-1, 3)

    # RGB(253,253,253) 判定為白色方塊；不再使用透明色分類。
    white_distance = np.linalg.norm(rgb - np.asarray(WHITE_RGB, dtype=np.float32), axis=1)
    white_pixels = (hp[:, 1] <= 35) & (hp[:, 2] >= 215) & (white_distance <= WHITE_TOLERANCE)
    if np.count_nonzero(white_pixels) >= max(3, int(len(rgb) * 0.20)):
        return 'white'

    # 排除背景、低彩度反光與過暗像素。
    valid = (hp[:, 1] >= 65) & (hp[:, 2] >= 55)
    pixels = rgb[valid]
    if len(pixels) < max(4, int(len(rgb) * 0.06)):
        return None

    chroma = _rgb_chromaticity(pixels)
    names = tuple(COLOR_CHROMA)
    refs = np.stack([COLOR_CHROMA[name] for name in names])
    distances = np.linalg.norm(chroma[:, None, :] - refs[None, :, :], axis=2)
    nearest = np.argmin(distances, axis=1)

    # 過遠的像素不參與投票，避免其他顏色或雜訊干擾。
    confidence = distances[np.arange(len(nearest)), nearest] <= 0.24
    if np.count_nonzero(confidence) < max(3, int(len(pixels) * 0.20)):
        return None

    votes = np.bincount(nearest[confidence], minlength=len(names))
    winner = int(np.argmax(votes))
    if votes[winner] / max(int(votes.sum()), 1) < 0.38:
        return None
    return names[winner]

def identify(patch):
    reference_color = classify_reference_colors(patch)
    if reference_color is not None:
        return reference_color
    h, s, v, r, g, b = sample_color(patch)
    if v < MIN_VALUE:
        return 'empty'
    if s < MIN_SAT:
        return 'white'
    distances = {name: hue_distance(h, center) for name, center in HUE_CENTERS.items()}
    color = min(distances, key=distances.get)
    if distances[color] > 18:
        return 'unknown'
    return color

def read_board(img):
    board = []
    for r in range(N):
        row = []
        for c in range(N):
            x = int((c + 0.5) * CW)
            y = int((r + 0.5) * CH)
            patch = img[y - SAMPLE_RADIUS:y + SAMPLE_RADIUS + 1, x - SAMPLE_RADIUS:x + SAMPLE_RADIUS + 1]
            row.append(identify(patch))
        board.append(row)
    return board

def print_board(board):
    for row in board:
        print('  ' + ' '.join((SYMBOL.get(c, '?') for c in row)))

def annotate(img, board):
    out = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
    for i in range(N + 1):
        x = int(i * CW * 3)
        y = int(i * CH * 3)
        cv2.line(out, (x, 0), (x, out.shape[0] - 1), (0, 255, 0), 1)
        cv2.line(out, (0, y), (out.shape[1] - 1, y), (0, 255, 0), 1)
    for r in range(N):
        for c in range(N):
            x = int((c + 0.5) * CW * 3) - 7
            y = int((r + 0.5) * CH * 3) + 7
            cv2.putText(out, SYMBOL.get(board[r][c], '?'), (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
    return out

def find_matches(board):
    found = set()
    for r in range(N):
        c = 0
        while c < N:
            color = board[r][c]
            end = c
            while end < N and board[r][end] == color:
                end += 1
            if color not in IGNORE and end - c >= 3:
                found.update(((r, x) for x in range(c, end)))
            c = end
    for c in range(N):
        r = 0
        while r < N:
            color = board[r][c]
            end = r
            while end < N and board[end][c] == color:
                end += 1
            if color not in IGNORE and end - r >= 3:
                found.update(((y, c) for y in range(r, end)))
            r = end
    return found
matches = find_matches

def move_key(a, b):
    return tuple(sorted((tuple(a), tuple(b))))

def best_move(board, excluded_moves=None):
    if excluded_moves is None:
        excluded_moves = set()
    best = None
    best_score = 0
    for r in range(N):
        for c in range(N):
            for dr, dc in ((0, 1), (1, 0)):
                r2, c2 = (r + dr, c + dc)
                if r2 >= N or c2 >= N:
                    continue
                a, b = ((r, c), (r2, c2))
                if move_key(a, b) in excluded_moves:
                    continue
                color = board[r][c]
                other = board[r2][c2]
                if color in IGNORE or other in IGNORE or color == other:
                    continue
                test = [row[:] for row in board]
                test[r][c], test[r2][c2] = (other, color)
                found = find_matches(test)
                if a not in found and b not in found:
                    continue
                score = len(found)
                if score > best_score:
                    best_score = score
                    best = (a, b, score)
    return best

def board_is_empty(board):
    empty = sum((cell == 'empty' for row in board for cell in row))
    return empty >= N * N * 0.7

def signature(board):
    return tuple((tuple(row) for row in board))

def swap(a, b):
    x1, y1 = gem_pos(*a)
    x2, y2 = gem_pos(*b)
    pyautogui.moveTo(x1, y1)
    pyautogui.dragTo(x2, y2, duration=0.12, button='left')

def wait_stable(timeout=SETTLE_TIMEOUT):
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

def calibrate():
    img = capture()
    board = read_board(img)
    print(f'棋盤範圍：x {LEFT}~{RIGHT}, y {TOP}~{BOTTOM}（{WIDTH}x{HEIGHT}）')
    print('辨識結果（R 紅 O 橙 Y 黃 G 綠 B 藍 P 紫 W 白 . 空）：')
    print_board(board)
    print('\n各格中心 HSV / RGB（彩色方塊採逐像素投票，白色獨立判為 white）：')
    for r in range(N):
        for c in range(N):
            x = int((c + 0.5) * CW)
            y = int((r + 0.5) * CH)
            patch = img[y - SAMPLE_RADIUS:y + SAMPLE_RADIUS + 1, x - SAMPLE_RADIUS:x + SAMPLE_RADIUS + 1]
            h, s, v, rr, g, b = sample_color(patch)
            print(f'  ({r},{c}) -> {board[r][c]:7s} h={h:3d} s={s:3d} v={v:3d} rgb=({rr:3d},{g:3d},{b:3d}) g/r={g / max(rr, 1):.2f}')
    counts = Counter((cell for row in board for cell in row))
    print('\n顏色統計：' + '、'.join((f'{name} x{n}' for name, n in counts.most_common())))
    if counts.most_common(1)[0][1] >= N * N * 0.9:
        print('！將近全部格子都是同一種顏色，可能畫面不在遊戲上，或棋盤座標 / 門檻需要調整')
    path = 'board_debug.png'
    ok, buf = cv2.imencode('.png', annotate(img, board))
    if ok:
        buf.tofile(path)
        print(f'\n標註圖已存成 {path}（綠線是格子，紅字是辨識結果，可用來核對）')

def pick():
    print('把滑鼠移到寶石上，會即時顯示辨識結果（按 q 結束）')
    last = None
    while not stop_pressed():
        x, y = pyautogui.position()
        if LEFT <= x < RIGHT and TOP <= y < BOTTOM:
            rx, ry = (x - LEFT, y - TOP)
            img = capture()
            patch = img[max(ry - SAMPLE_RADIUS, 0):ry + SAMPLE_RADIUS + 1, max(rx - SAMPLE_RADIUS, 0):rx + SAMPLE_RADIUS + 1]
            h, s, v, rr, g, b = sample_color(patch)
            text = f'({x},{y}) 第 {int(ry // CH)} 列 第 {int(rx // CW)} 行 -> {identify(patch):7s} h={h:3d} s={s:3d} v={v:3d} rgb=({rr:3d},{g:3d},{b:3d}) g/r={g / max(rr, 1):.2f}'
        else:
            text = f'({x},{y}) 不在棋盤範圍內'
        if text != last:
            print(text)
            last = text
        time.sleep(0.15)

def selftest():
    import random
    rng = random.Random(20260101)
    colors = ['red', 'green', 'blue', 'yellow', 'purple', 'orange']
    base = None
    for _ in range(5000):
        cand = [[rng.choice(colors) for _ in range(N)] for _ in range(N)]
        if not find_matches(cand) and best_move(cand) is not None:
            base = cand
            break
    assert base is not None, '找不到合適的測試盤面'
    lined = [row[:] for row in base]
    lined[0][0] = lined[0][1] = lined[0][2] = 'red'
    found = find_matches(lined)
    assert {(0, 0), (0, 1), (0, 2)} <= found, '橫向三連沒抓到'
    lined = [row[:] for row in base]
    lined[0][4] = lined[1][4] = lined[2][4] = 'blue'
    found = find_matches(lined)
    assert {(0, 4), (1, 4), (2, 4)} <= found, '縱向三連沒抓到'
    move = best_move(base)
    assert move is not None, '找不到有效步'
    a, b, score = move
    test = [row[:] for row in base]
    test[a[0]][a[1]], test[b[0]][b[1]] = (test[b[0]][b[1]], test[a[0]][a[1]])
    found = find_matches(test)
    assert a in found or b in found, '選到的步不會消除'
    assert score == len(found), '分數與實際消除數不一致'
    empty = [['empty'] * N for _ in range(N)]
    assert board_is_empty(empty)

    def patch_of(rgb):
        return np.full((9, 9, 3), tuple(reversed(rgb)), dtype=np.uint8)
    cases = [((89, 253, 132), 'green'), ((236, 15, 236), 'purple'), ((253, 253, 65), 'yellow'), ((220, 85, 25), 'orange'), ((253, 59, 108), 'red'), ((28, 138, 253), 'blue'), ((253, 253, 253), 'white'), ((20, 20, 20), 'empty')]
    for rgb, want in cases:
        got = identify(patch_of(rgb))
        assert got == want, f'rgb={rgb} 應為 {want}，卻判成 {got}'
    print(f'selftest OK（範例最佳步：{a} <-> {b}，可消 {score} 顆）')

def main():
    print('寶石方塊 自動消除')
    print(f'棋盤範圍：x {LEFT}~{RIGHT}, y {TOP}~{BOTTOM}')
    print(f'{START_DELAY} 秒後開始，請先切換到遊戲畫面')
    print('按 q，或把滑鼠移到左上角可停止')
    time.sleep(START_DELAY)
    start = time.time()
    moves = 0
    still = 0
    last_board = None
    attempted_signature = None
    attempted_moves = set()
    while True:
        if stop_pressed():
            print('手動停止')
            break
        elapsed = time.time() - start
        if elapsed >= ROUND_TIME:
            print(f'時間到（{elapsed:.1f} 秒），停止')
            break
        board = read_board(capture())
        if board_is_empty(board):
            print('盤面幾乎空了，遊戲可能已結束')
            break
        current_signature = signature(board)
        if current_signature != attempted_signature:
            attempted_signature = current_signature
            attempted_moves.clear()
            still = 0
        if VERBOSE and board != last_board:
            print_board(board)
            last_board = [row[:] for row in board]
        move = best_move(board, attempted_moves)
        if move is None:
            still += 1
            if attempted_moves:
                print('這個盤面剩下的有效位置都已經嘗試過，不重複操作，等待棋盤變化。')
            else:
                print(f'找不到可消除的組合（{still}/{STILL_LIMIT}）')
            if still >= STILL_LIMIT:
                print('連續找不到新步可走，判定遊戲可能結束')
                break
            time.sleep(0.15)
            continue
        still = 0
        a, b, score = move
        attempted_moves.add(move_key(a, b))
        print(f'[{elapsed:5.1f}s] 交換 {a} <-> {b}，預計消除 {score} 顆')
        swap(a, b)
        moves += 1
        wait_stable()
    print(f'結束：共交換 {moves} 次，耗時 {time.time() - start:.1f} 秒')
if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'run'
    if mode == 'calibrate':
        calibrate()
    elif mode == 'pick':
        pick()
    elif mode == 'selftest':
        selftest()
    else:
        main()

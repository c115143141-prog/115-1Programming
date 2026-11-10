import argparse
import ctypes
from ctypes import wintypes
import logging
import operator
from pathlib import Path
import subprocess
import sys
import time


def ensure_packages():
    required = {
        "cv2": "opencv-python",
        "mss": "mss",
        "numpy": "numpy",
    }
    for module_name, pkg_name in required.items():
        try:
            __import__(module_name)
        except ImportError:
            print(f"偵測到缺少套件 {pkg_name}，正在自動安裝...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg_name])


ensure_packages()

import cv2
import mss
import numpy as np

__file__ = "blitz.py"
SIZE = 8
COLORS = "ROYGBPW"
F2, F8 = 0x71, 0x77
LOG = logging.getLogger(__name__)
LOG_PATH = Path(__file__).with_name("blitz-last-run.log")



def read_board(frame):
    hsv = cv2.cvtColor(cv2.resize(frame, (256, 256)), cv2.COLOR_BGR2HSV)
    tiles = hsv.reshape(8, 32, 8, 32, 3).transpose(0, 2, 1, 3, 4)
    hue, sat, value = tiles[:, :, 7:25, 7:25, :].transpose(4, 0, 1, 2, 3)
    bright = (sat >= 100) & (value >= 95)
    masks = (
        bright & ((hue <= 8) | (hue >= 172)),
        bright & (hue >= 9) & (hue <= 21),
        bright & (hue >= 22) & (hue <= 38),
        bright & (hue >= 39) & (hue <= 82),
        bright & (hue >= 83) & (hue <= 125),
        bright & (hue >= 126) & (hue <= 171),
        (sat <= 80) & (value >= 145),
    )
    counts = np.stack([mask.sum(axis=(2, 3)) for mask in masks])
    ranked = np.sort(counts, axis=0)
    clear = (ranked[-1] >= 100) & (ranked[-1] - ranked[-2] >= 55)
    return tuple(
        tuple(COLORS[color] if valid else None for color, valid in zip(row, good))
        for row, good in zip(counts.argmax(axis=0), clear)
    )


def timer_mask(frame):
    hue, sat, value = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).transpose(2, 0, 1)
    return (hue >= 83) & (hue <= 107) & (sat >= 100) & (value >= 100)


def find_board(frame):
    _, frame_w = frame.shape[:2]
    mask = timer_mask(frame).astype(np.uint8)
    _, _, components, _ = cv2.connectedComponentsWithStats(mask)
    for x, y, length, thickness, area in sorted(components[1:], key=operator.itemgetter(2), reverse=True):
        if length < 150 or not 14 * thickness <= length <= 29 * thickness:
            continue
        if area < 0.7 * length * thickness:
            continue
        side = round(length * 1.013)
        left = int(x) - round(side * 0.008)
        top = int(y) - round(side * 0.018) - side
        if left < 0 or top < 0 or left + side > frame_w:
            continue
        board_frame = frame[top:top + side, left:left + side]
        gems = [gem for row in read_board(board_frame) for gem in row if gem is not None]
        if len(gems) >= 60 and len(set(gems)) >= 5:
            return left, top, side, side
    return None


def runs(board):
    found = []
    for vertical in (False, True):
        for line in range(SIZE):
            cells = [(i, line) if vertical else (line, i) for i in range(SIZE)]
            start = 0
            while start < SIZE:
                row, col = cells[start]
                color = board[row][col]
                end = start + 1
                while end < SIZE:
                    er, ec = cells[end]
                    if board[er][ec] != color:
                        break
                    end += 1
                if color is not None and end - start >= 3:
                    found.append(set(cells[start:end]))
                start = end
    return found


def predict_value(board, matches, can_predict_cascades):
    value = 0
    for step in range(4 if can_predict_cascades else 1):
        if not matches:
            break
        removed = set.union(*matches)
        longest = max(map(len, matches))
        intersects = sum(map(len, matches)) > len(removed)
        special_bonus = 12 if longest >= 5 else 8 if intersects else 4 if longest == 4 else 0
        value += (2 * len(removed) + special_bonus) / (step + 1)
        for col in range(SIZE):
            kept = [board[row][col] for row in range(SIZE) if (row, col) not in removed]
            for row, gem in enumerate([None] * (SIZE - len(kept)) + kept):
                board[row][col] = gem
        matches = runs(board)
    return value


def best_move(board):
    best = None
    best_value = 0
    complete = all(None not in row for row in board)
    for row in range(SIZE):
        for col in range(SIZE):
            source = board[row][col]
            if source is None:
                continue
            for r, c in ((row + 1, col), (row, col + 1)):
                if r >= SIZE or c >= SIZE or board[r][c] in (source, None):
                    continue
                trial = [list(line) for line in board]
                trial[row][col], trial[r][c] = trial[r][c], trial[row][col]
                matches = runs(trial)
                if not any((row, col) in run or (r, c) in run for run in matches):
                    continue
                value = predict_value(trial, matches, complete)
                if value > best_value:
                    best = ((row, col), (r, c))
                    best_value = value
    return best


class Windows:
    def __init__(self):
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.user.SetProcessDPIAware()
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user.GetAsyncKeyState.restype = ctypes.c_short
        self.user.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        self.user.mouse_event.argtypes = [wintypes.DWORD] * 4 + [ctypes.c_size_t]

    def pressed(self, key):
        return bool(self.user.GetAsyncKeyState(key) & 0x8000)

    def check(self):
        if self.pressed(F8):
            raise KeyboardInterrupt

    def wait_in_game(self, window=None):
        while True:
            while not self.pressed(F2):
                self.check()
                time.sleep(0.015)
            while self.pressed(F2):
                self.check()
                time.sleep(0.015)
            self.check()
            active = self.game_window()
            if active is not None and (window is None or active == window):
                return active
            LOG.warning("這次 F2 已略過。請切回原本的 Chrome 遊戲分頁再按 F2。")

    def game_window(self):
        window = self.user.GetForegroundWindow()
        title = ctypes.create_unicode_buffer(512)
        self.user.GetWindowTextW(window, title, len(title))
        if "bejeweled blitz" not in title.value.lower() or "chrome" not in title.value.lower():
            return None
        return window

    def window_region(self, window, desktop):
        bounds = wintypes.RECT()
        if not self.user.GetWindowRect(window, ctypes.byref(bounds)):
            raise ctypes.WinError(ctypes.get_last_error())
        left = max(bounds.left, desktop["left"])
        top = max(bounds.top, desktop["top"])
        right = min(bounds.right, desktop["left"] + desktop["width"])
        bottom = min(bounds.bottom, desktop["top"] + desktop["height"])
        if right <= left or bottom <= top:
            raise ValueError("Chrome 遊戲視窗在螢幕範圍外。")
        return dict(left=left, top=top, width=right - left, height=bottom - top)

    def move_cursor(self, point):
        if not self.user.SetCursorPos(*point):
            raise ctypes.WinError(ctypes.get_last_error())

    def swap(self, window, source, target):
        self.check()
        if self.game_window() != window:
            return False
        self.move_cursor(source)
        self.check()
        if self.game_window() != window:
            return False
        sx, sy = source
        tx, ty = target
        self.user.mouse_event(0x0002, 0, 0, 0, 0)
        try:
            for step in range(1, 6):
                self.check()
                x = round(sx + (tx - sx) * step / 5)
                y = round(sy + (ty - sy) * step / 5)
                self.move_cursor((x, y))
                time.sleep(0.008)
        finally:
            self.user.mouse_event(0x0004, 0, 0, 0, 0)
        return True


def cell_center(region, rect, cell):
    left, top, width, height = rect
    row, col = cell
    x = region["left"] + left + round((col + 0.5) * width / SIZE)
    y = region["top"] + top + round((row + 0.5) * height / SIZE)
    return x, y


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=0.05)
    parser.add_argument("--debug", action="store_true")
    args, _ = parser.parse_known_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
    )

    win = Windows()
    LOG.info("程式已啟動！切到 Chrome 遊戲分頁並開始遊戲後按 [F2] 開始，按 [F8] 結束。")

    try:
        with mss.mss() as sct:
            desktop, *_ = sct.monitors
            while True:
                window = win.wait_in_game()
                LOG.info("偵測到遊戲視窗，正在定位棋盤...")
                region = win.window_region(window, desktop)
                board_rect = None

                while board_rect is None:
                    win.check()
                    if win.game_window() != window:
                        break
                    raw = np.array(sct.grab(region))[:, :, :3]
                    board_rect = find_board(raw)
                    time.sleep(0.05)

                if board_rect is None:
                    continue

                bx, by, bw, bh = board_rect
                LOG.info("成功定位棋盤，開始自動配對！")
                board_region = dict(
                    left=region["left"] + bx,
                    top=region["top"] + by,
                    width=bw,
                    height=bh,
                )

                empty_frames = 0
                while True:
                    win.check()
                    if win.game_window() != window:
                        LOG.info("遊戲視窗已離開前景，暫停操作。若要繼續請切回視窗並按 F2。")
                        break

                    board_img = np.array(sct.grab(board_region))[:, :, :3]
                    move = best_move(read_board(board_img))

                    if move is None:
                        empty_frames += 1
                        if empty_frames > 60:
                            LOG.info("回合可能已結束，等待下一次按 F2。")
                            break
                        time.sleep(0.03)
                        continue

                    empty_frames = 0
                    src_cell, dst_cell = move
                    src_pt = cell_center(region, board_rect, src_cell)
                    dst_pt = cell_center(region, board_rect, dst_cell)
                    if win.swap(window, src_pt, dst_pt):
                        time.sleep(args.delay)

    except KeyboardInterrupt:
        LOG.info("偵測到 F8 或手動中斷，程式已結束。")


if __name__ == "__main__":
    main()

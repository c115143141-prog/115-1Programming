"""
顏色辨識方法比較 / 測試工具

同一個「判斷規則」，改用 5 種不同的取樣方式估算顏色，看哪一種最穩：

  1. median    取整塊的中位數（目前 寶石炸彈.py 用的方法）
  2. mean      取整塊的平均值
  3. dominant  只用飽和度夠的像素，取色相直方圖的眾數
  4. bright    只取最亮的 30% 像素（避開陰影與寶石邊緣）
  5. kmeans    用 K-means 分 3 群，取最大群的中心

使用方式
  python color_methods.py           用合成測試圖（含雜訊、亮度、模糊等變化）比較準確率
  python color_methods.py live      直接抓目前棋盤，印出 5 種方法的辨識結果
"""

import sys

import cv2
import numpy as np

MIN_VALUE = 55
MIN_SAT = 45
YELLOW_G_RATIO = 0.75

N = 8
LEFT, TOP, RIGHT, BOTTOM = 501, 376, 814, 691
WIDTH, HEIGHT = RIGHT - LEFT, BOTTOM - TOP
CW, CH = WIDTH / N, HEIGHT / N
SAMPLE_RADIUS = 4

BASE_COLORS = {
    "red": (255, 0, 0),
    "orange": (255, 154, 0),
    "yellow": (255, 228, 0),
    "green": (0, 200, 0),
    "blue": (0, 0, 255),
    "purple": (200, 0, 200),
    "white": (255, 255, 255),
    "empty": (18, 18, 18),
}


# =========================
# 共用的判斷規則（與 寶石炸彈.py 相同）
# =========================
def classify(h, s, v, r, g):
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


# =========================
# 五種取樣方式：回傳 (h, s, v, r, g)
# =========================
def est_median(patch):
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    h, s, v = np.median(hsv.reshape(-1, 3), axis=0)
    b, g, r = np.median(patch.reshape(-1, 3), axis=0)
    return h, s, v, r, g


def est_mean(patch):
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    h, s, v = np.mean(hsv.reshape(-1, 3), axis=0)
    b, g, r = np.mean(patch.reshape(-1, 3), axis=0)
    return h, s, v, r, g


def est_dominant(patch):
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    bgr = patch.reshape(-1, 3)

    mask = (hsv[:, 1] >= 60) & (hsv[:, 2] >= 60)
    if mask.sum() < 10:
        return est_median(patch)

    hue = hsv[mask, 0]
    hist = np.bincount(hue // 2, minlength=90)
    h = int(np.argmax(hist)) * 2 + 1
    s = float(np.median(hsv[mask, 1]))
    v = float(np.median(hsv[mask, 2]))
    b, g, r = np.median(bgr[mask], axis=0)
    return h, s, v, r, g


def est_bright(patch):
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    bgr = patch.reshape(-1, 3)

    k = max(1, int(len(hsv) * 0.3))
    idx = np.argsort(hsv[:, 2])[-k:]
    h, s, v = np.median(hsv[idx], axis=0)
    b, g, r = np.median(bgr[idx], axis=0)
    return h, s, v, r, g


def est_kmeans(patch):
    data = patch.reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(
        data, 3, None, criteria, 5, cv2.KMEANS_PP_CENTERS)

    biggest = int(np.argmax(np.bincount(labels.ravel(), minlength=3)))
    pixel = centers[biggest].reshape(1, 1, 3).astype(np.uint8)
    h, s, v = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0, 0]
    b, g, r = pixel[0, 0]
    return int(h), int(s), int(v), int(r), int(g)


METHODS = {
    "median": est_median,
    "mean": est_mean,
    "dominant": est_dominant,
    "bright": est_bright,
    "kmeans": est_kmeans,
}


def identify(patch, method="median"):
    h, s, v, r, g = METHODS[method](patch)
    return classify(h, s, v, r, g)


# =========================
# 合成測試圖片
# =========================
def make_variants(rgb, rng):
    bgr = np.array(rgb[::-1], dtype=np.uint8)
    base = np.full((9, 9, 3), bgr, dtype=np.uint8)

    noise = np.clip(
        base.astype(np.int16) + rng.normal(0, 8, base.shape), 0, 255
    ).astype(np.uint8)

    dim = np.clip(base.astype(np.float32) * 0.7, 0, 255).astype(np.uint8)
    bright = np.clip(base.astype(np.float32) * 1.2, 0, 255).astype(np.uint8)

    blur = cv2.GaussianBlur(base, (3, 3), 0)

    shine = base.copy()
    cv2.circle(shine, (3, 3), 3, (255, 255, 255), -1)
    shine = cv2.GaussianBlur(shine, (3, 3), 0)

    return [
        ("clean", base),
        ("noise", noise),
        ("dark", dim),
        ("bright", bright),
        ("blur", blur),
        ("shine", shine),
    ]


def compare():
    rng = np.random.default_rng(7)
    variants = []
    for name, rgb in BASE_COLORS.items():
        for vname, patch in make_variants(rgb, rng):
            variants.append((name, vname, patch))

    print(f"測試樣本：{len(BASE_COLORS)} 色 x "
          f"{len(variants) // len(BASE_COLORS)} 種變化 = {len(variants)} 張\n")

    header = f"{'方法':10s}" + "".join(f"{v:>9s}" for v in
                                       ["clean", "noise", "dark",
                                        "bright", "blur", "shine"])
    print(header)
    print("-" * len(header))

    scores = {}
    for method in METHODS:
        per_variant = {}
        for name, vname, patch in variants:
            ok = identify(patch, method) == name
            per_variant.setdefault(vname, [0, 0])
            per_variant[vname][0] += ok
            per_variant[vname][1] += 1

        row = f"{method:10s}"
        correct = total = 0
        for vname, _ in per_variant.items():
            good, all_ = per_variant[vname]
            correct += good
            total += all_
            row += f"{good:>4d}/{all_:<4d}"
        scores[method] = correct / total
        print(row + f"  總計 {correct}/{total} = {correct / total:.0%}")

    best = max(scores, key=scores.get)
    print(f"\n最穩的方法：{best}（{scores[best]:.0%}）")

    print(f"\n{best} 的錯誤明細：")
    wrong = 0
    for name, vname, patch in variants:
        got = identify(patch, best)
        if got != name:
            wrong += 1
            h, s, v, r, g = METHODS[best](patch)
            print(f"  應為 {name:7s} 判成 {got:7s} ({vname:6s}) "
                  f"h={h:5.1f} s={s:5.1f} v={v:5.1f} g/r={g / max(r, 1):.2f}")
    if not wrong:
        print("  （沒有錯誤）")


# =========================
# 直接抓目前畫面比較
# =========================
def live():
    from PIL import ImageGrab

    img = ImageGrab.grab(bbox=(LEFT, TOP, RIGHT, BOTTOM), all_screens=True)
    img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    print(f"棋盤範圍：x {LEFT}~{RIGHT}, y {TOP}~{BOTTOM}")
    print("每個方法對 64 格的辨識結果（同一格若不同方法給不同答案，就是有不確定）：\n")

    stats = {method: {} for method in METHODS}
    disagree = 0

    for r in range(N):
        line = []
        for c in range(N):
            x = int((c + .5) * CW)
            y = int((r + .5) * CH)
            patch = img[y - SAMPLE_RADIUS:y + SAMPLE_RADIUS + 1,
                        x - SAMPLE_RADIUS:x + SAMPLE_RADIUS + 1]

            answers = {m: identify(patch, m) for m in METHODS}
            for m, a in answers.items():
                stats[m][a] = stats[m].get(a, 0) + 1

            uniq = set(answers.values())
            if len(uniq) > 1:
                disagree += 1
                line.append(f"{r},{c}: " + "/".join(
                    f"{m[0]}{a[0]}" for m, a in answers.items()))
        if line:
            print("  " + "  ".join(line))

    print(f"\n有 {disagree} / {N * N} 格方法之間不一致")
    for m in METHODS:
        print(f"  {m:9s}: " + "、".join(
            f"{k} x{v}" for k, v in sorted(stats[m].items())))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "live":
        live()
    else:
        compare()

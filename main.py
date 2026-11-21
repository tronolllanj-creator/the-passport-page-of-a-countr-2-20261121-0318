import os
import struct
import sys
import zlib

W, H = 1024, 1024

# palette
DESK = (26, 32, 48)
SHADOW = (12, 16, 26)
COVER = (20, 33, 61)
PAPER = (244, 237, 218)
PAPER2 = (250, 245, 230)
INK = (22, 35, 63)
NAVY = (31, 58, 95)
RED = (166, 43, 43)
BLUE = (31, 78, 121)
TEAL = (20, 101, 94)
PURPLE = (110, 60, 110)
GOLD = (176, 138, 46)
GREY = (107, 107, 107)
LGREY = (210, 205, 190)
SKIN = (217, 180, 143)
HAIR = (43, 32, 24)
JACKET = (38, 54, 84)
SHIRT = (245, 245, 240)
PHOTOBG = (199, 210, 222)


class FB:
    """RGB framebuffer with an alpha channel (alpha 0 = transparent)."""

    def __init__(self, w, h, fill=(0, 0, 0), alpha=255):
        self.w = w
        self.h = h
        self.px = bytearray(fill[0] for _ in range(w * h * 3))
        # build row by row so fill is exact
        row = bytes(fill) * w
        self.px = bytearray(row * h)
        self.al = bytearray([alpha]) * (w * h)

    def set(self, x, y, c, a=255):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i] = c[0]
            self.px[i + 1] = c[1]
            self.px[i + 2] = c[2]
            self.al[y * self.w + x] = a

    def hline(self, x0, x1, y, c, a=255):
        if y < 0 or y >= self.h:
            return
        x0 = max(0, x0)
        x1 = min(self.w - 1, x1)
        if x1 < x0:
            return
        n = x1 - x0 + 1
        i = (y * self.w + x0) * 3
        self.px[i:i + n * 3] = bytes(c) * n
        j = y * self.w + x0
        self.al[j:j + n] = bytes([a]) * n

    def vline(self, x, y0, y1, c, a=255):
        if x < 0 or x >= self.w:
            return
        y0 = max(0, y0)
        y1 = min(self.h - 1, y1)
        for y in range(y0, y1 + 1):
            i = (y * self.w + x) * 3
            self.px[i] = c[0]
            self.px[i + 1] = c[1]
            self.px[i + 2] = c[2]
            self.al[y * self.w + x] = a

    def rect(self, x0, y0, x1, y1, c, a=255):
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(self.w - 1, x1)
        y1 = min(self.h - 1, y1)
        for y in range(y0, y1 + 1):
            self.hline(x0, x1, y, c, a)

    def line(self, x0, y0, x1, y1, c, w=1, a=255):
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        x, y = x0, y0
        r = w // 2
        while True:
            for oy in range(-r, r + 1):
                self.hline(x - r, x + r, y + oy, c, a)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    def circle(self, cx, cy, r, c, a=255):
        for y in range(cy - r, cy + r + 1):
            dy = y - cy
            dd = r * r - dy * dy
            if dd < 0:
                continue
            dx = int(dd ** 0.5)
            self.hline(cx - dx, cx + dx, y, c, a)

    def circle_outline(self, cx, cy, r, c, w=1, a=255):
        import math
        steps = max(24, int(2 * 3.14159 * r))
        for i in range(steps + 1):
            t = 2 * 3.14159 * i / steps
            x = int(cx + r * math.cos(t))
            y = int(cy + r * math.sin(t))
            self.circle(x, y, max(1, w // 2), c, a)

    def ellipse(self, cx, cy, rx, ry, c, a=255):
        for y in range(cy - ry, cy + ry + 1):
            dy = (y - cy) / float(ry)
            dd = 1.0 - dy * dy
            if dd < 0:
                continue
            dx = int(rx * (dd ** 0.5))
            self.hline(cx - dx, cx + dx, y, c, a)

    def polygon(self, pts, c, a=255):
        # scanline fill, even-odd, edges use [y0, y1)
        ys = [p[1] for p in pts]
        y0, y1 = min(ys), max(ys)
        n = len(pts)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x0, ya = pts[i]
                x1, yb = pts[(i + 1) % n]
                if ya == yb:
                    continue
                if (ya <= y < yb) or (yb <= y < ya):
                    t = (y - ya) / float(yb - ya)
                    xs.append(x0 + t * (x1 - x0))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                self.hline(int(xs[k]), int(xs[k + 1]), y, c, a)

    def arc(self, cx, cy, r, a0, a1, c, w=1, a=255):
        import math
        steps = max(8, int(abs(a1 - a0) / 360.0 * 2 * 3.14159 * r))
        for i in range(steps + 1):
            t = math.radians(a0 + (a1 - a0) * i / steps)
            x = int(cx + r * math.cos(t))
            y = int(cy + r * math.sin(t))
            self.circle(x, y, max(1, w // 2), c, a)


def save_png(fb, path):
    raw = bytearray()
    for y in range(fb.h):
        raw.append(0)
        i = y * fb.w * 3
        raw += fb.px[i:i + fb.w * 3]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(typ, data):
        out = struct.pack(">I", len(data)) + typ + data
        out += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        return out

    ihdr = struct.pack(">IIBBBBB", fb.w, fb.h, 8, 2, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n"
    data += chunk(b"IHDR", ihdr)
    data += chunk(b"IDAT", comp)
    data += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def rotate_blit(dst, src, cx, cy, angle_deg, alpha_scale=0.85):
    """Paste src FB centred at (cx, cy) on dst, rotated by angle_deg."""
    import math
    ang = math.radians(-angle_deg)
    ca, sa = math.cos(ang), math.sin(ang)
    hw, hh = src.w / 2.0, src.h / 2.0
    r = int((abs(src.w * ca) + abs(src.h * sa)) / 2) + 2
    r2 = int((abs(src.w * sa) + abs(src.h * ca)) / 2) + 2
    for dy in range(-r2, r2 + 1):
        for dx in range(-r, r + 1):
            sx = int(dx * ca - dy * sa + hw)
            sy = int(dx * sa + dy * ca + hh)
            if 0 <= sx < src.w and 0 <= sy < src.h:
                sa_v = src.al[sy * src.w + sx]
                if sa_v == 0:
                    continue
                a = sa_v / 255.0 * alpha_scale
                x, y = cx + dx, cy + dy
                if 0 <= x < dst.w and 0 <= y < dst.h:
                    i = (y * dst.w + x) * 3
                    j = (sy * src.w + sx) * 3
                    dst.px[i] = int(src.px[j] * a + dst.px[i] * (1 - a))
                    dst.px[i + 1] = int(src.px[j + 1] * a + dst.px[i + 1] * (1 - a))
                    dst.px[i + 2] = int(src.px[j + 2] * a + dst.px[i + 2] * (1 - a))


# Vector stroke font: glyphs as polylines on a 7-wide x 9-tall grid.
# y=0 top, y=7 baseline, y=8 descender. Rendered at any size with a stroke width.
GLYPHS = {
    "A": [[(0, 7), (3, 0), (6, 7)], [(2, 4), (4, 4)]],
    "B": [[(0, 0), (0, 7)], [(0, 0), (4, 0), (5, 1), (5, 2), (4, 3), (0, 3)],
          [(0, 3), (4, 3), (5, 4), (5, 6), (4, 7), (0, 7)]],
    "C": [[(5, 1), (4, 0), (2, 0), (1, 1), (0, 3), (0, 4), (1, 6), (2, 7), (4, 7), (5, 6)]],
    "D": [[(0, 0), (0, 7)], [(0, 0), (4, 0), (6, 2), (6, 5), (4, 7), (0, 7)]],
    "E": [[(0, 0), (0, 7)], [(0, 0), (5, 0)], [(0, 3), (4, 3)], [(0, 7), (5, 7)]],
    "F": [[(0, 0), (0, 7)], [(0, 0), (5, 0)], [(0, 3), (4, 3)]],
    "G": [[(5, 1), (4, 0), (2, 0), (1, 1), (0, 3), (0, 4), (1, 6), (2, 7),
           (4, 7), (5, 6), (5, 4), (3, 4)]],
    "H": [[(0, 0), (0, 7)], [(6, 0), (6, 7)], [(0, 3), (6, 3)]],
    "I": [[(3, 0), (3, 7)], [(1, 0), (5, 0)], [(1, 7), (5, 7)]],
    "J": [[(2, 0), (5, 0), (5, 6), (4, 7), (2, 7), (1, 6)]],
    "K": [[(0, 0), (0, 7)], [(6, 0), (0, 3)], [(2, 4), (6, 7)]],
    "L": [[(0, 0), (0, 7)], [(0, 7), (5, 7)]],
    "M": [[(0, 7), (0, 0), (3, 4), (6, 0), (6, 7)]],
    "N": [[(0, 7), (0, 0), (6, 7), (6, 0)]],
    "O": [[(2, 0), (4, 0), (6, 2), (6, 5), (4, 7), (2, 7), (0, 5), (0, 2), (2, 0)]],
    "P": [[(0, 0), (0, 7)], [(0, 0), (4, 0), (6, 1), (6, 3), (4, 4), (0, 4)]],
    "Q": [[(2, 0), (4, 0), (6, 2), (6, 5), (4, 7), (2, 7), (0, 5), (0, 2), (2, 0)],
          [(4, 5), (6, 7)]],
    "R": [[(0, 0), (0, 7)], [(0, 0), (4, 0), (6, 1), (6, 3), (4, 4), (0, 4)],
          [(3, 4), (6, 7)]],
    "S": [[(5, 1), (4, 0), (2, 0), (1, 1), (0, 2), (0, 3), (1, 4), (3, 4),
           (5, 4), (6, 5), (6, 6), (5, 7), (3, 7), (1, 6)]],
    "T": [[(0, 0), (6, 0)], [(3, 0), (3, 7)]],
    "U": [[(0, 0), (0, 5), (1, 7), (5, 7), (6, 5), (6, 0)]],
    "V": [[(0, 0), (3, 7), (6, 0)]],
    "W": [[(0, 0), (1, 7), (3, 3), (5, 7), (6, 0)]],
    "X": [[(0, 0), (6, 7)], [(6, 0), (0, 7)]],
    "Y": [[(0, 0), (3, 3), (6, 0)], [(3, 3), (3, 7)]],
    "Z": [[(0, 0), (6, 0), (0, 7), (6, 7)]],
    "0": [[(2, 0), (4, 0), (6, 2), (6, 5), (4, 7), (2, 7), (0, 5), (0, 2), (2, 0)]],
    "1": [[(2, 0), (3, 0), (3, 7)], [(1, 7), (5, 7)]],
    "2": [[(1, 1), (2, 0), (4, 0), (5, 1), (5, 2), (4, 4), (0, 7), (6, 7)]],
    "3": [[(1, 1), (2, 0), (4, 0), (5, 1), (5, 2), (3, 3), (5, 4), (5, 6),
           (4, 7), (2, 7), (1, 6)]],
    "4": [[(4, 0), (4, 7)], [(0, 4), (6, 4)], [(4, 0), (0, 4)]],
    "5": [[(5, 0), (0, 0), (0, 3), (4, 3), (5, 4), (5, 6), (4, 7), (2, 7), (1, 6)]],
    "6": [[(5, 1), (4, 0), (2, 0), (1, 1), (0, 3), (0, 5), (1, 7), (3, 7),
           (5, 6), (5, 4), (4, 3), (2, 3), (0, 4)]],
    "7": [[(0, 0), (6, 0), (3, 7)]],
    "8": [[(2, 0), (4, 0), (6, 2), (6, 3), (4, 4), (2, 4), (0, 3), (0, 2), (2, 0)],
          [(4, 4), (6, 5), (6, 6), (4, 7), (2, 7), (0, 6), (0, 5), (2, 4)]],
    "9": [[(1, 6), (2, 7), (4, 7), (5, 6), (6, 4), (6, 2), (5, 0), (3, 0),
           (1, 1), (1, 3), (2, 4), (4, 4), (6, 3)]],
    " ": [],
    ".": [[(3, 7), (3, 7)]],
    ",": [[(3, 6), (2, 8)]],
    ":": [[(3, 2), (3, 2)], [(3, 6), (3, 6)]],
    ";": [[(3, 2), (3, 2)], [(3, 6), (2, 8)]],
    "-": [[(1, 4), (5, 4)]],
    "/": [[(5, 7), (1, 0)]],
    "(": [[(4, 0), (2, 2), (2, 5), (4, 7)]],
    ")": [[(2, 0), (4, 2), (4, 5), (2, 7)]],
    "<": [[(5, 1), (1, 4), (5, 7)]],
    ">": [[(1, 1), (5, 4), (1, 7)]],
    "'": [[(3, 0), (3, 2)]],
    "+": [[(1, 4), (5, 4)], [(3, 2), (3, 6)]],
    "=": [[(1, 2), (5, 2)], [(1, 5), (5, 5)]],
    "!": [[(3, 0), (3, 5)], [(3, 7), (3, 7)]],
}


def text_w(s, size, tracking=1):
    sc = size / 9.0
    return int(len(s) * (7 * sc + tracking))


def draw_text(fb, x, y, s, size, color, bold=False, tracking=1, alpha=255):
    """Draw string with top-left at (x, y); size is the 9-grid height in px."""
    sc = size / 9.0
    wdt = max(1, int(round(size / 11.0)))
    if bold:
        wdt += 1
    cx = x
    for ch in s:
        strokes = GLYPHS.get(ch.upper(), GLYPHS.get(ch))
        if strokes is None:
            strokes = []
        for stroke in strokes:
            pts = [(int(cx + px * sc), int(y + py * sc)) for (px, py) in stroke]
            for i in range(len(pts) - 1):
                fb.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1],
                        color, wdt, alpha)
            if len(pts) == 1:
                fb.circle(pts[0][0], pts[0][1], max(1, wdt // 2), color, alpha)
        cx += int(7 * sc + tracking)
    return cx - x


def draw_text_c(fb, cx, y, s, size, color, bold=False, tracking=1, alpha=255):
    w = text_w(s, size, tracking)
    return draw_text(fb, cx - w // 2, y, s, size, color, bold, tracking, alpha)


def draw_text_r(fb, x1, y, s, size, color, bold=False, tracking=1, alpha=255):
    w = text_w(s, size, tracking)
    return draw_text(fb, x1 - w, y, s, size, color, bold, tracking, alpha)


def wrap_text(fb, s, size, max_w, tracking=1):
    words = s.split(" ")
    lines = []
    cur = ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if text_w(trial, size, tracking) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def draw_wrapped(fb, x, y, lines, size, color, leading=None, bold=False, alpha=255):
    if leading is None:
        leading = int(size * 1.35)
    for ln in lines:
        draw_text(fb, x, y, ln, size, color, bold, 1, alpha)
        y += leading
    return y


def guilloche(fb, x0, y0, x1, y1, color, step=14):
    """Fine concentric arcs in a corner, like a security print."""
    cx, cy = x0, y0
    r = step
    while r < min(x1 - x0, y1 - y0):
        fb.arc(cx, cy, r, 0, 90, color, 1)
        r += step


def star(fb, cx, cy, r, color, a=255):
    import math
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((int(cx + rr * math.cos(ang)), int(cy + rr * math.sin(ang))))
    fb.polygon(pts, color, a)


def coat_of_arms(fb, cx, cy, s):
    """Small shield: navy field, gold border, star over mountains and waves."""
    fb.polygon([(cx - s, cy - s), (cx + s, cy - s), (cx + s, cy + s // 4),
                (cx, cy + s), (cx - s, cy + s // 4)], NAVY)
    fb.line(cx - s, cy - s, cx + s, cy - s, GOLD, 2)
    fb.line(cx + s, cy - s, cx + s, cy + s // 4, GOLD, 2)
    fb.line(cx + s, cy + s // 4, cx, cy + s, GOLD, 2)
    fb.line(cx, cy + s, cx - s, cy + s // 4, GOLD, 2)
    fb.line(cx - s, cy + s // 4, cx - s, cy - s, GOLD, 2)
    star(fb, cx, cy - s // 3, s // 3, GOLD)
    fb.polygon([(cx - s + 6, cy + s // 4), (cx - s // 3, cy - s // 6),
                (cx, cy + s // 4)], (90, 120, 160))
    fb.polygon([(cx - s // 3, cy + s // 4), (cx + s // 6, cy - s // 8),
                (cx + s - 6, cy + s // 4)], (140, 170, 200))
    fb.arc(cx, cy + s // 2, s // 2, 200, 340, GOLD, 1)


def draw_portrait(fb, x0, y0, x1, y1):
    """Flat-illustration ID photo: guilloche bg, head, hair, jacket, collar."""
    fb.rect(x0, y0, x1, y1, PHOTOBG)
    guilloche(fb, x0, y0, x1, y1, (170, 185, 200), step=16)
    cx = (x0 + x1) // 2
    # shoulders / jacket
    fb.polygon([(x0 + 8, y1), (x0 + 26, y1 - 52), (cx - 12, y1 - 62),
                (cx + 12, y1 - 62), (x1 - 26, y1 - 52), (x1 - 8, y1)], JACKET)
    # shirt + collar
    fb.polygon([(cx - 12, y1 - 62), (cx, y1 - 38), (cx + 12, y1 - 62)], SHIRT)
    fb.line(cx - 12, y1 - 62, cx - 2, y1 - 46, (200, 200, 195), 1)
    fb.line(cx + 12, y1 - 62, cx + 2, y1 - 46, (200, 200, 195), 1)
    # neck
    fb.rect(cx - 10, y1 - 78, cx + 10, y1 - 58, SKIN)
    # head
    fb.ellipse(cx, y1 - 112, 30, 38, SKIN)
    # hair cap
    fb.ellipse(cx, y1 - 136, 32, 24, HAIR)
    fb.polygon([(cx - 32, y1 - 136), (cx - 28, y1 - 108), (cx - 22, y1 - 128)],
               HAIR)
    fb.polygon([(cx + 32, y1 - 136), (cx + 28, y1 - 108), (cx + 22, y1 - 128)],
               HAIR)
    # brows, eyes, nose, mouth (minimal, symmetric)
    fb.line(cx - 16, y1 - 118, cx - 6, y1 - 118, HAIR, 2)
    fb.line(cx + 6, y1 - 118, cx + 16, y1 - 118, HAIR, 2)
    fb.line(cx - 15, y1 - 112, cx - 7, y1 - 112, (40, 30, 25), 2)
    fb.line(cx + 7, y1 - 112, cx + 15, y1 - 112, (40, 30, 25), 2)
    fb.line(cx, y1 - 110, cx, y1 - 100, (190, 150, 115), 1)
    fb.line(cx - 8, y1 - 90, cx + 8, y1 - 90, (150, 90, 80), 2)
    # frame
    fb.line(x0, y0, x1, y0, NAVY, 2)
    fb.line(x0, y1, x1, y1, NAVY, 2)
    fb.line(x0, y0, x0, y1, NAVY, 2)
    fb.line(x1, y0, x1, y1, NAVY, 2)


def mrz_check(s):
    total = 0
    for i, ch in enumerate(s):
        if ch.isdigit():
            v = int(ch)
        elif ch.isalpha():
            v = ord(ch.upper()) - 55
        else:
            v = 0
        total += v * (7, 3, 1)[i % 3]
    return str(total % 10)


def mrz_lines():
    line1 = "P<ZVA" + ("NOVAK<<ELENA<MARA" + "<" * 22)
    doc = "ZV4829137"
    c1 = mrz_check(doc)
    nat = "ZVA"
    dob = "980314"
    c2 = mrz_check(dob)
    sex = "F"
    exp = "360601"
    c3 = mrz_check(exp)
    pers = "<" * 14
    c4 = mrz_check(pers)
    core = doc + c1 + nat + dob + c2 + sex + exp + c3 + pers + c4
    c5 = mrz_check(core)
    line2 = core + c5
    return line1, line2


def stamp_rect_layer(w, h, color, lines, sizes):
    """A rectangular rubber stamp on a transparent layer."""
    fb = FB(w, h, fill=(0, 0, 0), alpha=0)
    fb.rect(4, 4, w - 5, h - 5, color, a=0)
    for inset, wd in ((4, 2), (10, 1)):
        fb.line(inset, inset, w - 1 - inset, inset, color, wd)
        fb.line(inset, h - 1 - inset, w - 1 - inset, h - 1 - inset, color, wd)
        fb.line(inset, inset, inset, h - 1 - inset, color, wd)
        fb.line(w - 1 - inset, inset, w - 1 - inset, h - 1 - inset, color, wd)
    y = (h - sum(int(sz * 1.5) for sz in sizes)) // 2 + 2
    for txt, sz in zip(lines, sizes):
        draw_text_c(fb, w // 2, y, txt, sz, color, bold=True)
        y += int(sz * 1.5)
    return fb


def stamp_circle_layer(d, color, lines, sizes):
    """A circular rubber stamp on a transparent layer."""
    fb = FB(d, d, fill=(0, 0, 0), alpha=0)
    c = d // 2
    fb.circle_outline(c, c, c - 5, color, 3)
    fb.circle_outline(c, c, c - 14, color, 1)
    y = c - sum(int(sz * 1.5) for sz in sizes) // 2
    for txt, sz in zip(lines, sizes):
        draw_text_c(fb, c, y, txt, sz, color, bold=True)
        y += int(sz * 1.5)
    return fb


def draw_data_page(fb):
    x0, y0, x1, y1 = 12, 12, 506, 1012
    fb.rect(x0, y0, x1, y1, PAPER)
    fb.line(x0 + 8, y0 + 8, x1 - 8, y0 + 8, GOLD, 1)
    fb.line(x0 + 8, y1 - 8, x1 - 8, y1 - 8, GOLD, 1)
    fb.line(x0 + 8, y0 + 8, x0 + 8, y1 - 8, GOLD, 1)
    fb.line(x1 - 8, y0 + 8, x1 - 8, y1 - 8, GOLD, 1)
    # document number, top right
    draw_text_r(fb, x1 - 26, 34, "No. ZV 482 9137", 13, NAVY, bold=True)
    # header
    coat_of_arms(fb, 259, 84, 32)
    draw_text_c(fb, 259, 128, "REPUBLIC OF ZALVARIA", 28, INK, bold=True)
    draw_text_c(fb, 259, 162, "REPUBLIKA ZALVARSKA", 12, NAVY)
    draw_text_c(fb, 259, 182, "PASSPORT", 22, INK, bold=True)
    draw_text_c(fb, 259, 208, "PASPORT", 11, GREY)
    fb.line(40, 228, 478, 228, NAVY, 2)
    fb.line(40, 232, 478, 232, GOLD, 1)
    # portrait
    draw_portrait(fb, 36, 246, 196, 426)
    # gold seal overlapping the photo corner
    fb.circle_outline(188, 414, 20, GOLD, 2)
    fb.circle_outline(188, 414, 15, GOLD, 1)
    star(fb, 188, 414, 8, GOLD)
    # fields, right of the photo
    fx = 216
    rows = [
        ("SURNAME", "NOVAK"),
        ("GIVEN NAMES", "ELENA MARA"),
        ("NATIONALITY", "ZALVARIAN"),
        ("DATE OF BIRTH", "14 MAR 1998"),
        ("PLACE OF BIRTH", "VEYMAR"),
        ("SEX", "F"),
        ("DATE OF ISSUE", "02 JUN 2026"),
        ("DATE OF EXPIRY", "01 JUN 2036"),
    ]
    y = 248
    for label, value in rows:
        draw_text(fb, fx, y, label, 10, GREY)
        draw_text(fb, fx, y + 13, value, 17, NAVY, bold=True)
        y += 44
    # height / eyes under the photo
    draw_text(fb, 36, 444, "HEIGHT", 10, GREY)
    draw_text(fb, 36, 457, "172 CM", 15, NAVY, bold=True)
    draw_text(fb, 120, 444, "EYES", 10, GREY)
    draw_text(fb, 120, 457, "BROWN", 15, NAVY, bold=True)
    # authority
    draw_text(fb, 36, 600, "AUTHORITY", 10, GREY)
    draw_text(fb, 36, 613, "MINISTRY OF THE INTERIOR - VEYMAR", 14, NAVY, bold=True)
    draw_text(fb, 36, 636, "PLACE OF ISSUE  VEYMAR", 12, NAVY)
    # signature
    fb.line(36, 690, 300, 690, INK, 1)
    fb.line(40, 682, 80, 670, INK, 2)
    fb.line(80, 670, 120, 684, INK, 2)
    fb.line(120, 684, 160, 668, INK, 2)
    fb.line(160, 668, 200, 682, INK, 2)
    fb.line(200, 682, 240, 672, INK, 2)
    fb.line(240, 672, 280, 684, INK, 2)
    draw_text(fb, 36, 698, "SIGNATURE OF BEARER", 10, GREY)
    # endorsement: the telling paperwork detail on the data page
    fb.line(36, 730, 478, 730, LGREY, 1)
    draw_text(fb, 36, 742, "ENDORSEMENT", 10, RED, bold=True)
    lines = wrap_text(fb, "NOT VALID FOR TRAVEL TO THE NORTHERN "
                      "MARCHES WITHOUT A SEPARATE PERMIT.", 13, 442)
    draw_wrapped(fb, 36, 758, lines, 13, RED, bold=True)
    # MRZ strip
    fb.rect(26, 856, 492, 962, PAPER2)
    fb.line(26, 856, 492, 856, NAVY, 1)
    fb.line(26, 962, 492, 962, NAVY, 1)
    fb.line(26, 856, 26, 962, NAVY, 1)
    fb.line(492, 856, 492, 962, NAVY, 1)
    l1, l2 = mrz_lines()
    draw_text(fb, 40, 884, l1, 13, INK, tracking=0)
    draw_text(fb, 40, 912, l2, 13, INK, tracking=0)
    draw_text_c(fb, 259, 984, "ZALVARIA  -  PAGE 1", 10, GREY)


def draw_visa_page(fb):
    x0, y0, x1, y1 = 518, 12, 1012, 1012
    fb.rect(x0, y0, x1, y1, PAPER)
    fb.line(x0 + 8, y0 + 8, x1 - 8, y0 + 8, GOLD, 1)
    fb.line(x0 + 8, y1 - 8, x1 - 8, y1 - 8, GOLD, 1)
    fb.line(x0 + 8, y0 + 8, x0 + 8, y1 - 8, GOLD, 1)
    fb.line(x1 - 8, y0 + 8, x1 - 8, y1 - 8, GOLD, 1)
    # header
    draw_text(fb, 542, 34, "VISAS", 22, INK, bold=True)
    draw_text_r(fb, 988, 40, "16", 16, NAVY, bold=True)
    fb.line(542, 66, 988, 66, NAVY, 2)
    # visa sticker: Ostara visitor visa
    vx0, vy0, vx1, vy1 = 542, 84, 988, 316
    fb.rect(vx0, vy0, vx1, vy1, (232, 240, 248))
    fb.line(vx0, vy0, vx1, vy0, BLUE, 2)
    fb.line(vx0, vy1, vx1, vy1, BLUE, 2)
    fb.line(vx0, vy0, vx0, vy1, BLUE, 2)
    fb.line(vx1, vy0, vx1, vy1, BLUE, 2)
    fb.line(vx0 + 5, vy0 + 5, vx1 - 5, vy0 + 5, BLUE, 1)
    fb.line(vx0 + 5, vy1 - 5, vx1 - 5, vy1 - 5, BLUE, 1)
    fb.line(vx0 + 5, vy0 + 5, vx0 + 5, vy1 - 5, BLUE, 1)
    fb.line(vx1 - 5, vy0 + 5, vx1 - 5, vy1 - 5, BLUE, 1)
    fb.rect(vx0, vy0, vx1, vy0 + 36, NAVY)
    draw_text(fb, vx0 + 14, vy0 + 9, "VISA", 22, GOLD, bold=True)
    draw_text_r(fb, vx1 - 14, vy0 + 11, "OSTARA", 18, SHIRT, bold=True)
    vy = vy0 + 48
    draw_text(fb, vx0 + 14, vy, "TYPE   VISITOR - MULTIPLE ENTRIES", 13, INK, bold=True)
    vy += 24
    draw_text(fb, vx0 + 14, vy, "VALID   01 SEP 2026 TO 30 NOV 2026", 13, INK)
    vy += 24
    draw_text(fb, vx0 + 14, vy, "ISSUED   VEYMAR, 28 AUG 2026", 13, INK)
    vy += 24
    draw_text(fb, vx0 + 14, vy, "FEE PAID   40 KORUN - OS-7714-209", 13, INK)
    vy += 26
    cond = wrap_text(fb, "CONDITION: HOLDER MUST REGISTER WITH THE "
                     "HARBOURMASTER WITHIN 48 HOURS OF LANDING.", 13, 340)
    draw_wrapped(fb, vx0 + 14, vy, cond, 13, RED, bold=True)
    fb.circle_outline(vx1 - 44, vy1 - 26, 20, GOLD, 2)
    fb.circle_outline(vx1 - 44, vy1 - 26, 15, GOLD, 1)
    star(fb, vx1 - 44, vy1 - 26, 8, GOLD)
    # rubber stamps, each on its own layer, rotated
    s1 = stamp_rect_layer(260, 116, BLUE,
                          ["KARVOST", "ARRIVAL", "14 AUG 2026", "BORDER POST TARN"],
                          [20, 16, 16, 12])
    rotate_blit(fb, s1, 670, 425, -8)
    s2 = stamp_rect_layer(270, 116, RED,
                          ["DRAVENMARCH", "DEPARTURE", "02 OCT 2026"],
                          [20, 16, 16])
    rotate_blit(fb, s2, 870, 555, 6)
    s3 = stamp_circle_layer(160, TEAL,
                            ["OSTARA", "ENTRY", "05 SEP 2026", "PORT AURELIA"],
                            [16, 14, 14, 11])
    rotate_blit(fb, s3, 645, 670, -5)
    s4 = stamp_rect_layer(250, 100, NAVY,
                          ["ZALVARIA", "EXIT", "12 AUG 2026 - VEYMAR"],
                          [18, 16, 12])
    rotate_blit(fb, s4, 860, 795, 4)
    s5 = stamp_rect_layer(260, 100, PURPLE,
                          ["KARVOST", "DEPARTURE", "28 AUG 2026"],
                          [18, 16, 14])
    rotate_blit(fb, s5, 660, 890, -6)
    s6 = stamp_rect_layer(170, 72, RED,
                          ["HARBOUR TAX", "PAID - 12 KORUN"],
                          [14, 12])
    rotate_blit(fb, s6, 920, 382, -12)
    draw_text_c(fb, 765, 984, "PROPERTY OF THE REPUBLIC OF ZALVARIA.", 10, GREY)


def draw_spread():
    fb = FB(W, H, DESK)
    # soft shadow under the open book
    fb.rect(16, 16, 1020, 1020, SHADOW)
    # cover edge peeking out
    fb.rect(6, 6, 1018, 1018, COVER)
    # gutter
    fb.rect(506, 12, 518, 1012, (58, 48, 36))
    fb.line(506, 12, 506, 1012, (30, 24, 18), 2)
    fb.line(518, 12, 518, 1012, (30, 24, 18), 2)
    draw_data_page(fb)
    draw_visa_page(fb)
    return fb


def main():
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(outdir, exist_ok=True)
    fb = draw_spread()
    path = os.path.join(outdir, "entry.png")
    n = save_png(fb, path)
    print("wrote %s %dx%d bytes %d" % (path, W, H, n))


if __name__ == "__main__":
    main()





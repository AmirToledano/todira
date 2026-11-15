"""2026-11-15 (owner: "take the motion of the hind legs from the 8 pink pictures, and use the real legs from the drawing,
not legs you draw; all the legs should move like a real dog's"): builds Todi as a jointed puppet. One SVG, every piece of
it cut from the owner's illustration (static/todi/todi-rig.webp): head, tail and body, and four legs, each in three
pieces (upper leg, lower leg, paw) that turn on their joints. The far legs are the near legs again, darker, behind the
body. The walk is a dog's walk (lateral sequence: left hind, left fore, right hind, right fore, a quarter of a cycle
apart): each paw stays planted while the body passes over it, the heel rises, the toes push off, the hind paw flicks
back and up (the pink pictures), then the leg swings forward and the paw lands flat.
Each joint is a round cut centred on the pivot, the same circle on both pieces, so nothing opens up when a piece turns.
Run: python tools/todi_rig.py <out dir>; it writes rig.svg.html (goes into templates/_todi_dog.html, the non-sheet
branch) and rig.css (goes into static/style.css, before the paw prints block), and prints the walking speed that keeps
the paws from sliding (home.js uses it)."""
import math
import sys
from pathlib import Path

OUT = sys.argv[1]
IMG = "/static/todi/todi-rig.webp?v={{ static_version }}"
T = 0.66          # one full cycle of the four legs, seconds
D = 52            # stride: how far a planted paw travels under the body, drawing units (the image is 640 wide)
STANCE = 0.64     # share of the cycle a paw is on the ground (a walk: about two thirds)
N = 24            # keyframes per cycle
LINE, BROWN = "#3b1a17", "#5e3422"

# joints measured on the drawing (640x330, facing left): P hip/shoulder, K hock/carpus, A ankle (where the paw turns),
# R/rk/ra the joint circles, TOE the front of the paw (the paw rolls on it when the heel rises). Paws stand on their y.
KINDS = {
    "h": {"P": (496, 205), "R": 26, "K": (531, 256), "rk": 13, "A": (530, 284), "ra": 14, "TOE": (514, 303), "side": 1,
          "c": -16, "lift": 18, "kick": 26, "heel": 36, "flex": -80, "reach": 10,
          "upper": [(470, 205), (438, 209), (438.5, 211), (443.5, 222), (449.5, 233), (455.5, 244), (462.5, 251.5),
                    (470, 252.5), (490, 258.5), (510, 260), (517, 261), (518, 256), (546, 256), (546, 244),
             (541, 236), (532, 228), (525, 220), (524.5, 205)],
          "lower": [(516, 256), (516, 272), (513, 284), (549, 284), (549, 256)],
          "paw": [(502, 284), (553, 284), (553, 311), (502, 311)]},
    "f": {"P": (224, 232), "R": 16, "K": (215, 255), "rk": 20, "A": (206, 285), "ra": 14, "TOE": (170, 306), "side": -1,
          "c": 25, "lift": 7, "kick": 4, "heel": 26, "flex": -85, "reach": 12, "V": 1.5,
          "upper": [(208, 232), (196, 234), (194.5, 240), (194.5, 255), (243, 255), (244.5, 238), (240, 232)],
          "lower": [(194.5, 255), (193.5, 265), (190.5, 278), (186, 285), (222.5, 285), (228, 278), (234, 268),
             (240, 258), (243, 255)],
          "paw": [(158, 285), (230, 285), (230, 314), (158, 314)]},
}
# key: (kind, phase, offset of the whole leg, far side). The drawing faces left, so the near legs are his left legs.
# A leg's paw lands at (1 - phase) of the cycle (the CSS starts each leg phase * T early): left hind, left fore,
# right hind, right fore, a quarter apart, the lateral walk of a dog
LEGS = {
    "hn": ("h", 0.0, (0, 0), False),
    "fn": ("f", 0.75, (0, 0), False),
    "hf": ("h", 0.5, (-12, -8), True),
    "ff": ("f", 0.25, (12, -8), True),
}


def ss(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def rot(v, deg):
    a = math.radians(deg)
    return (v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a))


def ang(v):
    return math.degrees(math.atan2(v[1], v[0]))


def ik(P, A, l1, l2, side):
    """knee position for a two-piece leg from P to A; side +1 bends the joint back (hock), -1 forward (carpus)"""
    dx, dy = A[0] - P[0], A[1] - P[1]
    d = min(math.hypot(dx, dy), l1 + l2 - 0.01)
    base = math.atan2(dy, dx)
    a = math.acos(max(-1.0, min(1.0, (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d))))
    # in screen coordinates (y down), turning the P->A direction by -a puts the knee on the +x side for a leg
    # pointing down
    t = base - side * a
    return (P[0] + l1 * math.cos(t), P[1] + l1 * math.sin(t))


def paw_track(k, p):
    """(ankle position, paw angle) at phase p of the cycle; the paw angle is absolute (0 = as drawn, negative = heel up)"""
    A0, T0 = k["A"], k["TOE"]
    heel_from = STANCE - 0.2
    if p < STANCE:  # planted: the toe slides back with the ground; late in the stance the heel rises over the toe
        toe = (T0[0] + k["c"] - D / 2 + D * p / STANCE, T0[1])
        phi = -k["heel"] * ss((p - heel_from) / (STANCE - heel_from))
        return (toe[0] + rot((A0[0] - T0[0], A0[1] - T0[1]), phi)[0],
                toe[1] + rot((A0[0] - T0[0], A0[1] - T0[1]), phi)[1]), phi
    u = (p - STANCE) / (1 - STANCE)
    start, phi0 = paw_track(k, STANCE - 1e-9)
    land = (A0[0] + k["c"] - D / 2, A0[1])
    e = ss((u - 0.12) / 0.8)
    x = start[0] + (land[0] - start[0]) * e + k["kick"] * math.sin(math.pi * min(u / 0.5, 1.0))
    x -= k["reach"] * math.sin(math.pi * ss((u - 0.45) / 0.55)) * 0.6  # reaches a little past the landing spot
    y = start[1] + (land[1] - start[1]) * ss(u / 0.9) - k["lift"] * math.sin(math.pi * u ** 0.8)
    # the paw: from toe-off it curls further (the flick), then opens and lands flat, toes a touch up just before
    if u < 0.35:
        phi = phi0 + (k["flex"] - phi0) * ss(u / 0.35)
    elif u < 0.85:
        phi = k["flex"] + (8 - k["flex"]) * ss((u - 0.35) / 0.5)
    else:
        phi = 8 * (1 - ss((u - 0.85) / 0.15))
    return (x, y), phi


def shoulder(k, p):
    """where the top of the leg is at phase p. Hind legs: the hip, fixed. Fore legs: a dog's foreleg swings from the
    shoulder blade, high on the body, so the top of the visible leg slides along with the swing (it is plain body colour
    there, so the slide is not seen) and the leg stays straight while it carries the dog"""
    P, A0 = k["P"], k["A"]
    if "V" not in k:
        return P
    V = (A0[0] + k["V"] * (P[0] - A0[0]), A0[1] + k["V"] * (P[1] - A0[1]))
    Lt = math.dist(P, A0) - 0.02

    def reach(q):  # how far from the shoulder blade the shoulder sits, from the paw as if it were still flat
        flat = (A0[0] + k["c"] - D / 2 + D * min(q, STANCE) / STANCE, A0[1])
        return math.dist(flat, V) - Lt

    A, _ = paw_track(k, p)
    dv = math.dist(A, V)
    u = ((V[0] - A[0]) / dv, (V[1] - A[1]) / dv)
    r = reach(p) if p < STANCE else reach(STANCE) + (reach(0.0) - reach(STANCE)) * ss((p - STANCE) / (1 - STANCE))
    return (V[0] - r * u[0], V[1] - r * u[1])


def pose(k, p):
    """(hip shift x, hip shift y, hip turn, knee turn, paw turn) at phase p; turns are relative to the piece above"""
    P0, K0, A0 = k["P"], k["K"], k["A"]
    l1, l2 = math.dist(P0, K0), math.dist(K0, A0)
    A, phi = paw_track(k, p)
    P = shoulder(k, p)
    K = ik(P, A, l1, l2, k["side"])
    up = ang((K[0] - P[0], K[1] - P[1])) - ang((K0[0] - P0[0], K0[1] - P0[1]))
    lo_abs = ang((A[0] - K[0], A[1] - K[1])) - ang((A0[0] - K0[0], A0[1] - K0[1]))
    def norm(a):
        return (a + 180) % 360 - 180
    return P[0] - P0[0], P[1] - P0[1], norm(up), norm(lo_abs - up), norm(phi - lo_abs)


def tf(row, j):
    if j == 0:
        shift = f"translate({row[0]:.1f}px, {row[1]:.1f}px) " if (abs(row[0]) > 0.05 or abs(row[1]) > 0.05) else ""
        return f"{shift}rotate({row[2]:.1f}deg)"
    return f"rotate({row[j + 2]:.1f}deg)"


def keyframes(kind):
    k = KINDS[kind]
    rows = [pose(k, i / N) for i in range(N)]
    rows.append(rows[0])
    out = []
    for j, part in enumerate(("hip", "knee", "paw")):
        steps = " ".join(f"{100 * i / N:.4g}% {{ transform: {tf(rows[i], j)}; }}" for i in range(N + 1))
        out.append(f"@keyframes td-{kind}-{part} {{ {steps} }}")
    return out


def pts(poly):
    return " ".join(f"{x},{y}" for x, y in poly)


def clip(cid, circle, poly):
    (cx, cy), r = circle
    return f'<clipPath id="{cid}"><circle cx="{cx}" cy="{cy}" r="{r}"/><polygon points="{pts(poly)}"/></clipPath>'


def leg_svg(key):
    kind, phase, (ox, oy), far = LEGS[key]
    k = KINDS[kind]
    P, K, A = k["P"], k["K"], k["A"]
    j = f'style="--ph:{phase}"'
    # each <image> sits at minus its joint, so it lines up with the drawing inside its rotating group; the clip paths
    # are in the image's own (drawing) coordinates
    g = (f'<g transform="translate({P[0] + ox} {P[1] + oy})"><g class="td-j td-{kind}-hip" {j}>'
         f'<g transform="translate({-P[0]} {-P[1]})"><image href="{IMG}" width="640" height="330" clip-path="url(#td-c-{kind}1)"/></g>'
         f'<g transform="translate({K[0] - P[0]} {K[1] - P[1]})"><g class="td-j td-{kind}-knee" {j}>'
         f'<g transform="translate({-K[0]} {-K[1]})"><image href="{IMG}" width="640" height="330" clip-path="url(#td-c-{kind}2)"/></g>'
         f'<g transform="translate({A[0] - K[0]} {A[1] - K[1]})"><g class="td-j td-{kind}-paw" {j}>'
         f'<g transform="translate({-A[0]} {-A[1]})"><image href="{IMG}" width="640" height="330" clip-path="url(#td-c-{kind}3)"/></g>'
         '</g></g></g></g></g></g>')
    return f'<g filter="url(#td-far)">{g}</g>' if far else g


HEAD = "0,0 236,0 236,126 225,142 178,184 160,190 158,220 126,220 126,160 0,160"
TAIL = "508,135 640,135 640,206 576,199 540,186 526,179 516,168"
# the body without its legs: down the rump to the hind joint circle, round its bottom, along the far hind leg's top
# and just under the drawn belly line, up the fore leg's back edge, round the fore joint circle, down the chest
H, F = KINDS["h"], KINDS["f"]
TORSO = (f"M236,100L532,100L532,150L525,170L524,{H['P'][1]}L{H['P'][0] + H['R']},{H['P'][1]}"
         f"A{H['R']},{H['R']} 0 0 1 {H['P'][0] - H['R']},{H['P'][1]}"
         f"L438,209L437,224L410,224L390,227L370,234L350,242L330,249L300,260L270,266L250,267L240,262L243,250L244.5,238L240,{F['P'][1]}"
         f"A{F['R']},{F['R']} 0 0 1 {F['P'][0] - F['R']},{F['P'][1]}"
         "L196,234L194.5,240L194.5,255L193,259L166,242L148,215L158,220L160,190L178,184L225,142L236,126Z")
# plain body colour where the near legs join the body (drawn under the torso picture), so a turning leg shows body
# there, never the ground or a ghost of the drawn leg; its lower edge carries the fold line, seen only when a leg moves
FILL = [("M186,224L252,224L252,266L239,263Q215,266 194,257L186,250Z", "M194,257Q215,266 239,263"),
        ("M437,224L438,209L470,203L518,203L518,228Q500,238 474,236Q452,233 437,224Z", "M437,224Q452,233 474,236Q492,238 506,234")]

css = keyframes("h") + keyframes("f")
rest = {kind: pose(KINDS[kind], 0.0) for kind in "hf"}

svg = ['<svg class="todi-dog todi-rig{{ " " ~ extra_class if extra_class else "" }}" viewBox="0 0 640 330" aria-hidden="true" focusable="false">',
       '<defs>',
       f'<clipPath id="td-c-head"><polygon points="{HEAD}"/></clipPath>',
       f'<clipPath id="td-c-tail"><polygon points="{TAIL}"/></clipPath>',
       f'<clipPath id="td-c-torso"><path d="{TORSO}"/></clipPath>']
for kind, k in KINDS.items():
    svg.append(clip(f"td-c-{kind}1", (k["P"], k["R"]), k["upper"]))
    svg.append(clip(f"td-c-{kind}2", (k["K"], k["rk"]), k["lower"]))
    svg.append(clip(f"td-c-{kind}3", (k["A"], k["ra"]), k["paw"]))
svg += ['<filter id="td-far" color-interpolation-filters="sRGB"><feColorMatrix values="0.68 0 0 0 0 0 0.66 0 0 0 0 0 0.66 0 0 0 0 0 1 0"/></filter>',
        '</defs>',
        '<g class="td-rbob">']
for key in ("hf", "ff"):
    svg.append(leg_svg(key))
svg.append(f'<g class="td-tail"><image href="{IMG}" width="640" height="330" clip-path="url(#td-c-tail)"/></g>')
for shape, fold in FILL:
    svg.append(f'<path fill="{BROWN}" d="{shape}"/><path fill="none" stroke="{LINE}" stroke-width="3" stroke-linecap="round" d="{fold}"/>')
svg.append(f'<image href="{IMG}" width="640" height="330" clip-path="url(#td-c-torso)"/>')
for key in ("hn", "fn"):
    svg.append(leg_svg(key))
svg.append(f'<g class="td-head"><image href="{IMG}" width="640" height="330" clip-path="url(#td-c-head)"/></g>')
svg.append('</g></svg>')
Path(OUT, "rig.svg.html").write_text("\n".join(svg) + "\n")

r = rest
style = f"""/* Todi as a jointed puppet (templates/_todi_dog.html; all of this block is written by tools/todi_rig.py): every piece
   is cut from the owner's drawing; a dog's walk, one leg after another, each paw planted while the body passes over it,
   the heel rising, the paw pushing off and flicking back, then swinging forward */
.todi-rig {{ display: block; width: 100%; height: auto; overflow: visible; }}
.todi-rig .td-f-hip {{ transform: {tf(r['f'], 0)}; }} .todi-rig .td-f-knee {{ transform: {tf(r['f'], 1)}; }} .todi-rig .td-f-paw {{ transform: {tf(r['f'], 2)}; }}
.todi-rig .td-h-hip {{ transform: {tf(r['h'], 0)}; }} .todi-rig .td-h-knee {{ transform: {tf(r['h'], 1)}; }} .todi-rig .td-h-paw {{ transform: {tf(r['h'], 2)}; }}
.todi-rig .td-head {{ transform-origin: 196px 160px; transition: transform .45s ease; }}
.todi-rig .td-tail {{ transform-origin: 518px 166px; }}
.todi-rig.is-sniffing .td-head {{ transform: rotate(-26deg) translate(-4px, 10px); }}
.todi-rig.is-looking .td-head {{ transform: rotate(11deg); }}
@media (prefers-reduced-motion: no-preference) {{
  html:not(.a11y-no-motion) .todi-rig .td-tail {{ animation: td-wag .5s ease-in-out infinite alternate; }}
  html:not(.a11y-no-motion) .todi-rig.is-walking .td-j {{ animation-duration: {T}s; animation-timing-function: linear; animation-iteration-count: infinite; animation-delay: calc(var(--ph) * -{T}s); }}
  html:not(.a11y-no-motion) .todi-rig.is-walking .td-f-hip {{ animation-name: td-f-hip; }}
  html:not(.a11y-no-motion) .todi-rig.is-walking .td-f-knee {{ animation-name: td-f-knee; }}
  html:not(.a11y-no-motion) .todi-rig.is-walking .td-f-paw {{ animation-name: td-f-paw; }}
  html:not(.a11y-no-motion) .todi-rig.is-walking .td-h-hip {{ animation-name: td-h-hip; }}
  html:not(.a11y-no-motion) .todi-rig.is-walking .td-h-knee {{ animation-name: td-h-knee; }}
  html:not(.a11y-no-motion) .todi-rig.is-walking .td-h-paw {{ animation-name: td-h-paw; }}
  html:not(.a11y-no-motion) .todi-rig.is-walking .td-rbob {{ animation: td-rbob {T / 4}s ease-in-out infinite alternate; }}
  html:not(.a11y-no-motion) .todi-rig.is-sniffing .td-head {{ animation: td-rsniff .5s ease-in-out infinite alternate; }}
}}
@keyframes td-wag {{ from {{ transform: rotate(-7deg); }} to {{ transform: rotate(9deg); }} }}
@keyframes td-rbob {{ from {{ translate: 0 0; }} to {{ translate: 0 -2px; }} }}
@keyframes td-rsniff {{ from {{ transform: rotate(-26deg) translate(-4px, 10px); }} to {{ transform: rotate(-22deg) translate(-4px, 8px); }} }}
""" + "\n".join(css) + "\n"
Path(OUT, "rig.css").write_text(style)
print("walking speed:", round(D / 640 / (STANCE * T), 4), "dog widths a second")

"""2026-11-13 (owner: "all the legs must move like a real dog walking"): builds Todi as a jointed puppet. One SVG (the
body, head and tail are the owner's illustration, static/todi/todi-rig.webp; the four legs are drawn here with a hip,
a knee and a paw each) and the CSS of a dog's walk: each paw stays planted while the body passes over it, then lifts
and swings forward, the four legs a quarter of a cycle apart (near hind, near front, far hind, far front).
Run: python tools/todi_rig.py <out dir>; it writes rig.svg.html (goes into templates/_todi_dog.html) and rig.css
(goes into static/style.css). Walking speed that keeps the paws from sliding is printed (home.js uses it)."""
import math
import sys
from pathlib import Path

OUT = sys.argv[1]
T = 0.56          
D = 42            
STANCE = 0.65     
LIFT = 9
N = 20
LINE, DARK, FAR, TAN, FARTAN = "#3a1816", "#5f3421", "#4c2a1a", "#bb6a30", "#9c5727"

LEGS = {  
    "hn": (482, 240, 34, 32, 1, 0.0, False),
    "fn": (218, 248, 30, 28, -1, 0.25, False),
    "hf": (462, 238, 34, 32, 1, 0.5, True),
    "ff": (238, 250, 30, 28, -1, 0.75, True),
}
GROUND = 300      


def pose(hy, l1, l2, s, p):
    hh = GROUND - hy
    if p < STANCE:
        tx, ty, tilt = -D / 2 + D * p / STANCE, hh, 0.0
    else:
        u = (p - STANCE) / (1 - STANCE)
        e = u * u * (3 - 2 * u)
        tx, ty, tilt = D / 2 - D * e, hh - LIFT * math.sin(math.pi * u), -16 * math.sin(math.pi * u)
    d = min(math.hypot(tx, ty), l1 + l2 - 0.01)
    phi = math.atan2(-tx, ty)
    a = math.acos((l1 * l1 + d * d - l2 * l2) / (2 * l1 * d))
    b = math.acos((l2 * l2 + d * d - l1 * l1) / (2 * l2 * d))
    t1, t2 = phi + s * a, phi - s * b
    return math.degrees(t1), math.degrees(t2 - t1), -math.degrees(t2) + tilt


def keyframes(name, hy, l1, l2, s):
    rows = [pose(hy, l1, l2, s, i / N) for i in range(N)] + [pose(hy, l1, l2, s, 0)]
    out = []
    for j, part in enumerate(("hip", "knee", "paw")):
        steps = " ".join(f"{100 * i / N:g}% {{ transform: rotate({rows[i][j]:.1f}deg); }}" for i in range(N + 1))
        out.append(f"@keyframes td-{name}-{part} {{ {steps} }}")
    return out, rows[0]


def leg_svg(key, hx, hy, l1, l2, s, phase, far):
    hind = key[0] == "h"
    fill, tan = (FAR, FARTAN) if far else (DARK, TAN)
    if hind:  
        upper = f'<path fill="{fill}" d="M-30,-12C-33,8 -19,26 -11,{l1}L11,{l1}C24,27 40,10 42,-14Z"/>' \
                f'<path fill="none" stroke="{LINE}" stroke-width="3" stroke-linecap="round" d="M-29,2C-27,14 -18,27 -11,{l1}M11,{l1}C23,27 37,12 41,-4"/>'
    else:
        upper = f'<path fill="{fill}" d="M-19,-10C-19,10 -13,22 -12,{l1}L12,{l1}C13,22 19,10 19,-10Z"/>' \
                f'<path fill="none" stroke="{LINE}" stroke-width="3" stroke-linecap="round" d="M-18,6C-17,16 -13,23 -12,{l1}M12,{l1}C13,23 17,16 18,6"/>'
    lower = (f'<circle r="12" fill="{fill}"/>'
             f'<path fill="{fill}" stroke="{LINE}" stroke-width="3" stroke-linejoin="round" d="M-12,0L-11,{l2}L11,{l2}L12,0"/>'
             f'<path fill="{tan}" stroke="{LINE}" stroke-width="3" stroke-linejoin="round" d="M-11.6,13L-11,{l2 + 2}L11,{l2 + 2}L11.6,13Q0,9 -11.6,13Z"/>'
             f'<circle r="10.5" fill="{fill}"/>')
    paw = (f'<path fill="{tan}" stroke="{LINE}" stroke-width="3" stroke-linejoin="round" d="M11,-9L11,2Q11,8 4,8L-17,8Q-27,8 -27,-1Q-27,-9 -15,-10Z"/>'
           f'<path fill="none" stroke="{LINE}" stroke-width="2" stroke-linecap="round" d="M-19,1v6M-12,1.5v5.5"/>')
    kind = "h" if hind else "f"
    return (f'<g transform="translate({hx} {hy})"><g class="td-j td-{kind}-hip" style="--ph:{phase}">{upper}'
            f'<g transform="translate(0 {l1})"><g class="td-j td-{kind}-knee" style="--ph:{phase}">{lower}'
            f'<g transform="translate(0 {l2})"><g class="td-j td-{kind}-paw" style="--ph:{phase}">{paw}</g></g></g></g></g></g>')


HEAD = "0,0 236,0 236,126 225,142 178,184 160,190 158,220 126,220 126,160 0,160"
TAIL = "508,135 640,135 640,205 526,205 526,182 514,168"
TORSO = "M236,100L530,100L530,150L526,170L526,196Q526,230 496,231L470,227L430,220L400,226L350,247L300,264L240,271L196,263L168,240L150,215L158,220L160,190L178,184L225,142L236,126Z"
RUMP = "M526,180L526,196Q526,230 496,231"
BELLY = "M150,215C158,232 176,253 196,263C212,270 228,271 240,271C262,271 282,268 300,264C318,259 334,253 350,247C368,240 384,232 400,226C410,222 420,220 430,220"

css, rest = [], {}
for kind, key in (("h", "hn"), ("f", "fn")):
    hx, hy, l1, l2, s, _, _ = LEGS[key]
    k, r0 = keyframes(kind, hy, l1, l2, s)
    css += k
    rest[kind] = r0

svg = ['<svg class="todi-dog todi-rig{{ " " ~ extra_class if extra_class else "" }}" viewBox="0 0 640 330" aria-hidden="true" focusable="false">',
       '<defs>',
       f'<clipPath id="td-c-head"><polygon points="{HEAD}"/></clipPath>',
       f'<clipPath id="td-c-tail"><polygon points="{TAIL}"/></clipPath>',
       f'<clipPath id="td-c-torso"><path d="{TORSO}"/></clipPath>',
       '</defs>',
       '<g class="td-rbob">']
for key in ("hf", "ff"):
    svg.append(leg_svg(key, *LEGS[key]))
svg.append('<g class="td-tail"><image href="IMG" width="640" height="330" clip-path="url(#td-c-tail)"/></g>')
svg.append('<image href="IMG" width="640" height="330" clip-path="url(#td-c-torso)"/>')
svg.append(f'<path fill="none" stroke="{LINE}" stroke-width="3.2" stroke-linecap="round" d="{BELLY}"/>')
svg.append(f'<path fill="none" stroke="{LINE}" stroke-width="3.2" stroke-linecap="round" d="{RUMP}"/>')
svg.append(f'<ellipse cx="184" cy="160" rx="50" ry="15" transform="rotate(-30 184 160)" fill="{DARK}"/>')
for key in ("hn", "fn"):
    svg.append(leg_svg(key, *LEGS[key]))
svg.append('<g class="td-head"><image href="IMG" width="640" height="330" clip-path="url(#td-c-head)"/></g>')
svg.append('</g></svg>')
Path(OUT, "rig.svg.html").write_text("\n".join(svg))

r = rest
style = f"""/* Todi as a jointed puppet (templates/_todi_dog.html; all of this block is written by tools/todi_rig.py): a dog's
   walk, one leg after another, each paw planted while the body passes over it */
.todi-rig {{ display: block; width: 100%; height: auto; overflow: visible; }}
.todi-rig .td-f-hip {{ transform: rotate({r['f'][0]:.1f}deg); }} .todi-rig .td-f-knee {{ transform: rotate({r['f'][1]:.1f}deg); }} .todi-rig .td-f-paw {{ transform: rotate({r['f'][2]:.1f}deg); }}
.todi-rig .td-h-hip {{ transform: rotate({r['h'][0]:.1f}deg); }} .todi-rig .td-h-knee {{ transform: rotate({r['h'][1]:.1f}deg); }} .todi-rig .td-h-paw {{ transform: rotate({r['h'][2]:.1f}deg); }}
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
@keyframes td-rbob {{ from {{ translate: 0 0; }} to {{ translate: 0 -2.5px; }} }}
@keyframes td-rsniff {{ from {{ transform: rotate(-26deg) translate(-4px, 10px); }} to {{ transform: rotate(-22deg) translate(-4px, 8px); }} }}
""" + "\n".join(css) + "\n"
Path(OUT, "rig.css").write_text(style)
print("walking speed:", round(D / 640 / (STANCE * T), 3), "dog widths a second")

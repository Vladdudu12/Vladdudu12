#!/usr/bin/env python3
"""
Dragonite vs Politoed - a turn-based battle playable from a GitHub profile README.

How it works:
  * State lives in game/state.json
  * `python battle.py --move outrage` resolves the player's move + the CPU reply,
    updates state, then re-renders game/battle.png and README.md
  * `python battle.py --new` starts a fresh battle
  * The README shows the PNG + four clickable "move" links. Each link opens a
    pre-filled GitHub Issue; a GitHub Action parses it and runs this script.

The art is original, stylized vector drawing (Pillow) - no copyrighted sprites.
"""
import argparse, json, os, random, math, urllib.parse, glob, time
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(ROOT, "game", "state.json")
PNG_PATH = os.path.join(ROOT, "game", "battle.png")
GIF_PATH = os.path.join(ROOT, "game", "battle.gif")
README_PATH = os.path.join(ROOT, "README.md")

# ----------------------------------------------------------------------------
# Pokemon / move data
# ----------------------------------------------------------------------------
TYPE_CHART = {
    # attacking type -> {defending type: multiplier}
    "dragon":   {"dragon": 2.0},
    "fire":     {"water": 0.5, "dragon": 0.5},
    "electric": {"water": 2.0, "dragon": 0.5, "flying": 2.0},
    "ice":      {"dragon": 2.0, "flying": 2.0},
    "water":    {"dragon": 0.5, "fire": 2.0},
    "normal":   {},
}

MOVES = {
    "outrage":      {"label": "OUTRAGE",      "type": "dragon",   "dmg": (46, 54)},
    "fire-punch":   {"label": "FIRE PUNCH",   "type": "fire",     "dmg": (16, 24)},
    "thunderpunch": {"label": "THUNDERPUNCH", "type": "electric", "dmg": (54, 64)},
    "roost":        {"label": "ROOST",        "type": "normal",   "dmg": (0, 0), "heal": 0.5},
    "ice-beam":     {"label": "ICE BEAM",     "type": "ice",      "dmg": (52, 64)},
    "surf":         {"label": "SURF",         "type": "water",    "dmg": (38, 46)},
    "hypnosis":     {"label": "HYPNOSIS",     "type": "normal",   "dmg": (0, 0)},
}

DRAGONITE = {
    "name": "DRAGONITE", "types": ["dragon", "flying"], "max_hp": 160,
    "moves": ["outrage", "fire-punch", "thunderpunch", "roost"],
}
POLITOED = {
    "name": "POLITOED", "types": ["water"], "max_hp": 150,
    "moves": ["ice-beam", "surf", "hypnosis"],
}

def new_state():
    return {
        "player": {"hp": DRAGONITE["max_hp"]},   # Dragonite = you
        "cpu":    {"hp": POLITOED["max_hp"]},     # Politoed   = CPU
        "turn": 0,
        "message": "What will DRAGONITE do?",
        "over": False,
    }

# ----------------------------------------------------------------------------
# Battle logic
# ----------------------------------------------------------------------------
def effectiveness(move_type, defender_types):
    mult = 1.0
    for t in defender_types:
        mult *= TYPE_CHART.get(move_type, {}).get(t, 1.0)
    return mult

def eff_text(mult):
    if mult >= 2:  return "It's super effective!"
    if mult == 0:  return "It had no effect..."
    if mult < 1:   return "It's not very effective..."
    return ""

def damage(move, defender_types):
    m = MOVES[move]
    lo, hi = m["dmg"]
    if hi == 0:
        return 0, 1.0
    mult = effectiveness(m["type"], defender_types)
    return random.randint(lo, hi), mult

def apply_move(state, who, move):
    """who = 'player' or 'cpu'. Returns list of message lines."""
    lines = []
    m = MOVES[move]
    attacker = DRAGONITE if who == "player" else POLITOED
    defkey = "cpu" if who == "player" else "player"
    defender = POLITOED if who == "player" else DRAGONITE
    lines.append(f"{attacker['name']} used {m['label']}!")

    if m.get("heal"):
        healed = int(attacker["max_hp"] * m["heal"])
        state[who]["hp"] = min(attacker["max_hp"], state[who]["hp"] + healed)
        lines.append(f"{attacker['name']} regained health!")
        return lines
    if move == "hypnosis":
        lines.append("But nothing happened!")
        return lines

    dmg, mult = damage(move, defender["types"])
    et = eff_text(mult)
    state[defkey]["hp"] = max(0, state[defkey]["hp"] - dmg)
    if et:
        lines.append(et)
    return lines

def cpu_choose(state):
    # Politoed is smart enough to spam Ice Beam (4x on Dragonite). 60% Ice Beam.
    if random.random() < 0.6:
        return "ice-beam"
    return random.choice(["surf", "ice-beam"])

def resolve(state, player_move):
    if state.get("over"):
        return state
    msgs = []
    # Dragonite (player) moves first (higher speed in this matchup)
    msgs += apply_move(state, "player", player_move)
    if state["cpu"]["hp"] <= 0:
        msgs.append("Foe POLITOED fainted!")
        msgs.append("DRAGONITE wins! 🎉")
        state["over"] = True
        state["message"] = "  ".join(msgs)
        state["turn"] += 1
        return state
    # Politoed replies
    cpu_move = cpu_choose(state)
    msgs += apply_move(state, "cpu", cpu_move)
    if state["player"]["hp"] <= 0:
        msgs.append("DRAGONITE fainted!")
        msgs.append("POLITOED wins...")
        state["over"] = True
    state["message"] = "  ".join(msgs)
    state["turn"] += 1
    return state

# ----------------------------------------------------------------------------
# Rendering (Pillow) -- placeholder, refined below
# ----------------------------------------------------------------------------
def load_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()

OUTLINE = (40, 38, 52)

# ----------------------------------------------------------------------------
# Optional: real Pokémon sprites from PokéAPI's CDN.
#   These are ripped game sprites owned by Nintendo/Game Freak/The Pokémon Co.
#   Using them is technically copyright infringement; see SETUP.md. Set
#   USE_REAL_SPRITES = False to use the original drawn sprites instead.
# Sprite swap is easy: change the dex numbers (Dragonite=149, Politoed=186)
#   front:  .../pokemon/<id>.png      back: .../pokemon/back/<id>.png
#   artwork:.../pokemon/other/official-artwork/<id>.png  (big Sugimori art)
# ----------------------------------------------------------------------------
USE_REAL_SPRITES = True   # False -> hand-drawn sprites
USE_ANIMATION    = True    # True  -> fetch animated sprites, output battle.gif
MAX_FRAMES = 40            # cap on GIF frames (keeps file size sane)
FRAME_MS   = 90            # ms per frame

import urllib.request
from PIL import ImageSequence
_CDN  = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon"
_ANIM = f"{_CDN}/other/showdown"   # Pokémon Showdown animated GIFs

# Each entry: dex id, whether to use the back sprite, on-screen center + scale,
# and the hand-drawn fallback (function + its own center/scale).
SPRITES = {
    "politoed":  {"id": 186, "back": False, "cx": 486, "cy": 150, "scale": 1.9,
                  "draw": "politoed", "dx": 486, "dy": 132, "ds": 0.82},
    "dragonite": {"id": 149, "back": True,  "cx": 175, "cy": 232, "scale": 2.2,
                  "draw": "dragonite", "dx": 168, "dy": 244, "ds": 1.08},
}

def _sprite_url(cfg, animated):
    base = _ANIM if animated else _CDN
    sub  = "/back" if cfg["back"] else ""
    ext  = "gif" if animated else "png"
    return f"{base}{sub}/{cfg['id']}.{ext}"

def _fetch_frames(name):
    """Return a list of small RGBA sprite frames, or None on any failure."""
    if not USE_REAL_SPRITES:
        return None
    cfg = SPRITES[name]
    animated = USE_ANIMATION
    url = _sprite_url(cfg, animated)
    ext = "gif" if animated else "png"
    cache = os.path.join(ROOT, "game", "sprites", f"{name}.{ext}")
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    if not os.path.exists(cache):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "readme-battle"})
            open(cache, "wb").write(urllib.request.urlopen(req, timeout=20).read())
        except Exception as e:
            print(f"[sprite] fetch failed for {name}: {e} -> drawing fallback")
            return None
    try:
        im = Image.open(cache)
        frames = [f.convert("RGBA") for f in ImageSequence.Iterator(im)]
        return frames or None
    except Exception as e:
        print(f"[sprite] decode failed for {name}: {e} -> drawing fallback")
        return None

def sprite_layers(name, W, H):
    """List of full-canvas RGBA layers (one per animation frame), positioned & scaled.
    Falls back to a single hand-drawn layer if real sprites aren't available."""
    cfg = SPRITES[name]
    frames = _fetch_frames(name)
    layers = []
    if frames:
        for s in frames:
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            sc = cfg["scale"]
            s2 = s.resize((max(1, int(s.width*sc)), max(1, int(s.height*sc))), Image.NEAREST)
            layer.paste(s2, (int(cfg["cx"]-s2.width/2), int(cfg["cy"]-s2.height/2)), s2)
            layers.append(layer)
        return layers
    # hand-drawn fallback
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    {"politoed": draw_politoed, "dragonite": draw_dragonite}[cfg["draw"]](
        d, cfg["dx"], cfg["dy"], s=cfg["ds"])
    return [layer]

def _ellipse(d, cx, cy, rx, ry, fill, ow=4):
    d.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=fill, outline=OUTLINE, width=ow)

def draw_dragonite(d, cx, cy, s=1.0):
    O  = (242, 168, 70)    # body orange
    OD = (214, 140, 52)    # shade
    C  = (247, 235, 200)   # belly cream
    W  = (139, 205, 222)   # wing teal
    def E(x, y, rx, ry, fill, ow=4): _ellipse(d, cx+x*s, cy+y*s, rx*s, ry*s, fill, ow)
    # tail
    d.polygon([(cx-70*s, cy+40*s), (cx-120*s, cy+70*s), (cx-95*s, cy+18*s)], fill=O, outline=OUTLINE)
    # wings (behind body)
    d.polygon([(cx-30*s, cy-30*s), (cx-95*s, cy-70*s), (cx-40*s, cy-5*s)], fill=W, outline=OUTLINE)
    d.polygon([(cx+30*s, cy-30*s), (cx+95*s, cy-70*s), (cx+40*s, cy-5*s)], fill=W, outline=OUTLINE)
    # legs
    E(-28, 70, 22, 26, O); E(28, 70, 22, 26, O)
    E(-28, 86, 20, 12, C, 3); E(28, 86, 20, 12, C, 3)
    # body
    E(0, 30, 62, 70, O)
    E(0, 44, 40, 52, C)        # belly
    # arms
    E(-58, 18, 18, 30, O); E(58, 18, 18, 30, O)
    # head
    E(0, -58, 50, 46, O)
    E(0, -42, 30, 24, C, 3)    # muzzle
    # snout/nostrils
    d.ellipse([cx-22*s, cy-58*s, cx-14*s, cy-50*s], fill=OD)
    d.ellipse([cx+14*s, cy-58*s, cx+22*s, cy-50*s], fill=OD)
    # eyes
    E(-22, -72, 7, 9, (255,255,255), 2); E(22, -72, 7, 9, (255,255,255), 2)
    d.ellipse([cx-25*s, cy-74*s, cx-19*s, cy-66*s], fill=OUTLINE)
    d.ellipse([cx+19*s, cy-74*s, cx+25*s, cy-66*s], fill=OUTLINE)
    # antennae
    d.line([(cx-16*s, cy-100*s), (cx-26*s, cy-128*s)], fill=OUTLINE, width=int(5*s))
    d.line([(cx+16*s, cy-100*s), (cx+26*s, cy-128*s)], fill=OUTLINE, width=int(5*s))
    E(-28, -132, 8, 8, O); E(28, -132, 8, 8, O)

def draw_politoed(d, cx, cy, s=1.0):
    G  = (120, 196, 110)   # body green
    GD = (92, 168, 86)
    C  = (238, 226, 176)   # belly cream
    def E(x, y, rx, ry, fill, ow=4): _ellipse(d, cx+x*s, cy+y*s, rx*s, ry*s, fill, ow)
    # raised hands (Politoed conducts)
    E(-58, -30, 14, 16, G); E(58, -30, 14, 16, G)
    # feet
    E(-30, 60, 22, 14, C); E(30, 60, 22, 14, C)
    # body
    E(0, 18, 56, 60, G)
    E(0, 30, 40, 44, C)        # big belly
    # spots
    E(-34, 6, 9, 7, GD, 0); E(36, 14, 7, 6, GD, 0)
    # head region (Politoed's head blends with body); big eyes on top
    E(-22, -36, 17, 19, (255,255,255), 3)
    E(22, -36, 17, 19, (255,255,255), 3)
    d.ellipse([cx-26*s, cy-40*s, cx-16*s, cy-26*s], fill=OUTLINE)   # pupils
    d.ellipse([cx+16*s, cy-40*s, cx+26*s, cy-26*s], fill=OUTLINE)
    # wide mouth
    d.arc([cx-34*s, cy-30*s, cx+34*s, cy+18*s], start=10, end=170, fill=OUTLINE, width=int(5*s))
    d.line([(cx-33*s, cy-12*s), (cx+33*s, cy-12*s)], fill=OUTLINE, width=int(4*s))
    # signature curl on top of head
    d.arc([cx-4*s, cy-78*s, cx+30*s, cy-44*s], start=120, end=400, fill=OUTLINE, width=int(6*s))

def _hp_box(d, x, y, name, hp, maxhp, font, font_sm, align_right=False):
    bw, bh = 250, 72
    d.rounded_rectangle([x, y, x+bw, y+bh], radius=10, fill=(250, 250, 245),
                        outline=OUTLINE, width=3)
    d.text((x+14, y+9), name, font=font, fill=OUTLINE)
    lv = "Lv55"
    d.text((x+bw-14-d.textlength(lv, font=font_sm), y+12), lv, font=font_sm, fill=OUTLINE)
    # HP bar
    bx, by, bx2 = x+44, y+52, x+bw-16
    d.text((x+14, y+45), "HP", font=font_sm, fill=(216, 152, 40))
    d.rounded_rectangle([bx, by-7, bx2, by+7], radius=7, fill=(70, 70, 70))
    frac = max(0.0, hp / maxhp)
    col = (104, 200, 96) if frac > 0.5 else (240, 200, 72) if frac > 0.2 else (224, 80, 64)
    if frac > 0:
        d.rounded_rectangle([bx+2, by-5, bx+2+int((bx2-bx-4)*frac), by+5], radius=5, fill=col)
    if align_right:
        txt = f"{hp}/{maxhp}"
        d.text((bx2-d.textlength(txt, font=font_sm), y+31), txt, font=font_sm, fill=OUTLINE)

def _issue_link(repo, move, label):
    title = urllib.parse.quote(f"Battle: {move}")
    body = urllib.parse.quote(
        "Just press the green Create button below to make your move.\n"
        "A bot will play the turn and update the profile in a few seconds."
    )
    return f"https://github.com/{repo}/issues/new?title={title}&body={body}"

def render_readme(state, img_rel="game/battle.png"):
    repo = os.environ.get("GITHUB_REPOSITORY", "Vladdudu12/Vladdudu12")
    cache = state["turn"]
    over = state.get("over")
    new_link = _issue_link(repo, "new", "New")

    mv = DRAGONITE["moves"]
    def cell(m):
        if over:
            return f"~~{MOVES[m]['label']}~~"
        return f"[**{MOVES[m]['label']}**]({_issue_link(repo, m, MOVES[m]['label'])})"
    table = (
        "| | |\n|:--:|:--:|\n"
        f"| {cell(mv[0])} | {cell(mv[1])} |\n"
        f"| {cell(mv[2])} | {cell(mv[3])} |\n"
    )

    md = f"""<h1 align="center">⚔️ DRAGONITE vs POLITOED ⚔️</h1>
<p align="center"><em>A turn-based Pokémon battle, playable right here on my profile.</em></p>

<p align="center">
  <img src="{img_rel}" width="640" alt="battle scene"/>
</p>

<h3 align="center">{'🏁 Battle over — start a new one below!' if over else "Choose DRAGONITE's move:"}</h3>

<div align="center">

{table}

</div>

<p align="center">
  <a href="{new_link}">🔄 <b>Start a new battle</b></a>
</p>

---

<details>
<summary><b>How does this work?</b></summary>

GitHub strips JavaScript from READMEs, so this isn't a live game — it's turn-based
by commit. Each move above is a link that opens a pre-filled GitHub Issue. When you
submit it, a GitHub Action runs <code>battle.py</code>, resolves your move and
Politoed's reply, re-renders the animated scene, rewrites this README, and commits.
Refresh in a few seconds to see the result.

<b>Tip:</b> Politoed is a Water type. Think about what beats Water. 💡
</details>
"""
    open(README_PATH, "w").write(md)

def _draw_background(W, H):
    img = Image.new("RGB", (W, H), (170, 214, 236))
    d = ImageDraw.Draw(img)
    for i in range(260):                      # sky gradient
        t = i / 260
        d.line([(0, i), (W, i)], fill=(int(170+t*78), int(214+t*30), int(236+t*12)))
    d.rectangle([0, 250, W, H-92], fill=(150, 206, 138))   # ground
    d.rectangle([0, 250, W, 258], fill=(120, 180, 110))
    d.ellipse([350, 168, 600, 224], fill=(176, 220, 150), outline=(120,180,110), width=3)
    d.ellipse([40, 250, 330, 318], fill=(176, 220, 150), outline=(120,180,110), width=3)
    return img

def _build_overlay(state, W, H):
    """HP boxes + message box on a transparent layer, drawn ON TOP of sprites."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    med = load_font(17, bold=True); sm = load_font(14, bold=True); msgf = load_font(20, bold=True)
    _hp_box(d, 28, 26, POLITOED["name"], state["cpu"]["hp"], POLITOED["max_hp"], med, sm)
    _hp_box(d, W-278, 214, DRAGONITE["name"], state["player"]["hp"], DRAGONITE["max_hp"],
            med, sm, align_right=True)
    mb_y = H-86
    d.rounded_rectangle([10, mb_y, W-10, H-10], radius=12, fill=(40, 44, 64))
    d.rounded_rectangle([16, mb_y+6, W-16, H-16], radius=9, outline=(150,170,210), width=3)
    words, lines_, cur = state["message"].split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if d.textlength(test, font=msgf) > W-70 and cur:
            lines_.append(cur); cur = w
        else:
            cur = test
    if cur: lines_.append(cur)
    for i, ln in enumerate(lines_[:2]):
        d.text((34, mb_y+18+i*26), ln, font=msgf, fill=(244, 244, 250))
    return layer

def render(state):
    """Render the scene. Returns the README-relative image path (gif or png)."""
    W, H = 640, 400
    bg      = _draw_background(W, H)
    overlay = _build_overlay(state, W, H)
    pol = sprite_layers("politoed", W, H)
    dra = sprite_layers("dragonite", W, H)

    def compose(i):
        frame = bg.convert("RGBA")
        frame = Image.alpha_composite(frame, dra[i % len(dra)])   # player behind
        frame = Image.alpha_composite(frame, pol[i % len(pol)])
        frame = Image.alpha_composite(frame, overlay)
        return frame.convert("RGB")

    animated = USE_ANIMATION and (len(pol) > 1 or len(dra) > 1)
    # Unique filename per render so GitHub's image cache (camo) can't serve a stale copy.
    stamp = f"{int(time.time())}-{state['turn']}"
    if not animated:
        rel = f"game/battle-{stamp}.png"
        compose(0).save(os.path.join(ROOT, rel))
        _cleanup_frames(rel)
        return rel

    # number of frames: seamless LCM loop when small, else bounded
    n = math.lcm(len(pol), len(dra))
    if n > MAX_FRAMES:
        n = min(MAX_FRAMES, max(len(pol), len(dra)))
    base_frames = [compose(i) for i in range(n)]
    pal = base_frames[0].convert("P", palette=Image.ADAPTIVE, colors=256)
    pframes = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in base_frames]
    rel = f"game/battle-{stamp}.gif"
    pframes[0].save(os.path.join(ROOT, rel), save_all=True, append_images=pframes[1:],
                    duration=FRAME_MS, loop=0, optimize=True, disposal=2)
    _cleanup_frames(rel)
    return rel

def _cleanup_frames(keep_rel):
    """Delete every previous battle image so only the current frame remains."""
    keep = os.path.abspath(os.path.join(ROOT, keep_rel))
    pats = ["battle-*.gif", "battle-*.png", "battle.gif", "battle.png"]
    for pat in pats:
        for f in glob.glob(os.path.join(ROOT, "game", pat)):
            if os.path.abspath(f) != keep:
                try: os.remove(f)
                except OSError: pass

if __name__ == "__main__":
    os.makedirs(os.path.join(ROOT, "game"), exist_ok=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--move")
    ap.add_argument("--new", action="store_true")
    args = ap.parse_args()

    mv = (args.move or "").strip().lower()
    if args.new or mv == "new" or not os.path.exists(STATE_PATH):
        state = new_state()
    else:
        state = json.load(open(STATE_PATH))
        if mv in DRAGONITE["moves"] and not state.get("over"):
            resolve(state, mv)
        elif mv and mv not in ("new",):
            print(f"Ignored unknown move: {mv!r}")

    json.dump(state, open(STATE_PATH, "w"), indent=2)
    img_rel = render(state)
    render_readme(state, img_rel)
    print(f"{state['message']}  [{img_rel}]")
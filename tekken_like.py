# tekken_like.py
# A tiny 2D "Tekken-like" fighting prototype using pygame (no external assets).
# Run with:  pip install pygame
#            python tekken_like.py
#
# Features:
# - 2 Players (local): movement, jump, crouch, block, punch, kick
# - Health bars, round timer, best-of-3 rounds
# - Hitboxes & hurtboxes (rectangles), pushback, chip damage on block
# - Pause (ESC), restart (R), quit (Q)
#
# DISCLAIMER: This is only a lightweight learning prototype, not a full Tekken clone.
# Feel free to extend moves, add sprites, sound, combos, and AI.

import sys
import math
import pygame
from pygame import Rect

# ---------------------------- Config ----------------------------
WIDTH, HEIGHT = 1000, 560
GROUND_Y = HEIGHT - 90
FPS = 60

P1_COLOR = (40, 170, 255)
P2_COLOR = (255, 100, 80)
HITBOX_COLOR = (255, 230, 100)
BLOCK_COLOR = (120, 120, 255)

BG_TOP = (25, 27, 35)
BG_BOTTOM = (10, 10, 16)

# Gameplay tuning
GRAVITY = 0.85
FRICTION = 0.85
MOVE_SPEED = 6.0
JUMP_SPEED = -16.5
MAX_FALL = 18

PUSHBACK = 7
BLOCK_PUSHBACK = 4
HITSTOP = 4  # frames of freeze on hit

PUNCH_RANGE = (45, 16)   # width, height of attack box
KICK_RANGE  = (60, 18)
PUNCH_DMG = 8
KICK_DMG = 12
BLOCK_CHIP = 0.2  # 20% damage applies as chip on block

ROUND_TIME = 60  # seconds
BEST_OF = 3      # first to 2

# Key binds
# Player 1: Move A/D, Jump W, Crouch S, Punch J, Kick K, Block L
# Player 2: Arrows, Punch Numpad1 (or 1), Kick Numpad2 (or 2), Block RSHIFT (or 3)
KEYS = {
    "p1": {"left": pygame.K_a, "right": pygame.K_d, "up": pygame.K_w, "down": pygame.K_s,
           "punch": pygame.K_j, "kick": pygame.K_k, "block": pygame.K_l},
    "p2": {"left": pygame.K_LEFT, "right": pygame.K_RIGHT, "up": pygame.K_UP, "down": pygame.K_DOWN,
           "punch": pygame.K_KP1, "kick": pygame.K_KP2, "block": pygame.K_RSHIFT,
           "punch_alt": pygame.K_1, "kick_alt": pygame.K_2, "block_alt": pygame.K_3},
}

# ---------------------------- Helpers ----------------------------
def draw_vertical_gradient(surf, top_color, bottom_color):
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        r = int(top_color[0] * (1 - t) + bottom_color[0] * t)
        g = int(top_color[1] * (1 - t) + bottom_color[1] * t)
        b = int(top_color[2] * (1 - t) + bottom_color[2] * t)
        pygame.draw.line(surf, (r, g, b), (0, y), (WIDTH, y))

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def sign(x):
    return -1 if x < 0 else (1 if x > 0 else 0)

# ---------------------------- Fighter ----------------------------
class Fighter:
    def __init__(self, x, facing, color, name):
        self.w, self.h = 56, 98
        self.rect = Rect(x, GROUND_Y - self.h, self.w, self.h)
        self.velocity = pygame.Vector2(0,0)
        self.on_ground = True
        self.crouching = False
        self.blocking = False
        self.facing = facing  # -1 left, +1 right
        self.color = color
        self.name = name

        self.max_hp = 100
        self.hp = float(self.max_hp)
        self.rounds_won = 0

        # attack state
        self.attack_cooldown = 0
        self.attack_type = None  # "punch" or "kick"
        self.attack_timer = 0
        self.hitstop = 0
        self.hit_this_attack = False

    def hurtbox(self):
        # shrink when crouching
        if self.crouching and self.on_ground:
            return Rect(self.rect.x, self.rect.bottom - self.h//2, self.w, self.h//2)
        return self.rect.copy()

    def attack_box(self):
        if self.attack_type is None:
            return None
        if self.attack_type == "punch":
            aw, ah = PUNCH_RANGE
            frame_total = 14
            # simple startup/active/recovery windows
            startup, active = 4, 5
        else:
            aw, ah = KICK_RANGE
            frame_total = 18
            startup, active = 6, 6

        # Build box in front
        x = self.hurtbox().centerx + self.facing * (self.w//2 - 4)
        y = self.hurtbox().centery - ah//2
        hit_rect = Rect(0,0,aw,ah)
        if self.facing > 0:
            hit_rect.topleft = (x, y)
        else:
            hit_rect.topright = (x, y)

        # Only active during active frames
        if self.attack_timer < startup or self.attack_timer >= (startup + active):
            return None
        return hit_rect

    def start_attack(self, kind):
        if self.attack_cooldown > 0 or self.hitstop > 0:
            return
        if self.crouching and self.on_ground and kind == "kick":
            # allow low kick slightly faster
            pass
        self.attack_type = kind
        self.attack_timer = 0
        self.attack_cooldown = 0
        self.hit_this_attack = False

    def apply_gravity(self):
        if not self.on_ground:
            self.velocity.y = clamp(self.velocity.y + GRAVITY, -999, MAX_FALL)

    def update(self, keys, opp: "Fighter", bounds: Rect):
        # Recover from hitstop first
        if self.hitstop > 0:
            self.hitstop -= 1
            return

        # Face opponent
        if opp.rect.centerx != self.rect.centerx:
            self.facing = 1 if opp.rect.centerx > self.rect.centerx else -1

        # Basic movement
        move_left = keys[KEYS[self.name]["left"]]
        move_right = keys[KEYS[self.name]["right"]]

        # P2 alternate buttons handling
        if self.name == "p2":
            # include alt bindings
            punch_pressed = keys[KEYS["p2"]["punch"]] or keys[KEYS["p2"]["punch_alt"]]
            kick_pressed = keys[KEYS["p2"]["kick"]] or keys[KEYS["p2"]["kick_alt"]]
            block_down = keys[KEYS["p2"]["block"]] or keys[KEYS["p2"]["block_alt"]]
        else:
            punch_pressed = keys[KEYS["p1"]["punch"]]
            kick_pressed = keys[KEYS["p1"]["kick"]]
            block_down = keys[KEYS["p1"]["block"]]

        up = keys[KEYS[self.name]["up"]]
        down = keys[KEYS[self.name]["down"]]

        self.blocking = bool(block_down) and self.on_ground
        self.crouching = bool(down) and self.on_ground and not self.blocking

        # you cannot walk forward while blocking
        if not self.blocking:
            if move_left and not move_right:
                self.velocity.x = -MOVE_SPEED
            elif move_right and not move_left:
                self.velocity.x = MOVE_SPEED
            else:
                self.velocity.x *= FRICTION
                if abs(self.velocity.x) < 0.15: self.velocity.x = 0
        else:
            self.velocity.x *= FRICTION

        # jump
        if up and self.on_ground and not self.blocking:
            self.velocity.y = JUMP_SPEED
            self.on_ground = False
            self.crouching = False

        # attacks
        if punch_pressed:
            self.start_attack("punch")
        elif kick_pressed:
            self.start_attack("kick")

        # Advance attack timer
        if self.attack_type:
            self.attack_timer += 1
            # simple end of move timing
            end_frame = 14 if self.attack_type == "punch" else 18
            if self.attack_timer >= end_frame:
                self.attack_type = None
                self.attack_timer = 0
                self.attack_cooldown = 8

        if self.attack_cooldown > 0:
            self.attack_cooldown -= 1

        # gravity
        self.apply_gravity()

        # Move & collide with ground
        self.rect.x = int(self.rect.x + self.velocity.x)
        # keep within bounds
        if self.rect.left < bounds.left: self.rect.left = bounds.left
        if self.rect.right > bounds.right: self.rect.right = bounds.right

        self.rect.y = int(self.rect.y + self.velocity.y)
        if self.rect.bottom >= GROUND_Y:
            self.rect.bottom = GROUND_Y
            self.velocity.y = 0
            self.on_ground = True

        # Prevent overlapping fighters: simple push apart
        if self.rect.colliderect(opp.rect):
            overlap = self.rect.clip(opp.rect)
            if overlap.width < overlap.height:
                shift = overlap.width // 2 + 1
                if self.rect.centerx < opp.rect.centerx:
                    self.rect.x -= shift
                    opp.rect.x += shift
                else:
                    self.rect.x += shift
                    opp.rect.x -= shift

    def receive_hit(self, dmg, direction, blocked=False):
        if self.blocking and blocked:
            chip = max(1, int(dmg * BLOCK_CHIP))
            self.hp -= chip
            push = BLOCK_PUSHBACK * direction
        else:
            self.hp -= dmg
            push = PUSHBACK * direction
        self.hp = clamp(self.hp, 0, self.max_hp)
        # Pushback horizontally (only when on ground)
        if self.on_ground:
            self.rect.x += push
        # Hitstop
        self.hitstop = HITSTOP

# ---------------------------- UI ----------------------------
def draw_health_bar(surf, x, y, w, h, hp, max_hp, color, align_right=False):
    ratio = hp / max_hp
    ratio = clamp(ratio, 0, 1)
    bg = (40,40,40)
    pygame.draw.rect(surf, bg, (x, y, w, h), border_radius=6)
    filled = int(w * ratio)
    if align_right:
        rect = Rect(x + (w - filled), y, filled, h)
    else:
        rect = Rect(x, y, filled, h)
    pygame.draw.rect(surf, color, rect, border_radius=6)
    pygame.draw.rect(surf, (200,200,200), (x, y, w, h), 2, border_radius=6)

def draw_timer(surf, center, seconds, font):
    txt = font.render(f"{int(seconds):02d}", True, (250, 250, 250))
    r = txt.get_rect(center=center)
    surf.blit(txt, r)

def draw_round_counters(surf, p1_wins, p2_wins, font):
    x1, x2, y = 40, WIDTH - 40, 24
    for i in range(BEST_OF//2 + 1):
        c1 = (240, 240, 240) if i < p1_wins else (80, 80, 80)
        c2 = (240, 240, 240) if i < p2_wins else (80, 80, 80)
        pygame.draw.circle(surf, c1, (x1 + i*18, y), 6)
        pygame.draw.circle(surf, c2, (x2 - i*18, y), 6)

def banner_text(surf, msg, font_big):
    txt = font_big.render(msg, True, (255, 255, 255))
    r = txt.get_rect(center=(WIDTH//2, HEIGHT//2 - 140))
    surf.blit(txt, r)

# ---------------------------- Game ----------------------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Tiny Tekken-like (Prototype)")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 24)
        self.font_big = pygame.font.SysFont("consolas", 44, bold=True)

        self.bounds = Rect(40, 0, WIDTH-80, HEIGHT)

        self.reset_match()

        self.paused = False

    def reset_match(self):
        self.p1 = Fighter(200, 1, P1_COLOR, "p1")
        self.p2 = Fighter(WIDTH-260, -1, P2_COLOR, "p2")
        self.round_time = ROUND_TIME
        self.freeze_timer = 60  # "Ready... Fight!" moment

    def round_over(self, winner_name=None):
        if winner_name == "p1":
            self.p1.rounds_won += 1
        elif winner_name == "p2":
            self.p2.rounds_won += 1

        # Check match end
        needed = (BEST_OF // 2) + 1
        if self.p1.rounds_won >= needed or self.p2.rounds_won >= needed:
            # Reset entire match after a short display
            self.freeze_timer = 120
            self.round_time = 0
            self.match_end = True
        else:
            # New round
            self.p1.hp = self.p1.max_hp
            self.p2.hp = self.p2.max_hp
            self.p1.rect.topleft = (200, GROUND_Y - self.p1.h)
            self.p2.rect.topright = (WIDTH-200, GROUND_Y - self.p2.h)
            self.p1.velocity.update(0,0)
            self.p2.velocity.update(0,0)
            self.p1.attack_type = None
            self.p2.attack_type = None
            self.freeze_timer = 60
            self.round_time = ROUND_TIME
            self.match_end = False

    def handle_hits(self):
        # attack hit detection
        for atk, dfd in [(self.p1, self.p2), (self.p2, self.p1)]:
            box = atk.attack_box()
            if box and not atk.hit_this_attack:
                hb = dfd.hurtbox()
                if box.colliderect(hb):
                    # Determine if defender is blocking correctly (hold block; crouch still block mid here)
                    blocked = dfd.blocking
                    dmg = PUNCH_DMG if atk.attack_type == "punch" else KICK_DMG
                    dfd.receive_hit(dmg, direction=sign(atk.facing), blocked=blocked)
                    atk.hit_this_attack = True
                    # Hitstop for attacker as well
                    atk.hitstop = HITSTOP

    def update(self, dt):
        keys = pygame.key.get_pressed()

        if not self.paused and self.freeze_timer <= 0 and self.round_time > 0:
            self.p1.update(keys, self.p2, self.bounds)
            self.p2.update(keys, self.p1, self.bounds)
            self.handle_hits()

            # Timer
            self.round_time -= dt
            if self.round_time <= 0:
                # decide by remaining HP
                if self.p1.hp > self.p2.hp:
                    self.round_over("p1")
                elif self.p2.hp > self.p1.hp:
                    self.round_over("p2")
                else:
                    # draw -> nobody gets a round, restart round
                    self.round_over(None)

            # HP KO check
            if self.p1.hp <= 0:
                self.round_over("p2")
            elif self.p2.hp <= 0:
                self.round_over("p1")

        else:
            # Freeze countdown (round intro / match end hold)
            if self.freeze_timer > 0:
                self.freeze_timer -= 1

    def draw_stage(self, surf):
        draw_vertical_gradient(surf, BG_TOP, BG_BOTTOM)
        # simple "arena" floor
        pygame.draw.rect(surf, (26, 34, 40), (0, GROUND_Y, WIDTH, HEIGHT-GROUND_Y))
        # floor stripes
        for i in range(0, WIDTH, 40):
            pygame.draw.rect(surf, (36, 40, 50), (i, GROUND_Y + 40, 28, 10), border_radius=3)

        # bounds lines
        pygame.draw.rect(surf, (70, 80, 100), (self.bounds.left, 60, self.bounds.width, GROUND_Y-40), 2, border_radius=8)

    def draw_fighter(self, surf, f: Fighter):
        hb = f.hurtbox()
        color = f.color if not f.blocking else BLOCK_COLOR
        pygame.draw.rect(surf, color, hb, border_radius=8)
        # head
        head = Rect(0,0, hb.width//2, hb.width//2)
        head.midbottom = (hb.centerx, hb.top + 4)
        pygame.draw.ellipse(surf, (230, 230, 230), head)

        # fists / attack box
        atk_box = f.attack_box()
        if atk_box:
            pygame.draw.rect(surf, HITBOX_COLOR, atk_box, border_radius=6)

        # simple "eyes" to show facing
        eye_y = head.centery - 4
        dx = 6 * f.facing
        pygame.draw.circle(surf, (10,10,10), (head.centerx + dx, eye_y), 3)

    def render(self):
        self.draw_stage(self.screen)

        # UI
        draw_health_bar(self.screen, 40, 20, 360, 18, self.p1.hp, self.p1.max_hp, P1_COLOR, align_right=False)
        draw_health_bar(self.screen, WIDTH - 400, 20, 360, 18, self.p2.hp, self.p2.max_hp, P2_COLOR, align_right=True)
        draw_round_counters(self.screen, self.p1.rounds_won, self.p2.rounds_won, self.font)
        draw_timer(self.screen, (WIDTH//2, 28), self.round_time, self.font)

        # Fighters
        self.draw_fighter(self.screen, self.p1)
        self.draw_fighter(self.screen, self.p2)

        # Banners
        if self.freeze_timer > 0 and self.round_time == ROUND_TIME and not getattr(self, "match_end", False):
            banner_text(self.screen, "READY... FIGHT!", self.font_big)
        if getattr(self, "match_end", False):
            if self.p1.rounds_won > self.p2.rounds_won:
                banner_text(self.screen, "P1 WINS THE MATCH!", self.font_big)
            elif self.p2.rounds_won > self.p1.rounds_won:
                banner_text(self.screen, "P2 WINS THE MATCH!", self.font_big)
            else:
                banner_text(self.screen, "DRAW GAME!", self.font_big)

        # Controls help
        help_lines = [
            "P1: A/D move, W jump, S crouch, J punch, K kick, L block",
            "P2: Arrows move, UP jump, DOWN crouch, KP1/1 punch, KP2/2 kick, RSHIFT/3 block",
            "Esc: Pause | R: Restart Match | Q: Quit",
        ]
        for i, line in enumerate(help_lines):
            txt = self.font.render(line, True, (210, 210, 210))
            self.screen.blit(txt, (40, HEIGHT - 80 + i*22))

    def run(self):
        self.match_end = False
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.paused = not self.paused
                    if event.key == pygame.K_q:
                        pygame.quit(); sys.exit()
                    if event.key == pygame.K_r:
                        self.reset_match()

            if not self.paused:
                self.update(dt)

            self.render()
            pygame.display.flip()

if __name__ == "__main__":
    try:
        Game().run()
    except Exception as e:
        print("Error:", e)
        print("Make sure you installed pygame:  pip install pygame")

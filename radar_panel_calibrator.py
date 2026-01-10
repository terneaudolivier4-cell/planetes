# radar_panel_calibrator.py
# -------------------------------------------------------------
# Outil de calibration du panneau radar dans le cockpit
# 1) Affiche le cockpit (cover) + le radar rendu dans un FBO
# 2) Affiche les 4 coins (TL, TR, BR, BL) en couleur
# 3) Permet de déplacer les 4 coins à la souris (drag & drop)
# 4) Renvoie le résultat (console) et sauvegarde en JSON
# -------------------------------------------------------------

import sys, os, math, json
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

# ---------------------------- Helpers GL/Textures ----------------------------

def load_image_rgba(path):
    surf = pygame.image.load(path).convert_alpha()
    return surf

def create_texture_from_surface(surface, flip=False):
    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    w, h = surface.get_size()
    data = pygame.image.tostring(surface, 'RGBA', flip)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    glBindTexture(GL_TEXTURE_2D, 0)
    return tex, (w, h)

# Fullscreen textured quad with fit/cover modes (cover only used here)

def draw_fullscreen_textured_quad_cover(tex_id, tex_w, tex_h, win_w, win_h, alpha=1.0):
    r_tex = tex_w / float(tex_h)
    r_win = win_w / float(win_h)
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, win_w, win_h, 0, -1, 1)
    glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
    glDisable(GL_DEPTH_TEST)
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glColor4f(1,1,1,alpha)
    # Crop UVs to achieve 'cover'
    u0, v0, u1, v1 = 0.0, 0.0, 1.0, 1.0
    x0, y0, x1, y1 = 0.0, 0.0, win_w, win_h
    if r_tex > r_win:
        vis_tex_w = r_win * tex_h
        pad_w = (tex_w - vis_tex_w) / (2.0 * tex_w)
        u0 = pad_w; u1 = 1.0 - pad_w
    elif r_tex < r_win:
        vis_tex_h = tex_w / r_win
        pad_h = (tex_h - vis_tex_h) / (2.0 * tex_h)
        v0 = pad_h; v1 = 1.0 - pad_h
    glBegin(GL_QUADS)
    glTexCoord2f(u0, v0); glVertex2f(x0, y0)
    glTexCoord2f(u1, v0); glVertex2f(x1, y0)
    glTexCoord2f(u1, v1); glVertex2f(x1, y1)
    glTexCoord2f(u0, v1); glVertex2f(x0, y1)
    glEnd()
    glBindTexture(GL_TEXTURE_2D, 0)
    glDisable(GL_TEXTURE_2D)
    glEnable(GL_DEPTH_TEST)
    glMatrixMode(GL_MODELVIEW);  glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

# ---------------------------- Radar FBO ----------------------------

def create_radar_fbo(size=512):
    fbo = glGenFramebuffers(1)
    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size, size, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    glBindTexture(GL_TEXTURE_2D, 0)
    rbo = glGenRenderbuffers(1)
    glBindRenderbuffer(GL_RENDERBUFFER, rbo)
    glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, size, size)
    glBindRenderbuffer(GL_RENDERBUFFER, 0)
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0)
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, rbo)
    status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
    glBindFramebuffer(GL_FRAMEBUFFER, 0)
    if status != GL_FRAMEBUFFER_COMPLETE:
        print('[WARN] FBO incomplete:', status)
        return 0, 0, 0
    return fbo, tex, rbo

def render_radar_to_fbo(fbo, size, enemies=None):
    if fbo == 0: return
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)
    glViewport(0, 0, size, size)
    glDisable(GL_DEPTH_TEST)
    glClearColor(0.05,0.05,0.08,1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, size, size, 0, -1, 1)
    glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
    # Draw circular radar + crosshair
    cx, cy = size//2, size//2
    r = int(size*0.42)
    glColor3f(0.45,0.7,0.95); seg=128
    for k in (1/3.0, 2/3.0, 1.0):
        rr = r*k
        glBegin(GL_LINE_LOOP)
        for i in range(seg):
            a = 2.0*math.pi*i/seg
            glVertex2f(cx + rr*math.cos(a), cy + rr*math.sin(a))
        glEnd()
    glBegin(GL_LINES)
    glVertex2f(cx-6, cy); glVertex2f(cx+6, cy)
    glVertex2f(cx, cy-6); glVertex2f(cx, cy+6)
    glEnd()
    # Optionally draw a few enemy dots
    glPointSize(4); glColor3f(1.0,0.3,0.3); glBegin(GL_POINTS)
    if enemies:
        for (ex,ez) in enemies:
            glVertex2f(cx + ex, cy + ez)
    glEnd()
    glEnable(GL_DEPTH_TEST)
    glMatrixMode(GL_MODELVIEW);  glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix()
    glBindFramebuffer(GL_FRAMEBUFFER, 0)

# ---------------------------- Calibrator App ----------------------------

class Calibrator:
    def __init__(self, win_w=1280, win_h=720):
        pygame.init(); pygame.font.init()
        pygame.display.set_mode((win_w, win_h), DOUBLEBUF | OPENGL)
        pygame.display.set_caption('Radar Panel Calibrator')
        pygame.event.set_grab(False); pygame.mouse.set_visible(True)
        glEnable(GL_DEPTH_TEST); glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glClearColor(0.02,0.02,0.06,1.0)
        self.w, self.h = win_w, win_h
        self.clock = pygame.time.Clock()
        # Load cockpit overlay texture (required)
        self.tex_cockpit = 0; self.cockpit_w = 1; self.cockpit_h = 1
        try:
            surf = load_image_rgba('cockpit_overlay.png')
            self.tex_cockpit, (self.cockpit_w, self.cockpit_h) = create_texture_from_surface(surf, False)
        except Exception as e:
            print('[ERROR] cockpit_overlay.png introuvable:', e)
        # Create radar FBO
        self.radar_size = 512
        self.fbo, self.radar_tex, self.rbo = create_radar_fbo(self.radar_size)
        # Default UVs (normalized screen coords) TL, TR, BR, BL
        self.uv = [
            (0.385, 0.718),  # TL
            (0.615, 0.719),  # TR
            (0.592, 0.905),  # BR
            (0.408, 0.905),  # BL
        ]
        # Dragging state
        self.drag_idx = None
        self.threshold_px = 24  # selection radius in pixels
        # Font for text
        self.font = pygame.font.Font(None, 24)

    # Convert normalized (x,y) to pixels
    def to_px(self, pt):
        return (int(pt[0] * self.w), int(pt[1] * self.h))
    # Convert pixel (x,y) to normalized
    def to_norm(self, pos):
        return (max(0.0, min(1.0, pos[0] / float(self.w))), max(0.0, min(1.0, pos[1] / float(self.h))))

    def draw_text_2d(self, text, x, y, color=(255,255,255,255)):
        surf = self.font.render(text, True, color)
        tex, (tw, th) = create_texture_from_surface(surf, False)
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, self.w, self.h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
        glDisable(GL_DEPTH_TEST); glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D, tex)
        glColor4f(1,1,1,1); glBegin(GL_QUADS)
        glTexCoord2f(0,0); glVertex2f(x, y)
        glTexCoord2f(1,0); glVertex2f(x+tw, y)
        glTexCoord2f(1,1); glVertex2f(x+tw, y+th)
        glTexCoord2f(0,1); glVertex2f(x, y+th)
        glEnd()
        glBindTexture(GL_TEXTURE_2D, 0); glDisable(GL_TEXTURE_2D); glEnable(GL_DEPTH_TEST)
        glMatrixMode(GL_MODELVIEW);  glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)
        glDeleteTextures([tex])

    def blit_radar_to_panel(self):
        # Expect radar_tex bound to full 0..1 UV; project onto quad defined by self.uv
        TL = self.to_px(self.uv[0]); TR = self.to_px(self.uv[1]); BR = self.to_px(self.uv[2]); BL = self.to_px(self.uv[3])
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, self.w, self.h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
        glDisable(GL_DEPTH_TEST); glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D, self.radar_tex)
        glColor4f(1,1,1,1)
        glBegin(GL_QUADS)
        glTexCoord2f(0.0,0.0); glVertex2f(*TL)
        glTexCoord2f(1.0,0.0); glVertex2f(*TR)
        glTexCoord2f(1.0,1.0); glVertex2f(*BR)
        glTexCoord2f(0.0,1.0); glVertex2f(*BL)
        glEnd()
        glBindTexture(GL_TEXTURE_2D, 0); glDisable(GL_TEXTURE_2D); glEnable(GL_DEPTH_TEST)
        glMatrixMode(GL_MODELVIEW);  glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

    def draw_corners(self):
        pts_px = [self.to_px(p) for p in self.uv]
        colors = [(1,0,0), (0,1,0), (0,0,1), (1,1,0)]  # TL, TR, BR, BL
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, self.w, self.h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
        glDisable(GL_DEPTH_TEST)
        for (x,y), c in zip(pts_px, colors):
            glPointSize(10)
            glColor3f(*c)
            glBegin(GL_POINTS)
            glVertex2f(x, y)
            glEnd()
        glEnable(GL_DEPTH_TEST)
        glMatrixMode(GL_MODELVIEW);  glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

    def pick_corner(self, mouse_px):
        # Return index of nearest corner within threshold
        best_i, best_d2 = None, float('inf')
        for i, p in enumerate(self.uv):
            px = self.to_px(p)
            dx = mouse_px[0] - px[0]
            dy = mouse_px[1] - px[1]
            d2 = dx*dx + dy*dy
            if d2 < best_d2:
                best_d2, best_i = d2, i
        if math.sqrt(best_d2) <= self.threshold_px:
            return best_i
        return None

    def save_json(self, path='radar_panel_uv.json'):
        data = {
            'TL': {'x': self.uv[0][0], 'y': self.uv[0][1]},
            'TR': {'x': self.uv[1][0], 'y': self.uv[1][1]},
            'BR': {'x': self.uv[2][0], 'y': self.uv[2][1]},
            'BL': {'x': self.uv[3][0], 'y': self.uv[3][1]},
            'list': self.uv,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print('[SAVE]', path)

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(120) / 1000.0
            # --- Input ---
            for ev in pygame.event.get():
                if ev.type == QUIT:
                    running = False
                elif ev.type == KEYDOWN:
                    if ev.key == K_ESCAPE:
                        running = False
                    elif ev.key == K_RETURN:
                        # Print result and quit
                        print('[RESULT] radar_panel_uv =', self.uv)
                        self.save_json()
                        running = False
                    elif ev.key == K_s:
                        self.save_json()
                    elif ev.key == K_r:
                        # Reset to defaults
                        self.uv = [(0.385,0.718),(0.615,0.719),(0.592,0.905),(0.408,0.905)]
                        print('[RESET] Defaults applied')
                elif ev.type == MOUSEBUTTONDOWN and ev.button == 1:
                    mx, my = pygame.mouse.get_pos()
                    self.drag_idx = self.pick_corner((mx, my))
                elif ev.type == MOUSEBUTTONUP and ev.button == 1:
                    self.drag_idx = None
                elif ev.type == MOUSEMOTION:
                    if self.drag_idx is not None:
                        mx, my = pygame.mouse.get_pos()
                        self.uv[self.drag_idx] = self.to_norm((mx, my))
            # --- Render radar to FBO ---
            render_radar_to_fbo(self.fbo, self.radar_size)
            # IMPORTANT: reset viewport to window size
            glViewport(0, 0, self.w, self.h)
            # --- Draw scene ---
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            # Cockpit full cover
            if self.tex_cockpit != 0:
                draw_fullscreen_textured_quad_cover(self.tex_cockpit, self.cockpit_w, self.cockpit_h, self.w, self.h, 1.0)
            # Blit radar to the panel quad
            self.blit_radar_to_panel()
            # Draw corner handles
            self.draw_corners()
            # UI tips
            self.draw_text_2d('Drag & drop les coins (TL rouge, TR vert, BR bleu, BL jaune)', 16, 14, (240,240,255,255))
            self.draw_text_2d('[S] Sauvegarde JSON  [Enter] Valider/Sortir  [R] Reset  [Esc] Quit', 16, 40, (240,240,255,255))
            # Present
            pygame.display.flip()
        pygame.quit(); sys.exit()

if __name__ == '__main__':
    Calibrator().run()

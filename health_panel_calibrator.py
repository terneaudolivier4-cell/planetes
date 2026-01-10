# health_panel_calibrator.py
# -------------------------------------------------------------------
# Interactif : ajuste le panneau de santé (coin bas-droit cockpit)
# - Affiche le cockpit (cover)
# - Affiche le panneau Santé (vaisseau + aura + %)
# - Permet de déplacer ses 4 coins avec la souris (TL,TR,BR,BL)
# - Sauvegarde health_panel_uv.json et affiche la liste à valider
# -------------------------------------------------------------------
import sys, json, math
import pygame
from pygame.locals import *
from OpenGL.GL import *

from ui_health_panel import (
    create_health_fbo, make_ship_icon, make_aura_texture,
    render_health_fbo, blit_health_to_panel, load_health_panel_uv
)

# --- Texture helper ---

def load_image_rgba(path):
    return pygame.image.load(path).convert_alpha()

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

# --- Draw full cockpit in cover mode ---

def draw_cockpit_cover(tex, tw, th, w, h):
    r_tex = tw/float(th); r_win = w/float(h)
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0,w,h,0,-1,1)
    glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
    glDisable(GL_DEPTH_TEST); glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D, tex)
    glColor4f(1,1,1,1)
    u0,v0,u1,v1 = 0.0,0.0,1.0,1.0
    if r_tex>r_win:
        vis = r_win*th
        pad = (tw - vis)/(2.0*tw)
        u0 = pad; u1 = 1.0 - pad
    elif r_tex<r_win:
        vis = tw/r_win
        pad = (th - vis)/(2.0*th)
        v0 = pad; v1 = 1.0 - pad
    glBegin(GL_QUADS)
    glTexCoord2f(u0,v0); glVertex2f(0,0)
    glTexCoord2f(u1,v0); glVertex2f(w,0)
    glTexCoord2f(u1,v1); glVertex2f(w,h)
    glTexCoord2f(u0,v1); glVertex2f(0,h)
    glEnd()
    glBindTexture(GL_TEXTURE_2D,0); glDisable(GL_TEXTURE_2D); glEnable(GL_DEPTH_TEST)
    glMatrixMode(GL_MODELVIEW);  glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

# --- App ---

class HealthCalibrator:
    def __init__(self, w=1280, h=720):
        pygame.init(); pygame.font.init()
        pygame.display.set_mode((w,h), DOUBLEBUF|OPENGL)
        pygame.display.set_caption('Health Panel Calibrator')
        glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_DEPTH_TEST)
        self.clock = pygame.time.Clock(); self.w,self.h=w,h

        # cockpit texture
        try:
            surf = load_image_rgba('cockpit_overlay.png')
            self.tex_cockpit, (self.cw,self.ch) = create_texture_from_surface(surf, False)
        except Exception as e:
            print('[ERROR] cockpit_overlay.png manquant:', e); self.tex_cockpit=0; self.cw=self.ch=1

        # health FBO & sprites
        self.health_fbo, self.health_tex, self.health_rbo, self.health_size = create_health_fbo(256)
        self.ship_tex, _ = make_ship_icon(128)
        self.aura_tex, _ = make_aura_texture(256)
        self.font = pygame.font.Font(None, 28)
        self.health = 1.0

        # UV
        self.uv = load_health_panel_uv()
        self.drag_idx = None; self.pick_radius_px=22

    def to_px(self, p): return (int(p[0]*self.w), int(p[1]*self.h))
    def to_norm(self, pos):
        return (max(0,min(1,pos[0]/float(self.w))), max(0,min(1,pos[1]/float(self.h))))

    def pick_corner(self, mouse_px):
        best, bestd2=None, 1e9
        for i,p in enumerate(self.uv):
            x,y=self.to_px(p); dx=mouse_px[0]-x; dy=mouse_px[1]-y; d2=dx*dx+dy*dy
            if d2<bestd2: best, bestd2=i, d2
        return best if math.sqrt(bestd2)<=self.pick_radius_px else None

    def draw_handles(self):
        pts=[self.to_px(p) for p in self.uv]
        cols=[(1,0.2,0.2),(0.2,1,0.2),(0.2,0.2,1),(1,1,0.2)]
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0,self.w,self.h,0,-1,1)
        glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
        glDisable(GL_DEPTH_TEST)
        for (x,y),c in zip(pts,cols):
            glPointSize(10); glColor3f(*c); glBegin(GL_POINTS); glVertex2f(x,y); glEnd()
        glEnable(GL_DEPTH_TEST)
        glMatrixMode(GL_MODELVIEW);  glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

    def save_json(self, path='health_panel_uv.json'):
        d={
            'TL': {'x': self.uv[0][0], 'y': self.uv[0][1]},
            'TR': {'x': self.uv[1][0], 'y': self.uv[1][1]},
            'BR': {'x': self.uv[2][0], 'y': self.uv[2][1]},
            'BL': {'x': self.uv[3][0], 'y': self.uv[3][1]},
            'list': self.uv,
        }
        with open(path,'w',encoding='utf-8') as f: json.dump(d,f,indent=2)
        print('[SAVE]', path)

    def run(self):
        running=True
        while running:
            dt=self.clock.tick(120)/1000.0
            for ev in pygame.event.get():
                if ev.type==QUIT: running=False
                elif ev.type==KEYDOWN:
                    if ev.key==K_ESCAPE: running=False
                    elif ev.key==K_s: self.save_json()
                    elif ev.key==K_RETURN: self.save_json(); print('[RESULT] health_panel_uv =', self.uv); running=False
                    elif ev.key==K_UP:   self.health=min(1.0, self.health+0.05)
                    elif ev.key==K_DOWN: self.health=max(0.0, self.health-0.05)
                elif ev.type==MOUSEBUTTONDOWN and ev.button==1:
                    self.drag_idx = self.pick_corner(pygame.mouse.get_pos())
                elif ev.type==MOUSEBUTTONUP and ev.button==1:
                    self.drag_idx=None
                elif ev.type==MOUSEMOTION and self.drag_idx is not None:
                    mx,my=pygame.mouse.get_pos(); self.uv[self.drag_idx]=self.to_norm((mx,my))

            # render health in FBO
            render_health_fbo(self.health_fbo, self.health_size, self.ship_tex, self.aura_tex, self.health, self.font)

            # reset viewport for screen
            glViewport(0,0,self.w,self.h)
            glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)

            # draw cockpit
            if self.tex_cockpit!=0:
                draw_cockpit_cover(self.tex_cockpit, self.cw, self.ch, self.w, self.h)

            # blit health panel
            blit_health_to_panel(self.health_tex, self.uv, self.w, self.h)
            self.draw_handles()

            pygame.display.set_caption(f'Health Panel Calibrator  |  Health: {int(self.health*100)}%  |  [Up/Down] +/-  [S] Save  [Enter] Validate')
            pygame.display.flip()

        pygame.quit(); sys.exit()

if __name__=='__main__':
    HealthCalibrator().run()

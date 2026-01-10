# progress_panel_calibrator.py
# -------------------------------------------------------------------
# Interactif : ajuste le panneau de progression (coin bas-droite cockpit)
# - Affiche le cockpit (cover)
# - Affiche un panneau Progress (wave number + progress bar)
# - Permet de déplacer ses 4 coins avec la souris (TL,TR,BR,BL)
# - Sauvegarde progress_panel_uv.json
# -------------------------------------------------------------------
import sys, json, math
import pygame
from pygame.locals import *
from OpenGL.GL import *

from space_shooter_core import create_texture_from_surface, load_image_rgba
from ui_health_panel import create_health_fbo

# --- Draw full cockpit in cover mode (copied/adapted) ---

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

# --- Calibrator ---
class ProgressCalibrator:
    def __init__(self,w=1280,h=720):
        pygame.init(); pygame.font.init()
        pygame.display.set_mode((w,h), DOUBLEBUF|OPENGL)
        pygame.display.set_caption('Progress Panel Calibrator')
        glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_DEPTH_TEST)
        self.clock = pygame.time.Clock(); self.w,self.h = w,h

        # cockpit texture
        try:
            surf = load_image_rgba('cockpit_overlay.png')
            self.tex_cockpit,(self.cw,self.ch) = create_texture_from_surface(surf, False, True)
        except Exception as e:
            print('[ERROR] cockpit_overlay.png missing:', e); self.tex_cockpit=0; self.cw=self.ch=1

        # progress FBO
        self.progress_fbo, self.progress_tex, self.progress_rbo, self.progress_size = create_health_fbo(256)
        self.font = pygame.font.Font(None, 28)
        self.progress = 0.0

        # UV
        self.uv = [ (0.64,0.80), (0.96,0.80), (0.96,0.98), (0.64,0.98) ]
        self.drag_idx = None; self.pick_radius_px = 22

    def to_px(self,p): return (int(p[0]*self.w), int(p[1]*self.h))
    def to_norm(self,pos): return (max(0,min(1,pos[0]/float(self.w))), max(0,min(1,pos[1]/float(self.h))))

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

    def save_json(self,path='progress_panel_uv.json'):
        d={ 'TL': {'x': self.uv[0][0], 'y': self.uv[0][1]}, 'TR': {'x': self.uv[1][0], 'y': self.uv[1][1]}, 'BR': {'x': self.uv[2][0], 'y': self.uv[2][1]}, 'BL': {'x': self.uv[3][0], 'y': self.uv[3][1]}, 'list': self.uv }
        with open(path,'w',encoding='utf-8') as f: json.dump(d,f,indent=2)
        print('[SAVE]', path)

    def render_progress_fbo(self):
        if self.progress_fbo==0: return
        size=self.progress_size
        glBindFramebuffer(GL_FRAMEBUFFER,self.progress_fbo); glViewport(0,0,size,size); glDisable(GL_DEPTH_TEST)
        glClearColor(0,0,0,1); glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0,size,size,0,-1,1)
        glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity()
        # wave
        surf=self.font.render("Wave 1",True,(230,230,255,255)); tex,_ = create_texture_from_surface(surf,False,False); tw,th = surf.get_size(); pad=int(size*0.06)
        x=pad; y=pad
        glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D,tex)
        glBegin(GL_QUADS)
        glTexCoord2f(0,0); glVertex2f(x,y)
        glTexCoord2f(1,0); glVertex2f(x+tw,y)
        glTexCoord2f(1,1); glVertex2f(x+tw,y+th)
        glTexCoord2f(0,1); glVertex2f(x,y+th)
        glEnd(); glBindTexture(GL_TEXTURE_2D,0); glDisable(GL_TEXTURE_2D); glDeleteTextures([tex])
        # bar
        bar_w = int(size*0.8); bar_h = int(size*0.12)
        bx = (size - bar_w)//2; by = size - pad - bar_h
        glColor3f(0.12,0.12,0.14); glBegin(GL_QUADS)
        glVertex2f(bx,by); glVertex2f(bx+bar_w,by); glVertex2f(bx+bar_w,by+bar_h); glVertex2f(bx,by+bar_h)
        glEnd()
        fill_w = int(bar_w * max(0.0,min(1.0,self.progress)))
        glColor3f(0.2,0.7,0.3); glBegin(GL_QUADS); glVertex2f(bx,by); glVertex2f(bx+fill_w,by); glVertex2f(bx+fill_w,by+bar_h); glVertex2f(bx,by+bar_h); glEnd()
        # percent
        pct_text=f"{int(self.progress*100)}%"
        surf=self.font.render(pct_text,True,(240,240,255,255)); tex,_=create_texture_from_surface(surf,False,False)
        tw,th=surf.get_size(); tx=bx+(bar_w-tw)//2; ty=by+(bar_h-th)//2
        glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D,tex)
        glBegin(GL_QUADS)
        glTexCoord2f(0,0); glVertex2f(tx,ty)
        glTexCoord2f(1,0); glVertex2f(tx+tw,ty)
        glTexCoord2f(1,1); glVertex2f(tx+tw,ty+th)
        glTexCoord2f(0,1); glVertex2f(tx,ty+th)
        glEnd(); glBindTexture(GL_TEXTURE_2D,0); glDisable(GL_TEXTURE_2D); glDeleteTextures([tex])
        glEnable(GL_DEPTH_TEST); glMatrixMode(GL_MODELVIEW); glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glBindFramebuffer(GL_FRAMEBUFFER,0)

    def run(self):
        running=True
        while running:
            dt=self.clock.tick(120)/1000.0
            for ev in pygame.event.get():
                if ev.type==QUIT: running=False
                elif ev.type==KEYDOWN:
                    if ev.key==K_ESCAPE: running=False
                    elif ev.key==K_s: self.save_json()
                    elif ev.key==K_RETURN: self.save_json(); print('[RESULT] progress_panel_uv =', self.uv); running=False
                    elif ev.key==K_UP: self.progress=min(1.0,self.progress+0.05)
                    elif ev.key==K_DOWN: self.progress=max(0.0,self.progress-0.05)
                elif ev.type==MOUSEBUTTONDOWN and ev.button==1:
                    self.drag_idx = self.pick_corner(pygame.mouse.get_pos())
                elif ev.type==MOUSEBUTTONUP and ev.button==1:
                    self.drag_idx=None
                elif ev.type==MOUSEMOTION and self.drag_idx is not None:
                    mx,my=pygame.mouse.get_pos(); self.uv[self.drag_idx]=self.to_norm((mx,my))

            # render progress to fbo
            self.render_progress_fbo()

            # reset viewport, clear
            glViewport(0,0,self.w,self.h); glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)

            # draw cockpit
            if self.tex_cockpit!=0:
                draw_cockpit_cover(self.tex_cockpit,self.cw,self.ch,self.w,self.h)

            # blit progress panel
            TL=(self.uv[0][0]*self.w,self.uv[0][1]*self.h); TR=(self.uv[1][0]*self.w,self.uv[1][1]*self.h)
            BR=(self.uv[2][0]*self.w,self.uv[2][1]*self.h); BL=(self.uv[3][0]*self.w,self.uv[3][1]*self.h)
            glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0,self.w,self.h,0,-1,1)
            glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity()
            glDisable(GL_DEPTH_TEST); glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D,self.progress_tex)
            glColor4f(1,1,1,1)
            glBegin(GL_QUADS)
            glTexCoord2f(0,0); glVertex2f(*TL)
            glTexCoord2f(1,0); glVertex2f(*TR)
            glTexCoord2f(1,1); glVertex2f(*BR)
            glTexCoord2f(0,1); glVertex2f(*BL)
            glEnd(); glBindTexture(GL_TEXTURE_2D,0); glDisable(GL_TEXTURE_2D); glEnable(GL_DEPTH_TEST)
            glMatrixMode(GL_MODELVIEW); glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

            self.draw_handles()
            pygame.display.set_caption(f'Progress Panel Calibrator  |  Progress: {int(self.progress*100)}%  |  [Up/Down] +/-  [S] Save  [Enter] Validate')
            pygame.display.flip()

        pygame.quit(); sys.exit()

if __name__=='__main__': ProgressCalibrator().run()

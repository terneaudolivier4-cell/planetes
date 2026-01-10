# ui_radar_panel.py
import math
from render import clamp
from OpenGL.GL import *


def load_radar_panel_uv(path='assets/radar_panel_uv.json'):
    import json, os
    try:
        if not os.path.exists(path):
            print(f"[ERROR] Radar panel UV config not found: {path}")
        with open(path,'r',encoding='utf-8') as f:
            d=json.load(f)
        return [
            (float(d['TL']['x']), float(d['TL']['y'])),
            (float(d['TR']['x']), float(d['TR']['y'])),
            (float(d['BR']['x']), float(d['BR']['y'])),
            (float(d['BL']['x']), float(d['BL']['y'])),
        ]
    except Exception as e:
        print(f"[ERROR] Failed to load Radar panel UV info '{path}': {e}")
        return [(0.385,0.718),(0.615,0.719),(0.592,0.905),(0.408,0.905)]


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
        print('[WARN] Radar FBO incomplete:', status)
        return 0,0,0,0
    return fbo, tex, rbo, size


def render_radar_fbo(fbo, size, player_dir, player_pos, enemies_pos_list, max_range=70.0):
    if fbo == 0: return
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)
    glViewport(0,0,size,size)
    glDisable(GL_DEPTH_TEST)
    glClearColor(0,0,0,0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0,size,size,0,-1,1)
    glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()

    cx, cy = size//2, size//2
    r = int(size*0.42); seg=128
    glColor3f(0.45,0.7,0.95)
    for k in (1/3.0, 2/3.0, 1.0):
        rr=int(r*k); glBegin(GL_LINE_LOOP)
        for i in range(seg):
            a=2.0*math.pi*i/seg
            glVertex2f(cx + rr*math.cos(a), cy + rr*math.sin(a))
        glEnd()
    glBegin(GL_LINES)
    glVertex2f(cx-6,cy); glVertex2f(cx+6,cy)
    glVertex2f(cx,cy-6); glVertex2f(cx,cy+6)
    glEnd()

    # Accept `player_dir` (unit forward vector) and derive yaw/pitch locally
    if player_dir is None:
        player_dir = (0, 0, -1)
    px,py,pz = player_pos; scale=(0.40*r)/max_range
    pd = player_dir
    yw = math.radians(math.degrees(math.atan2(pd[0], -pd[2])))
    cosw, sinw = math.cos(-yw), math.sin(-yw)
    # Player "look angle" (positive is up)
    # Based on Player.forward() being (..., -sin(pitch), ...), positive pitch is looking down.
    v_deg = -math.degrees(math.asin(clamp(pd[1], -0.99, 0.99)))
    
    for ex,ey,ez in enemies_pos_list:
        dx=ex-px; dy=ey-py; dz=ez-pz
        rxp=dx*cosw - dz*sinw
        ryp=dx*sinw + dz*cosw
        sx=cx + rxp*scale
        sy=cy - ryp*scale
        
        if (sx-cx)**2 + (sy-cy)**2 <= r*r:
            hdist = math.sqrt(dx*dx + dz*dz)
            e_elevation = math.degrees(math.atan2(dy, hdist)) if hdist > 0.1 else (90 if dy > 0 else -90)
            diff = e_elevation - v_deg
            
            glColor3f(1.0, 0.2, 0.2)
            s = 5  # Symbol size
            if diff > 20: # Enemy above -> Triangle Down
                glBegin(GL_TRIANGLES)
                glVertex2f(sx, sy+s)
                glVertex2f(sx-s, sy-s)
                glVertex2f(sx+s, sy-s)
                glEnd()
            elif diff < -20: # Enemy below -> Triangle Up
                glBegin(GL_TRIANGLES)
                glVertex2f(sx, sy-s)
                glVertex2f(sx-s, sy+s)
                glVertex2f(sx+s, sy+s)
                glEnd()
            else: # Square
                glBegin(GL_QUADS)
                glVertex2f(sx-s, sy-s)
                glVertex2f(sx+s, sy-s)
                glVertex2f(sx+s, sy+s)
                glVertex2f(sx-s, sy+s)
                glEnd()

    glPointSize(6); glColor3f(0.2,0.9,1.0); glBegin(GL_POINTS); glVertex2f(cx,cy); glEnd()

    glEnable(GL_DEPTH_TEST)
    glMatrixMode(GL_MODELVIEW);  glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)
    glBindFramebuffer(GL_FRAMEBUFFER, 0)


def blit_radar_to_panel(radar_tex, uv_list, win_w, win_h, background_color=(0,0,0,1)):
    if radar_tex == 0: return
    TL = (uv_list[0][0]*win_w, uv_list[0][1]*win_h)
    TR = (uv_list[1][0]*win_w, uv_list[1][1]*win_h)
    BR = (uv_list[2][0]*win_w, uv_list[2][1]*win_h)
    BL = (uv_list[3][0]*win_w, uv_list[3][1]*win_h)
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0,win_w,win_h,0,-1,1)
    glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
    glDisable(GL_DEPTH_TEST)
    if background_color is not None:
        r,g,b,a = background_color
        glColor4f(r,g,b,a)
        glBegin(GL_QUADS)
        glVertex2f(*TL); glVertex2f(*TR); glVertex2f(*BR); glVertex2f(*BL)
        glEnd()
    glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D, radar_tex)
    # Normal blit
    glColor4f(1,1,1,1)
    glBegin(GL_QUADS)
    glTexCoord2f(0,0); glVertex2f(*TL)
    glTexCoord2f(1,0); glVertex2f(*TR)
    glTexCoord2f(1,1); glVertex2f(*BR)
    glTexCoord2f(0,1); glVertex2f(*BL)
    glEnd()
    # Additive brightness pass for radar
    # Increased boost for stronger perceived brightness
    boost_col = 0.45
    boost_alpha = 0.85
    glEnable(GL_BLEND)
    # Strong additive: add full source to destination for high brightness
    glBlendFunc(GL_ONE, GL_ONE)
    glColor4f(1.0, 1.0, 1.0, 1.0)
    glBegin(GL_QUADS)
    glTexCoord2f(0,0); glVertex2f(*TL)
    glTexCoord2f(1,0); glVertex2f(*TR)
    glTexCoord2f(1,1); glVertex2f(*BR)
    glTexCoord2f(0,1); glVertex2f(*BL)
    glEnd()
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glBindTexture(GL_TEXTURE_2D,0); glDisable(GL_TEXTURE_2D)
    glEnable(GL_DEPTH_TEST)
    glMatrixMode(GL_MODELVIEW);  glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

# ui_health_panel.py
import pygame
from OpenGL.GL import *


def _create_texture_from_surface(surface, flip=False, mip=True):
    tex=glGenTextures(1); glBindTexture(GL_TEXTURE_2D, tex)
    w,h=surface.get_size(); data=pygame.image.tostring(surface,'RGBA',flip)
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,data)
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR_MIPMAP_LINEAR if mip else GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE)
    try: glGenerateMipmap(GL_TEXTURE_2D)
    except Exception: pass
    glBindTexture(GL_TEXTURE_2D,0); return tex,(w,h)


def load_health_panel_uv(path='assets/health_panel_uv.json'):
    import json, os
    try:
        if not os.path.exists(path):
            print(f"[ERROR] Health panel UV config not found: {path}")
        with open(path,'r',encoding='utf-8') as f:
            d=json.load(f)
        return [
            (float(d['TL']['x']), float(d['TL']['y'])),
            (float(d['TR']['x']), float(d['TR']['y'])),
            (float(d['BR']['x']), float(d['BR']['y'])),
            (float(d['BL']['x']), float(d['BL']['y'])),
        ]
    except Exception as e:
        print(f"[ERROR] Failed to load Health panel UV info '{path}': {e}")
        return [(0.78,0.80),(0.94,0.80),(0.94,0.96),(0.78,0.96)]


def create_health_fbo(size=256):
    fbo=glGenFramebuffers(1); tex=glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D,tex)
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,size,size,0,GL_RGBA,GL_UNSIGNED_BYTE,None)
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE)
    glBindTexture(GL_TEXTURE_2D,0)
    rbo=glGenRenderbuffers(1); glBindRenderbuffer(GL_RENDERBUFFER,rbo)
    glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT24,size,size)
    glBindRenderbuffer(GL_RENDERBUFFER,0)
    glBindFramebuffer(GL_FRAMEBUFFER,fbo)
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,tex,0)
    glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,rbo)
    status=glCheckFramebufferStatus(GL_FRAMEBUFFER)
    glBindFramebuffer(GL_FRAMEBUFFER,0)
    if status!=GL_FRAMEBUFFER_COMPLETE:
        print('[WARN] Health FBO incomplete:',status); return 0,0,0,0
    return fbo,tex,rbo,size


def make_ship_icon(size=128,color=(200,220,255,255)):
    """Load `ship_icon.png` (or `ship_incon.png`) if present; otherwise fall back to generated vector icon.

    Returns: (tex, (w,h)) or (0,0) on failure (consistent with `_create_texture_from_surface` return value).
    """
    # Try to load an on-disk image first (supports both expected names for robustness)
    for fname in ('assets/ship_icon.png','assets/ship_incon.png'):
        try:
            surf = pygame.image.load(fname).convert_alpha()
            if surf.get_size() != (size, size):
                surf = pygame.transform.smoothscale(surf, (size, size))
            return _create_texture_from_surface(surf, False, True)
        except Exception:
            pass
    # Fallback: generate a simple polygon ship icon as before
    s = pygame.Surface((size, size), pygame.SRCALPHA); s.fill((0,0,0,0))
    cx, cy = size//2, int(size*0.56)
    import pygame as pg
    nose = (cx, int(size*0.16)); wing_l = (int(size*0.22), cy); wing_r = (int(size*0.78), cy)
    tail_t = (cx, int(size*0.86)); tail_l = (int(size*0.40), int(size*0.94)); tail_r = (int(size*0.60), int(size*0.94))
    pg.draw.polygon(s, color, [nose, wing_r, tail_t, wing_l]); pg.draw.polygon(s, color, [tail_l, tail_r, tail_t])
    return _create_texture_from_surface(s, False, True)


def make_aura_texture(size=256, inner_alpha=220, tint=(80,200,255)):
    s=pygame.Surface((size,size),pygame.SRCALPHA); cx,cy=size//2,size//2
    maxr=int(size*0.46)
    import pygame as pg
    for r in range(maxr,0,-1):
        t=r/float(maxr); a=int(inner_alpha*(t**1.5)); col=(tint[0],tint[1],tint[2],a)
        pg.draw.circle(s,col,(cx,cy),r)
    return _create_texture_from_surface(s,False,True)


def render_health_fbo(fbo,size,ship_tex,aura_tex,health_pct,percent_font=None,opaque_background=False):
    if fbo==0: return
    hp=max(0.0,min(1.0,health_pct))
    glBindFramebuffer(GL_FRAMEBUFFER,fbo); glViewport(0,0,size,size); glDisable(GL_DEPTH_TEST)
    glClearColor(0,0,0,1 if opaque_background else 0); glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0,size,size,0,-1,1)
    glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
    # Aura
    if aura_tex:
        glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D,aura_tex)
        k=0.30+0.70*hp; w=int(size*k); h=int(size*k); x=(size-w)//2; y=(size-h)//2
        glBegin(GL_QUADS)
        glTexCoord2f(0,0); glVertex2f(x,y)
        glTexCoord2f(1,0); glVertex2f(x+w,y)
        glTexCoord2f(1,1); glVertex2f(x+w,y+h)
        glTexCoord2f(0,1); glVertex2f(x,y+h)
        glEnd(); glBindTexture(GL_TEXTURE_2D,0); glDisable(GL_TEXTURE_2D)
    # Ship
    if ship_tex:
        s=int(size*0.58); x=(size-s)//2; y=(size-s)//2
        glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D,ship_tex)
        glBegin(GL_QUADS)
        glTexCoord2f(0,0); glVertex2f(x,y)
        glTexCoord2f(1,0); glVertex2f(x+s,y)
        glTexCoord2f(1,1); glVertex2f(x+s,y+s)
        glTexCoord2f(0,1); glVertex2f(x,y+s)
        glEnd(); glBindTexture(GL_TEXTURE_2D,0); glDisable(GL_TEXTURE_2D)
    # Percent
    if percent_font is not None:
        surf=percent_font.render(f"{int(round(hp*100))}%",True,(255,255,255,255))
        # Flip vertically so text is not upside-down in OpenGL
        tex,_=_create_texture_from_surface(surf,True,False); tw,th=surf.get_size(); pad=int(size*0.04)
        x=size-tw-pad; y=size-th-pad
        glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D,tex)
        glBegin(GL_QUADS)
        glTexCoord2f(0,0); glVertex2f(x,y)
        glTexCoord2f(1,0); glVertex2f(x+tw,y)
        glTexCoord2f(1,1); glVertex2f(x+tw,y+th)
        glTexCoord2f(0,1); glVertex2f(x,y+th)
        glEnd(); glBindTexture(GL_TEXTURE_2D,0); glDisable(GL_TEXTURE_2D); glDeleteTextures([tex])
    glEnable(GL_DEPTH_TEST); glMatrixMode(GL_MODELVIEW);  glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glBindFramebuffer(GL_FRAMEBUFFER,0)


def blit_health_to_panel(health_tex, uv_list, win_w, win_h, background_color=(0,0,0,1)):
    if health_tex==0: return
    TL=(uv_list[0][0]*win_w, uv_list[0][1]*win_h)
    TR=(uv_list[1][0]*win_w, uv_list[1][1]*win_h)
    BR=(uv_list[2][0]*win_w, uv_list[2][1]*win_h)
    BL=(uv_list[3][0]*win_w, uv_list[3][1]*win_h)
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0,win_w,win_h,0,-1,1)
    glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity(); glDisable(GL_DEPTH_TEST)
    if background_color is not None:
        r,g,b,a = background_color
        glColor4f(r,g,b,a)
        glBegin(GL_QUADS)
        glVertex2f(*TL); glVertex2f(*TR); glVertex2f(*BR); glVertex2f(*BL)
        glEnd()
    glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D, health_tex)
    # Normal blit
    glColor4f(1,1,1,1)
    glBegin(GL_QUADS)
    glTexCoord2f(0,0); glVertex2f(*TL)
    glTexCoord2f(1,0); glVertex2f(*TR)
    glTexCoord2f(1,1); glVertex2f(*BR)
    glTexCoord2f(0,1); glVertex2f(*BL)
    glEnd()
    # Additive brightness pass to make panel appear lighter/brighter
    # use a modest boost so whites don't clip too aggressively
    # Increased boost for stronger perceived brightness
    boost_col = 0.50
    boost_alpha = 0.90
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
    # Restore blending
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glBindTexture(GL_TEXTURE_2D,0); glDisable(GL_TEXTURE_2D); glEnable(GL_DEPTH_TEST)
    glMatrixMode(GL_MODELVIEW);  glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

# render.py
import os, math, random
import numpy as np
import pygame
from OpenGL.GL import *
from OpenGL.GLU import *

# ---------------- Math / Vec helpers ----------------
clamp = lambda x,a,b: max(a, min(b, x))
wrap_angle_deg = lambda a: ((a + 180.0) % 360.0) - 180.0
vec3 = lambda x=0.0,y=0.0,z=0.0: np.array([x,y,z], dtype=np.float32)
length = lambda v: float(np.linalg.norm(v))

def normalize(v):
    n = np.linalg.norm(v)
    return v if n == 0 else (v / n)

def deg2rad(d): return d * math.pi / 180.0

# ---------------- Shaders ----------------
BILLBOARD_VERT = """
#version 120
varying vec2 vUV;
void main(){
    vUV = gl_MultiTexCoord0.st;
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
"""

BILLBOARD_FRAG = """
#version 120
uniform sampler2D uTex;
varying vec2 vUV;
void main(){
    vec4 c = texture2D(uTex, vUV);
    if (c.a < 0.05) discard;
    gl_FragColor = c;
}
"""

MODEL_VERT = """
#version 120
attribute vec3 aPos;
attribute vec2 aTexCoord;
attribute vec3 aNormal;

varying vec2 vUV;
varying vec3 vNormal;
varying vec3 vPos;

void main(){
    vUV = aTexCoord;
    vNormal = normalize(gl_NormalMatrix * aNormal);
    vPos = vec3(gl_ModelViewMatrix * vec4(aPos, 1.0));
    gl_Position = gl_ModelViewProjectionMatrix * vec4(aPos, 1.0);
}
"""

MODEL_FRAG = """
#version 120
uniform sampler2D uTex;
uniform vec4 uTint;
varying vec2 vUV;
varying vec3 vNormal;
varying vec3 vPos;

void main(){
    vec4 texColor = texture2D(uTex, vUV);
    if (texColor.a < 0.05) discard;
    
    // Lighting calculation
    vec3 lightDir = normalize(vec3(0.5, 1.0, 0.8));  // Light direction
    vec3 eyeDir = normalize(-vPos);
    
    // Diffuse lighting
    float diffuse = max(dot(vNormal, lightDir), 0.0) * 0.7 + 0.3;  // Ambient fallback
    
    // Specular highlight
    vec3 halfVec = normalize(lightDir + eyeDir);
    float specular = pow(max(dot(vNormal, halfVec), 0.0), 16.0) * 0.3;
    
    // Combine lighting
    vec3 lit = texColor.rgb * diffuse + vec3(specular);
    
    gl_FragColor = vec4(lit, texColor.a) * uTint;
}
"""

SKYBOX_VERT = """
#version 120
varying vec3 vDir;
void main(){
    vDir = gl_Vertex.xyz;
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
"""

SKYBOX_FRAG = """
#version 120
uniform samplerCube uCube;
varying vec3 vDir;
void main(){
    vec3 d = normalize(vDir);
    vec4 c = textureCube(uCube, d);
    float v = clamp(0.65 + 0.35 * pow(abs(d.y), 0.6), 0.65, 1.0);
    gl_FragColor = vec4(c.rgb * v, 1.0);
}
"""

# ---------------- Compile / Link ----------------
def _compile_shader(src, st):
    sh = glCreateShader(st)
    glShaderSource(sh, src)
    glCompileShader(sh)
    if not glGetShaderiv(sh, GL_COMPILE_STATUS):
        raise RuntimeError(glGetShaderInfoLog(sh).decode())
    return sh

def create_program(vs_src, fs_src):
    v = _compile_shader(vs_src, GL_VERTEX_SHADER)
    f = _compile_shader(fs_src, GL_FRAGMENT_SHADER)
    p = glCreateProgram()
    glAttachShader(p, v)
    glAttachShader(p, f)
    glLinkProgram(p)
    if not glGetProgramiv(p, GL_LINK_STATUS):
        raise RuntimeError(glGetProgramInfoLog(p).decode())
    glDetachShader(p, v)
    glDetachShader(p, f)
    glDeleteShader(v)
    glDeleteShader(f)
    return p

# ---------------- Textures helpers ----------------
def create_texture_from_surface(surface, flip=False, mip=True):
    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    w, h = surface.get_size()
    data = pygame.image.tostring(surface, 'RGBA', flip)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR if mip else GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    if mip:
        try: glGenerateMipmap(GL_TEXTURE_2D)
        except Exception: pass
    glBindTexture(GL_TEXTURE_2D, 0)
    return tex, (w, h)

def load_image_rgba(path):
    try:
        if not os.path.exists(path):
            print(f"[ERROR] Asset file not found: {path}")
        return pygame.image.load(path).convert_alpha()
    except Exception as e:
        print(f"[ERROR] Failed to load image asset '{path}': {e}")
        raise

# ---------------- HUD: draw_text ----------------
def draw_text(text, x, y, size=22, color=(255,255,255,255)):
    font = pygame.font.Font(None, size)
    surf = font.render(text, True, color)
    tex, (tw, th) = create_texture_from_surface(surf, False, False)
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tex)
    glColor4f(1,1,1,1)
    glBegin(GL_QUADS)
    glTexCoord2f(0,0); glVertex2f(x, y)
    glTexCoord2f(1,0); glVertex2f(x+tw, y)
    glTexCoord2f(1,1); glVertex2f(x+tw, y+th)
    glTexCoord2f(0,1); glVertex2f(x, y+th)
    glEnd()
    glBindTexture(GL_TEXTURE_2D, 0)
    glDisable(GL_TEXTURE_2D)
    glDeleteTextures([tex])

# ---------------- 2D overlays ----------------
def draw_fullscreen_textured_quad(tex_id, w, h, parallax=(0.0, 0.0), alpha=1.0):
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, w, h, 0, -1, 1)
    glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
    glDisable(GL_DEPTH_TEST)
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glColor4f(1,1,1,alpha)
    dx, dy = parallax
    glBegin(GL_QUADS)
    glTexCoord2f(0,0); glVertex2f(0+dx, 0+dy)
    glTexCoord2f(1,0); glVertex2f(w+dx, 0+dy)
    glTexCoord2f(1,1); glVertex2f(w+dx, h+dy)
    glTexCoord2f(0,1); glVertex2f(0+dx, h+dy)
    glEnd()
    glBindTexture(GL_TEXTURE_2D,0)
    glDisable(GL_TEXTURE_2D)
    glEnable(GL_DEPTH_TEST)
    glMatrixMode(GL_MODELVIEW);  glPopMatrix()
    glMatrixMode(GL_PROJECTION); glPopMatrix()
    glMatrixMode(GL_MODELVIEW)

def draw_fullscreen_textured_quad_fit(tex_id, tex_w, tex_h, win_w, win_h,
                                      mode='cover', parallax=(0.0, 0.0), alpha=1.0):
    r_tex = tex_w / float(tex_h)
    r_win = win_w / float(win_h)
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, win_w, win_h, 0, -1, 1)
    glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
    glDisable(GL_DEPTH_TEST)
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glColor4f(1,1,1,alpha)
    u0, v0, u1, v1 = 0.0, 0.0, 1.0, 1.0
    x0, y0, x1, y1 = 0.0 + parallax[0], 0.0 + parallax[1], win_w + parallax[0], win_h + parallax[1]
    if mode == 'cover':
        if r_tex > r_win:
            vis_tex_w = r_win * tex_h
            pad_w = (tex_w - vis_tex_w) / (2.0 * tex_w)
            u0 = pad_w; u1 = 1.0 - pad_w
        elif r_tex < r_win:
            vis_tex_h = tex_w / r_win
            pad_h = (tex_h - vis_tex_h) / (2.0 * tex_h)
            v0 = pad_h; v1 = 1.0 - pad_h
    elif mode == 'contain':
        if r_tex > r_win:
            h_fit = win_w / r_tex
            y_pad = (win_h - h_fit) / 2.0
            y0 = y_pad + parallax[1]
            y1 = (y_pad + h_fit) + parallax[1]
        elif r_tex < r_win:
            w_fit = win_h * r_tex
            x_pad = (win_w - w_fit) / 2.0
            x0 = x_pad + parallax[0]
            x1 = (x_pad + w_fit) + parallax[0]
    glBegin(GL_QUADS)
    glTexCoord2f(u0, v0); glVertex2f(x0, y0)
    glTexCoord2f(u1, v0); glVertex2f(x1, y0)
    glTexCoord2f(u1, v1); glVertex2f(x1, y1)
    glTexCoord2f(u0, v1); glVertex2f(x0, y1)
    glEnd()
    glBindTexture(GL_TEXTURE_2D, 0)
    glDisable(GL_TEXTURE_2D)
    glEnable(GL_DEPTH_TEST)
    glMatrixMode(GL_MODELVIEW);  glPopMatrix()
    glMatrixMode(GL_PROJECTION); glPopMatrix()
    glMatrixMode(GL_MODELVIEW)

# ---------------- Billboards & UV helpers ----------------
def draw_billboard(prog, tex, pos, size, cr, cu, col=(1,1,1,1)):
    h=size*0.5
    p0=pos - cr*h - cu*h
    p1=pos + cr*h - cu*h
    p2=pos + cr*h + cu*h
    p3=pos - cr*h + cu*h
    glUseProgram(prog)
    glEnable(GL_TEXTURE_2D)
    glActiveTexture(GL_TEXTURE0)
    glBindTexture(GL_TEXTURE_2D, tex)
    loc=glGetUniformLocation(prog, b"uTex")
    if loc!=-1: glUniform1i(loc, 0)
    glColor4f(*col)
    glBegin(GL_QUADS)
    glTexCoord2f(0,0); glVertex3f(*p0)
    glTexCoord2f(1,0); glVertex3f(*p1)
    glTexCoord2f(1,1); glVertex3f(*p2)
    glTexCoord2f(0,1); glVertex3f(*p3)
    glEnd()
    glBindTexture(GL_TEXTURE_2D,0)
    glDisable(GL_TEXTURE_2D)
    glUseProgram(0)

def draw_billboard_uv(prog, tex, pos, size, cr, cu, uv_rect, col=(1,1,1,1)):
    u0,v0,u1,v1 = uv_rect
    h=size*0.5
    p0=pos - cr*h - cu*h
    p1=pos + cr*h - cu*h
    p2=pos + cr*h + cu*h
    p3=pos - cr*h + cu*h
    glUseProgram(prog)
    glEnable(GL_TEXTURE_2D)
    glActiveTexture(GL_TEXTURE0)
    glBindTexture(GL_TEXTURE_2D, tex)
    loc=glGetUniformLocation(prog, b"uTex")
    if loc!=-1: glUniform1i(loc, 0)
    glColor4f(*col)
    glBegin(GL_QUADS)
    glTexCoord2f(u0,v0); glVertex3f(*p0)
    glTexCoord2f(u1,v0); glVertex3f(*p1)
    glTexCoord2f(u1,v1); glVertex3f(*p2)
    glTexCoord2f(u0,v1); glVertex3f(*p3)
    glEnd()
    glBindTexture(GL_TEXTURE_2D,0)
    glDisable(GL_TEXTURE_2D)
    glUseProgram(0)

def flipbook_uv(frame, cols, rows):
    c = frame % cols
    r = frame // cols
    u0 = c/float(cols); v0 = r/float(rows)
    u1 = (c+1)/float(cols); v1 = (r+1)/float(rows)
    return (u0,v0,u1,v1)

# ---------------- Skybox loader ----------------
def load_skybox(prefix='assets/skybox', ext='png'):
    faces = ['px', 'nx', 'py', 'ny', 'pz', 'nz']
    targets = [
        GL_TEXTURE_CUBE_MAP_POSITIVE_X, GL_TEXTURE_CUBE_MAP_NEGATIVE_X,
        GL_TEXTURE_CUBE_MAP_POSITIVE_Y, GL_TEXTURE_CUBE_MAP_NEGATIVE_Y,
        GL_TEXTURE_CUBE_MAP_POSITIVE_Z, GL_TEXTURE_CUBE_MAP_NEGATIVE_Z
    ]
    surfs=[]
    for s in faces:
        path=f"{prefix}_{s}.{ext}"
        try:
            surf=load_image_rgba(path)
            surfs.append(surf)
        except Exception as e:
            print(f"[WARN] Skybox face missing: {path} -> {e}")
            return 0
    cm=glGenTextures(1)
    glBindTexture(GL_TEXTURE_CUBE_MAP,cm)
    glTexParameteri(GL_TEXTURE_CUBE_MAP,GL_TEXTURE_MIN_FILTER,GL_LINEAR)
    glTexParameteri(GL_TEXTURE_CUBE_MAP,GL_TEXTURE_MAG_FILTER,GL_LINEAR)
    glTexParameteri(GL_TEXTURE_CUBE_MAP,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_CUBE_MAP,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_CUBE_MAP,GL_TEXTURE_WRAP_R,GL_CLAMP_TO_EDGE)
    for i,surf in enumerate(surfs):
        w,h=surf.get_size(); data=pygame.image.tostring(surf,'RGBA',False)
        glTexImage2D(targets[i],0,GL_RGBA,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,data)
    glBindTexture(GL_TEXTURE_CUBE_MAP,0)
    return cm

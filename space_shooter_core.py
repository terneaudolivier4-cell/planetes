# space_shooter_core.py
# -------------------------------------------------------------------------------------
# Noyau du Space Shooter 3D (v7.3f core)
# - Helpers math (clamp, wrap_angle_deg, vec3, length, normalize, deg2rad)
# - Shaders (billboard, model, skybox)
# - Programme shaders (create_program)
# - Textures & HUD text (draw_text)
# - Overlays 2D (including draw_fullscreen_textured_quad_fit for cover/contain)
# - Billboards & UV helpers
# - VFX (FlashFX, FlipSmoke, FlipSparks), Tracer
# - Mesh (OBJ/MTL)
# - Audio (pygame.mixer)
# - Entities: Player, Bullet, ModelEnemy
# - Skybox loader (load_skybox)
# -------------------------------------------------------------------------------------

import sys, os, math, random, json
import numpy as np
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
from enemy_ai import update_enemy
from render import (
    clamp, wrap_angle_deg, vec3, length, normalize, deg2rad,
    BILLBOARD_VERT, BILLBOARD_FRAG, MODEL_VERT, MODEL_FRAG, SKYBOX_VERT, SKYBOX_FRAG,
    create_program, create_texture_from_surface, load_image_rgba, draw_text,
    draw_fullscreen_textured_quad, draw_fullscreen_textured_quad_fit,
    draw_billboard, draw_billboard_uv, flipbook_uv, load_skybox
)

# ---------------- VFX ----------------
class FlashFX:
    def __init__(self, pos, tex, cols=8, rows=6, fps=60, size=1.8):
        self.pos=np.copy(pos); self.tex=tex
        self.cols=cols; self.rows=rows; self.frames=cols*rows
        self.fps=fps; self.t=0.0; self.size=size
    def update(self,dt): self.t+=dt
    def alive(self): return self.t < (self.frames/self.fps)
    def draw(self, prog, cr, cu):
        f=min(int(self.t*self.fps), self.frames-1)
        uv=flipbook_uv(f,self.cols,self.rows)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        draw_billboard_uv(prog,self.tex,self.pos,self.size,cr,cu,uv,(1,1,1,1))
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

class FlipSmoke:
    def __init__(self, pos, tex, cols=8, rows=8, fps=28, size=3.2):
        self.pos=np.copy(pos); self.tex=tex
        self.cols=cols; self.rows=rows; self.frames=cols*rows
        self.fps=fps; self.t=0.0; self.size=size
    def update(self,dt): self.t+=dt
    def alive(self): return self.t < (self.frames/self.fps)
    def draw(self, prog, cr, cu):
        f=min(int(self.t*self.fps), self.frames-1)
        uv=flipbook_uv(f,self.cols,self.rows)
        draw_billboard_uv(prog,self.tex,self.pos,self.size,cr,cu,uv,(1,1,1,0.95))

class FlipSparks(FlipSmoke):
    def __init__(self, pos, tex, cols=8, rows=5, fps=48, size=2.0):
        super().__init__(pos, tex, cols, rows, fps, size)
    def draw(self, prog, cr, cu):
        f=min(int(self.t*self.fps), self.frames-1)
        uv=flipbook_uv(f,self.cols,self.rows)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        draw_billboard_uv(prog,self.tex,self.pos,self.size,cr,cu,uv,(1,1,1,1))
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

class Tracer:
    def __init__(self, tex, ttl=0.12):
        self.tex=tex; self.ttl=ttl; self.age=0.0; self.segs=[]
    def push(self,p):
        self.segs.append(np.copy(p))
        if len(self.segs)>3: self.segs.pop(0)
    def update(self,dt): self.age+=dt
    def alive(self): return self.age < self.ttl
    def draw(self,prog,cr,cu):
        if len(self.segs)<2: return
        p0=self.segs[-2]; p1=self.segs[-1]
        mid=(p0+p1)/2.0; dist=length(p1-p0)
        size=max(0.6,dist*0.6); a=max(0.0,1.0-self.age/self.ttl)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        draw_billboard(prog,self.tex,mid,size,cr,cu,(1,1,1,a))
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

# ---------------- Mesh (OBJ/MTL) ----------------
class Mesh:
    def __init__(self, path, tint=(1,1,1,1)):
        self.path=path; self.dir=os.path.dirname(path) or '.'; self.tint=tint
        self.materials={}; self.groups=[]; self.vbos={} # {mtl_name: (vbo_pos, vbo_uv, vbo_nrm, count)}
        self.__vs=[]; self.__vts=[]; self.__vns=[]
        self._parse_obj()
        self._upload_vbos()

    def _upload_vbos(self):
        for mtl_name, tris in self.groups:
            pos_data=[]; uv_data=[]; nrm_data=[]
            for face in tris:
                for vi, ti, ni in face:
                    pos_data.extend(self.__vs[vi])
                    if ti>=0 and self.__vts: uv_data.extend(self.__vts[ti])
                    else: uv_data.extend([0, 0])
                    if ni>=0 and self.__vns: nrm_data.extend(self.__vns[ni])
                    else: nrm_data.extend([0, 0, 1])
            count = len(tris)*3
            if count==0: continue
            vbo_pos=glGenBuffers(1); glBindBuffer(GL_ARRAY_BUFFER, vbo_pos)
            glBufferData(GL_ARRAY_BUFFER, np.array(pos_data,'f'), GL_STATIC_DRAW)
            vbo_uv=glGenBuffers(1); glBindBuffer(GL_ARRAY_BUFFER, vbo_uv)
            glBufferData(GL_ARRAY_BUFFER, np.array(uv_data,'f'), GL_STATIC_DRAW)
            vbo_nrm=glGenBuffers(1); glBindBuffer(GL_ARRAY_BUFFER, vbo_nrm)
            glBufferData(GL_ARRAY_BUFFER, np.array(nrm_data,'f'), GL_STATIC_DRAW)
            glBindBuffer(GL_ARRAY_BUFFER, 0)
            self.vbos[mtl_name] = (vbo_pos, vbo_uv, vbo_nrm, count)

    def _parse_obj(self):
        vs=[]; vts=[]; vns=[]; cur=None; tris=[]; mtllib=[]
        try:
            with open(self.path,'r',encoding='utf-8',errors='ignore') as f:
                for line in f:
                    if not line or line.startswith('#'): continue
                    p=line.strip().split();
                    if not p: continue
                    t=p[0]
                    if t=='v' and len(p)>=4: vs.append((float(p[1]),float(p[2]),float(p[3])))
                    elif t=='vt' and len(p)>=3: vts.append((float(p[1]),float(p[2])))
                    elif t=='vn' and len(p)>=4: vns.append((float(p[1]),float(p[2]),float(p[3])))
                    elif t=='mtllib' and len(p)>=2: mtllib.append(' '.join(p[1:]))
                    elif t=='usemtl' and len(p)>=2:
                        if tris: self.groups.append((cur,tris)); tris=[]
                        cur=' '.join(p[1:])
                    elif t=='f' and len(p)>=4:
                        def rf(tok):
                            w=tok.split('/'); vi=int(w[0]); ti=int(w[1]) if len(w)>1 and w[1] else 0; ni=int(w[2]) if len(w)>2 and w[2] else 0
                            if vi<0: vi=len(vs)+1+vi
                            if ti<0: ti=len(vts)+1+ti
                            if ni<0: ni=len(vns)+1+ni
                            return (vi-1, ti-1 if ti else -1, ni-1 if ni else -1)
                        r=[rf(x) for x in p[1:]]
                        for i in range(1,len(r)-1): tris.append((r[0],r[i],r[i+1]))
        except Exception as e:
            print(f"[ERROR] Failed to parse OBJ file '{self.path}': {e}")
            raise
        if tris: self.groups.append((cur,tris))
        self.__vs=vs; self.__vts=vts; self.__vns=vns
        for m in mtllib: self._parse_mtl(os.path.join(self.dir, m))
        for m in mtllib: self._parse_mtl(os.path.join(self.dir,m))
        for m,_ in self.groups:
            if m not in self.materials: self.materials[m]={'tex':None}
        self.__vs=vs; self.__vts=vts; self.__vns=vns
    def _parse_mtl(self, path):
        if not os.path.isfile(path):
            print(f"[ERROR] MTL file not found: {path}")
            return
        cur=None
        try:
            with open(path,'r',encoding='utf-8',errors='ignore') as f:
                for line in f:
                    p=line.strip().split();
                    if not p: continue
                    t=p[0]
                    if t=='newmtl' and len(p)>=2:
                        cur=' '.join(p[1:]); self.materials[cur]={'tex':None}
                    elif t.lower()=='map_kd' and cur is not None:
                        rel=' '.join(p[1:]); tex=os.path.join(self.dir,rel)
                        try:
                            surf=load_image_rgba(tex); tid,_=create_texture_from_surface(surf,False,True)
                            self.materials[cur]['tex']=tid
                        except Exception as e:
                            print(f"[ERROR] Failed to load MTL texture '{tex}': {e}")
        except Exception as e:
            print(f"[ERROR] Failed to parse MTL file '{path}': {e}")
    def draw(self, prog):
        glUseProgram(prog); lt=glGetUniformLocation(prog,b"uTint")
        if lt!=-1: glUniform4f(lt,*self.tint)
        
        a_pos = glGetAttribLocation(prog, b"aPos")
        a_uv  = glGetAttribLocation(prog, b"aTexCoord")
        a_nrm = glGetAttribLocation(prog, b"aNormal")

        for mtl_name, (vbo_pos, vbo_uv, vbo_nrm, count) in self.vbos.items():
            tex=self.materials.get(mtl_name,{}).get('tex',None)
            if tex:
                glEnable(GL_TEXTURE_2D); glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D,tex)
                ut=glGetUniformLocation(prog,b"uTex");
                if ut!=-1: glUniform1i(ut,0)
            else:
                glDisable(GL_TEXTURE_2D)

            if a_pos != -1:
                glEnableVertexAttribArray(a_pos)
                glBindBuffer(GL_ARRAY_BUFFER, vbo_pos)
                glVertexAttribPointer(a_pos, 3, GL_FLOAT, GL_FALSE, 0, None)
            
            if a_uv != -1:
                glEnableVertexAttribArray(a_uv)
                glBindBuffer(GL_ARRAY_BUFFER, vbo_uv)
                glVertexAttribPointer(a_uv, 2, GL_FLOAT, GL_FALSE, 0, None)

            if a_nrm != -1:
                glEnableVertexAttribArray(a_nrm)
                glBindBuffer(GL_ARRAY_BUFFER, vbo_nrm)
                glVertexAttribPointer(a_nrm, 3, GL_FLOAT, GL_FALSE, 0, None)

            glDrawArrays(GL_TRIANGLES, 0, count)

            if a_pos != -1: glDisableVertexAttribArray(a_pos)
            if a_uv != -1: glDisableVertexAttribArray(a_uv)
            if a_nrm != -1: glDisableVertexAttribArray(a_nrm)
            
            if tex: glBindTexture(GL_TEXTURE_2D,0); glDisable(GL_TEXTURE_2D)
        
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glUseProgram(0)

# ---------------- Audio ----------------
class Audio:
    def __init__(self):
        self.enabled=True
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        except Exception as e:
            print('[WARN] mixer init failed:',e); self.enabled=False
        self.sounds={}
        if self.enabled:
            def load(name,vol):
                try:
                    path = os.path.join('assets', name)
                    if not os.path.exists(path):
                        print(f"[ERROR] Sound file not found: {path}")
                    s=pygame.mixer.Sound(path); s.set_volume(vol); self.sounds[name]=s
                except Exception as e:
                    print(f"[ERROR] Failed to load sound '{name}': {e}")
            for name,vol in [('sfx_blaster_shot.wav',0.6),('sfx_sparks.wav',0.5),('sfx_explosion_small.wav',0.65),('sfx_ui_click.wav',0.35),('sfx_engine_hum.wav',0.25),('sfx_shield_hit.wav',0.5),('sfx_warning_beep.wav',0.6),('sfx_pickup.wav',0.5)]:
                load(name,vol)
            try: 
                music_path = os.path.join('assets', 'ambient_music.wav')
                if not os.path.exists(music_path):
                    print(f"[ERROR] Music file not found: {music_path}")
                pygame.mixer.music.load(music_path)
                pygame.mixer.music.set_volume(0.35)
                pygame.mixer.music.play(-1)
            except Exception as e: 
                print(f"[ERROR] Failed to load background music: {e}")
    def play(self,name):
        if not self.enabled: return
        s=self.sounds.get(name); 
        if s: s.play()
    def loop(self,name):
        if not self.enabled: return
        s=self.sounds.get(name);
        if s: s.play(-1)
    def stop(self,name):
        if not self.enabled: return
        s=self.sounds.get(name);
        if s: s.stop()

# ---------------- Entities ---------------- (Moved to entities.py)

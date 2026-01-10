import pygame
import json
import numpy as np
from OpenGL.GL import *

def _create_texture_from_surface(surf, repeat=False, flip_y=False):
    if flip_y:
        surf = pygame.transform.flip(surf, False, True)
    w, h = surf.get_size()
    data = pygame.image.tostring(surf, 'RGBA', True)
    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT if repeat else GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT if repeat else GL_CLAMP_TO_EDGE)
    glBindTexture(GL_TEXTURE_2D, 0)
    return tex, (w, h)

def create_progress_fbo(size=512):
    fbo = glGenFramebuffers(1)
    tex = glGenTextures(1)
    rbo = glGenRenderbuffers(1)
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size, size, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0)
    glBindRenderbuffer(GL_RENDERBUFFER, rbo)
    glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, size, size)
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, rbo)
    glBindFramebuffer(GL_FRAMEBUFFER, 0)
    return fbo, tex, rbo, size

def render_progress_fbo(fbo, size, wave, score, enemies_remaining, speed=None, progress_font=None):
    if fbo == 0: return
    glBindFramebuffer(GL_FRAMEBUFFER, fbo)
    glViewport(0, 0, size, size)
    glDisable(GL_DEPTH_TEST)
    glClearColor(0, 0, 0, 0.8)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, size, size, 0, -1, 1)
    glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
    
    if progress_font is not None:
        pad = int(size * 0.08)
        y_offset = pad
        
        # Wave text
        surf = progress_font.render(f"Wave: {wave}", True, (255, 255, 200, 255))
        tex, (tw, th) = _create_texture_from_surface(surf, False, False)
        glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D, tex)
        glColor4f(1, 1, 1, 1)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(pad, y_offset)
        glTexCoord2f(1, 0); glVertex2f(pad + tw, y_offset)
        glTexCoord2f(1, 1); glVertex2f(pad + tw, y_offset + th)
        glTexCoord2f(0, 1); glVertex2f(pad, y_offset + th)
        glEnd()
        glBindTexture(GL_TEXTURE_2D, 0); glDisable(GL_TEXTURE_2D); glDeleteTextures([tex])
        y_offset += th + int(size * 0.06)
        
        # Score text
        surf = progress_font.render(f"Score: {score}", True, (200, 255, 200, 255))
        tex, (tw, th) = _create_texture_from_surface(surf, False, False)
        glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D, tex)
        glColor4f(1, 1, 1, 1)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(pad, y_offset)
        glTexCoord2f(1, 0); glVertex2f(pad + tw, y_offset)
        glTexCoord2f(1, 1); glVertex2f(pad + tw, y_offset + th)
        glTexCoord2f(0, 1); glVertex2f(pad, y_offset + th)
        glEnd()
        glBindTexture(GL_TEXTURE_2D, 0); glDisable(GL_TEXTURE_2D); glDeleteTextures([tex])
        y_offset += th + int(size * 0.06)
        
        # Enemies remaining text
        surf = progress_font.render(f"Ennemis: {enemies_remaining}", True, (255, 200, 150, 255))
        tex, (tw, th) = _create_texture_from_surface(surf, False, False)
        glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D, tex)
        glColor4f(1, 1, 1, 1)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(pad, y_offset)
        glTexCoord2f(1, 0); glVertex2f(pad + tw, y_offset)
        glTexCoord2f(1, 1); glVertex2f(pad + tw, y_offset + th)
        glTexCoord2f(0, 1); glVertex2f(pad, y_offset + th)
        glEnd()
        glBindTexture(GL_TEXTURE_2D, 0); glDisable(GL_TEXTURE_2D); glDeleteTextures([tex])

        # Speed indicator (if provided)
        if speed is not None:
            y_offset += th + int(size * 0.06)
            spd_val = int(round(float(speed)))
            surf = progress_font.render(f"Vitesse: {spd_val}", True, (180, 220, 255, 255))
            tex, (tw, th) = _create_texture_from_surface(surf, False, False)
            glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D, tex)
            glColor4f(1, 1, 1, 1)
            glBegin(GL_QUADS)
            glTexCoord2f(0, 0); glVertex2f(pad, y_offset)
            glTexCoord2f(1, 0); glVertex2f(pad + tw, y_offset)
            glTexCoord2f(1, 1); glVertex2f(pad + tw, y_offset + th)
            glTexCoord2f(0, 1); glVertex2f(pad, y_offset + th)
            glEnd()
            glBindTexture(GL_TEXTURE_2D, 0); glDisable(GL_TEXTURE_2D); glDeleteTextures([tex])
    
    glEnable(GL_DEPTH_TEST)
    glMatrixMode(GL_MODELVIEW); glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix()
    glBindFramebuffer(GL_FRAMEBUFFER, 0)

def blit_progress_to_panel(progress_tex, uv_list, win_w, win_h, background_color=(0, 0, 0, 1)):
    if progress_tex == 0: return
    TL = (uv_list[0][0] * win_w, uv_list[0][1] * win_h)
    TR = (uv_list[1][0] * win_w, uv_list[1][1] * win_h)
    BR = (uv_list[2][0] * win_w, uv_list[2][1] * win_h)
    BL = (uv_list[3][0] * win_w, uv_list[3][1] * win_h)
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, win_w, win_h, 0, -1, 1)
    glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity(); glDisable(GL_DEPTH_TEST)
    if background_color is not None:
        r, g, b, a = background_color
        glColor4f(r, g, b, a)
        glBegin(GL_QUADS)
        glVertex2f(*TL); glVertex2f(*TR); glVertex2f(*BR); glVertex2f(*BL)
        glEnd()
    glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D, progress_tex)
    # Normal blit
    glColor4f(1, 1, 1, 1)
    glBegin(GL_QUADS)
    glTexCoord2f(0, 0); glVertex2f(*TL)
    glTexCoord2f(1, 0); glVertex2f(*TR)
    glTexCoord2f(1, 1); glVertex2f(*BR)
    glTexCoord2f(0, 1); glVertex2f(*BL)
    glEnd()
    # Additive brightness pass to enhance readability
    # Increased boost for stronger perceived brightness
    boost_col = 0.48
    boost_alpha = 0.88
    glEnable(GL_BLEND)
    # Strong additive: add full source to destination for high brightness
    glBlendFunc(GL_ONE, GL_ONE)
    glColor4f(1.0, 1.0, 1.0, 1.0)
    glBegin(GL_QUADS)
    glTexCoord2f(0, 0); glVertex2f(*TL)
    glTexCoord2f(1, 0); glVertex2f(*TR)
    glTexCoord2f(1, 1); glVertex2f(*BR)
    glTexCoord2f(0, 1); glVertex2f(*BL)
    glEnd()
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glBindTexture(GL_TEXTURE_2D, 0); glDisable(GL_TEXTURE_2D); glEnable(GL_DEPTH_TEST)
    glMatrixMode(GL_MODELVIEW); glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

def load_progress_panel_uv(filepath='assets/progress_panel_uv.json'):
    import os
    try:
        if not os.path.exists(filepath):
            print(f"[ERROR] Progress panel UV config not found: {filepath}")
        with open(filepath, 'r') as f:
            data = json.load(f)
            return data.get('list', [[0,0],[1,0],[1,1],[0,1]])
    except Exception as e:
        print(f"[ERROR] Failed to load Progress panel UV info '{filepath}': {e}")
        return [[0,0],[1,0],[1,1],[0,1]]

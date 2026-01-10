import pygame
import numpy as np
import math
from OpenGL.GL import *
from OpenGL.GLU import *
from render import draw_text, deg2rad

def draw_help_menu(game):
    """Draw a pause/help overlay with 3 simplified 3D previews (left) and controls (right)."""
    w, h = game.w, game.h
    # Draw frozen snapshot as background (if available) and dim it
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, w, h, 0, -1, 1)
    glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity(); glDisable(GL_DEPTH_TEST)
    glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    
    if getattr(game, 'pause_snapshot_tex', 0):
        glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D, game.pause_snapshot_tex)
        glColor4f(1.0, 1.0, 1.0, 1.0)
        glBegin(GL_QUADS)
        glTexCoord2f(0,0); glVertex2f(0,0)
        glTexCoord2f(1,0); glVertex2f(w,0)
        glTexCoord2f(1,1); glVertex2f(w,h)
        glTexCoord2f(0,1); glVertex2f(0,h)
        glEnd()
        glBindTexture(GL_TEXTURE_2D, 0); glDisable(GL_TEXTURE_2D)
    else:
        glColor4f(0.02, 0.02, 0.02, 1.0)
        glBegin(GL_QUADS)
        glVertex2f(0,0); glVertex2f(w,0); glVertex2f(w,h); glVertex2f(0,h)
        glEnd()
        
    # Dim overlay
    glColor4f(0.02, 0.02, 0.02, 0.5)
    glBegin(GL_QUADS)
    glVertex2f(0,0); glVertex2f(w,0); glVertex2f(w,h); glVertex2f(0,h)
    glEnd()
    
    # Panel area (centered, half-screen) and inner layout
    panel_w = int(w * 0.50); panel_h = int(h * 0.50)
    panel_x = (w - panel_w) // 2; panel_y = (h - panel_h) // 2
    pad = 12
    # Left area: split into two equal columns (half the original left area)
    left_total = int(panel_w * 0.60)
    col_w = left_total // 2
    col1_x = panel_x + int(panel_w * 0.03)
    col2_x = col1_x + col_w + pad
    # 4 rows per column
    slot_h = int((panel_h - pad*5) / 4)

    # Helper: draw a Mesh (or fallback cube) in a small viewport
    def _draw_mesh_preview(px, py, pw, ph, mesh, model_scale=1.0, tint=(1.0,0.8,0.6)):
        vp = glGetIntegerv(GL_VIEWPORT)
        glViewport(px, h - (py+ph), pw, ph)
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); gluPerspective(45.0, float(pw)/float(max(1,ph)), 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity()
        glEnable(GL_DEPTH_TEST); glEnable(GL_LIGHTING); glEnable(GL_COLOR_MATERIAL)
        
        center = None; max_extent = None
        try:
            vs = getattr(mesh, '_Mesh__vs', None) if mesh is not None else None
            if vs:
                arr = np.array(vs, dtype=float)
                mn = arr.min(axis=0); mx = arr.max(axis=0)
                center = (mn + mx) * 0.5
                max_extent = float(np.max(mx - mn) * 0.5)
        except Exception:
            center = None; max_extent = None

        if max_extent and max_extent > 1e-6:
            fov_rad = deg2rad(45.0)
            distance = (max_extent * float(model_scale)) / math.tan(fov_rad * 0.5) * 1.25
        else:
            distance = 4.0 * float(model_scale)

        glTranslatef(0.0, 0.0, -distance)
        glRotatef(25.0, 1, 0.3, 0); glRotatef(pygame.time.get_ticks()*0.02 % 360, 0,1,0)
        glColor3f(*tint)

        # Detect missile mesh
        is_missile = bool(getattr(mesh, 'path', '')) and ('missile' in getattr(mesh, 'path', ''))

        # Si c'est le missile, forcer une couleur claire et désactiver la texture
        # Pour le missile, on utilise exactement la même config que le jeu (GL_LIGHTING et GL_COLOR_MATERIAL activés, pas de couleur forcée)
        glEnable(GL_LIGHTING)
        glEnable(GL_COLOR_MATERIAL)

        if mesh is not None:
            try:
                glPushMatrix()
                glScalef(model_scale, model_scale, model_scale)
                if center is not None:
                    glTranslatef(-float(center[0]), -float(center[1]), -float(center[2]))
                # Temporarily boost tint for missile to simulate stronger light
                old_tint = getattr(mesh, 'tint', (1.0, 1.0, 1.0, 1.0))
                if is_missile:
                    mesh.tint = (1.35, 1.25, 1.1, 1.0)
                mesh.draw(game.model_prog)
                # Restore tint
                if is_missile:
                    mesh.tint = old_tint
                glPopMatrix()
            except Exception:
                # Skip cube fallback for missile; keep for enemies only
                if not is_missile:
                    s = 0.9 * float(model_scale)
                    glBegin(GL_QUADS)
                    glNormal3f(0,0,1); glVertex3f(-s,-s,s); glVertex3f(s,-s,s); glVertex3f(s,s,s); glVertex3f(-s,s,s)
                    glNormal3f(0,0,-1); glVertex3f(-s,-s,-s); glVertex3f(-s,s,-s); glVertex3f(s,s,-s); glVertex3f(s,-s,-s)
                    glNormal3f(-1,0,0); glVertex3f(-s,-s,-s); glVertex3f(-s,-s,s); glVertex3f(-s,s,s); glVertex3f(-s,s,-s)
                    glNormal3f(1,0,0); glVertex3f(s,-s,-s); glVertex3f(s,s,-s); glVertex3f(s,s,s); glVertex3f(s,-s,s)
                    glNormal3f(0,1,0); glVertex3f(-s,s,-s); glVertex3f(-s,s,s); glVertex3f(s,s,s); glVertex3f(s,s,-s)
                    glNormal3f(0,-1,0); glVertex3f(-s,-s,-s); glVertex3f(s,-s,-s); glVertex3f(s,-s,s); glVertex3f(-s,-s,s)
                    glEnd()
        else:
            s = 0.9 * float(model_scale)
            glBegin(GL_QUADS)
            glNormal3f(0,0,1); glVertex3f(-s,-s,s); glVertex3f(s,-s,s); glVertex3f(s,s,s); glVertex3f(-s,s,s)
            glNormal3f(0,0,-1); glVertex3f(-s,-s,-s); glVertex3f(-s,s,-s); glVertex3f(s,s,-s); glVertex3f(s,-s,-s)
            glNormal3f(-1,0,0); glVertex3f(-s,-s,-s); glVertex3f(-s,-s,s); glVertex3f(-s,s,s); glVertex3f(-s,s,-s)
            glNormal3f(1,0,0); glVertex3f(s,-s,-s); glVertex3f(s,s,-s); glVertex3f(s,s,s); glVertex3f(s,-s,s)
            glNormal3f(0,1,0); glVertex3f(-s,s,-s); glVertex3f(-s,s,s); glVertex3f(s,s,s); glVertex3f(s,s,-s)
            glNormal3f(0,-1,0); glVertex3f(-s,-s,-s); glVertex3f(s,-s,-s); glVertex3f(s,-s,s); glVertex3f(-s,-s,s)
            glEnd()
            
        glDisable(GL_LIGHTING); glDisable(GL_DEPTH_TEST)
        glMatrixMode(GL_MODELVIEW); glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix()
        glViewport(vp[0], vp[1], vp[2], vp[3])

    # Gather ordered enemy types + missile preview
    enemy_order = ['fighter','interceptor','bomber']
    bps = game.wave_cfg.get('enemy_blueprints', [])
    bp_map = {bp['name']: bp for bp in bps}

    items = []
    for name in enemy_order:
        items.append({'name': name, 'mesh': game.meshes.get(name), 'bp': bp_map.get(name, {}), 'tint': (0.6,0.8,1.0) if name=='bomber' else (1.0,0.6,0.4) if name=='interceptor' else (1.0,0.8,0.6)})
    # Missile entry
    items.append({
        'name': 'missile',
        'mesh': getattr(game, 'missile_mesh', None),
        'bp': {'damage': 'Explosif', 'speed': 150, 'note': 'Lock puis tir guidé'},
        'tint': (1.0, 0.9, 0.6),
        'scale': getattr(game, 'missile_scale', 1.0)
    })

    # Draw enemies + missile into the two columns
    for i, item in enumerate(items):
        slot_index = i
        col = slot_index // 4  # 0 -> first column, 1 -> second column
        row = slot_index % 4
        top = panel_y + pad + row * (slot_h + pad)
        bx = col1_x + col * (col_w + pad); by = top; bw = col_w - pad*2; bh = slot_h
        glColor4f(0.06,0.06,0.08,0.95)
        glBegin(GL_QUADS)
        glVertex2f(bx, by); glVertex2f(bx+bw, by); glVertex2f(bx+bw, by+bh); glVertex2f(bx, by+bh)
        glEnd()
        
        preview_size = min(int(bh*0.9), int(bw*0.35))
        pv_x = bx + pad; pv_y = by + (bh - preview_size)//2
        bp = item.get('bp', {})
        model_scale = float(bp.get('scale', item.get('scale', 1.0)))
        _draw_mesh_preview(pv_x, pv_y, preview_size, preview_size, item.get('mesh'), model_scale=model_scale, tint=item.get('tint', (1.0,0.8,0.6)))
        
        tx = pv_x + preview_size + pad*2
        ty = by + pad
        title = item['name'].capitalize() if item['name'] != 'missile' else 'Missile'
        draw_text(title, tx, ty, 24, (255,255,200,255))
        stats = []
        if item['name'] == 'missile':
            stats.append(f"Dégâts: {bp.get('damage', 'Explosif')}")
            stats.append(f"Guidage: lock + suivi")
            stats.append(f"Vitesse: {bp.get('maxspeed', bp.get('speed',150))}")
        else:
            if 'health' in bp: stats.append(f"PV: {bp.get('health')}")
            if 'damage' in bp: stats.append(f"Dégâts: {bp.get('damage')}")
            stats.append(f"Vitesse: {bp.get('maxspeed', bp.get('speed',4.2))}")
        stats_y = ty + 28
        for s in stats:
            draw_text(s, tx, stats_y, 20, (220,220,220,220))
            stats_y += 20

    # --- Finally: draw two pickup rows after the items ---
    pickups_info = [
        {'title': 'Bouclier', 'text': 'Restaure le bouclier', 'type': 'shield'},
        {'title': 'Missile', 'text': 'Donne un missile', 'type': 'missile'}
    ]
    start_slot = len(items)
    for pi, pk in enumerate(pickups_info):
        slot_index = start_slot + pi
        col = slot_index // 4
        row = slot_index % 4
        top = panel_y + pad + row * (slot_h + pad)
        bx = col1_x + col * (col_w + pad); by = top; bw = col_w - pad*2; bh = slot_h
        glColor4f(0.06,0.06,0.08,0.95)
        glBegin(GL_QUADS)
        glVertex2f(bx, by); glVertex2f(bx+bw, by); glVertex2f(bx+bw, by+bh); glVertex2f(bx, by+bh)
        glEnd()
        # draw texture for pickup (fallback to colored square if missing)
        sq = int(bh * 0.6)
        sq_x = bx + pad; sq_y = by + (bh - sq)//2
        tex = game.tex_shield if pk['type'] == 'shield' else game.tex_missile
        if tex:
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, tex)
            glColor4f(1.0,1.0,1.0,1.0)
            glBegin(GL_QUADS)
            glTexCoord2f(0,1); glVertex2f(sq_x, sq_y)
            glTexCoord2f(1,1); glVertex2f(sq_x+sq, sq_y)
            glTexCoord2f(1,0); glVertex2f(sq_x+sq, sq_y+sq)
            glTexCoord2f(0,0); glVertex2f(sq_x, sq_y+sq)
            glEnd()
            glBindTexture(GL_TEXTURE_2D, 0)
            glDisable(GL_TEXTURE_2D)
        else:
            if pk['type'] == 'shield':
                glColor4f(0.2,0.6,0.8,1.0)
            else:
                glColor4f(0.9,0.6,0.2,1.0)
            glBegin(GL_QUADS)
            glVertex2f(sq_x, sq_y); glVertex2f(sq_x+sq, sq_y); glVertex2f(sq_x+sq, sq_y+sq); glVertex2f(sq_x, sq_y+sq)
            glEnd()
        tx = sq_x + sq + pad
        ty = by + pad
        draw_text(pk['title'], tx, ty, 24, (255,255,200,255))
        draw_text(pk['text'], tx, ty+28, 20, (220,220,220,220))

    # Draw panel border/frame
    glLineWidth(2.0); glColor4f(1.0,1.0,1.0,0.9)
    glBegin(GL_LINE_LOOP)
    glVertex2f(panel_x, panel_y)
    glVertex2f(panel_x + panel_w, panel_y)
    glVertex2f(panel_x + panel_w, panel_y + panel_h)
    glVertex2f(panel_x, panel_y + panel_h)
    glEnd(); glLineWidth(1.0)
    
    # Right area: controls (anchored after the two left columns)
    right_x = col2_x + col_w + pad*2
    rx = right_x; ry = panel_y + int(panel_h * 0.12)
    draw_text('Contrôles', rx, ry-36, 28, (255,255,200,255))
    controls = [
        ('Souris', 'Regarder / viser'),
        ('Click gauche', 'Tirer lasers'),
        ('Click droit', 'Lancer missile (nécessite lock)'),
        ('Espace', 'Accélérer'),
        ('W/X', 'Roulis'),
        ('M', 'Lancer missile (nécessite lock)'),
        ('K', 'instant kill tous les ennemis (debug)'),
        ('ESC', 'Pause / Afficher cette aide'),
        ('Q', 'Quitter le jeu'),
    ]
    cy = ry
    for key, desc in controls:
        draw_text(f"{key} : {desc}", rx, cy, 20, (220,220,220,220))
        cy += 26

    # Bottom-right buttons block
    bw = int(panel_w * 0.28); bh = int(panel_h * 0.12)
    bx = panel_x + panel_w - bw - pad
    by = panel_y + panel_h - pad - (bh + pad) * 3
    
    glColor4f(0.08,0.08,0.10,0.95)
    glBegin(GL_QUADS)
    glVertex2f(bx-pad, by-pad); glVertex2f(bx+bw+pad, by-pad); glVertex2f(bx+bw+pad, by+(bh+pad)*3); glVertex2f(bx-pad, by+(bh+pad)*3)
    glEnd()
    
    # Music row
    music_y0 = by
    glColor4f(0.16,0.16,0.18,1.0)
    glBegin(GL_QUADS)
    glVertex2f(bx, music_y0); glVertex2f(bx+bw, music_y0); glVertex2f(bx+bw, music_y0+bh); glVertex2f(bx, music_y0+bh)
    glEnd()
    half = bw // 2
    if game.music_on:
        glColor4f(0.22,0.48,0.18,1.0)
    else:
        glColor4f(0.10,0.10,0.12,1.0)
    glBegin(GL_QUADS)
    glVertex2f(bx, music_y0); glVertex2f(bx+half, music_y0); glVertex2f(bx+half, music_y0+bh); glVertex2f(bx, music_y0+bh)
    glEnd()
    if not game.music_on:
        glColor4f(0.48,0.18,0.18,1.0)
    else:
        glColor4f(0.10,0.10,0.12,1.0)
    glBegin(GL_QUADS)
    glVertex2f(bx+half, music_y0); glVertex2f(bx+bw, music_y0); glVertex2f(bx+bw, music_y0+bh); glVertex2f(bx+half, music_y0+bh)
    glEnd()
    
    glLineWidth(2.0); glColor4f(1.0,1.0,1.0,1.0)
    sel_x0 = bx if game.music_on else bx+half
    glBegin(GL_LINE_LOOP)
    glVertex2f(sel_x0, music_y0); glVertex2f(sel_x0+half, music_y0); glVertex2f(sel_x0+half, music_y0+bh); glVertex2f(sel_x0, music_y0+bh)
    glEnd(); glLineWidth(1.0)
    draw_text(f"Musique {'On' if game.music_on else 'Off'}", bx+12, music_y0+int(bh*0.18), 20, (255,255,255,255))

    # SFX row
    sfx_y0 = by + bh + pad
    glColor4f(0.16,0.16,0.18,1.0)
    glBegin(GL_QUADS)
    glVertex2f(bx, sfx_y0); glVertex2f(bx+bw, sfx_y0); glVertex2f(bx+bw, sfx_y0+bh); glVertex2f(bx, sfx_y0+bh)
    glEnd()
    if game.sfx_on:
        glColor4f(0.22,0.48,0.18,1.0)
    else:
        glColor4f(0.10,0.10,0.12,1.0)
    glBegin(GL_QUADS)
    glVertex2f(bx, sfx_y0); glVertex2f(bx+half, sfx_y0); glVertex2f(bx+half, sfx_y0+bh); glVertex2f(bx, sfx_y0+bh)
    glEnd()
    if not game.sfx_on:
        glColor4f(0.48,0.18,0.18,1.0)
    else:
        glColor4f(0.10,0.10,0.12,1.0)
    glBegin(GL_QUADS)
    glVertex2f(bx+half, sfx_y0); glVertex2f(bx+bw, sfx_y0); glVertex2f(bx+bw, sfx_y0+bh); glVertex2f(bx+half, sfx_y0+bh)
    glEnd()
    
    glLineWidth(2.0); glColor4f(1.0,1.0,1.0,1.0)
    sel_x0 = bx if game.sfx_on else bx+half
    glBegin(GL_LINE_LOOP)
    glVertex2f(sel_x0, sfx_y0); glVertex2f(sel_x0+half, sfx_y0); glVertex2f(sel_x0+half, sfx_y0+bh); glVertex2f(sel_x0, sfx_y0+bh)
    glEnd(); glLineWidth(1.0)
    draw_text(f"SFX {'On' if game.sfx_on else 'Off'}", bx+12, sfx_y0+int(bh*0.18), 20, (255,255,255,255))

    # Quit row
    quit_y0 = by + (bh + pad) * 2
    glColor4f(0.16,0.16,0.18,1.0)
    glBegin(GL_QUADS)
    glVertex2f(bx, quit_y0); glVertex2f(bx+bw, quit_y0); glVertex2f(bx+bw, quit_y0+bh); glVertex2f(bx, quit_y0+bh)
    glEnd()
    draw_text('Quitter', bx+12, quit_y0+int(bh*0.18), 20, (255,220,220,255))

    glDisable(GL_BLEND)
    glEnable(GL_DEPTH_TEST)
    glMatrixMode(GL_MODELVIEW); glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

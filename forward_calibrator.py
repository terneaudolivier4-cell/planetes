# forward_calibrator.py
import sys, os, math, json
import numpy as np
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

# Reuse core and render functions
from render import (
    create_program, create_texture_from_surface, load_image_rgba,
    MODEL_VERT, MODEL_FRAG, vec3, normalize, deg2rad, clamp, length
)
from space_shooter_core import Mesh

class ForwardCalibrator:
    def __init__(self, w=1280, h=720):
        pygame.init()
        pygame.font.init() # Ensure font system is ready
        pygame.display.set_mode((w, h), DOUBLEBUF | OPENGL)
        pygame.display.set_caption("Forward Vector Calibrator")
        
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        glMatrixMode(GL_PROJECTION)
        gluPerspective(45, (w / h), 0.1, 500.0)
        glMatrixMode(GL_MODELVIEW)
        
        self.w, self.h = w, h
        self.prog = create_program(MODEL_VERT, MODEL_FRAG)
        
        # Load blueprints
        try:
            with open('wave_config.json', 'r') as f:
                cfg = json.load(f)
            self.blueprints = cfg.get('enemy_blueprints', [])
        except Exception as e:
            print("Failed to load blueprints:", e)
            self.blueprints = []

        self.index = 0
        self.mesh = None
        self.mesh_name = ""
        # Canonical forward vector for the model (unit vector)
        self.forward = np.array([0.0, 0.0, -1.0], dtype=float)
        # Camera view angles for preview (separate from forward editing)
        self.view_yaw = 0.0
        self.view_pitch = 0.0
        self.distance = 15.0
        
        # Load the current calibration settings if they exist
        self.offsets = {}
        if os.path.exists('forward_offsets.json'):
            with open('forward_offsets.json', 'r') as f:
                self.offsets = json.load(f)
            # Migrate any old-format entries (yaw/pitch) to new {'forward':[x,y,z]} format
            migrated = False
            for k, v in list(self.offsets.items()):
                if isinstance(v, dict) and (('yaw' in v) or ('pitch' in v)):
                    yaw = float(v.get('yaw', 0.0))
                    pitch = float(v.get('pitch', 0.0))
                    yaw_rad = math.radians(yaw)
                    pitch_rad = math.radians(pitch)
                    x = math.sin(yaw_rad) * math.cos(pitch_rad)
                    y = -math.sin(pitch_rad)
                    z = -math.cos(yaw_rad) * math.cos(pitch_rad)
                    self.offsets[k] = {'forward': [float(x), float(y), float(z)]}
                    migrated = True
            if migrated:
                try:
                    with open('forward_offsets.json', 'w') as f:
                        json.dump(self.offsets, f, indent=4)
                    print('[INFO] Migrated forward_offsets.json to new forward-vector format')
                except Exception as e:
                    print('[WARN] Failed to write migrated forward_offsets.json:', e)
        
        self.load_current_mesh()

    def load_current_mesh(self):
        if not self.blueprints: return
        bp = self.blueprints[self.index]
        self.mesh_name = bp['name']
        print(f"Loading mesh: {self.mesh_name} ({bp['obj']})")
        self.mesh = Mesh(bp['obj'], (1, 1, 1, 1))
        
        # Load stored forward vector if present, otherwise default -Z
        offset = self.offsets.get(self.mesh_name, None)
        if offset and isinstance(offset.get('forward', None), list):
            f = np.array(offset['forward'], dtype=float)
            if length(f) > 1e-6:
                self.forward = f / float(np.linalg.norm(f))
            else:
                self.forward = np.array([0.0, 0.0, -1.0], dtype=float)
        else:
            self.forward = np.array([0.0, 0.0, -1.0], dtype=float)

    def save_offsets(self):
        # Store the current forward vector for this mesh
        fwd = [float(self.forward[0]), float(self.forward[1]), float(self.forward[2])]
        self.offsets[self.mesh_name] = {'forward': fwd}
        with open('forward_offsets.json', 'w') as f:
            json.dump(self.offsets, f, indent=4)
        print(f"Saved forward for {self.mesh_name}: {fwd}")

    def run(self):
        clock = pygame.time.Clock()
        running = True
        
        # Mouse control state
        dragging = False
        last_mouse_pos = (0, 0)

        while running:
            dt = clock.tick(60) / 1000.0
            
            for event in pygame.event.get():
                if event.type == QUIT: running = False
                if event.type == KEYDOWN:
                    if event.key == K_ESCAPE: running = False
                    if event.key == K_SPACE:
                        self.index = (self.index + 1) % len(self.blueprints)
                        self.load_current_mesh()
                    if event.key == K_s:
                        self.save_offsets()
                
                if event.type == MOUSEBUTTONDOWN:
                    if event.button == 1:
                        dragging = True
                        last_mouse_pos = event.pos
                if event.type == MOUSEBUTTONUP:
                    if event.button == 1:
                        dragging = False
                if event.type == MOUSEMOTION and dragging:
                    dx = event.pos[0] - last_mouse_pos[0]
                    dy = event.pos[1] - last_mouse_pos[1]
                    # Adjust the preview camera angles (mouse controls viewpoint)
                    self.view_yaw = (self.view_yaw + dx * 0.5) % 360.0
                    self.view_pitch = clamp(self.view_pitch + dy * 0.5, -89.0, 89.0)
                    last_mouse_pos = event.pos

            keys = pygame.key.get_pressed()
            # Direct forward-vector editing
            sens = 0.6 * dt
            if keys[K_LEFT]:  self.forward[0] -= sens
            if keys[K_RIGHT]: self.forward[0] += sens
            if keys[K_UP]:    self.forward[1] += sens
            if keys[K_DOWN]:  self.forward[1] -= sens
            if keys[K_w]:     self.forward[2] -= sens
            if keys[K_s]:     self.forward[2] += sens
            if keys[K_r]:
                self.forward = np.array([0.0, 0.0, -1.0], dtype=float)
            if length(self.forward) > 1e-6:
                self.forward = self.forward / float(np.linalg.norm(self.forward))

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            glLoadIdentity()
            glTranslatef(0, 0, -self.distance)
            # Apply camera view rotation (use view_yaw/view_pitch)
            glRotatef(self.view_pitch, 1, 0, 0)
            glRotatef(self.view_yaw, 0, 1, 0)

            # Draw Static Forward Axis (World Target)
            # This is the direction the game considers "FORWARD"
            glDisable(GL_LIGHTING)
            # Thicker central shaft
            glLineWidth(6.0)
            glBegin(GL_LINES)
            glColor3f(1, 1, 0) # Yellow = Target Forward
            glVertex3f(0, 0, 0); glVertex3f(0, 0, -18.0)
            glEnd()
            glLineWidth(1.0)
            # Arrowhead at tip for better visibility
            ah = 1.2
            tip = -18.0
            glBegin(GL_TRIANGLES)
            glColor3f(1, 1, 0)
            glVertex3f(0.0, 0.0, tip)
            glVertex3f(-ah * 0.5, ah, tip + 2.0)
            glVertex3f( ah * 0.5, ah, tip + 2.0)
            glEnd()

            # Draw World Reference Axes (thin)
            glBegin(GL_LINES)
            glColor3f(0.5, 0, 0); glVertex3f(0, 0, 0); glVertex3f(5, 0, 0) # X
            glColor3f(0, 0.5, 0); glVertex3f(0, 0, 0); glVertex3f(0, 5, 0) # Y
            glEnd()

            # Draw Model with its user-adjusted offset
            glPushMatrix()
            # Compute yaw/pitch from forward vector and apply to the model for visual alignment
            fy = clamp(self.forward[1], -0.99, 0.99)
            yaw = math.degrees(math.atan2(self.forward[0], -self.forward[2]))
            pitch = -math.degrees(math.asin(fy))
            glRotatef(yaw, 0, 1, 0)
            glRotatef(pitch, 1, 0, 0)
            
            glUseProgram(self.prog)
            if self.mesh:
                self.mesh.draw(self.prog)
            glUseProgram(0)
            
            glPopMatrix()

            # HUD text in 2D
            glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, self.w, self.h, 0, -1, 1)
            glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity(); glDisable(GL_DEPTH_TEST)
            glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            
            from render import draw_text
            y_off = 30
            controls = [
                f"MODELE : {self.mesh_name}",
                f"FORWARD : [{self.forward[0]:.3f}, {self.forward[1]:.3f}, {self.forward[2]:.3f}]",
                "",
                "SOURIS (Maintenir Clic Gauche) : Tourner la vue",
                "FLECHES : Nudge X/Y composants",
                "W/S : Nudge Z composant",
                "R : Reset forward",
                "ESPACE : Changer de vaisseau",
                "S : Sauvegarder (forward_offsets.json)",
                "",
                "BUT : Aligner le nez du modele sur la LIGNE JAUNE"
            ]
            for line in controls:
                # Use a clear color for text
                draw_text(line, 30, y_off, 28, (255, 255, 150, 255))
                y_off += 30

            glEnable(GL_DEPTH_TEST); glMatrixMode(GL_MODELVIEW); glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

            pygame.display.flip()

        pygame.quit()

if __name__ == "__main__":
    ForwardCalibrator().run()

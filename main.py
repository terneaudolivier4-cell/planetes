# space_shooter_gamepy (cockpit cover fix)
import sys, os, math, random, json
import numpy as np
import pygame
import pygame.font
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

from render import (
    clamp, wrap_angle_deg, vec3, length, normalize, deg2rad,
    BILLBOARD_VERT, BILLBOARD_FRAG, MODEL_VERT, MODEL_FRAG, SKYBOX_VERT, SKYBOX_FRAG,
    create_program, create_texture_from_surface, load_image_rgba, draw_text,
    draw_fullscreen_textured_quad_fit,
    draw_billboard, load_skybox
)
from space_shooter_core import (
    FlashFX, FlipSmoke, FlipSparks, Tracer, Mesh, Audio
)
from ui_radar_panel import create_radar_fbo, render_radar_fbo, blit_radar_to_panel, load_radar_panel_uv
from ui_health_panel import create_health_fbo, render_health_fbo, blit_health_to_panel, load_health_panel_uv, make_ship_icon, make_aura_texture
from ui_progress_panel import create_progress_fbo, render_progress_fbo, blit_progress_to_panel, load_progress_panel_uv
from ui_help_menu import draw_help_menu
from entities import Missile, Player, Bullet, Laser, ModelEnemy, Pickup
from enemy_ai import update_all_enemies

# Local helper for center sprite

def draw_centered_sprite(tex_id, win_w, win_h, cx=0.5, cy=0.5, w_norm=0.10, h_norm=0.10, alpha=1.0):
    quad_w = int(win_w * w_norm)
    quad_h = int(win_h * h_norm)
    x = int(cx * win_w) - quad_w // 2
    y = int(cy * win_h) - quad_h // 2
    glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, win_w, win_h, 0, -1, 1)
    glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity()
    glDisable(GL_DEPTH_TEST)
    glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D, tex_id)
    glColor4f(1,1,1,alpha)
    glBegin(GL_QUADS)
    glTexCoord2f(0,0); glVertex2f(x,     y)
    glTexCoord2f(1,0); glVertex2f(x+quad_w, y)
    glTexCoord2f(1,1); glVertex2f(x+quad_w, y+quad_h)
    glTexCoord2f(0,1); glVertex2f(x,     y+quad_h)
    glEnd()
    glBindTexture(GL_TEXTURE_2D, 0); glDisable(GL_TEXTURE_2D); glEnable(GL_DEPTH_TEST)
    glMatrixMode(GL_MODELVIEW);  glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

class Game:
    def __init__(self, w=1920, h=1080):
        player_cfg = self._load_json('player_config.json', {})
        wave_cfg   = self._load_json('wave_config.json', {})
        self.wave_cfg = wave_cfg

        pygame.init(); pygame.font.init()
        # Enable multisampling for antialiasing
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
        pygame.display.set_mode((w,h), DOUBLEBUF|OPENGL)  # Windowed mode
        pygame.display.set_caption('Space Shooter 3D - v7.3f (Radar-in-panel)')
        pygame.event.set_grab(True); pygame.mouse.set_visible(False)

        glEnable(GL_DEPTH_TEST); glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_MULTISAMPLE)  # Enable multisampling for smoother edges
        glEnable(GL_LIGHTING)  # Enable lighting for better 3D perception
        glEnable(GL_COLOR_MATERIAL)  # Allow material colors with lighting
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glClearColor(0.02,0.02,0.06,1.0)
        glMatrixMode(GL_PROJECTION); glLoadIdentity(); gluPerspective(70.0, w/float(h), 0.1, 3000.0)
        glMatrixMode(GL_MODELVIEW)

        self.clock = pygame.time.Clock(); self.w,self.h = w,h
        self.player = Player(player_cfg)
        self.bullets=[]; self.enemies=[]; self.wave=1; self.wave_in_progress=False
        self.enemies_to_spawn=0; self.spawn_int=1.0; self.spawn_t=0.0; self.score=0

        # Programs
        self.billboard_prog = create_program(BILLBOARD_VERT, BILLBOARD_FRAG)
        self.model_prog     = create_program(MODEL_VERT,     MODEL_FRAG)
        self.skybox_prog    = create_program(SKYBOX_VERT,    SKYBOX_FRAG)
        try:
            self.skybox = load_skybox('assets/skybox','png')
            if self.skybox == 0: print('[WARN] No skybox cubemap found; continuing without.')
        except Exception as e:
            print('[WARN] Skybox load failed:', e); self.skybox=0

        # Audio & bullet textures
        self.audio=Audio()
        self.bullet_tex_player,_=self._make_bullet_sprite(96,(255,230,80,255))
        self.bullet_tex_enemy,_ =self._make_bullet_sprite(96,(80,180,255,255))
        self.missile_tex,_ = self._make_bullet_sprite(128,(255,150,30,255))  # Orange glowing missile

        # Flipbooks
        def safe_fb(p):
            try: return create_texture_from_surface(load_image_rgba(os.path.join('assets', p)),False,True)[0]
            except Exception as e: print('[WARN] flipbook missing:',p,e); return 0
        self.tex_fb_flash  = safe_fb('flipbook_flash.png')
        self.tex_fb_smoke  = safe_fb('flipbook_smoke.png')
        self.tex_fb_sparks = safe_fb('flipbook_sparks.png')

        # Cockpit overlay (ensure width/height captured)
        self.cockpit_w=self.cockpit_h=1
        try:
            surf_cockpit = load_image_rgba('assets/cockpit_overlay.png')
            self.tex_cockpit,(self.cockpit_w,self.cockpit_h)=create_texture_from_surface(surf_cockpit,False,True)
        except Exception as e:
            print('[WARN] cockpit overlay missing:',e); self.tex_cockpit=0

        # Reticle
        try:
            self.tex_reticle,_=create_texture_from_surface(load_image_rgba('assets/reticle_overlay.png'),False,True)
        except Exception as e:
            print('[WARN] reticle overlay missing:',e); self.tex_reticle=0

        # VFX Glow for pickups
        try:
            self.tex_glow,_=create_texture_from_surface(load_image_rgba('assets/vfx_glow.png'),False,True)
        except Exception as e:
            print('[WARN] vfx_glow missing:',e); self.tex_glow=0

        # Load textures for pickups with flipped vertical orientation
        self.tex_shield, _ = create_texture_from_surface(load_image_rgba('assets/shield.png'), flip=True)
        self.tex_missile, _ = create_texture_from_surface(load_image_rgba('assets/missile_pickup.png'), flip=True)

        self.pickups = []
        self.notifications = []

        # Parallax pixels
        px = player_cfg.get('parallax',{})
        self.parallax_x=float(px.get('x_pixels',10.0))
        self.parallax_y=float(px.get('y_pixels',8.0))

        # Mesh blueprints
        self.meshes={}
        ENEMY_BLUEPRINTS=wave_cfg.get('enemy_blueprints',[])
        for bp in ENEMY_BLUEPRINTS:
            try:
                self.meshes[bp['name']] = Mesh(bp['obj'],(1,1,1,1))
                print('[INFO] Loaded',bp['obj'])
            except Exception as e:
                print('[ERROR] Cannot load',bp['obj'],e)
        self.enemy_blueprints={bp['name']:bp for bp in ENEMY_BLUEPRINTS}
        # Migrate blueprint key 'speed' -> 'maxspeed' for consistency
        for bp in ENEMY_BLUEPRINTS:
            if 'speed' in bp and 'maxspeed' not in bp:
                bp['maxspeed'] = bp.pop('speed')
        self.enemy_can_shoot=False
        self.vfx_flashes_fb=[]; self.vfx_tracers=[]; self.vfx_sparks_fb=[]; self.vfx_smokes_fb=[]

        # Missile mesh (3D model)
        try:
            self.missile_mesh = Mesh('assets/missile.obj', (1, 1, 1, 1))
            self.missile_scale = 1.6
            print('[INFO] Loaded assets/missile.obj')
        except Exception as e:
            print('[ERROR] Cannot load missile mesh:', e)
            self.missile_mesh = None
            self.missile_scale = 1.0
        self.hum_playing=False

        # Radar FBO & panel
        self.radar_fbo, self.radar_tex, self.radar_rbo, self.radar_size = create_radar_fbo(512)
        self.radar_panel_uv = load_radar_panel_uv('assets/radar_panel_uv.json')

        # Health panel FBO & resources
        self.health_fbo, self.health_tex, self.health_rbo, self.health_size = create_health_fbo(256)
        self.health_panel_uv = load_health_panel_uv('assets/health_panel_uv.json')
        self.health_ship_tex, _ = make_ship_icon(128, (200,220,255,255))
        self.health_aura_tex, _ = make_aura_texture(256, 220, (80,200,255))
        self.health_font = pygame.font.Font(None, 45)

        # Progress panel FBO & resources
        self.progress_fbo, self.progress_tex, self.progress_rbo, self.progress_size = create_progress_fbo(512)
        self.progress_panel_uv = load_progress_panel_uv('assets/progress_panel_uv.json')
        self.progress_font = pygame.font.Font(None, 120)

        # Missile system
        self.missiles = []
        self.missile_count = 8
        self.lock_target = None
        self.lock_timer = 0.0
        self.lock_duration = 1.0  # 1 second to lock
        self.is_locked = False

        self.radar_calibration = True
        # Pause / help overlay
        self.paused = False
        self.debug_vectors = False
        # Audio toggles
        self.music_on = True
        self.sfx_on = True
        # Pause snapshot (texture) to freeze background when overlay active
        self.pause_snapshot_tex = 0
        self.snapshot_pending = False

        # Test pickups at startup
        self.pickups.append(Pickup(vec3(0, 0, -30), 'shield', self.tex_shield))
        self.pickups.append(Pickup(vec3(5, 0, -30), 'missile', self.tex_missile))
        #print(f"[INFO] Spawned pickup: shield at {vec3(0, 0, -30)}")
        #print(f"[INFO] Spawned pickup: missile at {vec3(5, 0, -30)}")

    def _load_json(self,path,default=None):
        try:
            if not os.path.exists(path):
                print(f"[ERROR] JSON file not found: {path}")
            with open(path,'r',encoding='utf-8') as f: return json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load JSON config '{path}': {e}")
            return ({} if default is None else default)

    def _make_bullet_sprite(self,size=64,color=(255,230,80,255)):
        s=pygame.Surface((size,size),SRCALPHA); s.fill((0,0,0,0)); cx,cy=size//2,size//2; r=size//2-2
        for R in range(r,0,-1):
            t=R/float(r); c=(int(color[0]*1.0),int(color[1]*t),int(color[2]*t),int(255*t))
            pygame.draw.circle(s,c,(cx,cy),R)
        return create_texture_from_surface(s,False)

    def remaining_enemies(self): return self.enemies_to_spawn + len(self.enemies)

    def _wave_params(self,n):
        wc=self.wave_cfg
        base=int(wc.get('wave_start_enemies_base',6)); extra=int(wc.get('wave_extra_per_wave',3))
        spawn_base=float(wc.get('spawn_interval_base',1.0)); spawn_dec=float(wc.get('spawn_interval_decrease_per_wave',0.06)); spawn_min=float(wc.get('spawn_interval_min',0.5))
        can_shoot_th=int(wc.get('enemy_can_shoot_wave_threshold',2))
        fire_base=float(wc.get('enemy_fire_rate_base',1.0)); fire_inc=float(wc.get('enemy_fire_rate_increment_per_wave',0.2))
        bs_base=float(wc.get('enemy_bullet_speed_base',36.0)); bs_inc=float(wc.get('enemy_bullet_speed_increment_per_wave',2.0))
        enemies_to_spawn=base+extra*(n-1); spawn_int=max(spawn_min,spawn_base-spawn_dec*(n-1))
        return enemies_to_spawn, spawn_int, (n>=can_shoot_th), (fire_base+fire_inc*(n-1)), (bs_base+bs_inc*(n-1))

    def _enemy_choices_for_wave(self,n):
        sel=self.wave_cfg.get('enemy_selection_by_wave',{}); key=str(n)
        if key in sel: return sel[key]
        return sel.get('default',['fighter'])

    def start_wave(self,n):
        enemies_to_spawn, spawn_int, can_shoot, fire_rate, bullet_speed = self._wave_params(n)
        self.wave=n; self.enemies_to_spawn=enemies_to_spawn; self.wave_in_progress=True; self.spawn_int=spawn_int
        self.enemy_can_shoot=can_shoot; self.enemy_fire_rate=fire_rate; self.enemy_bullet_speed=bullet_speed
        print(f'[INFO] Wave {n}: {self.enemies_to_spawn} enemies @ {self.spawn_int:.2f}s, can_shoot={self.enemy_can_shoot}')

    def spawn_enemy(self):
        choices=self._enemy_choices_for_wave(self.wave); name=random.choice(choices)
        bp=self.enemy_blueprints.get(name,None)
        if bp is None: return
        d=random.uniform(80.0,150.0); th=random.uniform(0,2*math.pi); ph=random.uniform(0.35*math.pi,0.65*math.pi)
        x=self.player.pos[0]+d*math.sin(ph)*math.cos(th); y=self.player.pos[1]+d*math.cos(ph); z=self.player.pos[2]+d*math.sin(ph)*math.sin(th)
        e=ModelEnemy(vec3(x,y,z),Mesh(bp['obj'],(1,1,1,1)),scale=bp['scale'],shoot=self.enemy_can_shoot,fire_rate=self.enemy_fire_rate,bullet_speed=self.enemy_bullet_speed)
        e.radius = bp.get('radius', 1.2)
        # Prefer blueprint 'maxspeed' (migrated) but fall back to legacy 'speed'
        e.maxspeed = bp.get('maxspeed', bp.get('speed', 4.2))
        # Initialize runtime speed as a percentage of blueprint maxspeed
        init_pct = float(bp.get('init_speed_pct', 100))
        e.speed = float(e.maxspeed * (init_pct / 100.0))
        # Set initial velocity along the entity's forward vector
        try:
            e.velocity = e.forward() * e.speed
        except Exception:
            e.velocity = e.velocity
        e.health=bp.get('health',1); e.damage=bp.get('damage',8)  # Health in laser hits, damage per hit
        self.enemies.append(e); self.enemies_to_spawn-=1

    def handle_input(self,dt):
        # Handle events; when paused we accept ESC, Q and mouse clicks for overlay buttons
        for ev in pygame.event.get():
            if ev.type==QUIT: raise SystemExit
            if ev.type==KEYDOWN and ev.key==K_ESCAPE:
                # Toggle pause/help overlay
                self.paused = not self.paused
                if self.paused:
                    pygame.event.set_grab(False); pygame.mouse.set_visible(True)
                    # request a snapshot to be captured after the next frame render
                    self.snapshot_pending = True
                else:
                    pygame.event.set_grab(True); pygame.mouse.set_visible(False)
                    # delete snapshot texture if present
                    try:
                        if getattr(self, 'pause_snapshot_tex', 0):
                            glDeleteTextures([self.pause_snapshot_tex]); self.pause_snapshot_tex = 0
                    except Exception:
                        pass
                continue
            
            if ev.type==KEYDOWN and ev.key==K_v:
                self.debug_vectors = not self.debug_vectors
                print(f"[DEBUG] Display vectors: {self.debug_vectors}")

            if self.paused:
                # While paused accept simple keys and mouse clicks
                if ev.type==KEYDOWN and ev.key==K_q:
                    print('[INFO] Quit.'); pygame.event.set_grab(False); raise SystemExit
                if ev.type==MOUSEBUTTONDOWN and ev.button==1:
                    mx,my = ev.pos
                    # Compute button block geometry to match draw_help_menu()
                    pad = 12
                    panel_w = int(self.w * 0.50); panel_h = int(self.h * 0.50)
                    panel_x = (self.w - panel_w) // 2; panel_y = (self.h - panel_h) // 2
                    bw = int(panel_w * 0.28); bh = int(panel_h * 0.12)
                    bx = panel_x + panel_w - bw - pad
                    # place the block so its bottom has a `pad` margin from panel bottom
                    by = panel_y + panel_h - pad - (bh + pad) * 3
                    # Music selector: left half = ON, right half = OFF
                    if bx <= mx <= bx + bw and by <= my <= by + bh:
                        # choose ON/OFF via which half was clicked
                        if mx - bx < (bw // 2):
                            self.music_on = True
                            try: pygame.mixer.music.unpause()
                            except Exception: pass
                        else:
                            self.music_on = False
                            try: pygame.mixer.music.pause()
                            except Exception: pass
                    # SFX selector
                    sfx_y0 = by + bh + pad
                    if bx <= mx <= bx + bw and sfx_y0 <= my <= sfx_y0 + bh:
                        if mx - bx < (bw // 2):
                            self.sfx_on = True
                        else:
                            self.sfx_on = False
                        self.audio.enabled = self.sfx_on
                    # Quit button (full row)
                    quit_y0 = by + (bh + pad) * 2
                    if bx <= mx <= bx + bw and quit_y0 <= my <= quit_y0 + bh:
                        print('[INFO] Quit.'); pygame.event.set_grab(False); raise SystemExit
                # ignore other events while paused
                continue

        # If not paused, process normal input state
        k=pygame.key.get_pressed(); mb=pygame.mouse.get_pressed(); mx,my=pygame.mouse.get_rel(); sens=0.08
        # Maintain yaw/pitch angles directly for unrestricted rotation
        if not hasattr(self.player, 'yaw'):
            # Initialize angles from current direction on first run
            cur_dir = self.player.forward()
            self.player.yaw = math.degrees(math.atan2(cur_dir[0], -cur_dir[2]))
            self.player.pitch = -math.degrees(math.asin(clamp(cur_dir[1], -0.99, 0.99)))
        
        # Update angles with mouse input (no wrapping on pitch for full rotation)
        self.player.yaw = wrap_angle_deg(self.player.yaw + mx * sens)
        self.player.pitch = self.player.pitch + my * sens  # No limit - allow full rotation
        
        # Reconstruct direction vector from unlimited yaw/pitch
        cy=math.cos(deg2rad(self.player.yaw)); sy=math.sin(deg2rad(self.player.yaw))
        cp=math.cos(deg2rad(self.player.pitch)); sp=math.sin(deg2rad(self.player.pitch))
        new_dir = normalize(vec3(sy*cp, -sp, -cy*cp))
        self.player.direction = new_dir
        thrust=bool(k[K_SPACE]); brake=k[K_s]; lat=0.0  # Lateral movement disabled
        # Roll input
        if k[K_w]: self.player.roll -= self.player.roll_rate * dt  # Roll left
        if k[K_x]: self.player.roll += self.player.roll_rate * dt  # Roll right
        if mb[0]: self.try_player_shoot()  # Left click = laser
        if mb[2]: self.fire_missile()      # Right click = missile
        if k[K_k]: self.enemies=[]; print('[DEBUG] All enemies killed.')
        if k[K_q]: print('[INFO] Quit.'); pygame.event.set_grab(False); raise SystemExit
        self.player.integrate_motion(dt,thrust,brake,lat)
        if thrust or length(self.player.velocity)>0.5:
            if not self.hum_playing: self.audio.loop('sfx_engine_hum.wav'); self.hum_playing=True
        else:
            if self.hum_playing: self.audio.stop('sfx_engine_hum.wav'); self.hum_playing=False

    def try_player_shoot(self):
        d=self.player.forward(); up=vec3(0,1,0); right=normalize(np.cross(d, up))
        # Fire two red lasers from each side of the ship
        for offset in (-1.8, 1.8):
            s=self.player.pos+d*2.0+right*offset
            laser=Laser(s, d, speed=800.0, radius=0.5, fr=True, max_range=2000.0, color=(1.0, 0.0, 0.0))
            self.bullets.append(laser)
        self.audio.play('sfx_blaster_shot.wav')

    def spawn_pickup(self, pos):
        with open('wave_config.json', 'r') as f:
            config = json.load(f)
        if random.random() < config['pickup_spawn_probability']:
            ptype = random.choice(['health', 'missile'])
            tex = self.tex_shield if ptype == 'health' else self.tex_missile
            self.pickups.append(Pickup(pos, ptype, tex))

    def spawn_notification(self, text, color=(255, 255, 255, 255)):
        self.notifications.append({'text': text, 'time': 2.5, 'max_time': 2.5, 'color': color})

    def update(self,dt):
        if not self.wave_in_progress: self.start_wave(self.wave)
        else:
            self.spawn_t+=dt
            if self.spawn_t>=self.spawn_int and self.enemies_to_spawn>0:
                self.spawn_t=0.0; self.spawn_enemy()
        # Update all enemies with advanced AI (formations, prediction, avoidance)
        update_all_enemies(self.enemies, self.player.pos, self.player.velocity, dt)
        
        new=[]
        for e in self.enemies:
            b=e.try_shoot(self.player.pos,dt,self.bullet_tex_enemy)
            if b is not None:
                new.append(b)
        for b in self.bullets:
            b.update(dt)
            if hasattr(b, 'tracer') and b.tracer: b.tracer.push(b.pos)
        self.bullets.extend(new)
        alive_e=[]
        for e in self.enemies:
            hit=False
            for b in self.bullets:
                if b.friendly and length(e.pos-b.pos)<= (e.radius+b.radius)*2.5:
                    hit=True; b.radius=-1; self.score+=1
                    # Reduce enemy health
                    e.health = getattr(e, 'health', 1) - 1
                    self.audio.play('sfx_sparks.wav')
                    if e.health <= 0:
                        # Enemy dies
                        self._spawn_explosion_burst(e.pos, e.radius)
                        self.audio.play('sfx_explosion_small.wav')
                        self.spawn_pickup(e.pos)
                    break
            if e.health > 0: alive_e.append(e)
        self.enemies=alive_e
        dmg=0; alive_b=[]
        for b in self.bullets:
            if length(b.pos-self.player.pos)>800.0: continue
            if (not b.friendly) and length(b.pos-self.player.pos)<= (b.radius+1.0): 
                dmg += getattr(b, 'damage', 8)  # Use bullet's damage value
            else:
                if b.radius>0: alive_b.append(b)
        self.bullets=alive_b
        if dmg>0: self.player.health=max(0,self.player.health-dmg); self.audio.play('sfx_shield_hit.wav')
        self.update_vfx(dt)
        
        # Update missiles
        alive_missiles = []
        for m in self.missiles:
            if m.update(dt):
                # Check collision with enemies
                hit = False
                for e in self.enemies:
                    if length(m.pos - e.pos) <= (e.radius + m.radius):
                        hit = True
                        self.enemies.remove(e)
                        self.score += 5  # Missile kill worth more
                        self._spawn_explosion_burst(e.pos, e.radius)
                        self.audio.play('sfx_explosion_small.wav')
                        self.spawn_pickup(e.pos)
                        break
                if not hit:
                    alive_missiles.append(m)
        self.missiles = alive_missiles
        
        # Update pickups
        alive_pickups = []
        for p in self.pickups:
            p.update(dt)
            if length(p.pos - self.player.pos) < 15.0: # Collection radius
                if p.type == 'health':
                    self.player.health = min(100, self.player.health + 25)
                    self.spawn_notification("+25 HEALTH", (50, 255, 100, 255))
                elif p.type == 'missile':
                    self.missile_count = min(12, self.missile_count + 2)
                    self.spawn_notification("+2 MISSILES", (255, 200, 50, 255))
                self.audio.play('sfx_pickup.wav') # Using the correct pickup sound
            else:
                alive_pickups.append(p)
        self.pickups = alive_pickups
        
        # Update notifications
        alive_notifs = []
        for n in self.notifications:
            n['time'] -= dt
            if n['time'] > 0: alive_notifs.append(n)
        self.notifications = alive_notifs
        
        # Target lock system
        self.update_lock(dt)
        
        if self.wave_in_progress and self.enemies_to_spawn<=0 and len(self.enemies)==0:
            self.wave_in_progress=False; self.wave+=1; print(f"[INFO] Wave cleared -> {self.wave}"); self.audio.play('sfx_ui_click.wav')

    def _spawn_explosion_burst(self,pos,radius=1.0):
        scale = max(0.5, radius / 1.2)  # Normalize to typical radius; minimum 0.5x
        if self.tex_fb_flash!=0:
            # Intense core flash + multiple expanding rings
            for s in (3.5, 2.8, 2.2, 1.5): self.vfx_flashes_fb.append(FlashFX(pos,self.tex_fb_flash,8,6,60,s*scale))
        if self.tex_fb_sparks!=0: 
            # Multiple sparks bursts for more dynamic effect
            for _ in range(3): self.vfx_sparks_fb.append(FlipSparks(pos,self.tex_fb_sparks,8,5,48,2.6*scale))
        if self.tex_fb_smoke!=0:
            # Larger, more numerous smoke clouds
            for s in (4.8, 3.8, 3.2, 4.4, 3.0): self.vfx_smokes_fb.append(FlipSmoke(pos,self.tex_fb_smoke,8,8,28,s*scale))

    def update_vfx(self,dt):
        for lst in (self.vfx_flashes_fb,self.vfx_tracers,self.vfx_sparks_fb,self.vfx_smokes_fb):
            alive=[]
            for fx in lst:
                fx.update(dt)
                if fx.alive(): alive.append(fx)
            lst[:]=alive

    def update_lock(self, dt):
        """Update target lock system - finds enemy in crosshair."""
        forward = self.player.forward()
        best_enemy = None
        best_angle = 0.995  # ~5 degree cone
        
        for e in self.enemies:
            to_enemy = e.pos - self.player.pos
            dist = length(to_enemy)
            if dist > 0.1:
                dir_to_enemy = to_enemy / dist
                dot = float(np.dot(forward, dir_to_enemy))
                if dot > best_angle:
                    best_angle = dot
                    best_enemy = e
        
        if best_enemy is not None:
            if self.lock_target == best_enemy:
                self.lock_timer += dt
                if self.lock_timer >= self.lock_duration:
                    self.is_locked = True
            else:
                self.lock_target = best_enemy
                self.lock_timer = 0.0
                self.is_locked = False
        else:
            self.lock_target = None
            self.lock_timer = 0.0
            self.is_locked = False

    def fire_missile(self):
        """Fire a missile at the locked target."""
        if self.missile_count > 0 and self.is_locked and self.lock_target is not None:
            forward = self.player.forward()
            cr, cu = self.camera_vectors()
            theta = deg2rad(45.0)
            dir0 = normalize(forward * math.cos(theta) - cu * math.sin(theta))
            missile = Missile(
                pos=self.player.pos.copy(),
                vel=dir0 * 150.0,
                target=self.lock_target
            )
            self.missiles.append(missile)
            self.missile_count -= 1
            self.is_locked = False
            self.lock_timer = 0.0
            self.audio.play('sfx_blaster_shot.wav')  # Use existing sound for now
            print(f"[INFO] Missile fired! Remaining: {self.missile_count}")

    def set_camera(self):
        # Use the player's stored yaw/pitch angles directly
        yaw = getattr(self.player, 'yaw', 0.0)
        pitch = getattr(self.player, 'pitch', 0.0)
        roll = getattr(self.player, 'roll', 0.0)
        f = self.player.forward()
        glLoadIdentity(); glRotatef(pitch,1,0,0); glRotatef(yaw,0,1,0); glRotatef(roll, f[0], f[1], f[2]); glTranslatef(-self.player.pos[0],-self.player.pos[1],-self.player.pos[2])

    def camera_vectors(self):
        f=self.player.forward(); wu=vec3(0,1,0); ru=vec3(0,0,1) if abs(float(np.dot(f,wu)))>0.99 else wu
        cr=normalize(np.cross(f,ru)); cu=normalize(np.cross(cr,f)); return cr,cu

    # Radar FBO
    def draw_hud(self):
        w, h = self.w, self.h
        # When paused, HUD panels are disabled per request
        if getattr(self, 'paused', False):
            return
        health_pct = self.player.health / 100.0
        
        # Render health panel to FBO (before changing viewport)
        render_health_fbo(self.health_fbo, self.health_size, self.health_ship_tex, self.health_aura_tex, health_pct, self.health_font)
        
        # Render radar to FBO (before changing viewport)
        enemies_pos_list = [e.pos for e in self.enemies]
        # Compute player yaw/pitch locally for HUD/radar (no player attributes)
        # Pass player's forward vector directly to radar rendering
        render_radar_fbo(self.radar_fbo, self.radar_size, self.player.forward(), self.player.pos, enemies_pos_list, max_range=70.0)
        
        # Render progress panel to FBO (before changing viewport)
        speed_val = length(self.player.velocity)
        render_progress_fbo(self.progress_fbo, self.progress_size, self.wave, self.score, self.remaining_enemies(), speed_val, self.progress_font)
        
        # Reset viewport to full window (no clear - scene 3D already rendered)
        glViewport(0, 0, w, h)
        
        # Disable lighting for UI
        glDisable(GL_LIGHTING)
        
        # Setup for 2D text/UI rendering
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, w, h, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW);  glPushMatrix(); glLoadIdentity(); glDisable(GL_DEPTH_TEST)
        
        # Blit panels to screen
        blit_health_to_panel(self.health_tex, self.health_panel_uv, w, h, background_color=(0, 0, 0, 1))
        blit_radar_to_panel(self.radar_tex, self.radar_panel_uv, w, h, background_color=None)
        blit_progress_to_panel(self.progress_tex, self.progress_panel_uv, w, h, background_color=(0, 0, 0, 1))
        
        # Draw LOCK indicator when locked
        if self.is_locked:
            lock_x = int(w * 0.52)  # Just right of center
            lock_y = int(h * 0.48)
            draw_text("LOCK", lock_x, lock_y, 36, (255, 50, 50, 255))
        
        # Draw missile count
        missile_x = int(w * 0.85)
        missile_y = int(h * 0.05)
        draw_text(f"Missiles: {self.missile_count}", missile_x, missile_y, 28, (255, 200, 100, 255))
        
        # Draw notifications
        y_notif = int(h * 0.35)
        for n in self.notifications:
            alpha = int(255 * (n['time'] / n['max_time']))
            c = (n['color'][0], n['color'][1], n['color'][2], alpha)
            draw_text(n['text'], int(w * 0.5) - 80, y_notif, 42, c)
            y_notif += 45
        
        glEnable(GL_LIGHTING)  # Re-enable lighting for 3D
        glEnable(GL_DEPTH_TEST); glMatrixMode(GL_MODELVIEW); glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

    def _draw_skybox(self):
        if getattr(self,'skybox',0)==0: return
        glPushMatrix()
        # Keep camera rotation/translation already applied, but cancel translation so skybox stays centered on the player
        glDisable(GL_DEPTH_TEST)
        glDepthMask(GL_FALSE)
        # Undo camera translation by translating to the player's world position
        glTranslatef(self.player.pos[0], self.player.pos[1], self.player.pos[2])
        glUseProgram(self.skybox_prog); glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_CUBE_MAP,self.skybox)
        loc=glGetUniformLocation(self.skybox_prog,b"uCube");
        if loc!=-1: glUniform1i(loc,0)
        s=1000.0; glBegin(GL_QUADS)
        glVertex3f( s,-s,-s); glVertex3f( s,-s, s); glVertex3f( s, s, s); glVertex3f( s, s,-s)
        glVertex3f(-s,-s, s); glVertex3f(-s,-s,-s); glVertex3f(-s, s,-s); glVertex3f(-s, s, s)
        glVertex3f(-s, s,-s); glVertex3f( s, s,-s); glVertex3f( s, s, s); glVertex3f(-s, s, s)
        glVertex3f(-s,-s, s); glVertex3f( s,-s, s); glVertex3f( s,-s,-s); glVertex3f(-s,-s,-s)
        glVertex3f( s,-s, s); glVertex3f(-s,-s, s); glVertex3f(-s, s, s); glVertex3f( s, s, s)
        glVertex3f(-s,-s,-s); glVertex3f( s,-s,-s); glVertex3f( s, s,-s); glVertex3f(-s, s,-s)
        glEnd(); glBindTexture(GL_TEXTURE_CUBE_MAP,0); glUseProgram(0)
        glDepthMask(GL_TRUE)
        glEnable(GL_DEPTH_TEST); glPopMatrix()

    def draw(self):
        glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
        # If paused and we already have a snapshot, show the snapshot instead of re-rendering the 3D scene
        if getattr(self, 'paused', False) and (not getattr(self, 'snapshot_pending', False)) and getattr(self, 'pause_snapshot_tex', 0):
            # Draw snapshot fullscreen
            glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(0, self.w, self.h, 0, -1, 1)
            glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity(); glDisable(GL_DEPTH_TEST)
            glEnable(GL_TEXTURE_2D); glBindTexture(GL_TEXTURE_2D, self.pause_snapshot_tex)
            glColor4f(1.0,1.0,1.0,1.0)
            glBegin(GL_QUADS)
            glTexCoord2f(0,0); glVertex2f(0,0)
            glTexCoord2f(1,0); glVertex2f(self.w,0)
            glTexCoord2f(1,1); glVertex2f(self.w,self.h)
            glTexCoord2f(0,1); glVertex2f(0,self.h)
            glEnd()
            glBindTexture(GL_TEXTURE_2D, 0); glDisable(GL_TEXTURE_2D)
            # draw overlay on top
            draw_help_menu(self)
            pygame.display.flip()
            glMatrixMode(GL_MODELVIEW); glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)
            return

        # Normal rendering path (scene rendered) or paused but snapshot pending (we must render once to capture)
        self.set_camera()
        self._draw_skybox()
        cr,cu=self.camera_vectors()
        for e in self.enemies: e.draw(self.model_prog)

        for p in self.pickups: p.draw(self.billboard_prog, cr, cu)
        
        # Draw missiles as lit 3D models (fall back to sprite if mesh unavailable)
        if getattr(self, 'missile_mesh', None) is not None:
            for m in self.missiles:
                dir_vec = normalize(m.vel) if length(m.vel) > 1e-3 else vec3(0, 0, -1)
                yaw   = math.degrees(math.atan2(dir_vec[0], -dir_vec[2]))
                pitch = -math.degrees(math.asin(clamp(dir_vec[1], -1.0, 1.0)))
                glPushMatrix()
                glTranslatef(m.pos[0], m.pos[1], m.pos[2])
                glRotatef(yaw, 0, 1, 0)
                glRotatef(pitch, 1, 0, 0)
                glScalef(self.missile_scale, self.missile_scale, self.missile_scale)
                self.missile_mesh.draw(self.model_prog)
                glPopMatrix()

        # Draw bullets - disable lighting for proper laser visibility
        glDisable(GL_LIGHTING)
        for b in self.bullets:
            if hasattr(b, 'tex'):
                draw_billboard(self.billboard_prog,b.tex,b.pos,b.size,cr,cu,(1,1,1,0.95))
            else:
                # Draw Laser as thick glowing lines
                glDisable(GL_TEXTURE_2D)
                glEnable(GL_LINE_SMOOTH)
                glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
                # Draw outer glow (thicker, semi-transparent)
                glLineWidth(4.0)
                glBegin(GL_LINES)
                glColor4f(b.color[0], b.color[1], b.color[2], 0.3)
                glVertex3f(*b.start)
                glVertex3f(*b.pos)
                glEnd()
                # Draw core (thinner, full brightness)
                glLineWidth(2.0)
                glBegin(GL_LINES)
                glColor3f(*b.color)
                glVertex3f(*b.start)
                glVertex3f(*b.pos)
                glEnd()
                glLineWidth(1.0)
                glDisable(GL_LINE_SMOOTH)
                glEnable(GL_TEXTURE_2D)

        # Missile trail (and billboard fallback if mesh missing)
        for m in self.missiles:
            if getattr(self, 'missile_mesh', None) is None:
                draw_billboard(self.billboard_prog, self.missile_tex, m.pos, 4.0, cr, cu, (1.0, 1.0, 1.0, 1.0))
            trail_dir = normalize(m.vel) if length(m.vel) > 1e-3 else vec3(0, 0, -1)
            trail_start = m.pos - trail_dir * 5.0
            glDisable(GL_TEXTURE_2D)
            glEnable(GL_LINE_SMOOTH)
            glLineWidth(8.0)
            glBegin(GL_LINES)
            glColor4f(1.0, 0.6, 0.1, 0.6)
            glVertex3f(*trail_start)
            glVertex3f(*m.pos)
            glEnd()
            glLineWidth(1.0)
            glDisable(GL_LINE_SMOOTH)
            glEnable(GL_TEXTURE_2D)

        glEnable(GL_LIGHTING)  # Re-enable lighting for VFX
        
        glBlendFunc(GL_SRC_ALPHA,GL_ONE)
        for fx in self.vfx_flashes_fb: fx.draw(self.billboard_prog,cr,cu)
        for fx in self.vfx_tracers:    fx.draw(self.billboard_prog,cr,cu)
        for fx in self.vfx_sparks_fb:  fx.draw(self.billboard_prog,cr,cu)
        glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA)
        for fx in self.vfx_smokes_fb:  fx.draw(self.billboard_prog,cr,cu)
        if getattr(self, 'debug_vectors', False):
            glDisable(GL_LIGHTING); glDisable(GL_TEXTURE_2D); glUseProgram(0)
            glLineWidth(2.0); glBegin(GL_LINES)
            for e in self.enemies:
                fwd = e.forward()
                glColor3f(1.0, 1.0, 0.0) # Yellow = Prow (Model Forward)
                glVertex3f(*e.pos); glVertex3f(*(e.pos + fwd * 8.0))
                if hasattr(e, 'velocity') and length(e.velocity) > 0.1:
                    glColor3f(0.0, 1.0, 1.0) # Cyan = Actual Velocity
                    glVertex3f(*e.pos); glVertex3f(*(e.pos + e.velocity * 1.5))
            glEnd(); glLineWidth(1.0); glEnable(GL_LIGHTING)
        # --- Render radar offscreen ---
        enemies_pos_list = [e.pos for e in self.enemies]
        render_radar_fbo(self.radar_fbo, self.radar_size, self.player.forward(), self.player.pos, enemies_pos_list, max_range=120.0)
        # IMPORTANT: reset viewport to full window after FBO pass
        glViewport(0, 0, self.w, self.h)

        # --- Cockpit FULL COVER (the actual fix) ---
        if getattr(self,'tex_cockpit',0)!=0 and self.cockpit_w>0 and self.cockpit_h>0:
            # Compute local yaw/pitch for cockpit parallax
            _f3 = self.player.forward()
            _yaw3 = math.degrees(math.atan2(_f3[0], -_f3[2]))
            _pitch3 = -math.degrees(math.asin(clamp(_f3[1], -0.99, 0.99)))
            px_norm=clamp(_yaw3,-10.0,10.0)/10.0
            py_norm=clamp(_pitch3,-8.0,8.0)/8.0
            parallax=(px_norm*self.parallax_x, py_norm*self.parallax_y)
            # Force 'cover' to fill the whole window
            draw_fullscreen_textured_quad_fit(
                self.tex_cockpit,
                self.cockpit_w, self.cockpit_h,
                self.w, self.h,
                'cover',  # <== ensures full-window coverage
                parallax,
                1.0
            )
            blit_radar_to_panel(self.radar_tex, self.radar_panel_uv, self.w, self.h)

        # Reticle - disable lighting for UI elements
        glDisable(GL_LIGHTING)
        if getattr(self,'tex_reticle',0)!=0:
            draw_centered_sprite(self.tex_reticle, self.w, self.h, 0.5, 0.5, 0.10, 0.10, 1.0)
        glEnable(GL_LIGHTING)

        # HUD
        # If paused, render help overlay on top of scene
        # If paused, capture a snapshot once (after scene rendered) and show overlay
        if getattr(self, 'paused', False):
            # capture snapshot texture on first paused frame after rendering the scene
            if getattr(self, 'snapshot_pending', False):
                try:
                    # read pixels and flip vertically for texture upload
                    raw = glReadPixels(0, 0, self.w, self.h, GL_RGBA, GL_UNSIGNED_BYTE)
                    arr = np.frombuffer(raw, dtype=np.uint8)
                    if arr.size == self.w * self.h * 4:
                        arr = arr.reshape((self.h, self.w, 4))
                        arr = np.flipud(arr)
                        data = arr.tobytes()
                        if getattr(self, 'pause_snapshot_tex', 0):
                            try: glDeleteTextures([self.pause_snapshot_tex])
                            except Exception: pass
                        tex = glGenTextures(1)
                        glBindTexture(GL_TEXTURE_2D, tex)
                        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.w, self.h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
                        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                        glBindTexture(GL_TEXTURE_2D, 0)
                        self.pause_snapshot_tex = tex
                except Exception as e:
                    print('[WARN] pause snapshot failed:', e)
                finally:
                    self.snapshot_pending = False
            draw_help_menu(self)
        self.draw_hud(); pygame.display.flip()

    def run(self):
        try:
            while True:
                dt=self.clock.tick(120)/1000.0
                self.handle_input(dt)
                if not getattr(self, 'paused', False):
                    self.update(dt)
                self.draw()
                if self.player.health<=0:
                    print('[ERROR] Player down. Game Over.'); pygame.time.wait(1200); return
        except SystemExit: pass
        except Exception as ex:
            print('[ERROR] Unhandled exception:',ex)
        finally:
            try: pygame.mixer.music.stop()
            except Exception: pass
            pygame.quit(); sys.exit()

# Entry
def main(): Game().run()
if __name__=='__main__': main()

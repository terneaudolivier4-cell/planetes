# entities.py
import math, random
import numpy as np
from OpenGL.GL import *
from render import vec3, length, normalize, deg2rad, clamp, draw_billboard
from enemy_ai import update_enemy

class Missile:
    def __init__(self, pos, vel, target):
        self.pos = np.array(pos, dtype=float)
        self.vel = np.array(vel, dtype=float)
        self.target = target
        self.life = 10.0  # Max lifetime
        self.straight_time = 0.5  # Go straight for 0.5s
        self.elapsed = 0.0
        self.speed = 80.0
        self.turn_rate = 4.0  # Radians per second
        self.radius = 5.0
    
    def update(self, dt):
        self.elapsed += dt
        self.life -= dt
        
        if self.elapsed < self.straight_time:
            # Go straight
            self.pos += self.vel * dt
        else:
            # Homing towards target
            if self.target is not None and hasattr(self.target, 'pos'):
                to_target = self.target.pos - self.pos
                dist = length(to_target)
                if dist > 0.1:
                    desired_dir = to_target / dist
                    vel_len = length(self.vel)
                    if vel_len > 0.1:
                        current_dir = self.vel / vel_len
                        
                        # Smooth turning
                        max_turn = self.turn_rate * dt
                        new_dir = current_dir + (desired_dir - current_dir) * min(1.0, max_turn)
                        new_dir_len = length(new_dir)
                        if new_dir_len > 0.1:
                            new_dir = new_dir / new_dir_len
                            self.vel = new_dir * self.speed
            
            self.pos += self.vel * dt
        
        return self.life > 0.0


class Player:
    def __init__(self,cfg):
        self.pos=vec3(0,0,0)
        # Player orientation represented by a unit `direction` vector (front) and `velocity`.
        self.direction = vec3(0,0,-1)
        self.velocity=vec3(0,0,0)
        self.acceleration=float(cfg.get('acceleration',22.0))
        self.max_speed=float(cfg.get('max_speed',24.0))
        self.drag=float(cfg.get('drag',4.0))
        self.brake_drag=float(cfg.get('brake_drag',12.0))
        self.health=int(cfg.get('health',100))
        # Roll system
        self.roll = 0.0  # Current roll angle in degrees
        self.roll_rate = 90.0  # Roll speed in degrees/second
    def forward(self):
        # Prefer explicit `direction` when available, otherwise fall back to velocity
        if hasattr(self, 'direction') and length(self.direction) > 0.001:
            return normalize(self.direction)
        if hasattr(self, 'velocity') and length(self.velocity) > 0.05:
            return normalize(self.velocity)
        return vec3(0,0,-1)
    def right(self):
        f=self.forward(); wu=vec3(0,1,0); ru=vec3(0,0,1) if abs(float(np.dot(f,wu)))>0.99 else wu
        return normalize(np.cross(f,ru))
    def integrate_motion(self,dt,thrust=False,brake=False,lat=0.0):
        if thrust: 
            # Accelerate in the player's forward `direction` vector
            self.velocity+=self.forward()*(self.acceleration*dt)
            if abs(lat)>1e-4: self.velocity+=self.right()*(self.acceleration*0.35*lat*dt)
        sp=length(self.velocity)
        if sp>self.max_speed: 
            self.velocity*=self.max_speed/sp
        if not thrust:
            drag=self.brake_drag if brake else self.drag
            if sp>1e-5:
                self.velocity*=max(0.0,1.0-drag*dt)
            if length(self.velocity)<0.02: self.velocity[:]=0.0
        self.pos+=self.velocity*dt

class Bullet:
    def __init__(self,pos,dir_vec,speed=60.0,radius=0.6,tex=None,size=1.0,fr=True):
        self.pos=np.copy(pos); self.dir=normalize(dir_vec); self.speed=speed
        self.radius=radius; self.friendly=fr; self.tex=tex; self.size=size; self.tracer=None
    def update(self,dt): 
        self.pos+=self.dir*self.speed*dt

class Laser:
    def __init__(self, start, dir_vec, speed=800.0, radius=0.3, fr=True, max_range=2000.0, color=(0.0,1.0,0.0), trail_length=8.0):
        self.start = np.copy(start)
        self.pos = np.copy(start)
        self.dir = normalize(dir_vec)
        self.speed = float(speed)
        self.radius = float(radius)
        self.friendly = fr
        self.traveled = 0.0
        self.max_range = float(max_range)
        self.color = tuple(float(c) for c in color)
        self.trail_length = float(trail_length)
    def update(self, dt):
        delta = self.dir * (self.speed * dt)
        self.pos += delta
        self.start = self.pos - (self.dir * self.trail_length)
        self.traveled += float(np.linalg.norm(delta))

class ModelEnemy:
    def __init__(self,pos,mesh,scale=1.8,shoot=False,fire_rate=1.5,bullet_speed=38.0):
        self.pos=np.copy(pos); self.radius=1.2; self.maxspeed=4.2; self.mesh=mesh; self.scale=scale
        self.can_shoot=shoot; self.fire_rate=fire_rate; self.bullet_speed=bullet_speed; self._fire=0.0
        # Enemy motion is represented by a unit `direction` vector and a scalar `speed`.
        # Blueprint max speed stored in `maxspeed`; runtime current speed mirrored in `speed` by AI.
        # `velocity` is still available for physics convenience but will be mirrored
        # into `direction`/`speed` by the AI update.
        self.velocity = vec3(0,0,0)
        self.direction = vec3(0,0,-1)
        self.speed = 0.0
        # Model-space forward vector for the mesh (allows models with different forward axes)
        # Default flipped: treat model -Z as rear, so front is +Z
        self.model_forward = vec3(0,0,1)
        # Last known non-zero direction to avoid jitter when speed ~ 0
        self._last_direction = vec3(0,0,-1)
    def forward(self):
        # Prefer `direction` if set (unit vector). Fall back to `model_forward`.
        if hasattr(self, 'direction') and length(self.direction) > 0.001:
            return normalize(self.direction)
        return normalize(self.model_forward)
    def update(self,player_pos,dt):
        update_enemy(self, player_pos, dt, nearby_enemies=None, cfg=None)
    def try_shoot(self,player_pos,dt,bullet_tex):
        if not self.can_shoot: return None
        self._fire+=dt; cd=1.0/max(0.05,self.fire_rate)
        if self._fire<cd: return None
        self._fire=0.0
        # Use `direction` (unit vector) as the authoritative facing for shooting
        fwd = self.forward()
        to=player_pos-self.pos
        if length(to)<1e-6: return None
        dir_to=normalize(to); dot=clamp(float(np.dot(fwd,dir_to)),-1.0,1.0)
        ang_deg=math.degrees(math.acos(dot))
        CONE=12.0
        if ang_deg<=CONE:
            dir=normalize(fwd + vec3(random.uniform(-0.02,0.02),random.uniform(-0.02,0.02),random.uniform(-0.02,0.02)))
        else:
            dir=normalize(fwd + vec3(random.uniform(-0.15,0.15),random.uniform(-0.08,0.08),random.uniform(-0.15,0.15)))
        start=self.pos+dir*(self.radius+0.6)
        laser = Laser(start, dir, speed=max(self.bullet_speed,300.0), radius=0.5, fr=False, max_range=2000.0, color=(1.0,0.0,0.0))
        laser.damage = getattr(self, 'damage', 8)
        return laser
    def draw(self,prog):
        # Orient the mesh so that `model_forward` aligns with `direction`.
        glPushMatrix(); glTranslatef(self.pos[0],self.pos[1],self.pos[2])
        # Determine facing direction (use last non-zero if needed)
        if hasattr(self, 'direction') and length(self.direction) > 0.001:
            dir_vec = normalize(self.direction)
            self._last_direction = dir_vec
        else:
            dir_vec = normalize(self._last_direction)

        mf = normalize(self.model_forward)
        dp = clamp(float(np.dot(mf, dir_vec)), -1.0, 1.0)
        # If vectors are nearly aligned, no rotation needed
        if dp < 0.999:
            # Axis-angle rotation from model forward to desired dir: axis = mf x dir
            axis = np.cross(mf, dir_vec)
            axis_len = length(axis)
            if axis_len < 1e-6:
                # Vectors are opposite; rotate 180 degrees around arbitrary up axis
                axis = vec3(0,1,0)
                angle_deg = 180.0
            else:
                axis = axis / axis_len
                angle_deg = math.degrees(math.acos(dp))
            glRotatef(angle_deg, axis[0], axis[1], axis[2])

        glScalef(self.scale,self.scale,self.scale)
        self.mesh.draw(prog); glPopMatrix()

class Pickup:
    def __init__(self, pos, type='health', tex_glow=None):
        self.base_pos = np.copy(pos)
        self.pos = np.copy(pos)
        self.type = type
        self.tex_glow = tex_glow
        self.time = random.uniform(0, 6.28)
        self.pulse = 1.0
        self.color = (0.2, 1.0, 0.4, 0.8) if type == 'health' else (1.0, 0.7, 0.2, 0.8)

    def update(self, dt):
        self.time += dt
        self.pos = self.base_pos + vec3(0, math.sin(self.time * 2.5) * 1.5, 0)
        self.pulse = 1.0 + 0.25 * math.sin(self.time * 5.0)

    def draw(self, prog, cr, cu):
        if self.tex_glow == 0 or self.tex_glow is None: return
        draw_billboard(prog, self.tex_glow, self.pos, 5.0 * self.pulse, cr, cu, self.color)
        draw_billboard(prog, self.tex_glow, self.pos, 1.2, cr, cu, (1,1,1,1))


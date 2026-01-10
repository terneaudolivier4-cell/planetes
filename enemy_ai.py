"""enemy_ai.py

Enemy AI System with Fixed Speed and Direction Control:
- Enemy velocity magnitude is ALWAYS fixed to blueprint maxspeed
- AI only controls the DIRECTION of the velocity vector
- Smooth directional steering behaviors (seek, flee, avoidance)
- Tactical formations and player prediction
- Collision avoidance using lateral dodging
"""

import math
import numpy as np
from enum import Enum
import random

# ============== MATH HELPERS ==============
clamp = lambda x, a, b: max(a, min(b, x))
vec3 = lambda x=0.0, y=0.0, z=0.0: np.array([x, y, z], dtype=np.float32)

def length(v):
    """Get the magnitude of a vector."""
    return float(np.linalg.norm(v))

def normalize(v):
    """Normalize a vector to unit length."""
    n = np.linalg.norm(v)
    return v if n < 1e-6 else (v / n)

def distance(a, b):
    """Distance between two points."""
    return length(a - b)

def dot(a, b):
    """Dot product of two vectors."""
    return float(np.dot(a, b))

def cross(a, b):
    """3D cross product for vec3 arrays."""
    return np.cross(a, b)

def lerp_direction(from_dir, to_dir, t):
    """Linearly interpolate between two directions (normalized vectors)."""
    # Use SLERP for better directional interpolation
    dot_product = clamp(dot(from_dir, to_dir), -1.0, 1.0)
    omega = math.acos(abs(dot_product))
    
    if omega < 1e-6:  # Directions are already very close
        return normalize(from_dir + (to_dir - from_dir) * t)
    
    sin_omega = math.sin(omega)
    a = math.sin((1.0 - t) * omega) / sin_omega
    b = math.sin(t * omega) / sin_omega
    
    result = from_dir * a + to_dir * b
    return normalize(result)

# ============== AI STATES ==============
class AIState(Enum):
    APPROACH = 1      # Moving toward player
    ATTACK = 2        # In attack range, engaging  
    FLANK = 3         # Flanking maneuver
    EVADE = 4         # Collision avoidance
    PURSUIT = 6       # Active pursuit

# ============== CONFIGURATION ==============
AI_CONFIG = {
    # Distances
    'attack_range': 80.0,
    'close_range': 25.0,
    'separation_radius': 20.0,
    'danger_radius': 15.0,
    'player_danger_radius': 35.0,
    
    # Physics - NOTE: max_speed is now only a fallback, each enemy uses its blueprint maxspeed
    'max_speed': 18.0,  # Fallback only
    
    # Steering control - how fast the AI can change direction
    'direction_change_rate': 2.0,  # Radians per second max turn rate
    
    # Behavior weights
    'pursuit_weight': 1.0,
    'separation_weight': 4.0,
    'alignment_weight': 0.3,
    'cohesion_weight': 0.2,
    'avoidance_weight': 10.0,
    
    # Prediction
    'prediction_time': 1.5,
    
    # Formation
    'formation_spacing': 15.0,
    
    # Inertia after collision avoidance
    'max_inertia_duration': 5.0,
}

# ============== CORE AI FUNCTIONS ==============
def get_enemy_max_speed(enemy, config):
    """Get the fixed speed for this enemy from its blueprint."""
    return getattr(enemy, 'maxspeed', config['max_speed'])

def predict_player_position(player_pos, player_vel, time_ahead):
    """Predict where the player will be in `time_ahead` seconds."""
    return player_pos + player_vel * time_ahead

# ============== DIRECTIONAL STEERING ==============
def calculate_desired_direction(enemy_pos, target_pos):
    """Calculate the desired direction vector (normalized) toward a target."""
    to_target = target_pos - enemy_pos
    if length(to_target) < 1e-6:
        return vec3(0, 0, -1)  # Default forward
    return normalize(to_target)

def seek_direction(enemy_pos, target_pos):
    """Calculate desired direction to seek a target."""
    return calculate_desired_direction(enemy_pos, target_pos)

def flee_direction(enemy_pos, threat_pos):
    """Calculate desired direction to flee from a threat."""
    away = enemy_pos - threat_pos
    if length(away) < 1e-6:
        return vec3(0, 0, 1)  # Default away
    return normalize(away)

def pursuit_direction(enemy_pos, player_pos, player_vel, max_speed, config):
    """Calculate direction for pursuing a moving target."""
    # Predict player future position
    dist = distance(enemy_pos, player_pos)
    prediction_time = min(dist / max(max_speed, 1.0), config['prediction_time'])
    future_pos = predict_player_position(player_pos, player_vel, prediction_time)
    return seek_direction(enemy_pos, future_pos)

# ============== FLOCKING BEHAVIORS ==============
def separation_direction(enemy, all_enemies, config):
    """Calculate direction to avoid clustering with other enemies."""
    steer = vec3()
    count = 0
    
    for other in all_enemies:
        if other is enemy:
            continue
        d = distance(enemy.pos, other.pos)
        if 0 < d < config['separation_radius']:
            # Stronger repulsion for closer enemies
            diff = normalize(enemy.pos - other.pos)
            weight = (config['separation_radius'] - d) / config['separation_radius']
            steer += diff * weight
            count += 1
    
    if count > 0:
        steer /= count
        return normalize(steer) if length(steer) > 1e-6 else vec3()
    return vec3()

def alignment_direction(enemy, all_enemies, config):
    """Calculate direction to match nearby allies' movement."""
    avg_dir = vec3()
    count = 0
    
    for other in all_enemies:
        if other is enemy:
            continue
        if distance(enemy.pos, other.pos) < config['separation_radius'] * 2:
            if hasattr(other, 'direction') and length(other.direction) > 0.1:
                avg_dir += other.direction
                count += 1
    
    if count > 0:
        avg_dir /= count
        return normalize(avg_dir) if length(avg_dir) > 1e-6 else vec3()
    return vec3()

def cohesion_direction(enemy, all_enemies, config):
    """Calculate direction toward center of nearby allies."""
    center = vec3()
    count = 0
    
    for other in all_enemies:
        if other is enemy:
            continue
        if distance(enemy.pos, other.pos) < config['separation_radius'] * 3:
            center += other.pos
            count += 1
    
    if count > 0:
        center /= count
        return calculate_desired_direction(enemy.pos, center)
    return vec3()

# ============== COLLISION AVOIDANCE ==============
def collision_avoidance_direction(enemy, all_enemies, player_pos, config):
    """Calculate lateral dodging direction for collision avoidance."""
    avoidance_dir = vec3()
    
    # Avoid other enemies
    for other in all_enemies:
        if other is enemy:
            continue
        d = distance(enemy.pos, other.pos)
        if d < config['danger_radius'] and d > 0:
            diff = normalize(enemy.pos - other.pos)
            urgency = (config['danger_radius'] - d) / config['danger_radius']
            avoidance_dir += diff * (urgency ** 2)
    
    # Lateral dodge from player
    d_player = distance(enemy.pos, player_pos)
    if d_player < config['player_danger_radius']:
        to_enemy = normalize(enemy.pos - player_pos)
        
        # Calculate lateral (perpendicular) direction
        current_dir = getattr(enemy, 'direction', vec3(0, 0, -1))
        lateral = cross(to_enemy, vec3(0, 1, 0))
        if length(lateral) < 1e-6:
            lateral = cross(to_enemy, vec3(1, 0, 0))
        
        if length(lateral) > 1e-6:
            lateral = normalize(lateral)
            # Choose dodge direction based on current movement
            if dot(current_dir, lateral) < 0:
                lateral = -lateral
        else:
            lateral = vec3(1, 0, 0)  # Fallback
        
        urgency = (config['player_danger_radius'] - d_player) / config['player_danger_radius']
        
        # Combine lateral dodge with slight retreat at very close range
        if urgency > 0.7:
            avoidance_dir += lateral * (urgency ** 2) * 2.0 + to_enemy * urgency
        else:
            avoidance_dir += lateral * urgency * 1.5
    
    return normalize(avoidance_dir) if length(avoidance_dir) > 1e-6 else vec3()

# ============== TACTICAL BEHAVIORS ==============
def flanking_direction(enemy, player_pos, player_vel, config):
    """Calculate direction for flanking maneuver."""
    to_player = player_pos - enemy.pos
    dist = length(to_player)
    
    if dist < 1e-6:
        return vec3()
    
    to_player_norm = to_player / dist
    
    # Get flank angle (from enemy's tactical role)
    flank_angle = getattr(enemy, '_flank_angle', 45.0)
    angle_rad = math.radians(flank_angle)
    
    # Rotate approach vector by flank angle (horizontal plane)
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    flank_dir = vec3(
        to_player_norm[0] * cos_a - to_player_norm[2] * sin_a,
        to_player_norm[1],
        to_player_norm[0] * sin_a + to_player_norm[2] * cos_a
    )
    
    # Target position offset from player
    target_dist = config['attack_range'] * 0.6
    target_pos = player_pos - flank_dir * target_dist
    
    # Predict player movement
    target_pos += player_vel * 0.5
    
    return calculate_desired_direction(enemy.pos, target_pos)

# ============== AI STATE MANAGEMENT ==============
def update_ai_state(enemy, player_pos, all_enemies, config):
    """Update enemy AI state based on current situation."""
    dist_to_player = distance(enemy.pos, player_pos)
    
    # Check for emergency collision situations
    for other in all_enemies:
        if other is enemy:
            continue
        if distance(enemy.pos, other.pos) < config['danger_radius']:
            enemy._ai_state = AIState.EVADE
            return
    
    # Check player collision zone
    if dist_to_player < config['player_danger_radius']:
        enemy._ai_state = AIState.EVADE
        return
    
    # Normal state transitions based on distance and role
    role = getattr(enemy, '_role', 'solo')
    
    if role in ['flank_left', 'flank_right']:
        enemy._ai_state = AIState.FLANK
    elif dist_to_player > config['attack_range'] * 1.5:
        enemy._ai_state = AIState.APPROACH
    elif dist_to_player < config['close_range']:
        enemy._ai_state = AIState.ATTACK
    elif dist_to_player < config['attack_range']:
        # Check if facing player for direct attack vs flanking
        current_dir = getattr(enemy, 'direction', vec3(0, 0, -1))
        to_player = normalize(player_pos - enemy.pos)
        alignment = dot(current_dir, to_player)
        
        if alignment > 0.7:  # Facing player directly
            enemy._ai_state = AIState.ATTACK
        else:
            enemy._ai_state = AIState.PURSUIT
    else:
        enemy._ai_state = AIState.APPROACH

# ============== FORMATION MANAGER ==============
class FormationManager:
    """Simple formation manager for tactical enemy coordination."""
    
    @staticmethod
    def assign_roles(enemies, player_pos):
        """Assign tactical roles to enemies based on situation."""
        if len(enemies) <= 1:
            return
        
        count = len(enemies)
        
        # Calculate group center
        center = vec3()
        for e in enemies:
            center += e.pos
        center /= count
        
        dist_to_player = distance(center, player_pos)
        
        # Assign roles based on group size and distance
        if count >= 4 and dist_to_player > AI_CONFIG['attack_range']:
            # Large group at distance: use flanking
            FormationManager._assign_flanking(enemies, player_pos)
        else:
            # Default: direct approach with some variety
            FormationManager._assign_approach(enemies, player_pos)
    
    @staticmethod
    def _assign_flanking(enemies, player_pos):
        """Assign flanking roles to enemies."""
        mid = len(enemies) // 2
        for i, e in enumerate(enemies):
            if i < mid:
                e._role = 'flank_left'
                e._flank_angle = -45.0 - random.uniform(0, 15)
            else:
                e._role = 'flank_right'
                e._flank_angle = 45.0 + random.uniform(0, 15)
    
    @staticmethod
    def _assign_approach(enemies, player_pos):
        """Assign approach roles with some flanking variety."""
        for i, e in enumerate(enemies):
            if i == 0:
                e._role = 'leader'
                e._flank_angle = 0.0
            else:
                e._role = 'wing'
                e._flank_angle = random.uniform(-30, 30)

# ============== MAIN AI UPDATE ==============
def update_enemy(enemy, player_pos, dt, nearby_enemies=None, cfg=None):
    """
    Main AI update function for fixed-speed directional control.
    
    Args:
        enemy: Enemy object with pos, velocity, direction attributes
        player_pos: Player position vector
        dt: Delta time in seconds
        nearby_enemies: List of all enemies for flocking/avoidance
        cfg: Optional config overrides
    """
    # Initialize enemy attributes if missing
    if not hasattr(enemy, 'velocity'):
        enemy.velocity = vec3(0, 0, -1)
    if not hasattr(enemy, 'direction'):
        enemy.direction = vec3(0, 0, -1)
    if not hasattr(enemy, '_ai_state'):
        enemy._ai_state = AIState.APPROACH
    if not hasattr(enemy, '_role'):
        enemy._role = 'solo'
    if not hasattr(enemy, '_inertia_timer'):
        enemy._inertia_timer = 0.0
    if not hasattr(enemy, '_inertia_direction'):
        enemy._inertia_direction = vec3()
    
    # Clean up old yaw/pitch attributes if they exist
    for attr in ['yaw', 'pitch']:
        if hasattr(enemy, attr):
            try:
                delattr(enemy, attr)
            except:
                pass
    
    config = AI_CONFIG.copy()
    if cfg:
        config.update(cfg)
    
    all_enemies = nearby_enemies if nearby_enemies else []
    player_vel = getattr(enemy, '_cached_player_vel', vec3())
    
    # Get enemy's fixed speed
    max_speed = get_enemy_max_speed(enemy, config)
    
    # Update AI state
    update_ai_state(enemy, player_pos, all_enemies, config)
    
    # Calculate desired direction based on current state and behaviors
    desired_direction = calculate_desired_direction_composite(
        enemy, player_pos, player_vel, all_enemies, config
    )
    
    # Apply directional change with smooth steering
    apply_directional_steering(enemy, desired_direction, max_speed, dt, config)
    
    # Update position
    enemy.pos += enemy.velocity * dt
    
    # Update runtime attributes
    enemy.speed = max_speed  # Always equal to blueprint maxspeed

def calculate_desired_direction_composite(enemy, player_pos, player_vel, all_enemies, config):
    """Calculate composite desired direction from all AI behaviors."""
    # Start with current direction
    current_dir = getattr(enemy, 'direction', vec3(0, 0, -1))
    
    # Initialize direction influences
    influences = []
    
    # 1. Primary behavior based on AI state
    primary_weight = 1.0
    
    if enemy._ai_state == AIState.APPROACH:
        target_pos = predict_player_position(player_pos, player_vel, 1.0)
        primary_dir = seek_direction(enemy.pos, target_pos)
        influences.append((primary_dir, primary_weight * config['pursuit_weight']))
        
    elif enemy._ai_state == AIState.ATTACK:
        primary_dir = pursuit_direction(enemy.pos, player_pos, player_vel, 
                                      get_enemy_max_speed(enemy, config), config)
        influences.append((primary_dir, primary_weight * config['pursuit_weight'] * 1.5))
        
    elif enemy._ai_state == AIState.FLANK:
        primary_dir = flanking_direction(enemy, player_pos, player_vel, config)
        influences.append((primary_dir, primary_weight))
        
    elif enemy._ai_state == AIState.PURSUIT:
        primary_dir = pursuit_direction(enemy.pos, player_pos, player_vel,
                                      get_enemy_max_speed(enemy, config), config)
        influences.append((primary_dir, primary_weight * config['pursuit_weight'] * 1.2))
        
    elif enemy._ai_state == AIState.EVADE:
        # Collision avoidance gets highest priority
        avoid_dir = collision_avoidance_direction(enemy, all_enemies, player_pos, config)
        if length(avoid_dir) > 1e-6:
            influences.append((avoid_dir, config['avoidance_weight']))
            # Set inertia
            enemy._inertia_timer = config['max_inertia_duration']*random.uniform(0.2,1.0)
            enemy._inertia_direction = avoid_dir
    
    # 2. Inertia behavior (after avoidance maneuvers)
    if enemy._inertia_timer > 0:
        if length(enemy._inertia_direction) > 1e-6:
            influences.append((enemy._inertia_direction, 2.0))
        enemy._inertia_timer = max(0.0, enemy._inertia_timer - 0.016)  # Approximate dt
    
    # 3. Always apply collision avoidance (even if not in EVADE state)
    avoid_dir = collision_avoidance_direction(enemy, all_enemies, player_pos, config)
    if length(avoid_dir) > 1e-6:
        influences.append((avoid_dir, config['avoidance_weight']))
    
    # 4. Flocking behaviors
    sep_dir = separation_direction(enemy, all_enemies, config)
    if length(sep_dir) > 1e-6:
        influences.append((sep_dir, config['separation_weight']))
    
    align_dir = alignment_direction(enemy, all_enemies, config)
    if length(align_dir) > 1e-6:
        influences.append((align_dir, config['alignment_weight']))
    
    coh_dir = cohesion_direction(enemy, all_enemies, config)
    if length(coh_dir) > 1e-6:
        influences.append((coh_dir, config['cohesion_weight']))
    
    # Combine all influences
    if not influences:
        return current_dir
    
    combined_direction = vec3()
    total_weight = 0.0
    
    for direction, weight in influences:
        if length(direction) > 1e-6:
            combined_direction += normalize(direction) * weight
            total_weight += weight
    
    if total_weight > 1e-6:
        combined_direction /= total_weight
        return normalize(combined_direction) if length(combined_direction) > 1e-6 else current_dir
    
    return current_dir

def apply_directional_steering(enemy, desired_direction, max_speed, dt, config):
    """Apply smooth directional steering while maintaining fixed speed."""
    current_dir = getattr(enemy, 'direction', vec3(0, 0, -1))
    
    if length(desired_direction) < 1e-6:
        desired_direction = current_dir
    else:
        desired_direction = normalize(desired_direction)
    
    # Calculate maximum turn angle for this frame
    max_turn_angle = config['direction_change_rate'] * dt
    
    # Calculate angle between current and desired direction
    dot_product = clamp(dot(current_dir, desired_direction), -1.0, 1.0)
    angle_between = math.acos(abs(dot_product))
    
    # Apply smooth directional interpolation
    if angle_between < max_turn_angle:
        # Can reach desired direction this frame
        new_direction = desired_direction
    else:
        # Interpolate toward desired direction
        t = max_turn_angle / angle_between if angle_between > 1e-6 else 1.0
        new_direction = lerp_direction(current_dir, desired_direction, t)
    
    # Update enemy direction and velocity
    enemy.direction = normalize(new_direction)
    enemy.velocity = enemy.direction * float(max_speed)

# ============== HELPER FOR MAIN GAME ==============
def update_all_enemies(enemies, player_pos, player_vel, dt):
    """
    Update all enemies with formation coordination.
    Call this from main.py instead of individual update_enemy calls.
    """
    if not enemies:
        return
    
    # Cache player velocity for all enemies
    for e in enemies:
        e._cached_player_vel = player_vel
    
    # Assign tactical formations
    FormationManager.assign_roles(enemies, player_pos)
    
    # Update each enemy
    for enemy in enemies:
        update_enemy(enemy, player_pos, dt, nearby_enemies=enemies)
        # Debug output
        #print(f"Vel:, {length(enemy.velocity)}")
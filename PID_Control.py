import sys
import math
import glob
import os
import numpy as np
import cv2
import queue
import time 

try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass

import carla

def get_speed(vehicle):
    vel = vehicle.get_velocity()
    return 3.6 * math.sqrt(vel.x**2 + vel.y**2 + vel.z**2)

class VehiclePIDController():
    def __init__(self, vehicle, args_Lateral, args_Longitudinal, max_throttle=0.75, max_break=0.3, max_steering=0.8):
        self.max_break = max_break
        self.max_steering = max_steering
        self.max_throttle = max_throttle

        self.vehicle = vehicle
        self.world = vehicle.get_world()
        self.past_steering = self.vehicle.get_control().steer
        self.long_controller = PIDlongitudnalControl(self.vehicle, **args_Longitudinal)
        self.lat_controller = PIDLateralControl(self.vehicle, **args_Lateral)

    def run_step(self, target_speed, waypoint):
        acceleration = self.long_controller.run_step(target_speed)
        current_steering = self.lat_controller.run_step(waypoint)
        control = carla.VehicleControl()

        if acceleration >= 0.0:
            control.throttle = min(abs(acceleration), self.max_throttle)
            control.brake = 0.0
        else:
            control.throttle = 0.0
            control.brake = min(abs(acceleration), self.max_break)

        if current_steering > self.past_steering + 0.1:
            current_steering = self.past_steering + 0.1
        elif current_steering < self.past_steering - 0.1:
            current_steering = self.past_steering - 0.1

        if current_steering >= 0:
            steering = min(self.max_steering, current_steering)
        else:
            steering = max(-self.max_steering, current_steering)

        control.steer = steering
        control.hand_brake = False
        self.past_steering = steering

        return control

class PIDlongitudnalControl():
    def __init__(self, vehicle, K_P=1.0, K_D=0.0, K_I=0.0, dt=0.03):
        self.vehicle = vehicle
        self.K_D = K_D
        self.K_P = K_P
        self.K_I = K_I
        self.dt = dt
        self.errorBuffer = queue.deque(maxlen=10)

    def pid_controller(self, target_speed, current_speed):
        error = target_speed - current_speed

        self.errorBuffer.append(error)

        if len(self.errorBuffer) >= 2:
            de = (self.errorBuffer[-1] - self.errorBuffer[-2]) / self.dt
            ie = sum(self.errorBuffer) * self.dt
        else:
            de = 0.0
            ie = 0.0
        return np.clip(self.K_P * error + self.K_D * de + self.K_I * ie, -1.0, 1.0)

    def run_step(self, target_speed):
        current_speed = get_speed(self.vehicle)
        return self.pid_controller(target_speed, current_speed)

class PIDLateralControl():
    def __init__(self, vehicle, K_P=1.0, K_D=0.0, K_I=0.0, dt=0.03):
        self.vehicle = vehicle
        self.K_D = K_D
        self.K_P = K_P
        self.K_I = K_I
        self.dt = dt
        self.errorBuffer = queue.deque(maxlen=10)

    def pid_controller(self, waypoint, vehicle_transform):
        v_begin = vehicle_transform.Location
        v_end = v_begin * carla.Location(x=math.cos(math.radians(vehicle_transform.Rotation.yaw)),
                                         y=math.sin(math.radians(vehicle_transform.Rotation.yaw)))
        v_vec = np.array([v_end.x - v_begin.x, v_end.y - v_begin.y, 0.0])

        w_vec = np.array([waypoint.Transform.Location.x - v_begin.x, waypoint.Transform.Location.y - v_begin.y])

        dot = math.acos(np.clip(np.dot(w_vec, v_vec) / np.linalg.norm(w_vec) * np.linalg.norm(v_vec), -1.0, 1.0))

        cross = np.cross(v_vec, w_vec)
        if cross[2] < 0:
            dot *= -1
        self.errorBuffer.append(dot)

        if len(self.errorBuffer) >= 2:
            de = (self.errorBuffer[-1] - self.errorBuffer[-2]) / self.dt
            ie = sum(self.errorBuffer) * self.dt
        else:
            de = 0.0
            ie = 0.0
        return np.clip((self.K_P * dot) + (self.K_I * ie) + (self.K_D * de), -1.0, 1.0)

    def run_step(self, waypoint):
        return self.pid_controller(waypoint, self.vehicle.get_transform())


def main():
    actor_list = []
    try:
        client = carla.Client('127.0.0.1', 2000)
        client.set_timeout(5.0)
        world = client.get_world()
        map = world.get_map()

        blueprint_library = world.get_blueprint_library()
        vehicle_bp = blueprint_library.filter('vehicle.*')[0]
        spawnpoint = carla.Transform(carla.Location(x=-75, y=-1.0, z=15),
                                     carla.Rotation(pitch=0, yaw=180, roll=0))
        vehicle = world.spawn_actor(vehicle_bp, spawnpoint)
        actor_list.append(vehicle)

        control_vehicle = VehiclePIDController(vehicle, args_Lateral={'K_P': 1, 'K_D': 0.0, 'K_I': 0.0},
                                               args_Longitudinal={'K_P': 1, 'K_D': 0.0, 'K_I': 0.0})

        while True:
            print("Spawnpoint:", spawnpoint)
            waypoints = world.get_map().get_waypoint(vehicle.get_location())
            print("Waypoints:", waypoints)
            waypoint = np.random.choice(waypoints.next(0.3))
            print("Vehicle spawned successfully")
            control_signal = control_vehicle.run_step(5, waypoint)
            print("Vehicle spawned successfully")
            vehicle.apply_control(control_signal)

            depth_camera_bp = blueprint_library.find('sensor.camera.depth')
            print("Depth camera blueprint:", depth_camera_bp)
            depth_camera_transform = carla.Transform(carla.Location(x=1.5, y=2.4))
            depth_camera = world.spawn_actor(depth_camera_bp, depth_camera_transform)
            depth_camera.listen(lambda image : image.save_to_disk('output/%.6d'%image.frame, carla.ColorConverter.LogarithmicDepth))
            time.sleep(0.1)
    finally:
        client.apply_batch([carla.command.DestroyActor(x) for x in actor_list]) 
        print("Actors destroyed:", actor_list)
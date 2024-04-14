import glob
import os
import sys

import random
import matplotlib.pyplot as plt
import time
import numpy as np 
import argparse
import math
 
try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass

import carla


def main():
    actorList = []
    try:
        client = carla.Client('localhost', 2000)
        client.set_timeout(10.0)
        world = client.load_world('Town02')
        print(client.get_available_maps())

        blueprintLibrary = world.get_blueprint_library()
        vehicle_bp = blueprintLibrary.filter('cybertruck')[0]
        transform = carla.Transform(carla.Location(x=130, y=195, z=40), carla.Rotation(yaw=180))
        vehicle = world.spawn_actor(vehicle_bp, transform)
        actorList.append(vehicle)

        camera_bp = blueprintLibrary.find('sensor.camera.rgb')
        camera_bp.set_attribute('image_size_x', '800')
        camera_bp.set_attribute('image_size_y', '600')
        camera_bp.set_attribute('fov', '90')
        camera_transform = carla.Transform(carla.Location(x=1.5, z=2.4))
        camera = world.spawn_actor(camera_bp, camera_transform, attach_to=vehicle)
        actorList.append(camera)

        camera.listen(lambda image: image.save_to_disk('output/{:06d}.png'.format(image.frame)))

        for i in range(0, 10):
            transform.location.x += 8.0
            bp = blueprintLibrary.filter('vehicle.*')[0]
            npc = world.try_spawn_actor(bp, transform)

            if npc is not None:
                actorList.append(npc)
                npc.set_autopilot(True)
                print('created %s' % npc.type_id)

        time.sleep(15)

    finally:
        print('delete actorList')
        client.apply_batch([carla.command.DestroyActor(x) for x in actorList])

if __name__ == '__main__':
    main()
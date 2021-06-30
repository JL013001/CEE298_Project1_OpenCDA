# -*- coding: utf-8 -*-

"""Platooning plugin for communication and track FSM
"""

# Author: Runsheng Xu <rxx3386@ucla.edu>
# License: MIT

import warnings

from opencda.core.common.misc import compute_distance, cal_distance_angle
from opencda.core.application.platooning.fsm import FSM


class PlatooningPlugin(object):
    """
    The default GNSS sensor module.
    
    Parameters
    -search_range : float
        The search range of the on board GNSS sensor.
    -cda_enabled : boolean
        Boolean indicator of CDA enable status.
    
    Attributes
    -leader : boolean
        Boolean indicator of the platoon leader status.
    -platooning_object : opencda object 
        The current platoon object.
    -platooning_id : int
        The current platoon ID.
    -in_id : int
        The inner platoon ID.
    -status : string
        The current platooning status.
    -ego_pos : carla.transformation
        The current position (i.e., location and rotation) of the ego vehicle.
    -ego_spd : CARLA actor
        The current speed of the ego vehicle.
    -platooning_blacklist : list
        The list of vehicle that are not suitable for platooning.
    -front_vehicle : carla.vehicle
        The front vehicle of the ego vehicle.
    -rear_vechile : carla.vehicle
        The rear vehicle of the ego vehicle.
    """

    def __init__(self, search_range, cda_enabled):

        self.search_range = search_range
        self.cda_enabled = cda_enabled

        # whether leader in a platoon
        self.leader = False
        self.platooning_object = None
        self.platooning_id = None
        self.in_id = None
        self.status = None

        # ego speed and position
        self.ego_pos = None
        self.ego_spd = None

        # the platoon in the black list won't be considered again
        self.platooning_blacklist = []

        # used to label the front and rear vehicle position
        self.front_vehicle = None
        self.rear_vechile = None

    def update_info(self, ego_pos, ego_spd):
        """
        Update the ego position and speed

        Args:
            -heading_direction: groundtruth heading_direction obtained from the server.
            -dummy_variable: dummy variable to test multiple return/args.
            -dummy_variable: dummy variable to test multiple return/args.
            -dummy_variable: dummy variable to test multiple return/args.
        Returns:
            -heading_direction: heading direction with noise.
            -dummy_variable: dummy variable to test multiple return/args.
        """
        self.ego_pos = ego_pos
        self.ego_spd = ego_spd

    def reset(self):
        """
        Reset to the origin status.
        """
        self.front_vehicle = None
        self.rear_vechile = None

        self.leader = False
        self.platooning_object = None
        self.platooning_id = None
        self.in_id = None

    def set_platoon(self, in_id, platooning_object=None, platooning_id=None, leader=False):
        """
        Set platooning status
        
        Args:
            -in_id (int): Inner platoon ID of the vehicle.
            -platooning_object (opencda object): The current platoon object.
            -platooning_id (int): The current platoon ID.
            -leader (boolean): Boolean indicator of the platoon leader status.
        """
        if in_id is None:
            if not self.cda_enabled:
                self.set_status(FSM.DISABLE)
                warnings.warn("CDA feature is disabled, can not activate platooning application ")
            else:
                self.set_status(FSM.SEARCHING)
            return

        if platooning_object:
            self.platooning_object = platooning_object
        if platooning_id:
            self.platooning_id = platooning_id

        self.in_id = in_id
        if leader:
            self.leader = leader
            self.set_status(FSM.LEADING_MODE)
        else:
            self.set_status(FSM.MAINTINING)

    def set_status(self, status):
        """
        Set FSM status
        
        Args:
            -status (string): The current platooning status.
        """
        self.status = status

    def search_platoon(self, ego_pos, cav_world):
        """
        Search platoon candidate in the range
        
        Args:
            -ego_pos (carla.transformation): Current position of the ego vehicle.
            -cav_world (carla.world): Current simulation world.
        Returns:
            -pmid (int): Platoon manager ID.
            -pm (opencda object): Platoon manager ID.
        """
        platoon_manager_dict = cav_world.get_platoon_dict()
        for pmid, pm in platoon_manager_dict.items():
            for vm in pm.vehicle_manager_list:
                distance = compute_distance(ego_pos, vm.localizer.get_ego_pos().location)
                if distance < self.search_range:
                    return pmid, pm
        return None, None

    def match_platoon(self, cav_world):
        """
        A naive way to find the best position to join a platoon
        
        Args:
            -cav_world (carla.world): Current simulation world.
        Returns:
            -(boolean): The boolean indicator of matching result. 
            -min_index (int): The minimum index inside the selected platoon.
            -platoon_vehicle_list (list): The list of platoon vehicle memebers.
        """

        # make sure the previous status won't influence current one
        self.reset()

        cur_loc = self.ego_pos.location
        cur_yaw = self.ego_pos.rotation.yaw

        pmid, pm = self.search_platoon(cur_loc, cav_world)

        if not pmid or pmid in self.platooning_blacklist:
            return False, -1, []

        # used to search the closest platoon member in the searched platoon
        min_distance = float('inf')
        min_index = -1
        min_angle = 0

        # if the platooning is not open to joining
        if not pm.response_joining_request(self.ego_pos.location):
            return False, -1, []

        platoon_vehicle_list = []

        for (i, vehicle_manager) in enumerate(pm.vehicle_manager_list):
            distance, angle = cal_distance_angle(vehicle_manager.vehicle.get_location(),
                                                 cur_loc, cur_yaw)
            platoon_vehicle_list.append(vehicle_manager)

            if distance < min_distance:
                min_distance = distance
                min_index = i
                min_angle = angle

        # if the ego is in front of the platooning
        if min_index == 0 and min_angle > 90:
            self.front_vehicle = None
            self.rear_vechile = pm.vehicle_manager_list[0]
            return True, min_index, platoon_vehicle_list

        self.front_vehicle = pm.vehicle_manager_list[min_index]

        if min_index < len(pm.vehicle_manager_list) - 1:
            self.rear_vechile = pm.vehicle_manager_list[min_index + 1]

        return True, min_index, platoon_vehicle_list

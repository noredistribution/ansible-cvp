#!/usr/bin/env python
# coding: utf-8 -*-
#
# GNU General Public License v3.0+
#
# Copyright 2019 Arista Networks AS-EMEA
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from __future__ import (absolute_import, division, print_function)

import jsonschema
__metaclass__ = type
import traceback
import logging
from ansible.module_utils.basic import AnsibleModule
import ansible_collections.arista.cvp.plugins.module_utils.logger   # noqa # pylint: disable=unused-import
from ansible_collections.arista.cvp.plugins.module_utils.response import CvApiResult, CvManagerResult, CvAnsibleResponse
from ansible_collections.arista.cvp.plugins.module_utils.generic_tools import CvElement
import ansible_collections.arista.cvp.plugins.module_utils.schema as schema
try:
    from cvprac.cvp_client import CvpClient
    from cvprac.cvp_client_errors import CvpApiError, CvpRequestError  # noqa # pylint: disable=unused-import
    HAS_CVPRAC = True
except ImportError:
    HAS_CVPRAC = False
    CVPRAC_IMP_ERR = traceback.format_exc()


MODULE_LOGGER = logging.getLogger('arista.cvp.device_tools_v3')
MODULE_LOGGER.info('Start device_tools module execution')


# ------------------------------------------ #
# Fields name to use in classes
# ------------------------------------------ #

FIELD_FQDN = 'fqdn'
FIELD_SYSMAC = 'systemMacAddress'
FIELD_SERIAL = 'serialNumber'
FIELD_CONFIGLETS = 'configlets'
FIELD_ID = 'key'
FIELD_CONTAINER_NAME = 'containerName'
FIELD_PARENT_NAME = 'parentContainerName'
FIELD_PARENT_ID = 'parentContainerId'
# Not yet implemented
FIELD_IMAGE_BUNDLE = 'image_bundle'
UNDEFINED_CONTAINER = 'undefined_container'


class CvClient(object):
    def __failure(self, msg: str):
        MODULE_LOGGER.error(msg)
        if self.__ansible is not None:
            self.__ansible.fail_json(msg=msg)


class DeviceElement(object):

    def __init__(self, data: dict):
        self.__data = data
        self.__fqdn = self.__data[FIELD_FQDN]
        self.__sysmac = None
        self.__serial = None
        self.__container = self.__data[FIELD_PARENT_NAME]
        self.__image_bundle = []
        self.__current_parent_container_id = None
        if FIELD_IMAGE_BUNDLE in self.__data:
            self.__image_bundle = data[FIELD_IMAGE_BUNDLE]
        if FIELD_SYSMAC in data:
            self.__sysmac = data[FIELD_SYSMAC]
        if FIELD_SERIAL in data:
            self.__serial = data[FIELD_SERIAL]

    @property
    def fqdn(self):
        return self.__fqdn

    @property
    def system_mac(self):
        return self.__sysmac

    @system_mac.setter
    def system_mac(self, mac: str):
        self.__sysmac = mac

    @property
    def serial_number(self):
        return self.__serial

    @property
    def container(self):
        return self.__container

    @property
    def configlets(self):
        if FIELD_CONFIGLETS in self.__data:
            return self.__data[FIELD_CONFIGLETS]
        return []

    @property
    def parent_container_id(self):
        return self.__current_parent_container_id

    @parent_container_id.setter
    def parent_container_id(self, id):
        self.__current_parent_container_id = id

    @property
    def info(self):
        res = dict()
        res[FIELD_FQDN] = self.__fqdn
        if self.__serial is not None:
            res[FIELD_SERIAL] = self.__serial
        if self.__sysmac is not None:
            res[FIELD_SYSMAC] = self.__sysmac
            res[FIELD_ID] = self.__sysmac
        res[FIELD_PARENT_NAME] = self.__container
        res[FIELD_CONFIGLETS] = self.__data[FIELD_CONFIGLETS]
        # res[FIELD_PARENT_ID] = self.__current_parent_container_id
        return res


class DeviceInventory(object):
    """
    DeviceInventory Local User defined inventory
    """

    def __init__(self, data: list, schema: jsonschema = schema.SCHEMA_CV_DEVICE, search_method: str = FIELD_FQDN):
        self.__inventory = list()
        self.__data = data
        self.__schema = schema
        self.search_method = search_method
        for entry in data:
            self.__inventory.append(DeviceElement(data=entry))

    @property
    def is_valid(self):
        """
        check_schemas Validate schemas for user's input
        """
        if not schema.validate_cv_inputs(user_json=self.__data, schema=self.__schema):
            MODULE_LOGGER.error(
                "Invalid configlet input : \n%s", str(self.__data))
            return False
        return True

    @property
    def devices(self):
        return self.__inventory

    def get_device(self, device_string: str, search_method: str = FIELD_FQDN):
        # Lookup using systemMacAddress
        if self.search_method is FIELD_SYSMAC or search_method is FIELD_SYSMAC:
            for device in self.__inventory:
                if device.system_mac == device_string:
                    return device
        # Cover search by fqdn or any unsupported options
        else:
            for device in self.__inventory:
                if device.fqdn == device_string:
                    return device
        return None


class CvDeviceTools(CvClient):

    def __init__(self, cv_connection: CvpClient, ansible_module: AnsibleModule = None, search_by: str = FIELD_FQDN, check_mode: bool = False):
        self.__cv_client = cv_connection
        self.__ansible = ansible_module
        self.__search_by = search_by
        self.__configlets_and_mappers_cache = None
        self.__check_mode = check_mode

    # ------------------------------------------ #
    # Getters & Setters
    # ------------------------------------------ #

    @property
    def search_by(self):
        return self.__search_by

    @search_by.setter
    def search_by(self, mode: str):
        self.__search_by = mode

    # ------------------------------------------ #
    # Private functions
    # ------------------------------------------ #

    def __get_device(self, search_value: str, search_by: str = FIELD_FQDN):
        cv_data: dict = dict()
        if search_by == FIELD_FQDN:
            cv_data = self.__cv_client.api.get_device_by_name(fqdn=search_value)
        if search_by == FIELD_SYSMAC:
            cv_data = self.__cv_client.api.get_device_by_mac(device_mac=search_value)
        return cv_data

    def __get_configlet_info(self, configlet_name):
        if self.__configlets_and_mappers_cache is None:
            self.__configlets_and_mappers_cache = self.__cv_client.api.get_configlets_and_mappers()
        for configlet in self.__configlets_and_mappers_cache['data']['configlets']:
            if configlet_name == configlet['name']:
                return configlet
        return None

    # ------------------------------------------ #
    # Get CV data functions
    # ------------------------------------------ #

    def get_device_facts(self, device_lookup: str):
        data = self.__get_device(
            search_value=device_lookup, search_by=self.__search_by)
        return data

    def get_device_id(self, device_lookup: str):
        data = self.get_device_facts(device_lookup=device_lookup)
        if data is not None:
            return data[FIELD_SYSMAC]
        return None

    def get_device_configlets(self, device_lookup: str):
        if self.__search_by == FIELD_FQDN:
            configlet_list = list()
            # get_configlets_by_device_id
            try:
                device_id = self.get_device_id(device_lookup=device_lookup)
            except CvpApiError:
                self.__failure(msg='Error getting device ID from cloudvision')
            else:
                if device_id is None:
                    self.__failure(
                        msg='Error cannot get device ID from Cloudvision')
                configlets_data = self.__cv_client.api.get_configlets_by_device_id(
                    mac=device_id)
                for configlet in configlets_data:
                    configlet_list.append(CvElement(cv_data=configlet))
                return configlet_list
        return None

    def get_device_container(self, device_lookup):
        cv_data = self.get_device(device_lookup=device_lookup)
        if cv_data is not None:
            return CvElement(cv_data={'key': cv_data['parentContainerId'], FIELD_FQDN: cv_data['containerName']})
        return None

    def get_container_info(self, container_name: str):
        try:
            resp = self.__cv_client.api.get_container_by_name(name=str(container_name))
        except CvpApiError:
            self.__failure(msg='Error getting container ID from Cloudvision')
        else:
            return resp
        return None

    def get_container_current(self, device_mac: str):
        container_id = self.__cv_client.api.get_device_by_mac(device_mac=device_mac)
        if FIELD_PARENT_ID in container_id:
            return {'name': container_id[FIELD_CONTAINER_NAME], 'key': container_id[FIELD_PARENT_ID]}
        else:
            return None

    # ------------------------------------------ #
    # Workers function
    # ------------------------------------------ #

    def manager(self, user_inventory: DeviceInventory, search_mode: str = FIELD_FQDN):
        response = CvAnsibleResponse()

        cv_deploy = CvManagerResult(builder_name='devices_deployed')
        cv_move = CvManagerResult(builder_name='devices_moved')
        cv_configlets_add = CvManagerResult(builder_name='configlets_attached')

        action_result = self.deploy_device(user_inventory=user_inventory)
        if action_result is not None:
            for update in action_result:
                cv_deploy.add_change(change=update)

        action_result = self.move_device(user_inventory=user_inventory)
        if action_result is not None:
            for update in action_result:
                cv_move.add_change(change=update)

        action_result = self.apply_configlets(user_inventory=user_inventory)
        if action_result is not None:
            for update in action_result:
                cv_configlets_add.add_change(change=update)

        response.add_manager(cv_move)
        response.add_manager(cv_deploy)
        response.add_manager(cv_configlets_add)

        return response.content

    def move_device(self, user_inventory: DeviceInventory):
        results = list()
        for device in user_inventory.devices:
            result_data = CvApiResult(
                action_name='{}_to_{}'.format(device.fqdn, device.container))
            if device.system_mac is not None:
                new_container_info = self.get_container_info(
                    container_name=device.container)
                current_container_info = self.get_container_current(
                    device_mac=device.system_mac)
                # Move devices when they are not in undefined container
                if (current_container_info is not None
                    and current_container_info['name'] != UNDEFINED_CONTAINER
                        and current_container_info['name'] != device.container):
                    if self.__check_mode:
                        result_data.changed = True
                        result_data.success = True
                        result_data.taskIds = ['unsupported_in_check_mode']
                    else:
                        try:
                            resp = self.__cv_client.api.move_device_to_container(app_name='CvDeviceTools.move_device',
                                                                                device=device.info,
                                                                                container=new_container_info,
                                                                                create_task=True)
                        except CvpApiError:
                            self.__failure(msg='Error to move device {} to container {}'.format(
                                device.fqdn, device.container))
                        else:
                            if resp['data']['status'] == 'success':
                                result_data.changed = True
                                result_data.success = True
                                result_data.taskIds = resp['data']['taskIds']

                    result_data.add_entry('{}-{}'.format(device.fqdn, device.container))
            results.append(result_data)
        return results

    def apply_configlets(self, user_inventory: DeviceInventory):
        results = list()
        for device in user_inventory.devices:
            result_data = CvApiResult(
                action_name='{}_configlet_attached'.format(device.fqdn))
            if device.configlets is not None:
                # get configlet information from CV
                configlets_info = list()
                for configlet in device.configlets:
                    configlets_info.append(
                        self.__get_configlet_info(configlet_name=configlet))
                # get device facts from CV
                device_facts = dict()
                if self.__search_by == FIELD_FQDN:
                    device_facts = self.__cv_client.api.get_device_by_name(
                        fqdn=device.fqdn)
                # Attach configlets to device
                try:
                    resp = self.__cv_client.api.apply_configlets_to_device(app_name='CvDeviceTools.apply_configlets',
                                                                           dev=device_facts,
                                                                           new_configlets=configlets_info,
                                                                           create_task=True)
                except CvpApiError:
                    self.__failure(msg='Error applying configlets to device')
                    result_data.success = False
                else:
                    if resp['data']['status'] == 'success':
                        result_data.changed = True
                        result_data.success = True
                        result_data.taskIds = resp['data']['taskIds']
                        result_data.add_entry('{} adds {}'.format(
                            device.fqdn, device.configlets))
                result_data.add_entry('{} to {}'.format(device.fqdn, device.container))
            results.append(result_data)
        return results

    def remove_configlets(self, user_inventory: DeviceInventory):
        results = list()
        for device in user_inventory.devices:
            result_data = CvApiResult(action_name='{}_configlet_removed'.format(device.fqdn))
            if device.configlets is not None:
                # get configlet information from CV
                configlets_info = list()
                for configlet in device.configlets:
                    configlets_info.append(
                        self.__get_configlet_info(configlet_name=configlet))
                # get device facts from CV
                device_facts = dict()
                if self.__search_by == FIELD_FQDN:
                    device_facts = self.__cv_client.api.get_device_by_name(
                        fqdn=device.fqdn)
                # Attach configlets to device
                try:
                    resp = self.__cv_client.api.remove_configlets_from_device(app_name='CvDeviceTools.apply_configlets',
                                                                              dev=device_facts,
                                                                              del_configlets=configlets_info,
                                                                              create_task=True)
                except CvpApiError:
                    self.__failure(msg='Error applying configlets to device')
                    result_data.success = False
                else:
                    if resp['data']['status'] == 'success':
                        result_data.changed = True
                        result_data.success = True
                        result_data.taskIds = resp['data']['taskIds']
                        result_data.add_entry('{} removes {}'.format(
                            device.fqdn, device.configlets))
            results.append(result_data)
        return results

    def deploy_device(self, user_inventory: DeviceInventory):
        results = list()
        for device in user_inventory.devices:
            result_data = CvApiResult(action_name='{}_deployed'.format(device.fqdn))
            if device.system_mac is not None:
                configlets_info = list()
                for configlet in device.configlets:
                    configlets_info.append(
                        self.__get_configlet_info(configlet_name=configlet))
                new_container_info = self.get_container_info(
                    container_name=device.container)
                # Move devices when they are not in undefined container
                if (self.get_device_facts(device_lookup=device.fqdn)[FIELD_CONTAINER_NAME] == 'Undefined'):
                    if self.__check_mode:
                        result_data.changed = True
                        result_data.success = True
                        result_data.taskIds = ['unsupported_in_check_mode']
                    else:
                        try:
                            resp = self.__cv_client.api.deploy_device(app_name='CvDeviceTools.deploy',
                                                                      device=device.info,
                                                                      container=new_container_info,
                                                                      configlets=configlets_info,
                                                                      create_task=True)
                        except CvpApiError:
                            self.__failure(msg='Error to move device {} to container {}'.format(
                                device.fqdn, device.container))
                        else:
                            if resp['data']['status'] == 'success':
                                result_data.changed = True
                                result_data.success = True
                                result_data.taskIds = resp['data']['taskIds']

                    result_data.add_entry('{} deployed to {}'.format(
                        device.fqdn, device.container))
            results.append(result_data)
        return results

    # ------------------------------------------ #
    # Helpers function
    # ------------------------------------------ #

    def list_devices_to_move(self, inventory: DeviceInventory):
        devices_to_move = list()
        for device in inventory.devices:
            if self.__search_by == FIELD_FQDN:
                if self.is_in_container(device_lookup=device.fqdn, container_name=device.container) is False:
                    devices_to_move.append(device)
            if self.__search_by == FIELD_SYSMAC:
                if self.is_in_container(device_lookup=device.system_mac, container_name=device.container) is False:
                    devices_to_move.append(device)
        return devices_to_move

    # ------------------------------------------ #
    # Boolean functions
    # ------------------------------------------ #

    def is_in_container(self, device_lookup: str, container_name: str):
        data = self.__get_device(search_value=device_lookup, search_by=self.__search_by)
        if data is not None and FIELD_PARENT_ID in data:
            container_data = self.get_container_info(container_name=container_name)
            if container_data is not None:
                if container_data['key'] == data[FIELD_PARENT_ID]:
                    return True
        return False

    def is_device_exist(self, device_lookup: str):
        data = self.__get_device(
            search_value=device_lookup, search_by=self.__search_by)
        if data is not None and len(data) > 0:
            return True
        return False

    def has_correct_id(self, device: DeviceElement):
        device_id_cv: str = None
        # Get ID with correct search method
        device_id_cv = self.get_device_id(device_lookup=device.fqdn)
        if device_id_cv == device.system_mac:
            return True
        return False
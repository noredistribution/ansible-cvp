from unittest.mock import create_autospec
from tests.data.device_tools_unit import validate_ruter_bgp, return_validate_config_for_device, validate_intf, validate_true
from cvprac.cvp_client import CvpClient, CvpApi

class MockCvpApi():
    def validate_config_for_device(self, device_mac, config):
        if config == validate_ruter_bgp['config']:
            return return_validate_config_for_device['return_validate_ruter_bgp']
        if config == validate_intf['config']:
            return return_validate_config_for_device['return_validate_intf']
        if config == validate_true['config']:
            return return_validate_config_for_device['return_validate_true']


class MockCvpClient():
    def __init__(self):
        self.mock_cvpClient = create_autospec(CvpClient)
        self.mock_cvpClient.api = create_autospec(CvpApi)


class MockModule():
    def apply_mock_patch(self, mocker, mock_module):
        return mocker.patch(mock_module)

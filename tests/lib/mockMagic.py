from unittest.mock import create_autospec
from tests.data.device_tools_unit import validate_ruter_bgp, return_validate_config_for_device, validate_intf, validate_true, device_info
from cvprac.cvp_client import CvpClient, CvpApi
# from tests.unit.test_cv_device_tools import status

class MockCvpApi():
    def validate_config_for_device(self, device_mac, config):
        if config == validate_ruter_bgp['config']:
            return return_validate_config_for_device['return_validate_ruter_bgp']
        if config == validate_intf['config']:
            return return_validate_config_for_device['return_validate_intf']
        if config == validate_true['config']:
            return return_validate_config_for_device['return_validate_true']

    def device_decommissioning(self, device_id, request_id):
        # TODO: need to check cvp_api.get_device_by_serial output for device_info
        if device_id == device_info["serialNumber"]:
            result = {'value': {'key': {'requestId': request_id},
                              'deviceId': device_id},
                    'time': '2022-02-12T02:58:30.765459650Z'}
        else:
            result = None

        self.result = result
        return result

    def device_decommissioning_status_get_one(self, request_id):
        if self.result and self.result["value"]["key"]["requestId"]:
            # Need to check what all values are possible for status
            # if status == 'DECOMMISSIONING_STATUS_SUCCESS':
            resp = {"result": {"value": {"key": {"requestId": request_id},
                                         "status": 'DECOMMISSIONING_STATUS_SUCCESS',
                                         "statusMessage": "Disabled TerminAttr, "
                                                          "waiting for device to be marked inactive"},
                               "time": "2022-02-04T19:41:46.376310308Z", "type": "INITIAL"}}

            # elif status == 'DECOMMISSIONING_STATUS_IN_PROGRESS':
            #     resp = {"result": {"value": {"key": {"requestId": request_id},
            #                                  "status": 'DECOMMISSIONING_STATUS_IN_PROGRESS',
            #                                  "statusMessage": "Disabled TerminAttr, waiting for device to be marked inactive"},
            #                        "time": "2022-02-04T19:41:46.376310308Z", "type": "INITIAL"}}

        else:
            resp = {"result": {"value": {"key": {"requestId": request_id},
                                         "status": 'DECOMMISSIONING_STATUS_FAILURE',
                                         "statusMessage": "Disabled TerminAttr, "
                                                          "waiting for device to be marked inactive"},
                               "time": "2022-02-04T19:41:46.376310308Z", "type": "INITIAL"}}

        return resp["result"]


class MockCvpClient():
    def __init__(self):
        self.mock_cvpClient = create_autospec(CvpClient)
        self.mock_cvpClient.api = create_autospec(CvpApi)


class MockModule():
    def apply_mock_patch(self, mocker, mock_module):
        return mocker.patch(mock_module)

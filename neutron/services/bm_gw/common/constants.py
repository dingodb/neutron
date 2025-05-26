# Copyright 2025 OpenStack Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Constants for bare metal gateway."""
from neutron_lib import constants as nl_constants

BMGW_AGENT = 'bmgw-agent'
AGENT_TYPE_BMGW = 'Bare Metal Gateway agent'
DEVICE_NAME_MAX_LEN = nl_constants.DEVICE_NAME_MAX_LEN - 1

BRIDGE_TYPE_LINUX = 'linux'
BRIDGE_TYPE_OVS = 'ovs'

BMGW_BRIDGE_NAME = 'br-bmgw'
BM_PORT_PREFIX = 'bmp'
TAP_PORT_PREFIX = 'tap'
#BM_PORT_PEER_PREFIX = TAP_PORT_PREFIX

TRUNK_BR_PREFIX = 'tbr-'

QBR_BRIDGE_PREFIX = 'qbr'
QVB_PORT_PREFIX = 'qvb'
QVO_PORT_PREFIX = 'qvo'
QVB_PORT_PEER_PREFIX = QVO_PORT_PREFIX
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

# mall@zetyun.com, 2025.5.20
# create file bmgwdriver.py
# BareMetal Gateway driver handling plugin messages and port operations inside OVS agent.

from neutron_lib.callbacks import events
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.api.definitions import portbindings

#from neutron_lib import context
from oslo_config import cfg
from oslo_log import log as logging
from neutron.services.bm_gw.common import utils
from neutron.services.bm_gw.common import constants
from neutron.services.bm_gw.rpc import agent as agent_rpc
from neutron.api.rpc.callbacks import events as rpc_events
from neutron_lib.plugins.ml2 import ovs_constants

LOG = logging.getLogger(__name__)

BM_GW_SKELETON = None

class BmGwDriver(object):
    """BmGw driver handling plugin messages and port operations inside OVS agent."""
    def __init__(self, trigger):
        self.host = cfg.CONF.host
        # br_bmgw bridge should be created by deployment tools
        # and should added the physical NIC (for baremetals access) to it.
        LOG.debug(f"BmGwDriver, init, bm_gw_brname={cfg.CONF.AGENT.bm_gw_brname}")
        self.br_bmgw = utils.BmgwBridge(cfg.CONF.AGENT.bm_gw_brname)
        #self.br_bmgw.create(secure_mode=True)
        #self.nic_ofport = self.br_bmgw.add_port(cfg.CONF.AGENT.bm_gw_nic)
        #self.br_bmgw.set_nic_ofport_id(self.nic_ofport)

        self.ovs_agent = trigger
        LOG.info(f"BmGwDriver self ovs agent={self.ovs_agent.agent_state}")
        if not self.br_bmgw.exists():
            LOG.error(f"BmGwDriver, bm_gw bridge {self.br_bmgw.br_name} not exists")

    def process_port(self, port, event_type):
        LOG.info("BEGIN: process_port [")
        LOG.debug(f"Type of port: {type(port)}")
        LOG.debug(f"Content of port: {port}")
        LOG.debug(f"Type of bindings: {type(port.bindings)}")
        LOG.debug(f"Content of bindings: {port.bindings}")

        port_id = port['id']

        try:
            host, vnic_type, vif_type, mac, qinq_id, bridge_name, ovs_hybrid_plug = parse_port(port)
            to_bridge = self.ovs_agent.int_br

            if vnic_type == portbindings.VNIC_BAREMETAL or event_type == rpc_events.DELETED:
                if self.host == host and (vif_type == portbindings.VIF_TYPE_OVS or vif_type == portbindings.VIF_TYPE_VHOST_USER):
                    if not cfg.CONF.AGENT.bm_gw:
                        LOG.error(f"BmGwDriver, process_port, bm_gw is not enabled, can not scheduler bmport({port_id}) on this host")
                        return
                    LOG.info(f"BmGwDriver, process_port, plug bmport {port_id}, event_type={event_type}")
                    if not bridge_name:
                        LOG.error(f"BmGwDriver, process_port, failed to plug bmport {port_id} for bridge_name is empty")
                        return
                    if bridge_name.startswith(constants.TRUNK_BR_PREFIX) and len(bridge_name) == constants.DEVICE_NAME_MAX_LEN:
                        datapath_type = ovs_constants.OVS_DATAPATH_NETDEV if vif_type == portbindings.VIF_TYPE_VHOST_USER else ovs_constants.OVS_DATAPATH_SYSTEM
                        to_bridge = utils.TrunkBridge(bridge_name, datapath_type)
                        to_bridge.verify()

                    if not (qinq_id > 0 and qinq_id < 4094):
                        LOG.error(f"BmGwDriver, process_port, failed to plug bmport {port_id} for qinq_id({qinq_id}) is invalid")
                        return

                    bmport = utils.BmPort(port_id, to_bridge, mac, qinq_id, ovs_hybrid_plug)
                    bmport.plug()
                else:
                    LOG.info(f"BmGwDriver, process_port, unplug bmport {port_id}, event_type={event_type}")
                    bmport = utils.BmPort(port_id, to_bridge, mac, qinq_id, ovs_hybrid_plug)
                    bmport.unplug()
            else:
                LOG.info(f"BmGwDriver, process_port, ignore non-baremetal port {port_id}")
        except Exception as e:
            LOG.error(f"BmGwDriver, process_port, Failed to process port {port_id}: {e}")

    def bmgw_port_update(self, context, resource, bmgwport, event_type):
        if not bmgwport:
            LOG.warning("BmGwDriver, bmgw_port_update, Received empty port update notification")
            return
            
        # make sure bmgwport is a list
        ports = bmgwport if isinstance(bmgwport, list) else [bmgwport]
        port_count = len(ports)
        
        LOG.info(f"BmGwDriver, bmgw_port_update, Received port update notification, "
                f"port count: {port_count} and event_type: {event_type}")
        
        success_count = 0
        for port in ports:
            port_id = port.get('id', 'unknown')
            port_name = port.get('name', 'unknown')
            LOG.debug(f"BmGwDriver, bmgw_port_update, Processing port id: {port_id} name: {port_name}")
            
            try:
                self.process_port(port, event_type)
                success_count += 1
            except Exception as e:
                LOG.error(f"BmGwDriver, bmgw_port_update, Failed to process port id: {port_id}: {e}")
        
        LOG.info(f"BmGwDriver, bmgw_port_update, Completed processing {success_count} of {port_count} ports")

def bmgwinit_handler(resource, event, trigger, payload=None):
    """Handler for agent init event."""
    global BM_GW_SKELETON

    if not cfg.CONF.AGENT.bm_gw:
        LOG.info("BmGwDriver, init_handler, bm_gw is not enabled, bmgwdriver init just for clear bmport on this host")
        #return

    driver = BmGwDriver(trigger)
    BM_GW_SKELETON = agent_rpc.BmGwSkeleton(driver)

    LOG.info("BmGwDriver, init_handler, Bmgw skeleton initialized")


def unregister():
    """Unregister the bmgw skeleton."""
    if BM_GW_SKELETON:
        BM_GW_SKELETON.unregister()

def parse_port(port):
    """Parse the port."""
    mac = None
    if 'mac_address' in port.fields and port.obj_attr_is_set('mac_address'):
        mac = str(port.mac_address)
    host = None
    vif_type = None
    vnic_type = None
    qinq_id = int(0)
    bridge_name = None
    ovs_hybrid_plug = False
    bindings = port.bindings

    if bindings is not None:
        binding = bindings[0]
        host = binding.host
        vif_type = binding.vif_type
        vnic_type = binding.vnic_type

        profile = binding.profile
        if profile is not None and profile.get('local_link_information') is not None:
            qinq_id = profile.get('local_link_information')[0].get('switch_info')

        vif_details = binding.vif_details
        if vif_details is not None:     
            bridge_name = vif_details.get('bridge_name')
            ovs_hybrid_plug = bool(vif_details.get('ovs_hybrid_plug'))
    
    LOG.debug(f"BmGwDriver, parse_port, host={host}, vnic_type={vnic_type}, vif_type={vif_type}, " \
              f"mac:={mac}, qinq_id={qinq_id}, bridge_name={bridge_name}, ovs_hybrid_plug={ovs_hybrid_plug}")
    return host, vnic_type, vif_type, mac, int(qinq_id), str(bridge_name), bool(ovs_hybrid_plug)
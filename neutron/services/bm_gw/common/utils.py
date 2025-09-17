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
# create file utils.py
# Utilities for bare metal gateway.

import os
import eventlet
from oslo_config import cfg
from neutron.agent.linux import ip_lib
from neutron.agent.linux import bridge_lib as linux_bridge
from neutron.agent.common import ovs_lib
from neutron.agent.linux import utils
from oslo_log import log as logging
from neutron.services.bm_gw.common import constants
from neutron_lib.plugins.ml2 import ovs_constants

LOG = logging.getLogger(__name__)

def get_bmport_name(port_id):
    """Get the name of the bm port."""
    #return f"{constants.BM_PORT_PREFIX}{port_id}"
    return ("%s%s" % (constants.BM_PORT_PREFIX, port_id))[:constants.DEVICE_NAME_MAX_LEN]

def get_bmport_peer_name(port_id, hybrid):
    """Get the name of the bm port peer."""
    if hybrid:
        return ("%s%s" % (constants.TAP_PORT_PREFIX, port_id))[:constants.DEVICE_NAME_MAX_LEN]
    else:
        return ("%s%s" % (constants.QVO_PORT_PREFIX, port_id))[:constants.DEVICE_NAME_MAX_LEN]

def get_tap_port_name(port_id):
    """Get the name of the tap port."""
    return ("%s%s" % (constants.TAP_PORT_PREFIX, port_id))[:constants.DEVICE_NAME_MAX_LEN]

def get_qvb_port_name(port_id):
    """Get the name of the qvb port."""
    return ("%s%s" % (constants.QVB_PORT_PREFIX, port_id))[:constants.DEVICE_NAME_MAX_LEN]

def get_qvo_port_name(port_id):
    """Get the name of the qvo port."""
    return ("%s%s" % (constants.QVO_PORT_PREFIX, port_id))[:constants.DEVICE_NAME_MAX_LEN]

def get_qvb_port_peer_name(port_id):
    """Get the name of the qvb port peer."""
    return ("%s%s" % (constants.QVB_PORT_PEER_PREFIX, port_id))[:constants.DEVICE_NAME_MAX_LEN]

def get_qbr_bridge_name(port_id):
    """Get the name of the qbr bridge."""
    return ("%s%s" % (constants.QBR_BRIDGE_PREFIX, port_id))[:constants.DEVICE_NAME_MAX_LEN]

def gen_trunk_br_name(trunk_id):
    return ((constants.TRUNK_BR_PREFIX + trunk_id)[:constants.DEVICE_NAME_MAX_LEN])

def get_port_attrs(port_id, port_mac=None, type=None, peer=None, hybrid=False):
    external_ids = {}
    if port_mac:
        external_ids['attached-mac'] = str(port_mac)
    if port_id:
        external_ids['iface-id'] = port_id
    
    attrs = []
    if type:
        attrs.append(('type', type))
    if peer:
        attrs.append(('options', {'peer': peer}))
    # attrs = [('type', ''), ('options', ''{'peer': peer_name}'')]
    if hybrid:
        attrs.append(('other_config', {'hybrid': 'true'}))
    else:
        attrs.append(('other_config', {'hybrid': 'false'}))

    if external_ids:
        attrs.append(
            ('external_ids', external_ids))
    return attrs

def create_veth_pair(if1, if2, f1mac = None, f2mac = None):
    """Create a veth pair if not exists."""
    if not ip_lib.device_exists(if1) and not ip_lib.device_exists(if2):
        utils.execute(['ip', 'link', 'add', if1, 'type', 'veth', 'peer', 'name', if2], run_as_root=True)
        if f1mac is not None:
            utils.execute(['ip', 'link','set', if1, 'address', f1mac], run_as_root=True)
        if f2mac is not None:
            utils.execute(['ip', 'link','set', if2, 'address', f2mac], run_as_root=True)

        utils.execute(['ip', 'link', 'set', if1, 'up'], run_as_root=True)
        utils.execute(['ip', 'link', 'set', if2, 'up'], run_as_root=True)
        LOG.debug(f"bmgw driver utils, Created veth pair {if1} <-> {if2}")

def delete_veth_pair(if1, if2):
    """Delete a veth pair if exists."""
    if ip_lib.device_exists(if1):
        utils.execute(['ip', 'link', 'del', if1], run_as_root=True)
        LOG.debug(f"bmgw driver utils, Deleted veth pair {if1} <-> {if2}")
    elif ip_lib.device_exists(if2):
        utils.execute(['ip', 'link', 'del', if2], run_as_root=True)
        LOG.debug(f"bmgw driver utils, Deleted veth pair {if2} <-> {if1}")


class BmgwBridge(ovs_lib.OVSBridge):
    """An OVS bm gw bridge.
    The bridge is created if it does not exist.
    bmgw bridge is used to connect the bm ports to the linux bridge.
    [ br-bmgw ]                    [ qbrXXX ]                     [ br-int ]
         \                          /     \                          /
         < bmpXXX > ---- < tapXXX >        < qvbXXX > ---- < qvoXXX >
    """
    def __init__(self, br_name):
        super(BmgwBridge, self).__init__(br_name=br_name)
        #self.nic_ofport_id = ovs_lib.INVALID_OFPORT

        # to enable qinq on ovs port, we need to set the following options globally in Open_vSwitch table
        other_config = {'vlan-limit': '2'}
        self.ovsdb.db_set('Open_vSwitch', '.', ('other_config', other_config))
        #eventlet.spawn_after(60, self.clean_dead_bmports)
    
    def spawn_clean_dead_bmports(self):
        LOG.info("bmgw driver utils, spawn job clean_dead_bmports")
        eventlet.spawn_after(60, self.clean_dead_bmports)

    def clean_dead_bmports(self):
        LOG.info("bmgw driver utils, run job clean_dead_bmports")
        ports = self.get_port_name_list()

        for bmp_name in ports:
            # here: port is port_name
            if not bmp_name.startswith(constants.BM_PORT_PREFIX):
                continue

            # # 获取当前 port 的接口属性字典
            # options = self.db_get_val('Interface', port, 'options')
            # if not options:
            #     LOG.warning(f"bmgw, clean_dead_bmports, port {port} has no options, skip it")                
            #     continue

            # peer_name = options.get('peer')
            # if not peer_name:
            #     LOG.warning(f"bmgw, clean_dead_bmports, port {port} has no peer, skip it")
            #     continue

            # qvo port name: qvoXXXXXXXX-XX
            qvo_name = constants.QVO_PORT_PREFIX + bmp_name[3:]
            # maybe bmp connect to tbr, trunk port, tpi_name: tpi-XXXXXXXX-XX
            tpi_name = constants.TRUNK_PORT_INT_PREFIX + bmp_name[4:]

            # 获取 br-int 上对应 port 的 tag
            tag = self.db_get_val('Port', qvo_name, 'tag')
            tag2 = 0;
            if self.port_exists(tpi_name):
                tag2 = self.db_get_val('Port', tpi_name, 'tag')

            if (tag is not None and tag == constants.OVS_DEAD_VLAN) or (tag2 is not None and tag2 == constants.OVS_DEAD_VLAN):
                external_ids = self.db_get_val('Interface', bmp_name, 'external_ids')
                port_id = external_ids.get('iface-id') if external_ids else None

                if not port_id:
                    LOG.warning(f"bmgw driver utils, clean_dead_bmports, port {bmp_name} has no port_id, skip it")
                    continue

                LOG.info(f"bmgw driver utils, clean_dead_bmports, port {bmp_name} is dead, delete it")
                try:
                    bmport = BmPort(port_id, to_bridge=None, mac=None, qinq=0, ovs_hybrid_plug=True)
                    bmport.unplug()
                except Exception as e:
                    LOG.error(f"bmgw driver utils, clean_dead_bmports, Failed to delete port {bmp_name}: {e}")


    def exists(self):
        return self.bridge_exists(self.br_name)

    # def set_nic_ofport_id(self, ofportid):
    #     self.nic_ofport_id = ofportid
    
class BmPort():
    """A Bm port."""
    def __init__(self, port_id, to_bridge, mac = None, qinq = 0, ovs_hybrid_plug = True):
        self.port_id = port_id
        self.mac = str(mac) if mac else None
        self.qinq = qinq
        self.ovs_hybrid_plug = ovs_hybrid_plug
        self.name = get_bmport_name(port_id)
        self.tap_name = get_tap_port_name(port_id)
        self.qvb_name = get_qvb_port_name(port_id)
        self.qvo_name = get_qvo_port_name(port_id)

        self.bridge = BmgwBridge(cfg.CONF.AGENT.bm_gw_brname)
        # to_bridge can be trunk bridge (tbr-XXX) or br-int
        self.to_bridge = to_bridge

        self.qbr_bridge = linux_bridge.BridgeDevice(get_qbr_bridge_name(port_id))
        #self.ofport_id = self.bridge.get_port_ofport(self.name)
        LOG.debug(f"bmgw driver utils, Init bm port Object {self.name}")

    def plug(self):
        ""
        """Plug patch ports between bmgw bridge and given bridge.

        The method plugs one patch port on the given bridge side using
        port MAC and ID as external IDs.  The other endpoint of patch port is
        attached to the bmgw bridge.  Everything is done in a single
        OVSDB transaction so either all operations succeed or fail.

        """
        # NOTE(jlibosva): OVSDB is an api so it doesn't matter whether we
        # use self.bridge or br_int
        
        # Once the bridges are connected with the following patch ports,
        # the ovs agent will recognize the ports for processing and it will
        # take over the wiring process and everything that entails.
        # REVISIT(rossella_s): revisit this integration part, should tighter
        # control over the wiring logic for bm ports be required.
        port_qvo_attrs = None
        port_bmp_attrs = None

        if self.ovs_hybrid_plug:
            create_veth_pair(self.name, self.tap_name)
            create_veth_pair(self.qvb_name, self.qvo_name)
            self.qbr_bridge.addbr(self.qbr_bridge._name)
            self.qbr_bridge.addif(self.qvb_name)
            self.qbr_bridge.addif(self.tap_name)
            utils.execute(['ip', 'link', 'set', self.qbr_bridge._name, 'up'], run_as_root=True)
            port_qvo_attrs = get_port_attrs(self.port_id, self.mac, peer=self.qvb_name, hybrid=True)
            port_bmp_attrs = get_port_attrs(self.port_id, self.mac, peer=self.tap_name, hybrid=True)
        else:
            # create_veth_pair(self.name, self.qvo_name)
            # for ovs_hybrid_plug = False (case of DPDK), we patch rather than veth pair
            # patch port can running in both user space and kernel space.
            port_qvo_attrs = get_port_attrs(self.port_id, self.mac, constants.OVS_PATCH, self.name, hybrid=False)
            port_bmp_attrs = get_port_attrs(self.port_id, self.mac, constants.OVS_PATCH, self.qvo_name, hybrid=False)

        ovsdb = self.bridge.ovsdb
        with ovsdb.transaction() as txn:
            txn.add(ovsdb.add_port(self.to_bridge.br_name,
                                self.qvo_name))
            txn.add(ovsdb.db_set('Interface', self.qvo_name,
                                *port_qvo_attrs))
            txn.add(ovsdb.add_port(self.bridge.br_name,
                                self.name))
            txn.add(ovsdb.db_set('Interface', self.name,
                                *port_bmp_attrs))
            txn.add(ovsdb.db_set('Port', self.name,
                                ('vlan_mode', 'dot1q-tunnel'),
                                ('tag', self.qinq),
                                ('other_config', {'qinq-ethtype':'802.1q'})))

        #self.ofport_id = self.bridge.get_port_ofport(self.name)
        LOG.info(f"bmgw driver utils, Plugged bm port {self.name} to bridge {self.bridge.br_name}")

    def unplug(self):
        """Unplug the bmport from bridge.

        Method unplugs in single OVSDB transaction the bmgw bridge and patch
        port on provided bridge.

        :param bridge: bridge that has peer side of patch port for this port.
        """

        # CAN NOT use the self.to_bridge in unplug method, 
        # because it may be trunk bridge or br-int, 
        # we didn't init self.to_bridge weth correct value.
        if not self.bridge.port_exists(self.name):
            LOG.debug(f"bmgw driver utils, bmport.unplug, port {self.name} does not exist, return")
            return

        hybrid = self.get_hybrid_flag()
        LOG.info(f"bmgw driver utils, bmport.unplug, port {self.name} hybrid flag is {hybrid}")
        
        ovsdb = self.bridge.ovsdb

        with ovsdb.transaction() as txn:
            txn.add(ovsdb.del_port(self.name))
            txn.add(ovsdb.del_port(self.qvo_name))
            #txn.add(ovsdb.db_destroy('Interface', self.qvo_name))

            if self.bridge.port_exists(self.qvo_name):
                peer_br_name = self.bridge.get_bridge_for_iface(self.qvo_name)
                if peer_br_name:
                    LOG.debug(f"bmgw driver utils, bmport.unplug, port {self.qvo_name} is connected to bridge {peer_br_name}")
                else:
                    LOG.debug(f"bmgw driver utils, bmport.unplug, port {self.qvo_name} is not connected to any bridge")

                if peer_br_name and peer_br_name.startswith(constants.TRUNK_BR_PREFIX):
                    # delete trunk bridge
                    LOG.debug(f"bmgw driver utils, bmport.unplug, spawn a job to delete trunk bridge {peer_br_name}")
                    eventlet.spawn_after(4, self.del_trunk_bridge, peer_br_name)
                    # trk_br = TrunkBridge(peer_br_name)
                    # if trk_br.bridge_exists(peer_br_name):
                    #     LOG.debug(f"bmgwdriver, bmport.unplug, delete trunk bridge {peer_br_name}")
                    #     trk_br.delete_ports(all_ports=True)
                    #     trk_br.destroy()

        if hybrid:
            if self.qbr_bridge.exists():
                self.qbr_bridge.delif(self.qvb_name)
                self.qbr_bridge.delif(self.tap_name)
                self.qbr_bridge.delbr()
            delete_veth_pair(self.name, self.tap_name)
            delete_veth_pair(self.qvb_name, self.qvo_name)

        LOG.info(f"bmgw driver utils, bmport.unplug, Unplugged bm port {self.name} from bridge {self.bridge.br_name}")

    def del_trunk_bridge(self, br_name):
        """Delete trunk bridge."""
        LOG.debug(f"bmgw driver utils, bmport.del_trunk_bridge, delete trunk bridge {br_name}")

        br = TrunkBridge(br_name)
        if br.bridge_exists(br_name):
            br.destroy()
    
    def get_hybrid_flag(self):
        """Get hybrid flag."""
        if not self.bridge.port_exists(self.name):
            LOG.debug(f"bmgw driver utils, bmport.get_hybrid_flag, port {self.name} does not exist")
            return False

        other_config = self.bridge.db_get_val('Interface', self.name, 'other_config')
        if not other_config:
            LOG.warning(f"bmgw driver utils, bmport.get_hybrid_flag, port {self.name} has no other_config")
            return True

        hybrid = other_config.get('hybrid')
        if not hybrid:
            LOG.warning(f"bmgw driver utils, bmport.get_hybrid_flag, port {self.name} has no hybrid")
            return True

        return hybrid == 'true'

class TrunkBridge(ovs_lib.OVSBridge):
    """A trunk bridge.
    The bridge is created if it does not exist.
    bmgw bridge is used to connect the bm ports to the OVS bridge.
    br-bmgw <-> bmport 
                      \ 
                       bmport-peer <-> tbr-xxxxxxxx-x (trunk bridge)
    """
    def __init__(self, name, datapath_type=ovs_constants.OVS_DATAPATH_SYSTEM):
        super(TrunkBridge, self).__init__(name, datapath_type)

    def verify(self):
        if not self.bridge_exists(self.br_name):
            self.create()
            LOG.debug(f"bmgw driver utils, TrunkBridge.verify, Created trunk bridge {self.br_name}")
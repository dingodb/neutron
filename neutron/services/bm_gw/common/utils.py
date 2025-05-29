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

"""Utilities for bare metal gateway."""

import os
import eventlet
from oslo_config import cfg
from neutron.agent.linux import ip_lib
from neutron.agent.linux import bridge_lib as linux_bridge
from neutron.agent.common import ovs_lib
from neutron.agent.linux import utils
from oslo_log import log as logging
from neutron.services.bm_gw.common import constants

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

def get_port_attrs(port_id, port_mac=None, type=None, peer=None):
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
        LOG.debug("Created veth pair %s <-> %s", if1, if2)

def delete_veth_pair(if1, if2):
    """Delete a veth pair if exists."""
    if ip_lib.device_exists(if1):
        utils.execute(['ip', 'link', 'del', if1], run_as_root=True)
    elif ip_lib.device_exists(if2):
        utils.execute(['ip', 'link', 'del', if2], run_as_root=True)

    LOG.debug("Deleted veth pair %s <-> %s", if1, if2)

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


    def exists(self):
        return self.bridge_exists(self.br_name)

    # def set_nic_ofport_id(self, ofportid):
    #     self.nic_ofport_id = ofportid
    
class BmPort():
    """A Bm port."""
    def __init__(self, port_id, to_bridge, mac = str(None), qinq = 0, ovs_hybrid_plug = True):
        self.port_id = port_id
        self.mac = mac
        self.qinq = qinq
        self.ovs_hybrid_plug = ovs_hybrid_plug
        self.name = get_bmport_name(port_id)
        self.tap_name = get_tap_port_name(port_id)
        self.qvb_name = get_qvb_port_name(port_id)
        self.qvo_name = get_qvo_port_name(port_id)

        self.bridge = BmgwBridge(cfg.CONF.AGENT.bm_gw_brname)
        # to_bridge can be trunk bridge (tbr-XXX) or br-int
        self.to_bridge = to_bridge

        self.qbr_bridge = None
        if self.ovs_hybrid_plug:
            self.qbr_bridge = linux_bridge.BridgeDevice(get_qbr_bridge_name(port_id))
        #self.ofport_id = self.bridge.get_port_ofport(self.name)
        LOG.debug("Init bm port Object %s", self.name)

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
        port_int_attrs = None
        port_bm_attrs = None

        if self.ovs_hybrid_plug:
            create_veth_pair(self.name, self.tap_name)
            create_veth_pair(self.qvb_name, self.qvo_name)
            self.qbr_bridge.addbr(self.qbr_bridge._name)
            self.qbr_bridge.addif(self.qvb_name)
            self.qbr_bridge.addif(self.tap_name)
            utils.execute(['ip', 'link', 'set', self.qbr_bridge._name, 'up'], run_as_root=True)
            port_int_attrs = get_port_attrs(self.port_id, self.mac)
        else:
            # create_veth_pair(self.name, self.qvo_name)
            # for ovs_hybrid_plug = False (case of DPDK), we patch rather than veth pair
            # patch port can running in both user space and kernel space.
            port_int_attrs = get_port_attrs(self.port_id, self.mac, constants.OVS_PATCH, self.name)
            port_bm_attrs = get_port_attrs(self.port_id, self.mac, constants.OVS_PATCH, self.qvo_name)

        ovsdb = self.bridge.ovsdb
        with ovsdb.transaction() as txn:
            txn.add(ovsdb.add_port(self.to_bridge.br_name,
                                self.qvo_name))
            txn.add(ovsdb.db_set('Interface', self.qvo_name,
                                *port_int_attrs))
            txn.add(ovsdb.add_port(self.bridge.br_name,
                                self.name))
            if not self.ovs_hybrid_plug:
                txn.add(ovsdb.db_set('Interface', self.name,
                                *port_bm_attrs))
            txn.add(ovsdb.db_set('Port', self.name,
                                ('vlan_mode', 'dot1q-tunnel'),
                                ('tag', self.qinq),
                                ('other_config', {'qinq-ethtype':'802.1q'})))

        #self.ofport_id = self.bridge.get_port_ofport(self.name)
        LOG.debug("Plugged bm port %s to bridge %s", self.name, self.bridge.br_name)

    def unplug(self):
        """Unplug the bmport from bridge.

        Method unplugs in single OVSDB transaction the bmgw bridge and patch
        port on provided bridge.

        :param bridge: bridge that has peer side of patch port for this port.
        """

        # CAN NOT use the self.to_bridge in unplug method, 
        # because it may be trunk bridge or br-int, 
        # we didn't init self.to_bridge weth correct value.

        ovsdb = self.bridge.ovsdb

        with ovsdb.transaction() as txn:
            txn.add(ovsdb.del_port(self.name))
            txn.add(ovsdb.del_port(self.qvo_name))
            #txn.add(ovsdb.db_destroy('Interface', self.qvo_name))

            if self.bridge.port_exists(self.qvo_name):
                peer_br_name = self.bridge.get_bridge_for_iface(self.qvo_name)
                if peer_br_name:
                    LOG.debug(f"bmgwdriver, bmport.unplug, port {self.qvo_name} is connected to bridge {peer_br_name}")
                else:
                    LOG.debug(f"bmgwdriver, bmport.unplug, port {self.qvo_name} is not connected to any bridge")

                if peer_br_name and peer_br_name != 'br-int':
                    # delete trunk bridge
                    LOG.debug(f"bmgwdriver, bmport.unplug, spawn a job to delete trunk bridge {peer_br_name}")
                    eventlet.spawn_after(2, self.del_trunk_bridge, peer_br_name)
                    # trk_br = TrunkBridge(peer_br_name)
                    # if trk_br.bridge_exists(peer_br_name):
                    #     LOG.debug(f"bmgwdriver, bmport.unplug, delete trunk bridge {peer_br_name}")
                    #     trk_br.delete_ports(all_ports=True)
                    #     trk_br.destroy()

        if self.ovs_hybrid_plug:
            if self.qbr_bridge.exists():
                self.qbr_bridge.delif(self.qvb_name)
                self.qbr_bridge.delif(self.tap_name)
                self.qbr_bridge.delbr()
            delete_veth_pair(self.name, self.tap_name)
            delete_veth_pair(self.qvb_name, self.qvo_name)

        # else:
        #     delete_veth_pair(self.name, self.qvo_name)

        LOG.debug("Unplugged bm port %s from bridge %s", self.name, self.bridge.br_name)

    def del_trunk_bridge(self, br_name):
        """Delete trunk bridge."""
        LOG.debug(f"bmgwdriver, bmport.del_trunk_bridge, delete trunk bridge {br_name}")
        br = TrunkBridge(br_name)
        if br.bridge_exists(br_name):
            br.destroy()

class TrunkBridge(ovs_lib.OVSBridge):
    """A trunk bridge.
    The bridge is created if it does not exist.
    bmgw bridge is used to connect the bm ports to the OVS bridge.
    br-bmgw <-> bmport 
                      \ 
                       bmport-peer <-> tbr-xxxxxxxx-x (trunk bridge)
    """
    def __init__(self, name):
        super(TrunkBridge, self).__init__(name)

    def verify(self):
        if not self.bridge_exists(self.br_name):
            self.create()
            LOG.debug("bmgwdriver Created trunk bridge %s", self.br_name)
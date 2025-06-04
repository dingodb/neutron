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
# create file plugin.py
# BareMetal Gateway plugin handling schedule and reschedule bmgwport.

import random
from re import A

from neutron_lib.callbacks import events
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib import context
from neutron_lib.plugins import directory
from neutron_lib.api.definitions import portbindings
from neutron_lib.plugins import constants as plugin_constants
from neutron_lib.callbacks import resources as res
from neutron_lib import constants
from neutron_lib.agent import constants as agent_constants
from oslo_log import log as logging
from oslo_utils import timeutils
from oslo_messaging import Target
from oslo_messaging import RPCClient

from neutron_lib.services import base as service_base
from neutron.services.tag import tag_plugin
from neutron.services.bm_gw.rpc import server as rpc_server

LOG = logging.getLogger(__name__)

class BmgwPlugin(service_base.ServicePluginBase):
    """Plugin to handle Bare Metal Gateway management."""

    #supported_extension_aliases = ['bm-gw']

    def __init__(self):
        super(BmgwPlugin, self).__init__()
        self._setup_rpc()
        self.register_callbacks()
        self.tag_plugin_instance = tag_plugin.TagPlugin()
        directory.add_plugin('standard-attr-tag', self.tag_plugin_instance)

        # Cache to store scheduled ports: {port_id: {'host_id': host_id, 'timestamp': timestamp}}
        #self._scheduled_ports = {}
        LOG.info("BMGW plugin initialized")

    def register_callbacks(self):
        """Register callbacks for agent and port events from Neutron-server."""
        registry.subscribe(self._handle_agent_update,
                         resources.AGENT,
                         events.AFTER_UPDATE)
        registry.subscribe(self._handle_port_update,
                         resources.PORT,
                         events.AFTER_UPDATE)
    
    #define a func, start a daemon loop to check if all ovs agents are alive


    def _handle_agent_update(self, resource, event, trigger, payload=None):
        """Handle agent update events.
        
        When an agent is update, find all ports scheduled to the agent using this
        agent and reschedule them to other available agents.
        """
        if not payload:
            LOG.warning("No payload for agent update event")
            return

        # agent_id = payload.resource_id
        # if not agent_id:
        #     LOG.warning("No agent_id in payload for agent update event")
        #     return

        admin_context = context.get_admin_context()
        plugin = directory.get_plugin()

        # Find all ports scheduled to the down agent
        # we check all agents (not only the agent event triggered) to find all down agents.
        agents = plugin.get_agents(admin_context, filters={'alive': [False], 'agent_type': [constants.AGENT_TYPE_OVS]})
        if not agents or len(agents) == 0:
            LOG.debug(f"[bmgw plugin : _handle_agent_update] No down agent found, no need rechedule bmgwport.")
            return

        ports_to_reschedule = []
        for agent in agents:
            down_host = agent['host']
            LOG.info(f"[bmgw plugin : _handle_agent_update] bmgwAgent {down_host} is down, rechedule bmgwport in this host.")
            ports_to_reschedule = plugin.get_ports_by_vnic_type_and_host(admin_context,
                                                                     vnic_type = portbindings.VNIC_BAREMETAL,
                                                                     host = down_host)

            LOG.info(f"[bmgw plugin : _handle_agent_update] Found {len(ports_to_reschedule)} ports need to reschedule for down agent {down_host}")

            # Reschedule each port
            for port in ports_to_reschedule:
                port_id = port['id']
                try:
                    # Schedule port to a new agent
                    new_host = self.schedule_port_to_bmgw(admin_context, port)
                    if not new_host:
                        LOG.error(f"Failed to reschedule port {port_id}")
                        continue
                    # Update port binding
                    port_binding = {
                        'binding:host_id': new_host
                    }
                    plugin.update_port(admin_context, port_id, {'port': port_binding})
                    LOG.info(f"[bmgw plugin : _handle_agent_update], Rescheduled port {port_id} to agent {new_host}")
                except Exception as e:
                    LOG.error(f"[bmgw plugin : _handle_agent_update], Failed to process port {port_id}: {e}")



    def _handle_port_update(self, resource, event, trigger, payload=None):
        """Handle port update events.
        
        When an unbound baremetal port is updated:
        1. Update its binding information to use OVS as the VIF type
        2. Schedule it to a BMGW agent
        """
        LOG.debug("BmgwPlugin,_handle_port_update:[begin]")
        if not payload:
            LOG.error("BmgwPlugin,_handle_port_update:[no payload]")
            return
        port = payload.latest_state
        if not port:
            LOG.error("BmgwPlugin,_handle_port_update:[not port]")
            return
        port_id = port.get('id')

        # Check if port's vnic_type is baremetal
        vnic_type = port.get('binding:vnic_type')
        if vnic_type != portbindings.VNIC_BAREMETAL:
            LOG.debug(f"BmgwPlugin,_handle_port_update: port {port_id} vnic not baremetal, return.")
            return

        # Only handle baremetal ports that have been attach to a host by ironic.
        #  ironic will set binding:host_id to the host where the baremetal port is attached to.
        bmhostid = port.get('binding:host_id')
        if not bmhostid:
            LOG.debug("BmgwPlugin,_handle_port_update: binding:hostid is None, return.")
            return
        LOG.info(f"BmgwPlugin,_handle_port_update: port pre attached host is {bmhostid}")

        # Check if network type is VXLAN
        network_id = port.get('network_id')
        if not network_id:
            LOG.debug("BmgwPlugin,_handle_port_update:[no network_id]")
            return

        if port.get('binding:vif_type') not in portbindings.VIF_UNPLUGGED_TYPES:
            LOG.debug("BmgwPlugin,_handle_port_update: port is BOUND already, return.")
            return

        try:
            plugin = directory.get_plugin()
            admin_context = context.get_admin_context()

            bmagents = plugin.get_agents(admin_context, filters={'alive': [True], 'host': [bmhostid], 'agent_type': ['Baremetal Node']})
            if not bmagents or len(bmagents) == 0:
                LOG.debug(f"BmgwPlugin,_handle_port_update: port pre attached host {bmhostid} is not a baremetal node, return.")
                return

            network = plugin.get_network(admin_context, network_id)
            network_type = network.get('provider:network_type')
            if network_type != constants.TYPE_VXLAN:
                LOG.debug("BmgwPlugin,_handle_port_update: network type is not VXLAN, type={network_type}, return.")
                return
            
            LOG.info(f"BmgwPlugin,_handle_port_update, Processing baremetal port update for port {port_id}")
            # Schedule port to a BMGW agent
            host = self.schedule_port_to_bmgw(admin_context, port)
            if not host:
                LOG.error(f"Failed to schedule port {port_id} to any BMGW agent")
                return
            
            LOG.info(f"BmgwPlugin,_handle_port_update, port {port_id} scheduled to BMGW agent {host}")
            # Update port binding with OVS info and host ID
            port_binding = {
                # 'binding:vif_type': portbindings.VIF_TYPE_OVS,
                # 'binding:vif_details': {
                #     portbindings.CAP_PORT_FILTER: True,
                #     portbindings.OVS_HYBRID_PLUG: True
                # },
                'binding:host_id': host
            }
            
            # Update port binding
            plugin.update_port(admin_context,
                             port_id,
                             {'port': port_binding})
            LOG.debug(f"BmgwPlugin,_handle_port_update,Updated port {port_id} binding:host_id to OVS BMGW agent {host}")

            #target = Target(topic=messaging.TOPIC_BM_GW_RESOURCE, version='1.0', host=host)
            #self.agent_rpc.bmgw_port_created_to_agent(context, port, host)
        except Exception as e:
            LOG.error(f"Failed to process port {port_id}: {e}")

    def get_bmgw_ovs_agents(self, context, active=None, admin_up=None, host=None):
        """Get OVS agents that support bare metal gateway functionality.

        :param context: request context
        :param active: Filter by active status when True or False
        :param up: Filter by alive status when True or False
        :param host: Filter by host
        :returns: List of OVS agent dictionaries
        """
        # Get core plugin to access agent functionality
        core_plugin = directory.get_plugin()
        if not core_plugin:
            LOG.error("Core plugin not initialized")
            return []

        filters = {
            'agent_type': [constants.AGENT_TYPE_OVS],
            'alive': [True]
        }
        if admin_up is not None:
            filters['admin_state_up'] = [admin_up]
        if host:
            filters['host'] = [host]

        agents = core_plugin.get_agents(context, filters=filters)
        LOG.info(f"BmgwPlugin,get_bmgw_ovs_agents,Found {len(agents)} OVS agents")
        # Filter agents with bm_gw configuration
        agents = [
            agent for agent in agents
            if agent.get('configurations', {}).get('bm_gw') is True 
            # and agent['alive'] == active
        ]
        LOG.info(f"BmgwPlugin,get_bmgw_ovs_agents,Found {len(agents)} OVS agents with bm_gw")
        # Filter by alive status if requested
        # if up is not None:
        #     curr_time = timeutils.utcnow(with_timezone=True)
        #     agents = [
        #         agent for agent in agents
        #         if agent['alive'] == up
        #         and agent['heartbeat_timestamp']
        #         and (curr_time - agent['heartbeat_timestamp']).total_seconds()
        #         <= constants.AGENT_ALIVE_TIMEOUT
        #     ]

        return agents

    def schedule_port_to_bmgw(self, context, port):
        """Schedule a port to a bare metal gateway agent.

        This method uses random selection to choose a suitable BMGW agent.
        It considers only active and alive agents.

        :param context: request context
        :param port: The port dict to schedule
        :returns: Tuple of 'host' of the selected agent or 
                'None' if no suitable agent found
        """
        port_id = port.get('id')
        if not port_id:
            LOG.error("Invalid port: no port ID found")
            return None

        # Get all active and alive BMGW agents
        agents = self.get_bmgw_ovs_agents(context, active=True, admin_up=True)
        if not agents:
            LOG.error(f"No available BMGW agents found for port {port_id}")
            return None

        # check port --tags to select agent host
        # read the --tags value 'bm_gw_host=<host>'
        tags = self.get_port_tags(context, port_id)
        LOG.debug(f"BmgwPlugin,schedule_port_to_bmgw,port {port_id} --tags {tags}")
        tags = [tag for tag in tags if tag.startswith('bm_gw_host=')]
        if tags:
            bm_gw_host = tags[0].split('=')[1]
            LOG.debug(f"BmgwPlugin,schedule_port_to_bmgw,port {port_id} --tags[bm_gw_host={bm_gw_host}]")
            if bm_gw_host:
                agents = [agent for agent in agents if agent['host'] == bm_gw_host]
                if not agents:
                    LOG.debug(f"BmgwPlugin,schedule_port_to_bmgw, No available BMGW agents found for port {port_id} in --tags[bm_gw_host={bm_gw_host}], use random choice.")
                else:
                    LOG.debug(f"BmgwPlugin,schedule_port_to_bmgw, Read configuration from port {port_id} in --tags[bm_gw_host={bm_gw_host}]")

        # Randomly select an agent for simple load balancing
        # if port's --tag bm_gw_host=<host> is set, the agents shoud be only one item, so random will return the only one.
        selected_agent = random.choice(agents)
        host = selected_agent['host']
        
        LOG.info(f"BmgwPlugin,schedule_port_to_bmgw,Selected BMGW agent {host} for port {port_id}")

        return host

    def get_plugin_type(self):
        """Get the plugin type string."""
        return 'bm_gw'

    def get_plugin_description(self):
        """Get the plugin description string."""
        return 'Plugin for managing Bare Metal Gateway'

    # def get_port_scheduling_info(self, port_id):
    #     """Get scheduling information for a port.

    #     :param port_id: ID of the port to query
    #     :returns: Dict containing host_id and timestamp if port was scheduled,
    #              None otherwise
    #     """
    #     return 0 #self._scheduled_ports.get(port_id)

    def _setup_rpc(self):
        """Initialize RPC communication."""
        from oslo_config import cfg
        from oslo_messaging import get_rpc_transport
        self.server_rpc = rpc_server.BmgwSkeleton()
        self.agent_rpc = rpc_server.BmgwStub()
        transport = get_rpc_transport(cfg.CONF)
        # 推荐用统一的topic常量
        try:
            from neutron.services.bm_gw.rpc import topics
            topic_name = topics.BM_GW_RESOURCE
        except ImportError:
            topic_name = 'bm_gw'
        target = Target(topic=topic_name, version='1.0')
        self.client = RPCClient(transport, target)

    def get_port_tags(self, context, port_id):
        #tag_plugin = directory.get_plugin('standard-attr-tag')
        if self.tag_plugin_instance:
            LOG.debug(f"BmgwPlugin,get_port_tags,get_tags for port {port_id}")
            tags_dict = self.tag_plugin_instance.get_tags(context, resources.PORTS, port_id)
            LOG.debug(f"BmgwPlugin,get_port_tags,get_tags for port {port_id}, tags_dict={tags_dict}")
            return tags_dict.get('tags', [])
        LOG.debug("BmgwPlugin, get_port_tags, tag_plugin not initialized successfully.")
        return []

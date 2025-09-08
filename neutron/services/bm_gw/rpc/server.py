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

from neutron_lib import rpc as n_rpc
from oslo_log import helpers as log_helpers
from oslo_log import log as logging
import oslo_messaging

from neutron.api.rpc.callbacks import events
from neutron.api.rpc.callbacks.producer import registry
from neutron.api.rpc.callbacks import resources
from neutron.api.rpc.handlers import resources_rpc
from neutron.services.bm_gw.rpc import constants

LOG = logging.getLogger(__name__)

def tunnel_by_port_provider(resource, port_id, context, **kwargs):
    """Provider callback to supply tunnel information by port."""
    # Add implementation to lookup tunnel info by port
    pass

class BmgwSkeleton(object):
    """Skeleton proxy code for agent->server communication."""

    target = oslo_messaging.Target(version='1.0',
                                 namespace=constants.BM_GW_BASE_NAMESPACE)

    def __init__(self):
        """Initialize RPC server."""
        registry.provide(tunnel_by_port_provider, resources.PORT)
        self._connection = n_rpc.Connection()
        self._connection.create_consumer(
            constants.BM_GW_BASE_TOPIC, [self], fanout=False)
        self._rpc_servers = self._connection.consume_in_threads()
        LOG.debug("RPC server initialized for BM Gateway plugin")

    @property
    def rpc_servers(self):
        return self._rpc_servers

    @log_helpers.log_method_call
    def update_tunnel_status(self, context, tunnel_id, status):
        """Update tunnel status from agent."""
        # Add implementation to update tunnel status
        pass

    @log_helpers.log_method_call
    def update_port_binding(self, context, port_id, host):
        """Update port binding from agent."""
        # Add implementation to update port binding
        pass

class BmgwStub(object):
    """Stub proxy code for server->agent communication."""

    def __init__(self):
        self._resource_rpc = resources_rpc.ResourcesPushRpcApi()

    @log_helpers.log_method_call
    def bmgw_port_created(self, context, bmgwport):
        """Tell agent about bmgw port being created."""
        self._resource_rpc.push(context, [bmgwport], events.CREATED)

    def bmgw_port_created_to_agent(self, context, bmgwport, host):
        """只通知指定host的agent去创建port"""
        from neutron.services.bm_gw.rpc import topics as bmgw_topics

        topic = bmgw_topics.resource_type_versioned_topic('bm_gw', host=host)
        self._resource_rpc.push(context, [bmgwport], events.CREATED)


    @log_helpers.log_method_call
    def bmgw_port_deleted(self, context, bmgwport):
        """Tell agent about bmgw port being deleted."""
        self._resource_rpc.push(context, [bmgwport], events.DELETED)

    @log_helpers.log_method_call
    def bmgw_port_updated(self, context, bmgwport):
        """Tell agent about bmgw port being updated."""
        self._resource_rpc.push(context, [bmgwport], events.UPDATED)

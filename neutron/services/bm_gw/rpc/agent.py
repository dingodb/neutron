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
import oslo_messaging

from neutron.api.rpc.callbacks.consumer import registry
from neutron.api.rpc.callbacks import resources
from neutron.api.rpc.handlers import resources_rpc
from neutron.services.bm_gw.rpc import constants
from oslo_log import log as logging

LOG = logging.getLogger(__name__)

class BmGwSkeleton(object):
    """Skeleton proxy code for server->agent communication."""

    def __init__(self, driver):
        """Initialize RPC consumer."""

        self.driver = driver
        registry.register(self.driver.bmgw_port_update, resources.PORT)
        
    def unregister(self):
        return

class BmGwStub(object):
    """Stub proxy code for agent->server communication."""

    VERSION = '1.0'

    def __init__(self):
        """Initialize RPC client."""
        self.stub = resources_rpc.ResourcesPullRpcApi()
        target = oslo_messaging.Target(
            topic=constants.BM_GW_BASE_TOPIC,
            version=self.VERSION,
            namespace=constants.BM_GW_BASE_NAMESPACE)
        self.rpc_client = n_rpc.get_client(target)

    @log_helpers.log_method_call
    def get_tunnel_details(self, context, port_id):
        """Get tunnel information for the given port."""
        cctxt = self.rpc_client.prepare()
        return cctxt.call(context, 'get_tunnel_details',
                         port_id=port_id)

    @log_helpers.log_method_call
    def update_tunnel_status(self, context, tunnel_id, status):
        """Update tunnel status."""
        cctxt = self.rpc_client.prepare()
        return cctxt.call(context, 'update_tunnel_status',
                         tunnel_id=tunnel_id, status=status)

    @log_helpers.log_method_call
    def update_port_binding(self, context, port_id, host):
        """Update port binding."""
        cctxt = self.rpc_client.prepare()
        return cctxt.call(context, 'update_port_binding',
                         port_id=port_id, host=host)

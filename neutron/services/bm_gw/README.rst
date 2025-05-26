Bare Metal Gateway Service Plugin
============================

Last Updated: 2025-05-26

This service plugin provides functionality for managing bare metal gateway connectivity in OpenStack Neutron, specifically support VXLAN network for bare metal nodes.

A bare metal gateway is a device or software component that facilitates communication between virtual networks and physical networks, typically for bare metal servers. It enables the management and orchestration of bare metal resources within an OpenStack cloud environment.

The service plugin manages the lifecycle of bare metal gateways, including their creation, deletion, and configuration. It also handles the assignment of ports to specific gateways, ensuring efficient and reliable network connectivity.

## Functionality
- Support VXLAN network for bare metal nodes
- Support security-group for bare metal nodes
- Support trunk port for bare metal nodes
- BMGW High Availability

Features
--------
* Port Scheduling
    - Schedules ports to available BMGW agents
    - Handles agent failover and port rescheduling
    - Maintains scheduling state cache

* Agent Management
    - Subscribes to agent update events
    - Rescheduling bmgw ports when agent goes down

* Port Management
    - Subscribes to port update events
    - Manages OVS bridge configuration
    - Integrates with OpenVSwitch for network connectivity

* Agent Integration
    - Integrates with Neutron OVS agent as an extension
    - Provides bridge management capabilities
    - Handles OpenFlow protocol configuration

Components
----------
1. Plugin (plugin.py)
    - BmGwPlugin: Core plugin implementation
    - Handles port scheduling and agent monitoring
    - Manages service state and RPC communication

2. Agent Extension (agent/l2/extensions/bm_gw.py)
    - BmGwAgentExtension: OVS agent extension
    - Manages OVS bridge configuration
    - Handles port updates and tunnel events

3. Drivers (drivers/openvswitch/agent/)
    - BmGwDriver: Handles port operations in OVS agent
    - Manages br_bmgw bridge and port bindings
    - Implements OpenFlow rules for traffic steering

4. RPC Layer (rpc/)
    - Server-side RPC implementation (server.py)
    - Agent-side RPC implementation (agent.py)
    - Bidirectional communication between plugin and agent

Configuration
------------
1. Enable the service plugin in neutron.conf::

    [service_plugins]
    bm_gw = neutron.services.bm_gw.plugin.BmGwPlugin

2. Enable the agent extension in openvswitch_agent.ini::

    [agent]
    extensions = bm_gw
    bm_gw = True
    bm_gw_brname = br-bmgw

3. Pre-deployment Requirements:
    - Create br-bmgw bridge using deployment tools
    - Add physical NIC to br-bmgw bridge for baremetal access
    - Configure OpenFlow protocol version 1.3

4. Restart the neutron-server and neutron-openvswitch-agent services.

RPC Communication
---------------
The plugin and agent communicate through RPC for:
* Port scheduling and binding updates
* Tunnel status updates
* Bridge management operations
* Event notifications

The RPC layer provides both synchronous and asynchronous communication patterns.

Bridge Management
---------------
The bare metal gateway requires:
* Pre-created OVS bridge (br-bmgw) for baremetal traffic
* Physical NIC configuration in the bridge
* OpenFlow 1.3 protocol support
* Proper fail-mode and controller settings

Development
----------
To extend or modify this service:
1. Plugin customization: Extend BmGwPlugin for new features
2. Agent extension: Modify BmGwAgentExtension for new OVS capabilities
3. Driver modifications: Update BmGwDriver for new port operations
4. RPC additions: Add methods to RPC classes for new operations

Troubleshooting
--------------
Common issues and solutions:

1. Bridge Creation Failures
   * Verify br-bmgw exists: `ovs-vsctl show`
   * Check physical NIC connection
   * Ensure OpenFlow version compatibility

2. RPC Communication Issues
   * Verify message broker (RabbitMQ) status
   * Check neutron-server logs
   * Ensure agent is properly registered

3. Port Binding Problems
   * Verify port scheduling status
   * Check agent availability
   * Examine port binding details

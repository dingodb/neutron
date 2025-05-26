Bare Metal Gateway Service Plugin
============================

Last Updated: 2025-04-11

This service plugin provides functionality for managing bare metal gateway connectivity in OpenStack Neutron,
specifically handling tunnel management and port updates for bare metal nodes.

For detailed documentation, see:
* `Neutron Documentation <https://docs.openstack.org/neutron/latest/>`_
* `OpenStack Bare Metal Documentation <https://docs.openstack.org/ironic/latest/>`_

Features
--------
* Tunnel Management
    - Subscribes to tunnel deletion events
    - Manages tunnel lifecycle
    - Provides RPC communication for tunnel status updates

* Port Management
    - Subscribes to port update events
    - Manages OVS bridge creation and configuration
    - Integrates with OpenVSwitch for network connectivity

* Agent Integration
    - Integrates with Neutron OVS agent as an extension
    - Provides bridge management capabilities
    - Handles OpenFlow protocol configuration

Components
----------
1. Plugin (plugin.py)
    - BmGwPlugin: Core plugin implementation
    - Handles tunnel and port events
    - Manages service state and RPC communication

2. Agent Extension (agent/l2/extensions/bm_gw.py)
    - BmGwAgentExtension: OVS agent extension
    - Creates and manages OVS bridges
    - Handles port updates and tunnel events

3. RPC Layer (rpc/)
    - Server-side RPC implementation (server.py)
    - Agent-side RPC implementation (agent.py)
    - Bidirectional communication between plugin and agent

Configuration
------------
1. Enable the service plugin in neutron.conf::

    [service_providers]
    service_provider = BMGW:bm_gw:neutron.services.bm_gw.plugin.BmGwPlugin:default

2. Enable the agent extension in openvswitch_agent.ini::

    [agent]
    extensions = bm_gw

3. Restart the neutron-server and neutron-openvswitch-agent services.

RPC Communication
---------------
The plugin and agent communicate through RPC for:
* Tunnel status updates
* Port binding updates
* Bridge management operations
* Event notifications

The RPC layer provides both synchronous and asynchronous communication patterns.

Bridge Management
---------------
The agent extension automatically:
* Creates OVS bridges for networks when needed
* Configures OpenFlow 1.3 protocol
* Sets up bridge controllers
* Manages fail-mode and other bridge settings

Development
----------
To extend or modify this service:
1. Plugin customization: Extend BmGwPlugin for new features
2. Agent extension: Modify BmGwAgentExtension for new OVS capabilities
3. RPC additions: Add methods to RPC classes for new operations

Troubleshooting
--------------
Common issues and solutions:

1. Bridge Creation Failures
   * Verify OVS is running: ``systemctl status openvswitch``
   * Check OVS logs: ``journalctl -u openvswitch``
   * Ensure correct permissions for OVS operations

2. RPC Communication Issues
   * Verify message broker (RabbitMQ) status
   * Check neutron-server logs
   * Ensure agent is properly registered

3. Port Binding Problems
   * Verify port status in neutron database
   * Check agent logs for binding errors
   * Ensure network connectivity between components

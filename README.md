# Virtual Scenario Deployment

## Overview
This project automates the creation and management of a virtual network scenario using KVM virtual machines and Open vSwitch.

The scenario includes:
- **1 client** (`c1`)
- **1 load balancer / router** (`lb`)
- **N web servers** (`s1` ... `sN`)

The number of servers is configurable in `auto-p2.json`.

## Project Structure
- `auto-p2.py` -> Main automation script
- `auto-p2.json` -> Configuration file
- `lib_vm.py` -> Helper library for VM and virtual network management

## Features
- Creates and destroys virtual networks with Open vSwitch
- Defines virtual machines from a base QCOW2 image and XML template
- Configures static networking automatically
- Enables IP forwarding on the load balancer
- Starts, stops, and undefines the full scenario
- Supports debug logging

## Network Topology
The lab is divided into two networks:

- **LAN1 / RED1**: client-side network
- **LAN2 / RED2**: server-side network

### Addressing
**RED1 - 192.168.1.0/26**
- `c1` -> `192.168.1.11`
- `lb (eth0)` -> `192.168.1.1`

**RED2 - 192.168.1.64/26**
- `lb (eth1)` -> `192.168.1.65`
- `s1` -> `192.168.1.101`
- `s2` -> `192.168.1.102`
- ...

## Requirements
Before running the script, make sure the following files are available:
- `cdps-vm-base-pc1.qcow2`
- `plantilla-vm-pc1.xml`

You also need a Linux environment with:
- `qemu-img`
- `virsh`
- `virt-customize`
- `virt-edit`
- `ovs-vsctl`
- `xterm`

## Configuration
Edit `auto-p2.json` to define:
- `num_servers`: number of servers to deploy (between 1 and 5)
- `debug`: enable or disable debug logs

Example:
```json
{
  "num_servers": 2,
  "debug": true
}

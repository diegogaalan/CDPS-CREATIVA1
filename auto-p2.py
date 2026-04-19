#!/usr/bin/env python3

import json
import logging
import sys
import os
import subprocess
from lib_vm import VM, NET

# Nombre del logger (coincide con lib_vm.py)
LOG_NAME = "auto-p2"
log = logging.getLogger(LOG_NAME)

# Parámetros del escenario (ajusta si tus profes te dan otros)
BASE_IMAGE = "cdps-vm-base-pc1.qcow2"
TEMPLATE_XML = "plantilla-vm-pc1.xml"

LAN1_NAME = "LAN1"  # RED1
LAN2_NAME = "LAN2"  # RED2

# Plan de direccionamiento (según la figura típica del enunciado)
# RED1: 192.168.1.0/26
C1_IP = "192.168.1.11"
C1_MASK = "255.255.255.192"
LB_LAN1_IP = "192.168.1.1"
LB_LAN1_MASK = "255.255.255.192"

# RED2: 192.168.1.64/26
LB_LAN2_IP = "192.168.1.65"
LB_LAN2_MASK = "255.255.255.192"
SERVER_NET = "192.168.1."
SERVER_FIRST_IP = 101  # s1 = .101, s2 = .102, ...


def init_log(debug: bool) -> None:
    """Inicializa el sistema de logging."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    global log
    log = logging.getLogger(LOG_NAME)


def load_config(config_file: str = "auto-p2.json") -> tuple[int, bool]:
    """Carga auto-p2.json y devuelve (num_servers, debug)."""
    try:
        with open(config_file) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: No se encontró el archivo de configuración {config_file}")
        sys.exit(1)

    num_servers = cfg.get("num_servers")
    debug = bool(cfg.get("debug", False))

    if not isinstance(num_servers, int) or not (1 <= num_servers <= 5):
        print("ERROR: 'num_servers' debe ser un entero entre 1 y 5 en auto-p2.json")
        sys.exit(1)

    return num_servers, debug


def check_required_files() -> None:
    """Comprueba que existen la imagen base y la plantilla XML."""
    missing = []
    if not os.path.exists(BASE_IMAGE):
        missing.append(BASE_IMAGE)
    if not os.path.exists(TEMPLATE_XML):
        missing.append(TEMPLATE_XML)

    if missing:
        for f in missing:
            log.error(f"Falta el fichero requerido: {f}")
        sys.exit(1)


def prepare_env() -> None:
    """Ejecuta el script de preparación del laboratorio."""
    try:
        subprocess.run(
            ["/lab/cnvr/bin/prepare-vnx-debian"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        log.info("Entorno preparado correctamente (/lab/cnvr/bin/prepare-vnx-debian).")
    except FileNotFoundError:
        log.error("No se encontró /lab/cnvr/bin/prepare-vnx-debian.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        log.error(f"Error preparando el entorno: {e.stderr}")
        sys.exit(1)


def create_networks() -> None:
    """Crea las redes LAN1 y LAN2 con Open vSwitch."""
    lan1 = NET(LAN1_NAME)
    lan2 = NET(LAN2_NAME)
    lan1.create_net()
    lan2.create_net()


def destroy_networks() -> None:
    """Elimina las redes LAN1 y LAN2."""
    lan1 = NET(LAN1_NAME)
    lan2 = NET(LAN2_NAME)
    lan1.destroy_net()
    lan2.destroy_net()


def create_servers(num_servers: int) -> None:
    """Define y configura los servidores web s1..sN."""
    for i in range(1, num_servers + 1):
        name = f"s{i}"
        vm = VM(name)

        vm.define_vm(
            base_image=BASE_IMAGE,
            template_xml=TEMPLATE_XML,
            lan1_bridge=LAN1_NAME,
            lan2_bridge=LAN2_NAME,
        )

        ip = f"{SERVER_NET}{SERVER_FIRST_IP + i - 1}"
        iface_cfg = [
            {
                "name": "eth0",
                "address": ip,
                "netmask": LB_LAN2_MASK,
                "gateway": LB_LAN2_IP,
            }
        ]
        vm.configure_network(iface_cfg)
        log.info(f"Servidor {name} definido y configurado (IP {ip}).")


def create_client() -> None:
    """Define y configura el cliente c1 (en RED1)."""
    vm = VM("c1")
    vm.define_vm(
        base_image=BASE_IMAGE,
        template_xml=TEMPLATE_XML,
        lan1_bridge=LAN1_NAME,
        lan2_bridge=LAN2_NAME,
    )

    iface_cfg = [
        {
            "name": "eth0",
            "address": C1_IP,
            "netmask": C1_MASK,
            "gateway": LB_LAN1_IP,
        }
    ]
    vm.configure_network(iface_cfg)
    log.info(f"Cliente c1 definido y configurado (IP {C1_IP}).")


def create_load_balancer() -> None:
    """Define y configura el balanceador lb como router (dos interfaces)."""
    vm = VM("lb")
    vm.define_vm(
        base_image=BASE_IMAGE,
        template_xml=TEMPLATE_XML,
        lan1_bridge=LAN1_NAME,
        lan2_bridge=LAN2_NAME,
    )

    iface_cfg = [
        {
            "name": "eth0",  # RED1
            "address": LB_LAN1_IP,
            "netmask": LB_LAN1_MASK,
            # sin gateway; actúa como router
        },
        {
            "name": "eth1",  # RED2
            "address": LB_LAN2_IP,
            "netmask": LB_LAN2_MASK,
        },
    ]
    vm.configure_network(iface_cfg, enable_ip_forward=True)
    log.info("Balanceador lb definido, configurado y habilitado como router.")


def define_scenario(num_servers: int) -> None:
    """Crea redes, define VMs y configura su red."""
    check_required_files()
    prepare_env()
    create_networks()
    create_servers(num_servers)
    create_client()
    create_load_balancer()
    log.info("Escenario definido correctamente.")


def start_scenario(num_servers: int) -> None:
    """Arranca todas las VMs del escenario y muestra su consola."""
    # Arrancamos primero el router
    lb = VM("lb")
    lb.start_vm()

    # Luego servidores
    for i in range(1, num_servers + 1):
        VM(f"s{i}").start_vm()

    # Finalmente el cliente
    VM("c1").start_vm()
    log.info("Todas las VMs han sido arrancadas.")


def stop_scenario(num_servers: int) -> None:
    """Detiene todas las VMs del escenario (shutdown limpio)."""
    # Cliente primero
    VM("c1").stop_vm()

    # Servidores
    for i in range(1, num_servers + 1):
        VM(f"s{i}").stop_vm()

    # Router al final
    VM("lb").stop_vm()
    log.info("Todas las VMs han sido detenidas.")


def undefine_scenario(num_servers: int) -> None:
    """Libera el escenario: VMs + redes."""
    # VMs
    VM("c1").undefine_vm()

    for i in range(1, num_servers + 1):
        VM(f"s{i}").undefine_vm()

    VM("lb").undefine_vm()

    # Redes
    destroy_networks()
    log.info("Escenario liberado completamente (undefine).")


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: auto-p2.py <orden>")
        print("Orden puede ser: define, start, stop, undefine")
        sys.exit(1)

    order = sys.argv[1]
    num_servers, debug = load_config()
    init_log(debug)

    if order == "define":
        define_scenario(num_servers)
    elif order == "start":
        start_scenario(num_servers)
    elif order == "stop":
        stop_scenario(num_servers)
    elif order == "undefine":
        undefine_scenario(num_servers)
    else:
        print("Orden no válida. Órdenes conocidas: define, start, stop, undefine")
        log.error(f"Orden desconocida: {order}")
        sys.exit(1)


if __name__ == "__main__":
    main()

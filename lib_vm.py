import logging
import os
import subprocess
from lxml import etree

log = logging.getLogger("auto-p2")


class VM:
    """Gestión de una máquina virtual KVM usando virsh y virt-tools."""

    def __init__(self, name: str):
        self.name = name
        log.debug(f"Inicializada VM: {self.name}")

    # -------------------------
    # Definición de la VM
    # -------------------------
    def define_vm(
        self,
        base_image: str,
        template_xml: str,
        lan1_bridge: str,
        lan2_bridge: str,
    ) -> None:
        """
        Crea la imagen qcow2 (diferencias) a partir de base_image,
        personaliza el XML de la plantilla y define la VM con virsh.
        """
        qcow2_path = f"{self.name}.qcow2"
        xml_path = f"{self.name}.xml"

        # 1. Crear imagen de diferencias
        subprocess.run(
            [
                "qemu-img",
                "create",
                "-F",
                "qcow2",
                "-f",
                "qcow2",
                "-b",
                base_image,
                qcow2_path,
            ],
            check=True,
        )
        log.info(f"Imagen QCOW2 creada para {self.name}: {qcow2_path}")

        # 2. Personalizar XML
        tree = etree.parse(template_xml)
        root = tree.getroot()

        # Nombre de la VM
        name_node = root.find("name")
        if name_node is not None:
            name_node.text = self.name

        # Disco
        source_disk = root.find("./devices/disk/source")
        if source_disk is not None:
            source_disk.set("file", os.path.abspath(qcow2_path))

        devices = root.find("devices")
        if devices is None:
            devices = etree.SubElement(root, "devices")

        # Interfaces de red
        # - c1: solo LAN1
        # - sX: solo LAN2
        # - lb: LAN1 + LAN2
        if self.name == "lb":
            # Primera interfaz (LAN1)
            iface1 = devices.find("interface")
            if iface1 is None:
                iface1 = etree.SubElement(devices, "interface", type="bridge")
            src1 = iface1.find("source")
            if src1 is None:
                src1 = etree.SubElement(iface1, "source")
            src1.set("bridge", lan1_bridge)
            self._ensure_interface_defaults(iface1)

            # Segunda interfaz (LAN2)
            iface2 = etree.SubElement(devices, "interface", type="bridge")
            etree.SubElement(iface2, "source", bridge=lan2_bridge)
            self._ensure_interface_defaults(iface2)
        else:
            iface = devices.find("interface")
            if iface is None:
                iface = etree.SubElement(devices, "interface", type="bridge")
            src = iface.find("source")
            if src is None:
                src = etree.SubElement(iface, "source")

            if self.name.startswith("s"):
                src.set("bridge", lan2_bridge)  # servidores en LAN2
            else:
                src.set("bridge", lan1_bridge)  # c1 en LAN1

            self._ensure_interface_defaults(iface)

        tree.write(xml_path)
        log.debug(f"XML generado para {self.name}: {xml_path}")

        # 3. Definir VM
        subprocess.run(["sudo", "virsh", "define", xml_path], check=True)
        log.info(f"VM {self.name} definida con virsh.")

    def _ensure_interface_defaults(self, iface) -> None:
        """Añade modelo virtio y virtualport openvswitch si no existen."""
        model = iface.find("model")
        if model is None:
            model = etree.SubElement(iface, "model")
        model.set("type", "virtio")

        vport = iface.find("virtualport")
        if vport is None:
            vport = etree.SubElement(iface, "virtualport")
        vport.set("type", "openvswitch")

    # -------------------------
    # Configuración de red
    # -------------------------
    def configure_network(
        self,
        interfaces: list[dict],
        enable_ip_forward: bool = False,
    ) -> None:
        """
        Configura hostname y /etc/network/interfaces usando virt-customize.

        interfaces: lista de diccionarios con:
        {
            "name": "eth0",
            "address": "192.168.1.X",
            "netmask": "255.255.255.192",
            "gateway": "192.168.1.Y" (opcional)
        }
        """
        image = f"{self.name}.qcow2"

        # Hostname
        subprocess.run(
            ["sudo", "virt-customize", "-a", image, "--hostname", self.name],
            check=True,
        )
        log.debug(f"Hostname configurado en {self.name}.")

        # /etc/network/interfaces: lo generamos línea a línea con virt-customize
        commands = [
            "echo 'auto lo' > /etc/network/interfaces",
            "echo 'iface lo inet loopback' >> /etc/network/interfaces",
        ]

        for iface in interfaces:
            name = iface["name"]
            addr = iface["address"]
            mask = iface["netmask"]
            gw = iface.get("gateway")

            commands.append("echo '' >> /etc/network/interfaces")
            commands.append(f"echo 'auto {name}' >> /etc/network/interfaces")
            commands.append(f"echo 'iface {name} inet static' >> /etc/network/interfaces")
            commands.append(f"echo '    address {addr}' >> /etc/network/interfaces")
            commands.append(f"echo '    netmask {mask}' >> /etc/network/interfaces")
            if gw:
                commands.append(f"echo '    gateway {gw}' >> /etc/network/interfaces")

        for cmd in commands:
            subprocess.run(
                ["sudo", "virt-customize", "-a", image, "--run-command", cmd],
                check=True,
            )

        log.info(f"Red configurada para {self.name}.")

        # Habilitar reenvío de paquetes si es router
        if enable_ip_forward:
            subprocess.run(
                [
                    "sudo",
                    "virt-edit",
                    "-a",
                    image,
                    "/etc/sysctl.conf",
                    "-e",
                    "s/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/",
                ],
                check=False,
            )
            log.info(f"IP forwarding habilitado en {self.name}.")

    # -------------------------
    # Ciclo de vida
    # -------------------------
    def start_vm(self) -> None:
        subprocess.run(["sudo", "virsh", "start", self.name], check=False)
        log.info(f"VM {self.name} arrancada.")
        # Consola en xterm
        subprocess.Popen(["xterm", "-e", f"sudo virsh console {self.name}"])
        log.debug(f"Consola de {self.name} abierta en xterm.")

    def show_console_vm(self) -> None:
        subprocess.Popen(["xterm", "-e", f"sudo virsh console {self.name}"])
        log.debug(f"Consola de {self.name} solicitada.")

    def stop_vm(self) -> None:
        subprocess.run(["sudo", "virsh", "shutdown", self.name], check=False)
        log.info(f"VM {self.name} detenida (shutdown).")

    def undefine_vm(self) -> None:
        """
        Libera completamente la VM:
        - Apaga si sigue encendida.
        - Undefine en virsh.
        - Borra qcow2 y xml.
        """
        subprocess.run(["sudo", "virsh", "destroy", self.name], check=False)
        subprocess.run(["sudo", "virsh", "undefine", self.name], check=False)

        for path in (f"{self.name}.qcow2", f"{self.name}.xml"):
            if os.path.exists(path):
                os.remove(path)
                log.debug(f"Eliminado fichero {path} de la VM {self.name}.")

        log.info(f"VM {self.name} liberada (undefine + ficheros borrados).")


class NET:
    """Gestión de redes virtuales con Open vSwitch."""

    def __init__(self, name: str):
        self.name = name
        log.debug(f"Inicializada red: {self.name}")

    def create_net(self) -> None:
        subprocess.run(
            ["sudo", "ovs-vsctl", "add-br", self.name],
            check=False,
        )
        log.info(f"Bridge {self.name} creado con Open vSwitch.")

    def destroy_net(self) -> None:
        subprocess.run(
            ["sudo", "ovs-vsctl", "del-br", self.name],
            check=False,
        )
        log.info(f"Bridge {self.name} eliminado.")

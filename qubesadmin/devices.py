# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2015-2016  Wojtek Porczyk <woju@invisiblethingslab.com>
# Copyright (C) 2016       Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
# Copyright (C) 2017 Marek Marczykowski-Górecki
#                               <marmarek@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.

"""API for various types of devices.

Main concept is that some domain main
expose (potentially multiple) devices, which can be attached to other domains.
Devices can be of different classes (like 'pci', 'usb', etc.). Each device
class is implemented by an extension.

Devices are identified by pair of (backend domain, `ident`), where `ident` is
:py:class:`str`.
"""
import base64
import itertools
import sys
from enum import Enum
from typing import Optional, Dict, Any, List, Type, Iterable


# TODO:
# Proposed device events:
## - device-list-changed: device-added
## - device-list-changed: device-remove
# - device-property-changed: property_name
## - device-assignment-changed: created
## - device-assignment-changed: removed
## - device-assignment-changed: attached
## - device-assignment-changed: detached
# - device-assignment-changed: property-set [? this is not great]

class Device:
    def __init__(self, backend_domain, ident, devclass=None):
        self.__backend_domain = backend_domain
        self.__ident = ident
        self.__bus = devclass

    def __hash__(self):
        return hash((str(self.backend_domain), self.ident))

    def __eq__(self, other):
        return (
            self.backend_domain == other.backend_domain and
            self.ident == other.ident
        )

    def __lt__(self, other):
        if isinstance(other, Device):
            return (self.backend_domain, self.ident) < \
                   (other.backend_domain, other.ident)
        return NotImplemented

    def __repr__(self):
        return "[%s]:%s" % (self.backend_domain, self.ident)

    def __str__(self):
        return '{!s}:{!s}'.format(self.backend_domain, self.ident)

    @property
    def ident(self) -> str:
        """
        Immutable device identifier.

        Unique for given domain and device type.
        """
        return self.__ident

    @property
    def backend_domain(self) -> 'qubesadmin.vm.QubesVM':
        """ Which domain provides this device. (immutable)"""
        return self.__backend_domain

    @property
    def devclass(self) -> str:
        """ Immutable* Device class such like: 'usb', 'pci' etc.

        For unknown devices "peripheral" is returned.

        *see `@devclass.setter`
        """
        if self.__bus:
            return self.__bus
        else:
            return "peripheral"

    @property
    def devclass_is_set(self) -> bool:
        """
        Returns true if devclass is already initialised.
        """
        return bool(self.__bus)

    @devclass.setter
    def devclass(self, devclass: str):
        """ Once a value is set, it should not be overridden.

        However, if it has not been set, i.e., the value is `None`,
        we can override it."""
        if self.__bus != None:
            raise TypeError("Attribute devclass is immutable")
        self.__bus = devclass


class DeviceCategory(Enum):
    """
    Arbitrarily selected interfaces that are important to users,
    thus deserving special recognition such as a custom icon, etc.

    """
    Other = "*******"

    Communication = ("u02****", "p07****")  # eg. modems
    Input = ("u03****", "p09****")  # HID etc.
    Keyboard = ("u03**01", "p0900**")
    Mouse = ("u03**02", "p0902**")
    Printer = ("u07****",)
    Scanner = ("p0903**",)
    # Multimedia = Audio, Video, Displays etc.
    Multimedia = ("u01****", "u0e****", "u06****", "u10****", "p03****",
                  "p04****")
    Wireless = ("ue0****", "p0d****")
    Bluetooth = ("ue00101", "p0d11**")
    Mass_Data = ("b******", "u08****", "p01****")
    Network = ("p02****",)
    Memory = ("p05****",)
    PCI_Bridge = ("p06****",)
    Docking_Station = ("p0a****",)
    Processor = ("p0b****", "p40****")
    PCI_Serial_Bus = ("p0c****",)
    PCI_USB = ("p0c03**",)

    @staticmethod
    def from_str(interface_encoding: str) -> 'DeviceCategory':
        result = DeviceCategory.Other
        if len(interface_encoding) != len(DeviceCategory.Other.value):
            return result
        best_score = 0

        for interface in DeviceCategory:
            for pattern in interface.value:
                score = 0
                for t, p in zip(interface_encoding, pattern):
                    if t == p:
                        score += 1
                    elif p != "*":
                        score = -1  # inconsistent with pattern
                        break

                if score > best_score:
                    best_score = score
                    result = interface

        return result


class DeviceInterface:
    def __init__(self, interface_encoding: str, devclass: Optional[str] = None):
        ifc_padded = interface_encoding.ljust(6, '*')
        if devclass:
            if len(ifc_padded) > 6:
                print(
                    f"interface_encoding is too long "
                    f"(is {len(interface_encoding)}, expected max. 6) "
                    f"for given {devclass=}",
                    file=sys.stderr
                )
            ifc_full = devclass[0] + ifc_padded
        else:
            known_devclasses = {'p': 'pci', 'u': 'usb', 'b': 'block'}
            devclass = known_devclasses.get(interface_encoding[0], None)
            if len(ifc_padded) > 7:
                print(
                    f"interface_encoding is too long "
                    f"(is {len(interface_encoding)}, expected max. 7)",
                    file=sys.stderr
                )
                ifc_full = ifc_padded
            elif len(ifc_padded) == 6:
                ifc_full = ' ' + ifc_padded
            else:
                ifc_full = ifc_padded

        self._devclass = devclass
        self._interface_encoding = ifc_full
        self._category = DeviceCategory.from_str(self._interface_encoding)

    @property
    def devclass(self) -> Optional[str]:
        """ Immutable Device class such like: 'usb', 'pci' etc. """
        return self._devclass

    @property
    def category(self) -> DeviceCategory:
        """ Immutable Device category such like: 'Mouse', 'Mass_Data' etc. """
        return self._category

    @classmethod
    def unknown(cls) -> 'DeviceInterface':
        """ Value for unknown device interface. """
        return cls(" ******")

    @property
    def __repr__(self):
        return self._interface_encoding

    @property
    def __str__(self):
        if self.devclass == "block":
            return "Block device"
        if self.devclass in ("usb", "pci"):
            self._load_classes(self.devclass).get(
                self._interface_encoding[1:],
                f"Unclassified {self.devclass} device")
        return repr(self)

    @staticmethod
    def _load_classes(bus: str):
        """
        List of known device classes, subclasses and programming interfaces.
        """
        # Syntax:
        # C class       class_name
        #       subclass        subclass_name           <-- single tab
        #               prog-if  prog-if_name   <-- two tabs
        result = {}
        with open(f'/usr/share/hwdata/{bus}.ids',
                  encoding='utf-8', errors='ignore') as pciids:
            class_id = None
            subclass_id = None
            for line in pciids.readlines():
                line = line.rstrip()
                if line.startswith('\t\t') and class_id and subclass_id:
                    (progif_id, _, progif_name) = line[2:].split(' ', 2)
                    result[class_id + subclass_id + progif_id] = \
                        f"{class_name}: {subclass_name} ({progif_name})"
                elif line.startswith('\t') and class_id:
                    (subclass_id, _, subclass_name) = line[1:].split(' ', 2)
                    # store both prog-if specific entry and generic one
                    result[class_id + subclass_id + '**'] = \
                        f"{class_name}: {subclass_name}"
                elif line.startswith('C '):
                    (_, class_id, _, class_name) = line.split(' ', 3)
                    result[class_id + '****'] = class_name
                    subclass_id = None

        return result


class DeviceInfo(Device):
    """ Holds all information about a device """

    # pylint: disable=too-few-public-methods
    def __init__(
            self,
            backend_domain: 'qubes.vm.qubesvm.QubesVM',  # TODO
            ident: str,
            devclass: Optional[str] = None,
            vendor: Optional[str] = None,
            product: Optional[str] = None,
            manufacturer: Optional[str] = None,
            name: Optional[str] = None,
            serial: Optional[str] = None,
            interfaces: Optional[List[DeviceInterface]] = None,
            parent: Optional[Device] = None,
            **kwargs
    ):
        super().__init__(backend_domain, ident, devclass)

        self._vendor = vendor
        self._product = product
        self._manufacturer = manufacturer
        self._name = name
        self._serial = serial
        self._interfaces = interfaces
        self._parent = parent

        self.data = kwargs

    @property
    def vendor(self) -> str:
        """
        Device vendor name from local database.

        Could be empty string or "unknown".

        Override this method to return proper name from `/usr/share/hwdata/*`.
        """
        if not self._vendor:
            return "unknown"
        return self._vendor

    @property
    def product(self) -> str:
        """
        Device name from local database.

        Could be empty string or "unknown".

        Override this method to return proper name from `/usr/share/hwdata/*`.
        """
        if not self._product:
            return "unknown"
        return self._product

    @property
    def manufacturer(self) -> str:
        """
        The name of the manufacturer of the device introduced by device itself.

        Could be empty string or "unknown".

        Override this method to return proper name directly from device itself.
        """
        if not self._manufacturer:
            return "unknown"
        return self._manufacturer

    @property
    def name(self) -> str:
        """
        The name of the device it introduced itself with.

        Could be empty string or "unknown".

        Override this method to return proper name directly from device itself.
        """
        if not self._name:
            return "unknown"
        return self._name

    @property
    def serial(self) -> str:
        """
        The serial number of the device it introduced itself with.

        Could be empty string or "unknown".

        Override this method to return proper name directly from device itself.
        """
        if not self._serial:
            return "unknown"
        return self._serial

    @property
    def description(self) -> str:
        """
        Short human-readable description.

        For unknown device returns `unknown device (unknown vendor)`.
        For unknown USB device returns `unknown usb device (unknown vendor)`.
        For unknown USB device with known serial number returns
            `<serial> (unknown vendor)`.
        """
        if self.product and self.product != "unknown":
            prod = self.product
        elif self.name and self.name != "unknown":
            prod = self.name
        elif self.serial and self.serial != "unknown":
            prod = self.serial
        elif self.parent_device is not None:
            return f"sub-device of {self.parent_device}"
        else:
            prod = f"unknown {self.devclass if self.devclass else ''} device"

        if self.vendor and self.vendor != "unknown":
            vendor = self.vendor
        elif self.manufacturer and self.manufacturer != "unknown":
            vendor = self.manufacturer
        else:
            vendor = "unknown vendor"

        return f"{prod} ({vendor})"

    @property
    def interfaces(self) -> List[DeviceInterface]:
        """
        Non-empty list of device interfaces.

        Every device should have at least one interface.
        """
        if not self._interfaces:
            return [DeviceInterface.unknown()]
        return self._interfaces

    @property
    def parent_device(self) -> Optional[Device]:
        """
        The parent device if any.

        If the device is part of another device (e.g. it's a single
        partition of an usb stick), the parent device id should be here.
        """
        return self._parent

    @property
    def subdevices(self) -> List['DeviceInfo']:
        """
        The list of children devices if any.

        If the device has subdevices (e.g. partitions of an usb stick),
        the subdevices id should be here.
        """
        return [dev for dev in self.backend_domain.devices[self.devclass]
                if dev.parent_device.ident == self.ident]

    @property
    def attachments(self) -> List['DeviceAssignment']:
        """
        Device attachments
        """
        return []  # TODO

    def serialize(self) -> bytes:
        """
        Serialize object to be transmitted via Qubes API.
        """
        # 'backend_domain', 'interfaces', 'data', 'parent_device'
        # are not string, so they need special treatment
        default_attrs = {
            'ident', 'devclass', 'vendor', 'product', 'manufacturer', 'name',
            'serial'}
        properties = b' '.join(
            base64.b64encode(f'{prop}={value!s}'.encode('ascii'))
            for prop, value in (
                (key, getattr(self, key)) for key in default_attrs)
        )

        backend_domain_name = self.backend_domain.name
        backend_domain_prop = (b'backend_domain=' +
                               backend_domain_name.encode('ascii'))
        properties += b' ' + base64.b64encode(backend_domain_prop)

        interfaces = ''.join(repr(ifc) for ifc in self.interfaces)
        interfaces_prop = b'interfaces=' + str(interfaces).encode('ascii')
        properties += b' ' + base64.b64encode(interfaces_prop)

        if self.parent_device is not None:
            parent_prop = b'parent=' + self.parent_device.ident.encode('ascii')
            properties += b' ' + base64.b64encode(parent_prop)

        data = b' '.join(
            base64.b64encode(f'_{prop}={value!s}'.encode('ascii'))
            for prop, value in ((key, self.data[key]) for key in self.data)
        )
        if data:
            properties += b' ' + data

        return properties

    @classmethod
    def deserialize(
            cls,
            serialization: bytes,
            expected_backend_domain: 'qubes.vm.qubesvm.QubesVM',
            expected_devclass: Optional[str] = None,
    ) -> 'DeviceInfo':
        try:
            result = DeviceInfo._deserialize(
                cls, serialization, expected_backend_domain, expected_devclass)
        except Exception as exc:
            print(exc, file=sys.stderr)
            ident = serialization.split(b' ')[0].decode(
                'ascii', errors='ignore')
            result = UnknownDevice(
                backend_domain=expected_backend_domain,
                ident=ident,
                devclass=expected_devclass,
            )
        return result

    @staticmethod
    def _deserialize(
            cls: Type,
            serialization: bytes,
            expected_backend_domain: 'qubes.vm.qubesvm.QubesVM',
            expected_devclass: Optional[str] = None,
    ) -> 'DeviceInfo':
        properties_str = [
            base64.b64decode(line).decode('ascii', errors='ignore')
            for line in serialization.split(b' ')[1:]]

        properties = dict()
        for line in properties_str:
            key, _, param = line.partition("=")
            if key.startswith("_"):
                properties[key[1:]] = param
            else:
                properties[key] = param

        if properties['backend_domain'] != expected_backend_domain.name:
            raise ValueError("Unexpected device backend domain: "
                             f"{properties['backend_domain']} != "
                             f"{expected_backend_domain.name}")
        properties['backend_domain'] = expected_backend_domain
        if expected_devclass and properties['devclass'] != expected_devclass:
            raise ValueError("Unexpected device class: "
                             f"{properties['devclass']} != {expected_devclass}")

        interfaces = properties['interfaces']
        interfaces = [
            DeviceInterface(interfaces[i:i + 7])
            for i in range(0, len(interfaces), 7)]
        properties['interfaces'] = interfaces

        if 'parent' in properties:
            properties['parent'] = Device(
                backend_domain=expected_backend_domain,
                ident=properties['parent']
            )

        return cls(**properties)

    @property
    def frontend_domain(self):
        return self.data.get("frontend_domain", None)


class UnknownDevice(DeviceInfo):
    # pylint: disable=too-few-public-methods
    """Unknown device - for example exposed by domain not running currently"""

    def __init__(self, backend_domain, devclass, ident, **kwargs):
        super().__init__(backend_domain, ident, devclass=devclass, **kwargs)


class DeviceAssignment(Device):
    """ Maps a device to a frontend_domain. """

    def __init__(self, backend_domain, ident, options=None,
                 frontend_domain=None, devclass=None,
                 required=False, attach_automatically=False):
        super().__init__(backend_domain, ident, devclass)
        self.__options = options or {}
        self.__required = required
        self.__attach_automatically = attach_automatically
        self.__frontend_domain = frontend_domain

    def clone(self, **kwargs):
        """
        Clone object and substitute attributes with explicitly given.
        """
        attr = {
            "backend_domain": self.backend_domain,
            "ident": self.ident,
            "options": self.options,
            "required": self.required,
            "attach_automatically": self.attach_automatically,
            "frontend_domain": self.frontend_domain,
            "devclass": self.devclass,
        }
        attr.update(kwargs)
        return self.__class__(**attr)

    @property
    def device(self) -> DeviceInfo:
        """Get DeviceInfo object corresponding to this DeviceAssignment"""
        return self.backend_domain.devices[self.devclass][self.ident]

    @property
    def frontend_domain(self) -> Optional['qubesadmin.vm.QubesVM']:
        """ Which domain the device is attached to. """
        return self.__frontend_domain

    @frontend_domain.setter
    def frontend_domain(
            self, frontend_domain: Optional['qubesadmin.vm.QubesVM']
    ):
        """ Which domain the device is attached to. """
        self.__frontend_domain = frontend_domain

    @property
    def required(self) -> bool:
        """
        Is the presence of this device required for the domain to start? If yes,
        it will be attached automatically.
        """
        return self.__required

    @required.setter
    def required(self, required: bool):
        self.__required = required

    @property
    def attach_automatically(self) -> bool:
        """
        Should this device automatically connect to the frontend domain when
        available and not connected to other qubes?
        """
        return self.__attach_automatically

    @attach_automatically.setter
    def attach_automatically(self, attach_automatically: bool):
        self.__attach_automatically = attach_automatically

    @property
    def options(self) -> Dict[str, Any]:
        """ Device options (same as in the legacy API). """
        return self.__options

    @options.setter
    def options(self, options: Optional[Dict[str, Any]]):
        """ Device options (same as in the legacy API). """
        self.__options = options or {}


class DeviceCollection:
    """Bag for devices.

    Used as default value for :py:meth:`DeviceManager.__missing__` factory.

    :param vm: VM for which we manage devices
    :param class_: device class

    """

    def __init__(self, vm, class_):
        self._vm = vm
        self._class = class_
        self._dev_cache = {}

    def attach(self, device_assignment: DeviceAssignment) -> None:
        """
        Attach (add) device to domain.

        :param DeviceAssignment device_assignment: device object
        """

        if not device_assignment.frontend_domain:
            device_assignment.frontend_domain = self._vm
        else:
            assert device_assignment.frontend_domain == self._vm, \
                "Trying to attach DeviceAssignment belonging to other domain"
        if not device_assignment.devclass_is_set:
            device_assignment.devclass = self._class
        elif device_assignment.devclass != self._class:
            raise ValueError(
                f"Device assignment class does not match to expected: "
                f"{device_assignment.devclass=}!={self._class=}")

        options = device_assignment.options.copy()
        options_str = ' '.join('{}={}'.format(opt, val)
                               for opt, val in sorted(options.items()))
        self._vm.qubesd_call(None,
                             'admin.vm.device.{}.Attach'.format(self._class),
                             '{!s}+{!s}'.format(
                                 device_assignment.backend_domain,
                                 device_assignment.ident),
                             options_str.encode('utf-8'))

    def detach(self, device_assignment: DeviceAssignment) -> None:
        """
        Detach (remove) device from domain.

        :param DeviceAssignment device_assignment: device to detach
            (obtained from :py:meth:`assignments`)
        """
        if not device_assignment.frontend_domain:
            device_assignment.frontend_domain = self._vm
        else:
            assert device_assignment.frontend_domain == self._vm, \
                "Trying to detach DeviceAssignment belonging to other domain"
        if not device_assignment.devclass_is_set:
            device_assignment.devclass = self._class
        elif device_assignment.devclass != self._class:
            raise ValueError(
                f"Device assignment class does not match to expected: "
                f"{device_assignment.devclass=}!={self._class=}")

        self._vm.qubesd_call(None,
                             'admin.vm.device.{}.Detach'.format(self._class),
                             '{!s}+{!s}'.format(
                                 device_assignment.backend_domain,
                                 device_assignment.ident))

    def assign(self, device_assignment: DeviceAssignment) -> None:
        """
        Assign device to domain (add to :file:`qubes.xml`).

        :param DeviceAssignment device_assignment: device object
        """

        if not device_assignment.frontend_domain:
            device_assignment.frontend_domain = self._vm
        else:
            assert device_assignment.frontend_domain == self._vm, \
                "Trying to assign DeviceAssignment belonging to other domain"
        if not device_assignment.devclass_is_set:
            device_assignment.devclass = self._class
        elif device_assignment.devclass != self._class:
            raise ValueError(
                f"Device assignment class does not match to expected: "
                f"{device_assignment.devclass=}!={self._class=}")

        options = device_assignment.options.copy()
        if device_assignment.required:
            options['required'] = 'True'
        options_str = ' '.join('{}={}'.format(opt, val)
                               for opt, val in sorted(options.items()))
        self._vm.qubesd_call(None,
                             'admin.vm.device.{}.Assign'.format(self._class),
                             '{!s}+{!s}'.format(
                                 device_assignment.backend_domain,
                                 device_assignment.ident),
                             options_str.encode('utf-8'))

    def unassign(self, device_assignment: DeviceAssignment) -> None:
        """
        Unassign device from domain (remove from :file:`qubes.xml`).

        :param DeviceAssignment device_assignment: device to unassign
            (obtained from :py:meth:`assignments`)
        """
        if not device_assignment.frontend_domain:
            device_assignment.frontend_domain = self._vm
        else:
            assert device_assignment.frontend_domain == self._vm, \
                "Trying to unassign DeviceAssignment belonging to other domain"
        if not device_assignment.devclass_is_set:
            device_assignment.devclass = self._class
        elif device_assignment.devclass != self._class:
            raise ValueError(
                f"Device assignment class does not match to expected: "
                f"{device_assignment.devclass=}!={self._class=}")

        self._vm.qubesd_call(None,
                             'admin.vm.device.{}.Unassign'.format(self._class),
                             '{!s}+{!s}'.format(
                                 device_assignment.backend_domain,
                                 device_assignment.ident))

    def get_dedicated_devices(self) -> Iterable[DeviceAssignment]:
        """
        List devices which are attached or assigned to this vm.
        """
        dedicated = {dev for dev in itertools.chain(
            self.get_attached_devices(), self.get_assigned_devices())}
        for dev in dedicated:
            yield dev

    def get_attached_devices(self) -> Iterable[DeviceAssignment]:
        """
        List devices which are attached to this vm.
        """
        assignments_str = self._vm.qubesd_call(
            None, 'admin.vm.device.{}.Attached'.format(self._class)).decode()
        for assignment_str in assignments_str.splitlines():
            device, _, options_all = assignment_str.partition(' ')
            backend_domain, ident = device.split('+', 1)
            options = dict(opt_single.split('=', 1)
                           for opt_single in options_all.split(' ') if
                           opt_single)
            dev_required = (options.pop('required', False) in
                            ['True', 'yes', True])
            dev_auto_attach = (options.pop('attach_automatically', False) in
                               ['True', 'yes', True])
            backend_domain = self._vm.app.domains.get_blind(backend_domain)
            yield DeviceAssignment(backend_domain, ident, options,
                                   required=dev_required,
                                   attach_automatically=dev_auto_attach,
                                   frontend_domain=self._vm,
                                   devclass=self._class)

    def get_assigned_devices(
            self, required_only: bool = False
    ) -> Iterable[DeviceAssignment]:
        """
        Devices assigned to this vm (included in :file:`qubes.xml`).

        Safe to access before libvirt bootstrap.
        """
        assignments_str = self._vm.qubesd_call(
            None, 'admin.vm.device.{}.Assigned'.format(self._class)).decode()
        for assignment_str in assignments_str.splitlines():
            device, _, options_all = assignment_str.partition(' ')
            backend_domain, ident = device.split('+', 1)
            options = dict(opt_single.split('=', 1)
                           for opt_single in options_all.split(' ') if
                           opt_single)
            dev_required = (options.pop('required', False) in
                            ['True', 'yes', True])
            dev_auto_attach = (options.pop('attach_automatically', False) in
                               ['True', 'yes', True])
            if required_only is not None and dev_required != required_only:
                continue
            backend_domain = self._vm.app.domains.get_blind(backend_domain)
            yield DeviceAssignment(backend_domain, ident, options,
                                   required=dev_required,
                                   attach_automatically=dev_auto_attach,
                                   frontend_domain=self._vm,
                                   devclass=self._class)

    def get_exposed_devices(self) -> Iterable[DeviceInfo]:
        """
        List devices exposed by this vm.
        """
        devices: bytes = self._vm.qubesd_call(
            None, 'admin.vm.device.{}.Available'.format(self._class))
        for dev_serialized in devices.splitlines():
            yield DeviceInfo.deserialize(
                serialization=dev_serialized,
                expected_backend_domain=self._vm,
                expected_devclass=self._class,
            )

    def update_assignment(self, device: DeviceInfo, required: Optional[bool]):
        """Update assignment of already attached device.

        :param DeviceInfo device: device for which change required flag
        :param bool required: new assignment:
                              `None` -> unassign device from qube
                              `False` -> device will be auto-attached to qube
                              `True` -> device is required to start qube
        """
        self._vm.qubesd_call(
            None,
            'admin.vm.device.{}.Set.assignment'.format(self._class),
            '{!s}+{!s}'.format(device.backend_domain, device.ident),
            repr(required).encode('utf-8')
        )

    __iter__ = get_exposed_devices

    def clear_cache(self):
        """
        Clear cache of available devices.
        """
        self._dev_cache.clear()

    def __getitem__(self, item):
        """Get device object with given ident.

        :returns: py:class:`DeviceInfo`

        If domain isn't running, it is impossible to check device validity,
        so return UnknownDevice object. Also do the same for non-existing
        devices - otherwise it will be impossible to detach already
        disconnected device.
        """
        # fist, check if we have cached device info
        if item in self._dev_cache:
            return self._dev_cache[item]
        # then look for available devices
        for dev in self.get_exposed_devices():
            if dev.ident == item:
                self._dev_cache[item] = dev
                return dev
        # if still nothing, return UnknownDevice instance for the reason
        # explained in docstring, but don't cache it
        return UnknownDevice(self._vm, self._class, item)


class DeviceManager(dict):
    """Device manager that hold all devices by their classes.

    :param vm: VM for which we manage devices
    """

    def __init__(self, vm):
        super().__init__()
        self._vm = vm

    def __missing__(self, key):
        self[key] = DeviceCollection(self._vm, key)
        return self[key]

    def __iter__(self):
        return iter(self._vm.app.list_deviceclass())

    def keys(self):
        return self._vm.app.list_deviceclass()

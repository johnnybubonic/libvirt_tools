#!/usr/bin/env python3

import argparse
import time
import uuid
##
import libvirt
from lxml import etree


# The next dummy function and proceeding statement are because of the fucking worst design decisions.
# https://stackoverflow.com/a/45543887/733214
def libvirt_callback(userdata, err):
    pass


libvirt.registerErrorHandler(f = libvirt_callback, ctx = None)


# Defaults.
_def_uri = 'qemu:///system'
_def_rsrt_guests = True

# "Ignore" these libvirt.libvirtError codes in shutdown attempts.
#
_lv_err_pass = (86, 8)


class DomainNetwork(object):
    def __init__(self, dom):
        # dom is a libvirt.virDomain (or whatever it's called) instance.
        self.dom = dom
        self.dom_xml = None
        self.ifaces = []
        self._get_xml()

    def _get_xml(self):
        self.dom_xml = etree.fromstring(self.dom.XMLDesc())
        return(None)

    def get_nets(self, netnames, chk = None):
        if not self.ifaces and chk:
            return(None)
        _netnames = []
        for iface in self.dom_xml.xpath('devices/interface'):
            if iface.attrib.get('type') == 'network':
                src_xml = iface.find('source')
                netname = src_xml.attrib.get('network')
                if src_xml is not None and netname in netnames and not chk:
                    # Why, oh why, does the libvirt API want the XML??
                    self.ifaces.append(etree.tostring(iface).decode('utf-8'))
                elif src_xml is not None and netname in netnames:
                    _netnames.append(netname)
        if chk:
            pass  # TODO: confirm that network is removed so we can remove the time.sleep() below.
        return(None)


class VMManager(object):
    def __init__(self, netname, restart_guests = True, uri = _def_uri, *args, **kwargs):
        self.netname = netname
        self.restart_guests = restart_guests
        self.uri = uri
        self.networks = []
        self._listonly = True
        self.conn = None
        self._connect()
        self._get_networks()
        if self.netname:
            self._listonly = False
            self.networks = [i for i in self.networks if i.name() == self.netname]
        self.errs = []

    def _connect(self):
        if self.conn:
            return(None)
        self.conn = libvirt.open(self.uri)
        return(None)

    def _disconnect(self):
        if not self.conn:
            return(None)
        self.conn.close()
        self.conn = None
        return(None)

    def _get_networks(self):
        self._connect()
        self.networks = self.conn.listAllNetworks(flags = libvirt.VIR_CONNECT_LIST_NETWORKS_ACTIVE)
        self.networks.sort(key = lambda i: i.name())
        self._disconnect()
        return(None)

    def restart(self):
        if self._listonly:
            return(False)
        self._connect()
        doms = {}
        netnames = [i.name() for i in self.networks]
        # https://libvirt.org/html/libvirt-libvirt-domain.html#virConnectListAllDomains
        # _flags = (libvirt.VIR_CONNECT_LIST_DOMAINS_ACTIVE | libvirt.VIR_CONNECT_LIST_DOMAINS_RUNNING)
        _findflags = libvirt.VIR_CONNECT_LIST_DOMAINS_RUNNING
        # https://libvirt.org/html/libvirt-libvirt-domain.html#virDomainDetachDeviceFlags
        # https://libvirt.org/html/libvirt-libvirt-domain.html#virDomainAttachDeviceFlags
        # TODO: actually use _CURRENT?
        _ifaceflags = (libvirt.VIR_DOMAIN_AFFECT_LIVE | libvirt.VIR_DOMAIN_AFFECT_CURRENT)
        for dom in self.conn.listAllDomains(flags = _findflags):
            domnet = DomainNetwork(dom)
            domnet.get_nets(netnames)
            if domnet.ifaces:
                doms[uuid.UUID(bytes = dom.UUID())] = domnet
        for n in self.networks:
            n.destroy()
            n.create()
        for dom_uuid, domnet in doms.items():
            for iface_xml in domnet.ifaces:
                # Nice that we don't actually need to shut the machine down.
                # Here be dragons, though, if the OS doesn't understand NIC hotplugging.
                domnet.dom.detachDeviceFlags(iface_xml, flags = _ifaceflags)
                # TODO: modify DomainNetwork so we can check if an interface is removed or not. How?
                time.sleep(3)
                domnet.dom.attachDeviceFlags(iface_xml, flags = _ifaceflags)
        self._disconnect()
        if not doms:
            doms = None
        return(doms)

    def print_nets(self):
        max_name = len(max([i.name() for i in self.networks], key = len)) + 2
        hdr = '| Name{0} | Active | Persistent |'.format((' ' * (max_name - 6)))
        sep = '-' * len(hdr)
        print(sep)
        print(hdr)
        print(sep)
        vmtpl = '| {{name:<{0}}} |      {{isActive}} |          {{isPersistent}} |'.format((max_name - 2))
        for n in self.networks:
            vals = {}
            for i in ('name', 'isActive', 'isPersistent'):
                v = getattr(n, i)
                v = v()
                if isinstance(v, int):
                    v = ('Y' if v else 'N')
                vals[i] = v
            print(vmtpl.format(**vals))
        print(sep)
        return(None)


def parseArgs():
    args = argparse.ArgumentParser(description = 'Restart a network and all associated guests ("domains")')
    args.add_argument('-u', '--uri',
                      dest = 'uri',
                      default = _def_uri,
                      help = ('The URI to use for which libvirt to connect to. '
                              'Default: {0}').format(_def_uri))
    args.add_argument('-n', '--no-guests',
                      action = 'store_false',
                      dest = 'restart_guests',
                      help = ('If specified, suppress rebooting guests and only restart the network'))
    args.add_argument('netname',
                      metavar = 'NETWORK_NAME',
                      nargs = '?',
                      help = ('Restart this network name. If not specified, list all networks and quit'))
    return(args)


def main():
    args = parseArgs().parse_args()
    VMM = VMManager(**vars(args))
    if not args.netname:
        VMM.print_nets()
    VMM.restart()
    return(None)


if __name__ == '__main__':
    main()

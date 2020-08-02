#!/usr/bin/env python3

import argparse
# import os
# import getpass
import re
##
import libvirt
# from lxml import etree

# NOTE: docs URLS are super long. Extrapolate using following:
# docsurl = 'https://libvirt.org/docs/libvirt-appdev-guide-python/en-US/html'

# TODO: flesh this out. only supports guests atm
# TODO: use openAuth?
#       {docsurl}/libvirt_application_development_guide_using_python-Connections.html#idp13928160

# I would like to take the moment to point out that I did in three hours with exactly NO prior knowledge of the libvirt
# API what Red Hat couldn't do in four YEARS. https://bugzilla.redhat.com/show_bug.cgi?id=1244093


def libvirt_callback(userdata, err):
    # fucking worst design decision.
    # https://stackoverflow.com/a/45543887/733214
    pass


# fucking worst design decision.
# https://stackoverflow.com/a/45543887/733214
libvirt.registerErrorHandler(f = libvirt_callback, ctx = None)


class LV(object):
    def __init__(self, uri, *args, **kwargs):
        self.uri = uri
        self.conn = None
        self._args = args
        self._kwargs = kwargs

    def _getTargets(self, target, regex = False, ttype = 'guest',
                    state = None, nocase = False, *args, **kwargs):
        targets = []
        # TODO: ..._RUNNING as well? can add multiple flags
        state_flags = {'guest': (libvirt.VIR_CONNECT_LIST_DOMAINS_ACTIVE,
                                 libvirt.VIR_CONNECT_LIST_DOMAINS_INACTIVE),
                       'net': (libvirt.VIR_CONNECT_LIST_NETWORKS_ACTIVE,
                               libvirt.VIR_CONNECT_LIST_NETWORKS_INACTIVE),
                       'storage': (libvirt.VIR_CONNECT_LIST_STORAGE_POOLS_ACTIVE,
                                   libvirt.VIR_CONNECT_LIST_STORAGE_POOLS_INACTIVE)}
        re_flags = re.UNICODE  # The default
        if nocase:
            re_flags += re.IGNORECASE
        if not self.conn:
            self.startConn()
        search_funcs = {'guest': self.conn.listAllDomains,
                        'net': self.conn.listAllNetworks,
                        'storage': self.conn.listAllStoragePools}
        if not regex:
            ptrn = r'^{0}$'.format(target)
        else:
            ptrn = target
        ptrn = re.compile(ptrn, re_flags)
        if state == 'active':
            flag = state_flags[ttype][0]
        elif state == 'inactive':
            flag = state_flags[ttype][1]
        else:
            flag = 0
        for t in search_funcs[ttype](flag):
            if ptrn.search(t.name()):
                targets.append(t)
        targets.sort(key = lambda i: i.name())
        return(targets)

    def list(self, target, verbose = False, *args, **kwargs):
        # {docsurl}/libvirt_application_development_guide_using_python-Guest_Domains-Information-Info.html
        if not self.conn:
            self.startConn()
        targets = self._getTargets(target, **kwargs)
        results = []
        # Each attr is a tuple; the name of the attribute and the key name the result should use (if defined)
        attr_map = {'str': (('name', None),
                            ('OSType', 'os'),
                            ('UUIDString', 'uuid'),
                            ('hostname', None)),
                    'bool': (('autostart', None),
                             ('hasCurrentSnapshot', 'current_snapshot'),
                             ('hasManagedSaveImage', 'managed_save_image'),
                             ('isActive', 'active'),
                             ('isPersistent', 'persistent'),
                             ('isUpdated', 'updated')),
                    'int': (('ID', 'id'),
                            ('maxMemory', 'max_memory_KiB'),
                            ('maxVcpus', 'max_vCPUs'))}
        for t in targets:
            if not verbose:
                results.append(t.name())
            else:
                r = {}
                for attrname, newkey in attr_map['str']:
                    keyname = (newkey if newkey else attrname)
                    try:
                        r[keyname] = str(getattr(t, attrname)())
                    except libvirt.libvirtError:
                        r[keyname] = '(N/A)'
                for attrname, newkey in attr_map['bool']:
                    keyname = (newkey if newkey else attrname)
                    try:
                        r[keyname] = bool(getattr(t, attrname)())
                    except (libvirt.libvirtError, ValueError):
                        r[keyname] = None
                for attrname, newkey in attr_map['int']:
                    keyname = (newkey if newkey else attrname)
                    try:
                        r[keyname] = int(getattr(t, attrname)())
                        if r[keyname] == -1:
                            r[keyname] = None
                    except (libvirt.libvirtError, ValueError):
                        r[keyname] = None
                results.append(r)
        return(results)

    def restart(self, target, *args, **kwargs):
        self.stop(target, state = 'active', **kwargs)
        self.start(target, state = 'inactive', **kwargs)
        return()

    def start(self, target, **kwargs):
        if not self.conn:
            self.startConn()
        targets = self._getTargets(target, state = 'inactive', **kwargs)
        for t in targets:
            t.create()
        return()

    def stop(self, target, force = False, *args, **kwargs):
        if not self.conn:
            self.startConn()
        targets = self._getTargets(target, state = 'active', **kwargs)
        for t in targets:
            if not force:
                t.shutdown()
            else:
                t.destroy()
        return ()

    def startConn(self):
        self.conn = libvirt.open(self.uri)
        return()

    def stopConn(self):
        if self.conn:
            self.conn.close()
        self.conn = None
        return()


def parseArgs():
    args = argparse.ArgumentParser(description = 'Some better handling of libvirt guests')
    common_args = argparse.ArgumentParser(add_help = False)
    common_args.add_argument('-u', '--uri',
                             dest = 'uri',
                             default = 'qemu:///system',
                             help = 'The URI for the libvirt to connect to. Default: qemu:///system')
    common_args.add_argument('-r', '--regex',
                             action = 'store_true',
                             help = 'If specified, use a regex pattern for TARGET instead of exact match')
    common_args.add_argument('-i', '--case-insensitive',
                             action = 'store_true',
                             dest = 'nocase',
                             help = 'If specified, match the target name/regex pattern case-insensitive')
    common_args.add_argument('-T', '--target-type',
                             # choices = ['guest', 'net', 'storage'],
                             choices = ['guest'],
                             default = 'guest',
                             dest = 'ttype',
                             help = 'The type of TARGET')
    common_args.add_argument('-t', '--target',
                             dest = 'target',
                             metavar = 'TARGET',
                             default = '.*',
                             help = ('The guest, network, etc. to manage. '
                                     'If not specified, operate on all (respecting other filtering)'))
    subparsers = args.add_subparsers(help = 'Operation to perform',
                                     dest = 'oper',
                                     metavar = 'OPERATION',
                                     required = True)
    start_args = subparsers.add_parser('start', help = 'Start the target(s)', parents = [common_args])
    restart_args = subparsers.add_parser('restart', help = 'Restart the target(s)', parents = [common_args])
    stop_args = subparsers.add_parser('stop', help = 'Stop ("destroy") the target(s)', parents = [common_args])
    stop_args.add_argument('-f', '--force',
                           dest = 'force',
                           action = 'store_true',
                           help = 'Hard poweroff instead of send a shutdown/ACPI powerdown signal')
    list_args = subparsers.add_parser('list', help = 'List the target(s)', parents = [common_args])
    list_args.add_argument('-v', '--verbose',
                           dest = 'verbose',
                           action = 'store_true',
                           help = 'Display more output')
    list_args.add_argument('-s', '--state',
                           dest = 'state',
                           choices = ['active', 'inactive'],
                           default = None,
                           help = 'Filter results by state. Default is all states')
    return(args)


def main():
    args = parseArgs().parse_args()
    varargs = vars(args)
    lv = LV(**varargs)
    f = getattr(lv, args.oper)(**varargs)
    if args.oper == 'list':
        if args.verbose:
            import json
            print(json.dumps(f, indent = 4, sort_keys = True))
        else:
            print('\n'.join(f))
    return()


if __name__ == '__main__':
    main()

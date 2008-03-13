#!/usr/bin/env python

""" networking - Provides wrappers for common network operations

This module provides wrappers of the common network tasks as well as
threads to perform the actual connecting to networks.

class Controller() -- Parent class to Wireless and Wired
class ConnectThread() -- Parent class to WirelessConnectThread and
    WiredConnectThread
class Wireless() -- Wrapper for various wireless functions
class Wired() -- Wrapper for various wired functions
class WirelessConnectThread() -- Connection thread for wireless
    interface
class WiredConnectThread() -- Connection thread for wired
    interface

"""

#
#   Copyright (C) 2007 Adam Blackburn
#   Copyright (C) 2007 Dan O'Reilly
#   Copyright (C) 2007 Byron Hillis
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License Version 2 as
#   published by the Free Software Foundation.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

#
# Much thanks to wieman01 for help and support with various types of encyption.
# Also thanks to foxy123, yopnono, and the many others who reported bugs helped
# and helped keep this project moving.
#

import re
import threading
import thread
import misc
import wnettools
import wpath
import time

if __name__ == '__main__':
    wpath.chdir(__file__)



class Controller(object):
    """ Parent class for the different interface types. """
    wireless_interface = None
    wired_interface = None
    connecting_thread = None
    before_script = None
    after_script = None
    disconnect_script = None
    driver = None
    wiface = None
    liface = None

    def __init__(self):
        """ Initialise the class. """
        self.global_dns_1 = None
        self.global_dns_2 = None
        self.global_dns_3 = None
        
    def __setattr__(self, attr, value):
        """ Provided custom self.variable assignments.

        Calls the appropriate methods if self.wireless_interface or
        self.wired_interface is set.
        
        """
        if attr == 'wireless_interface':
            object.__setattr__(self, attr, value)
            if self.wiface:
                self.SetWiface(value)
        elif attr == 'wired_interface':
            object.__setattr__(self, attr, value)
            if self.liface:
                self.SetLiface(value)
        else:
            object.__setattr__(self, attr, value)
            
    def SetWiface(self, iface):
        """ Sets the wireless interface for the associated wnettools class. """
        if self.wiface:
            self.wiface.SetInterface(iface)
    
    def SetLiface(self, iface):
        """ Sets the wired interface for the associated wnettools class. """
        if self.liface:
            self.liface.SetInterface(iface)


class ConnectThread(threading.Thread):
    """ A class to perform network connections in a multi-threaded way.

    Useless on it's own, this class provides the generic functions
    necessary for connecting using a separate thread.
    
    """

    is_connecting = None
    connecting_thread = None
    should_die = False
    lock = thread.allocate_lock()

    def __init__(self, network, wireless, wired, before_script, after_script, 
                 disconnect_script, gdns1, gdns2, gdns3, debug):
        """ Initialise the required object variables and the thread.

        Keyword arguments:
        network -- the network to connect to
        wireless -- name of the wireless interface
        wired -- name of the wired interface
        before_script -- script to run before bringing up the interface
        after_script -- script to run after bringing up the interface
        disconnect_script -- script to run after disconnection
        gdns1 -- global DNS server 1
        gdns2 -- global DNS server 2
        gdns3 -- global DNS server 3
        debug -- debug mode status

        """
        threading.Thread.__init__(self)
        self.network = network
        self.wireless_interface = wireless
        self.wired_interface = wired
        self.is_connecting = False
        self.is_aborted = False
        self.abort_msg = None
        self.before_script = before_script
        self.after_script = after_script
        self.disconnect_script = disconnect_script
        self.should_die = False

        self.global_dns_1 = gdns1
        self.global_dns_2 = gdns2
        self.global_dns_3 = gdns3

        self.connecting_message = None
        self.debug = debug
        
        self.SetStatus('interface_down')


    def SetStatus(self, status):
        """ Set the threads current status message in a thread-safe way.

        Keyword arguments:
        status -- the current connection status

        """
        self.lock.acquire()
        try:
            self.connecting_message = status
        finally:
            self.lock.release()


    def GetStatus(self):
        """ Get the threads current status message in a thread-safe way.

        Returns:
        The current connection status.

        """
        self.lock.acquire()
        try:
            message = self.connecting_message
        finally:
            self.lock.release()
        return message
    
    def reset_ip_addresses(self, wiface, liface):
        """ Resets the IP addresse for both wired/wireless interfaces.
        
        Sets a false ip so that when we set the real one, the correct
        routing entry is created.
        
        """
        print 'Setting false IP...'
        self.SetStatus('resetting_ip_address')
        wiface.SetAddress('0.0.0.0')
        liface.SetAddress('0.0.0.0')
        
    def put_iface_down(self, iface):
        """ Puts the given interface down. """
        print 'Putting interface down'
        self.SetStatus('interface_down')
        iface.Down()
        
    def run_script_if_needed(self, script, msg):
        """ Execute a given script if needed.
        
        Keyword arguments:
        script -- the script to execute, or None/'' if there isn't one.
        msg -- the name of the script to display in the log.
        
        """
        if script:
            print 'Executing %s script' % (msg)
            misc.ExecuteScript(script)
            
    def flush_routes(self, wiface, liface):
        """ Flush the routes for both wired/wireless interfaces. """
        self.SetStatus('flushing_routing_table')
        print 'Flushing the routing table...'
        wiface.FlushRoutes()
        liface.FlushRoutes()

    def set_broadcast_address(self, iface):
        """ Set the broadcast address for the given interface. """
        if not self.network.get('broadcast') == None:
            self.SetStatus('setting_broadcast_address')
            print 'Setting the broadcast address...' + self.network['broadcast']
            iface.SetAddress(broadcast=self.network['broadcast'])
            
    def set_ip_address(self, iface):
        """ Set the IP address for the given interface. 
        
        Assigns a static IP if one is requested, otherwise calls DHCP.
        
        """
        if self.network.get('ip'):
            self.SetStatus('setting_static_ip')
            print 'Setting static IP : ' + self.network['ip']
            iface.SetAddress(self.network['ip'], self.network['netmask'])
            print 'Setting default gateway : ' + self.network['gateway']
            iface.SetDefaultRoute(self.network['gateway'])
        else:
            # Run dhcp...
            self.SetStatus('running_dhcp')
            print "Running DHCP"
            dhcp_status = iface.StartDHCP()
            if dhcp_status in ['no_dhcp_offers', 'dhcp_failed']:
                self.connect_aborted(dhcp_status)
                return
            
    def set_dns_addresses(self):
        """ Set the DNS address(es).

        If static DNS servers or global DNS servers are specified, set them.
        Otherwise do nothing.
        
        """
        if (((self.network.get('dns1') or self.network.get('dns2') or
            self.network.get('dns3')) and self.network.get('use_static_dns')) or
            self.network.get('use_global_dns')):
            self.SetStatus('setting_static_dns')
            if self.network.get('use_global_dns'):
                wnettools.SetDNS(misc.Noneify(self.global_dns_1),
                    misc.Noneify(self.global_dns_2),
                    misc.Noneify(self.global_dns_3))
            else:
                wnettools.SetDNS(self.network.get('dns1'),
                    self.network.get('dns2'), self.network.get('dns3'))

    def connect_aborted(self, reason):
        """ Sets the thread status to aborted in a thread-safe way.
        
        Sets the status to aborted, and also delays returning for
        a few seconds to make sure the message is readable
        
        """
        self.SetStatus(reason)
        self.is_aborted = True
        self.abort_msg = reason
        self.is_connecting = False
        print 'exiting connection thread'
        
    def stop_dhcp_clients(self, iface):
        """ Stop and running DHCP clients, as well as wpa_supplicant. """
        print 'Stopping wpa_supplicant, and any dhcp clients'
        iface.StopWPA()
        wnettools.StopDHCP()
        
    def abort_if_needed(self):
        """ Abort the thread is it has been requested. """
        if self.should_die:
            self.connect_aborted('aborted')
            thread.exit()
            
    def put_iface_up(self, iface):
        """ Bring up given interface. """
        print 'Putting interface up...'
        self.SetStatus('interface_up')
        iface.Up()


class Wireless(Controller):
    """ A wrapper for common wireless interface functions. """

    def __init__(self):
        """ Initialize the class. """
        Controller.__init__(self)
        self.wpa_driver = None
        self.wiface = wnettools.WirelessInterface(self.wireless_interface,
                                                  self.wpa_driver)
    
    def __setattr__(self, attr, value):
        if attr == 'wpa_driver':
            self.__dict__[attr] = value
            if self.wiface:
                self.SetWPADriver(value)
        else:
            object.__setattr__(self, attr, value)
                
    def LoadInterfaces(self):
        """ Load the wnettools controls for the wired/wireless interfaces. """
        self.wiface = wnettools.WirelessInterface(self.wireless_interface,
                                                  self.wpa_driver)

    def Scan(self, essid=None):
        """ Scan for available wireless networks.

        Keyword arguments:
        essid -- The essid of a hidden network

        Returns:
        A list of available networks sorted by strength.

        """
        wiface = self.wiface

        # Prepare the interface for scanning
        wiface.Up()

        # If there is a hidden essid then set it now, so that when it is
        # scanned it will be recognized.
        essid = misc.Noneify(essid)
        if essid is not None:
            print 'Setting hidden essid' + essid
            wiface.SetEssid(essid)

        aps = wiface.GetNetworks()
        #print aps
        aps.sort(key=lambda x: x['strength'])
        return aps

    def Connect(self, network):
        """ Spawn a connection thread to connect to the network.

        Keyword arguments:
        network -- network to connect to

        """
        self.connecting_thread = WirelessConnectThread(network,
            self.wireless_interface, self.wired_interface,
            self.wpa_driver, self.before_script, self.after_script,
            self.disconnect_script, self.global_dns_1,
            self.global_dns_2, self.global_dns_3)
        self.connecting_thread.setDaemon(True)
        self.connecting_thread.start()
        return True

    def GetSignalStrength(self, iwconfig=None):
        """ Get signal strength of the current network.

        Returns:
        The current signal strength.

        """
        return self.wiface.GetSignalStrength(iwconfig)

    def GetDBMStrength(self, iwconfig=None):
        """ Get the dBm signal strength of the current network.

        Returns:
        The current dBm signal strength.

        """
        return self.wiface.GetDBMStrength(iwconfig)

    def GetCurrentNetwork(self, iwconfig=None):
        """ Get current network name.

        Returns:
        The name of the currently connected network.

        """
        return self.wiface.GetCurrentNetwork(iwconfig)

    def GetIP(self):
        """ Get the IP of the interface.

        Returns:
        The IP address of the interface in dotted notation.

        """
        return self.wiface.GetIP()

    def GetIwconfig(self):
        """ Get the out of iwconfig. """
        return self.wiface.GetIwconfig()
    
    def IsUp(self):
        """ Calls the IsUp method for the wireless interface.
        
        Returns:
        True if the interface is up, False otherwise.
        
        """
        return self.wiface.IsUp()

    def CreateAdHocNetwork(self, essid, channel, ip, enctype, key,
            enc_used, ics):
        """ Create an ad-hoc wireless network.

        Keyword arguments:
        essid -- essid of the ad-hoc network
        channel -- channel of the ad-hoc network
        ip -- ip of the ad-hoc network
        enctype -- unused
        key -- key of the ad-hoc network
        enc_used -- encrytion enabled on ad-hoc network
        ics -- enable internet connection sharing

        """
        wiface = self.wiface
        print 'Creating ad-hoc network'
        print 'Killing dhclient and wpa_supplicant'
        wnettools.StopDHCP()
        wiface.StopWPA()
        print 'Putting wireless interface down'
        wiface.Down()
        print 'Setting mode, channel, and essid'
        wiface.SetMode('ad-hoc')
        wiface.SetChannel(channel)
        wiface.SetEssid(essid)
        # Right now it just assumes you're using WEP
        if enc_used:
            print 'Setting encryption key'
            wiface.SetKey(key)
        print 'Putting interface up'
        wiface.Up()
        # Just assume that the netmask is 255.255.255.0, it simplifies ICS
        print 'Setting IP address'
        wiface.SetAddress(ip, '255.255.255.0')

        ip_parts = misc.IsValidIP(ip)

        if ics and ip_parts:
            # Set up internet connection sharing here
            # Flush the forward tables
            misc.Run('iptables -F FORWARD')
            misc.Run('iptables -N fw-interfaces')
            misc.Run('iptables -N fw-open')
            misc.Run('iptables -F fw-interfaces')
            misc.Run('iptables -F fw-open')
            misc.Run('iptables -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS \
                     --clamp-mss-to-pmtu')
            misc.Run('iptables -A FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT')
            misc.Run('iptables -A FORWARD -j fw-interfaces ')
            misc.Run('iptables -A FORWARD -j fw-open ')
            misc.Run('iptables -A FORWARD -j REJECT --reject-with icmp-host-unreachable')
            misc.Run('iptables -P FORWARD DROP')
            misc.Run('iptables -A fw-interfaces -i ' + self.wireless_interface + ' -j ACCEPT')
            net_ip = '.'.join(ip_parts[0:3]) + '.0'
            misc.Run('iptables -t nat -A POSTROUTING -s ' + net_ip + \
                     '/255.255.255.0 -o ' + self.wired_interface + \
                     ' -j MASQUERADE')
            misc.Run('echo 1 > /proc/sys/net/ipv4/ip_forward') # Enable routing

    def DetectWirelessInterface(self):
        """ Detect available wireless interfaces.

        Returns:
        The first available wireless interface.

        """
        return wnettools.GetWirelessInterfaces()

    def GetKillSwitchStatus(self):
        """ Get the current status of the Killswitch. 
        
        Returns:
        True if the killswitch is on, False otherwise.
        
        """
        return self.wiface.GetKillSwitchStatus()

    def Disconnect(self):
        """ Disconnect the given iface.
        
        Executes the disconnect script associated with a given interface,
        Resets it's IP address, and puts the interface down then up.
        
        """
        wiface = self.wiface
        if self.disconnect_script not in (None, ""):
            print 'Running wireless network disconnect script'
            misc.ExecuteScript(self.disconnect_script)

        wiface.SetAddress('0.0.0.0')
        wiface.Down()
        wiface.Up()

    def EnableInterface(self):
        """ Puts the interface up. """
        return self.wiface.Up()
    
    def DisableInterface(self):
        """ Puts the interface down. """
        return self.wiface.Down()
    
    def SetWPADriver(self, driver):
        """ Sets the wpa_supplicant driver associated with the interface. """
        self.wiface.SetWpaDriver(driver)

class WirelessConnectThread(ConnectThread):
    """ A thread class to perform the connection to a wireless network.

    This thread, when run, will perform the necessary steps to connect
    to the specified network.

    """

    def __init__(self, network, wireless, wired, wpa_driver,
            before_script, after_script, disconnect_script, gdns1,
            gdns2, gdns3, debug=False):
        """ Initialise the thread with network information.

        Keyword arguments:
        network -- the network to connect to
        wireless -- name of the wireless interface
        wired -- name of the wired interface
        wpa_driver -- type of wireless interface
        before_script -- script to run before bringing up the interface
        after_script -- script to run after bringing up the interface
        disconnect_script -- script to run after disconnection
        gdns1 -- global DNS server 1
        gdns2 -- global DNS server 2
        gdns3 -- global DNS server 3

        """
        ConnectThread.__init__(self, network, wireless, wired,
            before_script, after_script, disconnect_script, gdns1,
            gdns2, gdns3, debug)
        self.wpa_driver = wpa_driver


    def run(self):
        """ The main function of the connection thread.

        This function performs the necessary calls to connect to the
        specified network, using the information provided. The following
        indicates the steps taken.
        1. Run pre-connection script.
        2. Take down the interface and clean up any previous
           connections.
        3. Generate a PSK if required and authenticate.
        4. Associate with the WAP.
        5. Get/set IP address and DNS servers.

        """
        wiface = wnettools.WirelessInterface(self.wireless_interface,
                                             self.wpa_driver)
        liface = wnettools.WiredInterface(self.wired_interface)
        self.is_connecting = True
        
        # Run pre-connection script.
        self.abort_if_needed()
        self.run_script_if_needed(self.before_script, 'pre-connection')
        self.abort_if_needed()
        
        # Dake down interface and clean up previous connections.
        self.put_iface_down(wiface)
        self.abort_if_needed()
        self.reset_ip_addresses(wiface, liface)
        self.stop_dhcp_clients(wiface)
        self.abort_if_needed()
        self.flush_routes(wiface, liface)

        # Generate PSK and authenticate if needed.
        if self.wpa_driver != 'ralink legacy':
            self.generate_psk_and_authenticate(wiface)

        # Put interface up.
        self.abort_if_needed()
        self.SetStatus('configuring_interface')
        self.put_iface_up(wiface)
        self.abort_if_needed()
        
        # Associate.
        wiface.SetMode(self.network['mode'])
        wiface.Associate(self.network['essid'], self.network['channel'],
                         self.network['bssid'])

        # Authenticate after association for Ralink legacy cards.
        if self.wpa_driver == 'ralink legacy':
            if self.network.get('key'):
                wiface.Authenticate(self.network)
                
        # Validate Authentication.
        if self.network.get('enctype'):
            self.SetStatus('validating_authentication')
            if not wiface.ValidateAuthentication(time.time()):
                self.connect_aborted('bad_pass')
                return

        # Set up gateway, IP address, and DNS servers.
        self.set_broadcast_address(wiface)
        self.abort_if_needed()
        self.set_ip_address(wiface)
        self.set_dns_addresses()
        
        # Run post-connection script.
        self.abort_if_needed()
        self.run_script_if_needed(self.after_script, 'post-connection')

        self.SetStatus('done')
        print 'Connecting thread exiting.'
        if self.debug:
            print "IP Address is: " + wiface.GetIP()
        self.is_connecting = False
    
    def generate_psk_and_authenticate(self, wiface):
        """ Generates a PSK and authenticates if necessary. 
        
        Generates a PSK using wpa_passphrase, and starts the authentication
        process if encryption is on.
        
        """
        # Check to see if we need to generate a PSK (only for non-ralink
        # cards).
        if self.network.get('key'):
            self.SetStatus('generating_psk')

            print 'Generating psk...'
            key_pattern = re.compile('network={.*?\spsk=(.*?)\n}.*',
                                     re.I | re.M  | re.S)
            self.network['psk'] = misc.RunRegex(key_pattern,
                                misc.Run(''.join(['wpa_passphrase "',
                                         self.network['essid'], '" "', 
                                         re.escape(self.network['key']), '"'])))
        # Generate the wpa_supplicant file...
        if self.network.get('enctype'):
            self.SetStatus('generating_wpa_config')
            print 'Attempting to authenticate...'
            wiface.Authenticate(self.network)


class Wired(Controller):
    """ A wrapper for common wired interface functions. """

    def __init__(self):
        """ Initialise the class. """
        Controller.__init__(self)
        self.wpa_driver = None
        self.liface = wnettools.WiredInterface(self.wired_interface)
        
    def __setattr__(self, attr, val):
        object.__setattr__(self, attr, val)
        
    def LoadInterfaces(self):
        """ Load the wnettools controls for the wired/wireless interfaces. """
        self.liface = wnettools.WiredInterface(self.wired_interface)

    def CheckPluggedIn(self):
        """ Check whether the wired connection is plugged in.

        Returns:
        The status of the physical connection link.

        """
        return self.liface.GetPluggedIn()

    def Connect(self, network):
        """ Spawn a connection thread to connect to the network.

        Keyword arguments:
        network -- network to connect to

        """
        self.connecting_thread = WiredConnectThread(network,
            self.wireless_interface, self.wired_interface,
            self.before_script, self.after_script,
            self.disconnect_script, self.global_dns_1,
            self.global_dns_2, self.global_dns_3)
        self.connecting_thread.setDaemon(True)
        self.connecting_thread.start()
        return True

    def GetIP(self):
        """ Get the IP of the interface.

        Returns:
        The IP address of the interface in dotted notation.

        """
        return self.liface.GetIP()

    def Disconnect(self):
        """ Disconnect from the network. """
        liface = self.liface
        if self.disconnect_script != None:
            print 'Running wired disconnect script'
            misc.Run(self.disconnect_script)

        liface.SetAddress('0.0.0.0')
        liface.Down()
        liface.Up()
        
    def IsUp(self):
        """ Calls the IsUp method for the wired interface. 
        
        Returns:
        True if the interface is up, False otherwise.
        
        """
        return self.liface.IsUp()
    
    def EnableInterface(self):
        """ Puts the interface up.
        
        Returns:
        True if the interface was put up succesfully, False otherwise.
        
        """
        return self.liface.Up()
    
    def DisableInterface(self):
        """ Puts the interface down.
        
        Returns:
        True if the interface was put down succesfully, False otherwise.
        
        """
        return self.liface.Down()


class WiredConnectThread(ConnectThread):
    """ A thread class to perform the connection to a wired network.

    This thread, when run, will perform the necessary steps to connect
    to the specified network.

    """
    def __init__(self, network, wireless, wired,
            before_script, after_script, disconnect_script, gdns1,
            gdns2, gdns3, debug=False):
        """ Initialise the thread with network information.

        Keyword arguments:
        network -- the network to connect to
        wireless -- name of the wireless interface
        wired -- name of the wired interface
        before_script -- script to run before bringing up the interface
        after_script -- script to run after bringing up the interface
        disconnect_script -- script to run after disconnection
        gdns1 -- global DNS server 1
        gdns2 -- global DNS server 2
        gdns3 -- global DNS server 3

        """
        ConnectThread.__init__(self, network, wireless, wired,
            before_script, after_script, disconnect_script, gdns1,
            gdns2, gdns3, debug)

    def run(self):
        """ The main function of the connection thread.

        This function performs the necessary calls to connect to the
        specified network, using the information provided. The following
        indicates the steps taken.
        1. Run pre-connection script.
        2. Take down the interface and clean up any previous
           connections.
        3. Bring up the interface.
        4. Get/set IP address and DNS servers.
        5. Run post-connection script.

        """
        wiface = wnettools.WirelessInterface(self.wireless_interface)
        liface = wnettools.WiredInterface(self.wired_interface)

        self.is_connecting = True

        # Run pre-connection script.
        self.abort_if_needed()
        self.run_script_if_needed(self.before_script, 'pre-connection')
        self.abort_if_needed()
        
        # Take down interface and clean up previous connections.
        self.put_iface_down(liface)
        self.reset_ip_addresses(wiface, liface)
        self.stop_dhcp_clients(wiface)
        self.abort_if_needed()
        self.flush_routes(wiface, liface)
        
        # Bring up interface.
        self.put_iface_up(liface)
        self.abort_if_needed()
        
        # Set gateway, IP adresses, and DNS servers.
        self.set_broadcast_address(liface)
        self.abort_if_needed()
        self.set_ip_address(liface)
        self.set_dns_addresses()
        self.abort_if_needed()
        
        # Run post-connection script.
        self.run_script_if_needed(self.after_script, 'post-connection')

        self.SetStatus('done')
        print 'Connecting thread exiting.'
        if self.debug:
            print "IP Address is: " + liface.GetIP()
        self.is_connecting = False

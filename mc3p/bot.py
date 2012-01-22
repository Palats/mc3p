# Copyright (C) 2012 Pierre Palatin

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License v2 as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import logging
import re
import signal
import sys
import threading
import math
from optparse import OptionParser

from twisted.internet import reactor, protocol
from twisted.python import log

import util
import messages
import parsing
import packets


logger = logging.getLogger(__name__)


def parse_args():
    """Return host and port, or print usage and exit."""
    usage = "usage: %prog [options] host [port]"
    desc = """Minecraft bot"""
    parser = OptionParser(usage=usage,
                          description=desc)
    parser.add_option("-l", "--log-level", dest="loglvl", metavar="LEVEL",
                      choices=["debug","info","warn","error"],
                      help="Override logging.conf root log level")
    parser.add_option("--log-file", dest='logfile', metavar="FILE", default=None,
                      help="logging configuration file (optional)")
    (opts,args) = parser.parse_args()

    if not 1 <= len(args) <= 2:
        parser.error("Incorrect number of arguments.") # Calls sys.exit()

    host = args[0]
    port = 25565
    if len(args) > 1:
        try:
            port = int(args[1])
        except ValueError:
            parser.error("Invalid port %s" % args[1])

    if len(args) == 2:
        try:
            port = int(sys.argv[2])
        except:
            parser.error("Invalid port '%s'" % args[1])

    return (host, port, opts)


class MCProtocol(protocol.Protocol):
    def connectionMade(self):
        logger.debug('Protocol connectionMade.')

        self.protocol_id = 23
        self.send_spec = messages.protocol[self.protocol_id][0]
        self.receive_spec = messages.protocol[self.protocol_id][1]
        self.stream = util.Stream()

    def sendMessage(self, msg):
        msgtype = msg['msgtype']
        msg_emitter = self.send_spec[msgtype]
        s = msg_emitter.emit(msg)
        #logger.debug("Sending message (size %i): %s = %r", len(s), msg, s)
        self.transport.write(s)

    def _parsePacket(self):
        """Parse a single packet out of stream, and return it."""
        try:
            # read Packet ID
            msgtype = parsing.parse_unsigned_byte(self.stream)
            if not self.receive_spec[msgtype]:
                raise parsing.UnsupportedPacketException(msgtype)
            logger.debug("Trying to parse message type %x" % (msgtype))
            msg_parser = self.receive_spec[msgtype]
            msg = msg_parser.parse(self.stream)
            msg['raw_bytes'] = self.stream.packet_finished()
            logger.debug("Received message (size %i): %s", len(msg['raw_bytes']), msg)
            return msg
        except util.PartialPacketException:
            return None

    def dataReceived(self, data):
        self.stream.append(data)

        msg = self._parsePacket()
        while msg:
            # Do something
            self.messageReceived(msg)
            msg = self._parsePacket()

    def messageReceived(self, msg):
        pass


class Position(object):
    def __init__(self):
        self.x = self.y = self.z = 0.0
        self.stance = 0.0
        self.yaw = self.pitch = 0.0
        self.on_ground = True

    def fromMessage(self, msg):
        self.x = msg['x']
        self.y = msg['y']
        self.z = msg['z']
        self.stance = msg['stance']
        self.yaw = msg['yaw']
        self.pitch = msg['pitch']
        self.on_ground = msg['on_ground']

    def toMessage(self):
        msg = {
                'x': self.x,
                'y': self.y,
                'z': self.z,
                'stance': self.stance,
                'yaw': self.yaw,
                'pitch': self.pitch,
                'on_ground': self.on_ground,
        }
        return msg


class Spawn(object):
    def __init__(self):
        self.x = self.y = self.z = 0.0

    def fromMessage(self, msg):
        self.x = msg['x']
        self.y = msg['y']
        self.z = msg['z']

    def toMessage(self):
        msg = {
                'x': self.x,
                'y': self.y,
                'z': self.z,
        }
        return msg


class MCBot(MCProtocol):
    def connectionMade(self):
        MCProtocol.connectionMade(self)

        self.delayed_call = None
        self.time = None
        self.position = Position()
        self.spawn = Spawn()
        self.players = {}

        self.sendMessage({'msgtype': packets.HANDSHAKE, 'username': 'palatstest'})

    def _backgroundUpdate(self):
        msg = {'msgtype': packets.PLAYERPOSITIONLOOK}
        msg.update(self.position.toMessage())
        self.sendMessage(msg)

        if self.delayed_call:
            self.delayed_call.reset()
        else:
            reactor.callLater(0.050, self._backgroundUpdate)

    def messageReceived(self, msg):
        if msg['msgtype'] == packets.KEEPALIVE:
            self.sendMessage({'msgtype': packets.KEEPALIVE, 'id': 0})
        elif msg['msgtype'] == packets.LOGIN:
            pass
        elif msg['msgtype'] == packets.HANDSHAKE:
            logger.debug('Handshake done, hash: %s', msg['hash'])
            self.sendMessage({
                'msgtype': packets.LOGIN,
                'proto_version': 23,
                'username': 'palatstest',
                'nu1': 0,
                'nu2': 0,
                'nu3': 0,
                'nu4': 0,
                'nu5': 0,
                'nu6': 0,
                'nu7': '',
             })
        elif msg['msgtype'] == packets.CHAT:
            self.chatReceived(msg['chat_msg'])
        elif msg['msgtype'] == packets.UPDATETIME:
            self.time = msg['time']
        elif msg['msgtype'] == packets.SPAWNPOSITION:
            self.spawn.fromMessage(msg)
        elif msg['msgtype'] == packets.PLAYERPOSITIONLOOK:
            self.position.fromMessage(msg)
            self._backgroundUpdate()
        elif msg['msgtype'] == packets.PRECHUNK:
            # Remove the old chunk data, nothing to do really
            pass
        elif msg['msgtype'] == packets.CHUNK:
            logger.debug("Chunk %s,%s,%s", msg['x'], msg['y'], msg['z'])
        elif msg['msgtype'] == packets.PLAYERLIST:
            if msg['online']:
                self.players[msg['name']] = msg['ping']
                logger.debug('Player %s @ %s ms', msg['name'], msg['ping'])
            elif msg['name'] in self.players:
                self.players.pop(msg['name'])
        else:
            logger.info("Received message (size %i): %s", len(msg['raw_bytes']), msg)

    def chatReceived(self, message):
        logger.info('Chat message: %s', message)

    def sendPosition(self):
        reactor.callFromThread(self._backgroundUpdate)


class TestBot(MCBot):
    def move(self, x=None, y=None, z=None):
        if x == y == z == None:
            x = 1
            y = 0
            z = 0
        self.position.x += x or 0
        self.position.y += y or 0
        self.position.z += z or 0
        self.sendPosition()

    def chatReceived(self, message):
        m = re.search('^<[^>]+> (.+)$', message)
        if not m:
            logger.info('Chat message: %s', message)
            return
        tokens = re.split('\s+', m.group(1))

        cmd = tokens[0].upper()
        param = None
        if len(tokens) > 1:
            try:
                param = float(tokens[1])
            except ValueError:
                param = None

        if cmd == 'LT':
            param = param or 0
            self.position.yaw += param
            self.sendPosition()
        elif cmd == 'RT':
            param = param or 0
            self.position.yaw -= param
            self.sendPosition()
        elif cmd == 'FD':
            param = param or 1
            yaw = self.position.yaw * math.pi / 180

            self.position.x += -math.sin(yaw) * param
            self.position.z += math.cos(yaw) * param
            self.sendPosition()
        elif cmd == 'BK':
            param = param or 1
            yaw = self.position.yaw * math.pi / 180

            self.position.x -= -math.sin(yaw) * param
            self.position.z -= math.cos(yaw) * param
            self.sendPosition()


class MCBotFactory(protocol.ReconnectingClientFactory):
    def startedConnecting(self, connector):
        print 'Started to connect.'

    def buildProtocol(self, addr):
        print 'Connected. (resetting reconnection delay)'
        self.resetDelay()
        return self.bot

    def clientConnectionLost(self, connector, reason):
        print 'Lost connection.  Reason:', reason
        protocol.ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        print 'Connection failed. Reason:', reason
        protocol.ReconnectingClientFactory.clientConnectionFailed(self, connector,
                                                                  reason)



def backgroundReactor():
    reactor_thread = threading.Thread(target=reactor.run, kwargs={'installSignalHandlers': 0})
    reactor_thread.setDaemon(True)
    reactor_thread.start()


def cliCommands(bot):
    return {
            'move': bot.move,
    }


def runIPython(bot):
    """Run the bot and provide access to a python shell."""

    import IPython

    backgroundReactor()
    IPython.embed(user_ns=cliCommands(bot))


def runBPython(bot):
    import bpython
    backgroundReactor()
    bpython.embed(locals_=cliCommands(bot))


def run(bot):
    """Just run the bot, without any interaction."""
    reactor.run()


class LogHandler(logging.StreamHandler):
    def emit(self, record):
        super(LogHandler, self).emit(record)
        #print 'coin'


if __name__ == "__main__":
    ch = LogHandler()
    formatter = logging.Formatter(logging.BASIC_FORMAT)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    (host, port, opts) = parse_args()

    if opts.logfile:
        util.config_logging(opts.logfile)


    if opts.loglvl:
        logger.root.setLevel(getattr(logging, opts.loglvl.upper()))


    factory = MCBotFactory()
    bot = TestBot()
    factory.bot = bot
    bot.factory = factory
    reactor.connectTCP(host, port, factory)

    run(bot)
    #runIPython(bot)
    #runBPython(bot)

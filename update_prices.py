#!/usr/bin/env python2

import signal
import sys
import os
import optparse
import logging
from ConfigParser import SafeConfigParser
from price_updater import PriceUpdater
from logging.handlers import TimedRotatingFileHandler


VERSION = "1.7.0"
AUTHOR = "Balogh Peter <bercob@gmail.com>"


def signal_handler(signal, frame):
    sys.exit(0)


def help(parser):
    parser.print_help()


def parse_arguments(m_args=None):
    parser = optparse.OptionParser(usage="%s <ini file path>\n\nupdate prices\n\nauthor: %s" % (__file__, AUTHOR))
    parser.add_option("-v", "--version", action="store_true", help="get version", default=False)
    (options, args) = parser.parse_args()

    if m_args is not None:
        args = m_args

    if options.version:
        print(VERSION)
        sys.exit(0)

    if len(args) == 0:
        parser.error('ini file path is required')

    return options, args


def set_logging(ini_parser):
    path = os.path.join(ini_parser.get("logging", "log_file_dir"), ini_parser.get("logging", "log_file_name"))

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logging.getLogger().addHandler(sh)

    logging.getLogger().setLevel(logging.getLevelName(ini_parser.get("logging", "log_level").upper()))

    handler = TimedRotatingFileHandler(path, when="midnight", interval=1, backupCount=7)
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logging.getLogger().addHandler(handler)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    reload(sys)

    (options, args) = parse_arguments()
    ini_parser = SafeConfigParser()
    ini_parser.read(args[0])
    set_logging(ini_parser)

    price_updater = PriceUpdater(ini_parser)
    price_updater.process()

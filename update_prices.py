#!/usr/bin/env python3

import logging
import os
import sys
from argparse import ArgumentParser
from configparser import RawConfigParser
from logging.handlers import TimedRotatingFileHandler

from price_updater import PriceUpdater

VERSION = "3.0.0"
AUTHOR = "Balogh Peter <bercob@gmail.com>"


def parse_arguments():
    parser = ArgumentParser(usage="%s <ini file path>\n\nupdate prices\n\nauthor: %s" % (__file__, AUTHOR))
    parser.add_argument("ini_file_path", help="ini config file path")
    parser.add_argument("-v", "--version", action="version", help="get version", version=VERSION)
    return parser.parse_args()


def set_logging(parser):
    path = os.path.join(parser.get("logging", "log_file_dir"), parser.get("logging", "log_file_name"))

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logging.getLogger().addHandler(sh)

    logging.getLogger().setLevel(logging.getLevelName(parser.get("logging", "log_level").upper()))

    handler = TimedRotatingFileHandler(path, when="midnight", interval=1, backupCount=7)
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logging.getLogger().addHandler(handler)


if __name__ == "__main__":
    args = parse_arguments()
    ini_parser = RawConfigParser()
    ini_parser.read(args.ini_file_path)
    set_logging(ini_parser)

    price_updater = PriceUpdater(ini_parser)
    price_updater.process()

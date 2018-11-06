#!/usr/bin/python
# -*- coding: utf-8 -*-

import optparse
import requests
import logging
import signal
import sys
import urllib
import traceback
import json
import re
import os
from bs4 import BeautifulSoup
from ConfigParser import SafeConfigParser

VERSION = "1.0.0"
AUTHOR = "Balogh Peter <bercob@gmail.com>"


def signal_handler(signal, frame):
    sys.exit(0)


def help(parser):
    parser.print_help()


def set_logging(ini_parser):
    logging.basicConfig(filename = os.path.join(ini_parser.get("logging", "log_file_dir"),
                                                ini_parser.get("logging", "log_file_name")),
                        level = logging.INFO, format = "%(asctime)s %(message)s")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logging.getLogger().addHandler(sh)
    logging.getLogger().setLevel(logging.getLevelName(ini_parser.get("logging", "log_level").upper()))


def parse_arguments(m_args):
    parser = optparse.OptionParser(usage = "%s <ini file path>\n\nupdate prices\n\nauthor: %s" % (__file__, AUTHOR))
    parser.add_option("-v", "--version", action="store_true", help = "get version", default = False)
    (options, args) = parser.parse_args()

    if m_args is not None:
        args = m_args

    if options.version:
        print(VERSION)
        sys.exit(0)

    if len(args) == 0:
        parser.error('ini file path is required')

    return options, args


def url_validator(url):
    regex = re.compile(
        r'^(?:http|ftp)s?://' # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' # domain...
        r'localhost|' # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
        r'(?::\d+)?' # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return re.match(regex, url) is not None


def get_token(session, api_url, login_page, username, password):
    login_response = session.post(api_url + login_page, data = { "username": username, "password": password })
    return json.loads(login_response.text)["token"]


def get_products(session, token, api_url, product_list_page):
    product_list_response = session.get(api_url + product_list_page, params = { "token": token })
    return json.loads(product_list_response.text)["products"]


def open_url_and_parse(session, url):
    logging.debug("opening %s" % url)
    return BeautifulSoup(session.get(url).text, features="html.parser")


def get_product_url(parser, product, product_found_selector, product_link_selector, second_product_link_selector):
    if not parser.select(product_found_selector):
        logging.warning("product %s has not found" % product["name"])
        return None

    product_url = parser.select(product_link_selector)[0]["href"]
    if not url_validator(product_url):
        product_url = parser.select(second_product_link_selector)[0]["href"]
        if not url_validator(product_url):
            logging.warning("%s is not valid url for product %s" % (product_url, product["name"]))
            return None

    return product_url


def get_product_identification(product):
    return "%s (product ID: %s)" % (product["name"], product["product_id"])


def get_min_accepted_price(product, vat, minimum_discount):
    return float(product["mrp_price"]) * (1 + vat) * (1 + minimum_discount)


def main(m_args=None):
    reload(sys)
    sys.setdefaultencoding("utf8")

    (options, args) = parse_arguments(m_args)
    ini_parser = SafeConfigParser()
    ini_parser.read(args[0])
    
    # set constant variables
    # general
    PRICE_UPDATE_ENABLED = ini_parser.get("general", "price_update_enabled")
    VAT = float(ini_parser.get("general", "vat"))
    MY_SHOP_NAME = ini_parser.get("general", "my_shop_name")
    # credentials
    CREDENTIAL_INI_FILE_PATH = os.path.join(ini_parser.get("credentials", "ini_file_dir"), ini_parser.get("credentials", "ini_file_name"))
    # urls
    API_URL = ini_parser.get("urls", "api_url")
    SEARCH_URL = ini_parser.get("urls", "search_url")
    SEARCH_VAR_NAME = ini_parser.get("urls", "search_var_name")
    # pages
    LOGIN_PAGE = ini_parser.get("pages", "login_page")
    PRODUCT_LIST_PAGE = ini_parser.get("pages", "product_list_page")
    PRODUCT_UPDATE_PAGE = ini_parser.get("pages", "product_update_page")
    # price
    MINIMUM_DISCOUNT = float(ini_parser.get("price", "minimum_discount"))
    UNDER_BEST_PRICE_AMOUNT = float(ini_parser.get("price", "under_best_price_amount"))
    # selectors
    PRODUCT_LINK_SELECTOR = ini_parser.get("selectors", "product_link_selector")
    SECOND_PRODUCT_LINK_SELECTOR = ini_parser.get("selectors", "second_product_link_selector")
    PRODUCT_PRICE_SELECTOR = ini_parser.get("selectors", "product_price_selector")
    SHOP_NAME_SELECTOR = ini_parser.get("selectors", "shop_name_selector")
    PRODUCT_NAME_SELECTOR = ini_parser.get("selectors", "product_name_selector")
    PRODUCT_FOUND_SELECTOR = ini_parser.get("selectors", "product_found_selector")

    credentials_ini_parser = SafeConfigParser()
    credentials_ini_parser.read(CREDENTIAL_INI_FILE_PATH)

    # credentials
    USERNAME = credentials_ini_parser.get("authentication", "user_name")
    PASSWORD = credentials_ini_parser.get("authentication", "password")

    set_logging(ini_parser)
    logging.info("starting")
    
    try:
        with requests.Session() as session:
            token = get_token(session, API_URL, LOGIN_PAGE, USERNAME, PASSWORD)

            products = get_products(session, token, API_URL, PRODUCT_LIST_PAGE)
            
            for product in products:
                try:
                    parser = open_url_and_parse(session, "%s/?%s" % (SEARCH_URL, urllib.urlencode({ SEARCH_VAR_NAME: product["name"] })))

                    product_url = get_product_url(parser, product, PRODUCT_FOUND_SELECTOR, PRODUCT_LINK_SELECTOR, SECOND_PRODUCT_LINK_SELECTOR)
                    if product_url is None:
                        continue

                    parser = open_url_and_parse(session, product_url)

                    best_price_array = parser.select(PRODUCT_PRICE_SELECTOR)[0].contents[0].rsplit(" ", 1)
                    best_price = float(best_price_array[0].replace(" ", "").replace(",", "."))
                    best_price_currency = best_price_array[1]
                    best_shop_name = parser.select(SHOP_NAME_SELECTOR)[0].contents[0].strip()
                    product_name = parser.select(PRODUCT_NAME_SELECTOR)[0].contents[0]
                    my_offer_exist = any(MY_SHOP_NAME in shop_name for shop_name in [tag.contents[0] for tag in parser.select(SHOP_NAME_SELECTOR)])
                    min_accepted_price = get_min_accepted_price(product, VAT, MINIMUM_DISCOUNT)

                    logging.debug("Heureka product's name is %s" % product_name)
                    logging.info("best price for %s is %.2f %s from %s (accepted minimum price: %.2f €)" % (get_product_identification(product), best_price, best_price_currency, best_shop_name, min_accepted_price))
                    
                    new_price = best_price - UNDER_BEST_PRICE_AMOUNT
                    if (my_offer_exist and 
                        best_shop_name != MY_SHOP_NAME and 
                        best_price <= float(product["price"]) and
                        float(product["mrp_price"]) > 0 and 
                        new_price >= min_accepted_price
                    ):
                        logging.info("%s price changing from %.2f € to %.2f €" % (get_product_identification(product), float(product["price"]),  new_price))
                        if PRICE_UPDATE_ENABLED == "1":
                            product_update_response = session.post(API_URL + PRODUCT_UPDATE_PAGE, params = { "token": token },  data = { "product_id": product["product_id"], "price":  new_price})
                            if "success" in json.loads(product_update_response.text):
                                logging.info("%s price update has been successful" % get_product_identification(product))
                            else:
                                logging.error("%s price update has been unsuccessful" % get_product_identification(product))
                        else:
                            logging.warning("%s price update is disabled" % get_product_identification(product))
                        
                except:
                    logging.error("error: %s" % traceback.format_exc(sys.exc_info()[2]))
                    continue
    except:
        logging.error("error: %s" % traceback.format_exc(sys.exc_info()[2]))
    
    logging.info("end")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    main()

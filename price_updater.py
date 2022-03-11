# -*- coding: utf-8 -*-

import sys
import requests
import logging
import urllib
import traceback
import json
import re
import os
import time
from bs4 import BeautifulSoup
from ConfigParser import SafeConfigParser

DEVELOPMENT = True


class PriceUpdater:
    def __init__(self, ini_parser):
        sys.setdefaultencoding("utf8")

        # set constant variables
        # general
        self.price_update_enabled = ini_parser.get("general", "price_update_enabled")
        self.vat = float(ini_parser.get("general", "vat"))
        self.my_shop_name = ini_parser.get("general", "my_shop_name")
        self.request_sleep = int(ini_parser.get("general", "request_sleep"))
        self.bot_hunter_title = ini_parser.get("general", "bot_hunter_title")
        # credentials
        self.credential_ini_file_path = os.path.join(ini_parser.get("credentials", "ini_file_dir"), 
                                                     ini_parser.get("credentials", "ini_file_name"))
        # urls
        self.api_url = ini_parser.get("urls", "api_url")
        self.search_url = ini_parser.get("urls", "search_url")
        self.search_var_name = ini_parser.get("urls", "search_var_name")
        # pages
        self.login_page = ini_parser.get("pages", "login_page")
        self.product_list_page = ini_parser.get("pages", "product_list_page")
        self.product_update_page = ini_parser.get("pages", "product_update_page")
        # price
        self.minimum_discount = float(ini_parser.get("price", "minimum_discount"))
        self.under_best_price_amount = float(ini_parser.get("price", "under_best_price_amount"))
        # selectors
        self.product_link_selector = ini_parser.get("selectors", "product_link_selector")
        self.second_product_link_selector = ini_parser.get("selectors", "second_product_link_selector")
        self.product_price_selector = ini_parser.get("selectors", "product_price_selector")
        self.shop_name_selector = ini_parser.get("selectors", "shop_name_selector")
        self.product_name_selector = ini_parser.get("selectors", "product_name_selector")
        self.product_found_selector = ini_parser.get("selectors", "product_found_selector")

        self.credentials_ini_parser = SafeConfigParser()
        self.credentials_ini_parser.read(self.credential_ini_file_path)

        # credentials
        self.username = self.credentials_ini_parser.get("authentication", "user_name")
        self.password = self.credentials_ini_parser.get("authentication", "password")

        # cookies
        self.cookies_domain = self.credentials_ini_parser.get("cookies", "domain")
        self.bot_hunter_cookie = self.credentials_ini_parser.get("cookies", "bot_hunter")
        
    @staticmethod
    def __url_validator(url):
        regex = re.compile(
            r'^(?:http|ftp)s?://' # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' # domain...
            r'localhost|' # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
            r'(?::\d+)?' # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        return re.match(regex, url) is not None

    def __get_token(self, session):
        login_response = session.post(self.api_url + self.login_page, data={"username": self.username, "password": self.password})
        return json.loads(login_response.text)["token"]

    def __get_products(self, session, token):
        product_list_response = session.get(self.api_url + self.product_list_page, params={"token": token})
        return json.loads(product_list_response.text)["products"]

    def __open_url_and_parse(self, session, url):
        logging.debug("sleeping %d seconds" % self.request_sleep)
        time.sleep(self.request_sleep)
        logging.debug("opening %s" % url)
        response = session.get(url)
        logging.debug("Response URL: %s" % response.url)
        return BeautifulSoup(response.text, features="html.parser")

    def __get_product_url(self, parser, product):
        # find the searched product by exact name
        exact_name_parser = parser
        search_results_tag = exact_name_parser.find("div", class_="c-product-list")
        if search_results_tag is not None:
            for tag in search_results_tag.find_all("a", class_="c-product__link"):
                if product["name"] in tag.contents[0] and self.valid_product_url(tag["href"], self.search_url):
                    return tag["href"]

    def valid_product_url(self, product_url, search_url):
        return self.__url_validator(product_url) and "%s/exit" % search_url not in product_url

    @staticmethod
    def __get_product_identification(product):
        return "%s (product ID: %s)" % (product["name"], product["product_id"])

    def __get_min_accepted_price(self, product):
        return float(product["mrp_price"]) * (1 + self.vat) * (1 + self.minimum_discount)

    @staticmethod
    def __get_product_price(product):
        if 0 < float(product["special"]) < float(product["price"]):
            return round(float(product["special"]), 2)
        else:
            return round(float(product["price"]), 2)

    def __bot_hunter_page(self, parser):
        return parser.title.contents[0] == self.bot_hunter_title

    def __set_bot_hunter_cookie(self, session):
        if self.bot_hunter_cookie:
            bot_hunter_cookie_obj = requests.cookies.create_cookie(domain=self.cookies_domain,
                                                                   name='bothunter',
                                                                   value=self.bot_hunter_cookie)
            session.cookies.set_cookie(bot_hunter_cookie_obj)

    def __update_price(self, product, new_price, session, token):
        logging.info("%s price changing from %.2f € to %.2f €" % (self.__get_product_identification(product),
                                                                  self.__get_product_price(product),
                                                                  new_price))
        if self.price_update_enabled == "1":
            product_update_response = session.post(self.api_url + self.product_update_page,
                                                   params={"token": token},
                                                   data={"product_id": product["product_id"], "price": new_price})
            if "success" in json.loads(product_update_response.text):
                logging.info("%s price update has been successful" % self.__get_product_identification(product))
            else:
                logging.error("%s price update has been unsuccessful" % self.__get_product_identification(product))
        else:
            logging.warning("%s price update is disabled" % self.__get_product_identification(product))

    def __process_product(self, product, parser, session, token):
        product_url = self.__get_product_url(parser, product)
        if product_url is None:
            logging.error("URL for product %s has been not found" % product["name"])
            return

        parser = self.__open_url_and_parse(session, product_url)

        product_prices = parser.select(self.product_price_selector)
        if product_prices is None or len(product_prices) == 0:
            logging.error("Error parsing product prices")
            return
        best_price_array = product_prices[0].contents[0].rsplit(" ", 1)
        best_price = float(best_price_array[0].replace(" ", "").replace(",", "."))
        best_price_currency = best_price_array[1]
        best_shop_name = parser.select(self.shop_name_selector)[0].contents[0].strip()

        second_best_price = second_best_price_currency = None
        if len(product_prices) > 1:
            second_best_price_array = product_prices[1].contents[0].rsplit(" ", 1)
            second_best_price = float(second_best_price_array[0].replace(" ", "").replace(",", "."))
            second_best_price_currency = second_best_price_array[1]

        product_name = parser.select(self.product_name_selector)[0].contents[0]
        my_offer_exist = any(self.my_shop_name in shop_name for shop_name in
                             [tag.contents[0] for tag in parser.select(self.shop_name_selector)])
        min_accepted_price = self.__get_min_accepted_price(product)

        if product["limit"] is not None and float(product["limit"]) >= 0:
            under_best_price_amount = float(product["limit"])
        else:
            under_best_price_amount = self.under_best_price_amount

        logging.debug("Heureka product's name is %s" % product_name)
        logging.info("The best price for %s is %.2f %s from %s (accepted minimum price: %.2f €, limit: %.2f €)" % (self.__get_product_identification(product), 
                                                                                                                   best_price, 
                                                                                                                   best_price_currency, 
                                                                                                                   best_shop_name, 
                                                                                                                   min_accepted_price, 
                                                                                                                   under_best_price_amount))
        if best_shop_name == self.my_shop_name and second_best_price is not None:
            logging.info("The second best price for %s is %.2f %s" % (self.__get_product_identification(product), 
                                                                      second_best_price, 
                                                                      second_best_price_currency))

        if not my_offer_exist:
            logging.info("My offer does not exist for product %s" % product["name"])
            return

        if float(product["mrp_price"]) <= 0:
            logging.info('MRP price is not set (%s)' % product["mrp_price"])
            return

        new_price = None
        if best_shop_name == self.my_shop_name:
            if second_best_price is not None:
                new_price = round(second_best_price - under_best_price_amount, 2)
        else:
            new_price = round(best_price - under_best_price_amount, 2)

        if new_price is not None and new_price != self.__get_product_price(product) and new_price >= min_accepted_price:
            self.__update_price(product, new_price, session, token)

    def process(self):
        logging.info("starting")

        try:
            with requests.Session() as session:
                self.__set_bot_hunter_cookie(session)

                token = self.__get_token(session)
                products = self.__get_products(session, token)

                for index, product in enumerate(products):
                    if DEVELOPMENT and index > 0:
                        break
                    try:
                        parser = self.__open_url_and_parse(session, "%s/?%s" % (self.search_url, 
                                                                                urllib.urlencode({self.search_var_name: product["name"]})))
                        if self.__bot_hunter_page(parser):
                            logging.warning("Bot Hunter page has been occurred")
                            logging.debug(parser.contents)
                            break

                        self.__process_product(product, parser, session, token)

                    except:
                        logging.error("error: %s" % traceback.format_exc(sys.exc_info()[2]))
        except:
            logging.error("error: %s" % traceback.format_exc(sys.exc_info()[2]))

        logging.info("end")

import json
import logging
import os
import random
import re
import time
import traceback
from configparser import RawConfigParser

import requests
from bs4 import BeautifulSoup

DEVELOPMENT = os.getenv("DEVELOPMENT", "False").lower() in ("true", "1", "t")


class PriceUpdater:
    def __init__(self, ini_parser):
        # set constant variables
        # general
        self.price_update_enabled = ini_parser.get("general", "price_update_enabled")
        self.vat = float(ini_parser.get("general", "vat"))
        self.my_shop_name = ini_parser.get("general", "my_shop_name")
        self.request_sleep = int(ini_parser.get("general", "request_sleep"))
        self.request_timeout = int(ini_parser.get("general", "request_timeout"))
        self.bot_hunter_title = ini_parser.get("general", "bot_hunter_title")
        # credentials
        self.credential_ini_file_path = os.path.join(
            ini_parser.get("credentials", "ini_file_dir"), ini_parser.get("credentials", "ini_file_name")
        )
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

        self.credentials_ini_parser = RawConfigParser()
        self.credentials_ini_parser.read(self.credential_ini_file_path)

        # credentials
        self.username = self.credentials_ini_parser.get("authentication", "user_name")
        self.password = self.credentials_ini_parser.get("authentication", "password")

        # cookies
        self.cookies_domain = self.credentials_ini_parser.get("cookies", "domain")
        self.bot_hunter_cookie = self.credentials_ini_parser.get("cookies", "bot_hunter")

        # user agents
        with open("user_agents.json", "r") as f_user_agents:
            self.user_agents = json.load(f_user_agents).get("result", [])

    @staticmethod
    def __url_validator(url):
        regex = re.compile(
            r"^(?:http|ftp)s?://"  # http:// or https://
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # domain...
            r"localhost|"  # localhost...
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
            r"(?::\d+)?"  # optional port
            r"(?:/?|[/?]\S+)$",
            re.IGNORECASE,
        )

        return re.match(regex, url) is not None

    def __get_token(self, session):
        login_response = session.post(
            self.api_url + self.login_page,
            headers={"User-Agent": self.__get_random_user_agent()},
            data={"username": self.username, "password": self.password},
            timeout=self.request_timeout,
        )
        login_response.raise_for_status()
        return json.loads(login_response.text)["token"]

    def __get_products(self, session, token):
        product_list_response = session.get(
            self.api_url + self.product_list_page,
            headers={"User-Agent": self.__get_random_user_agent()},
            params={"token": token},
            timeout=self.request_timeout,
        )
        product_list_response.raise_for_status()
        return json.loads(product_list_response.text)["products"]

    def __open_url_and_parse(self, session, url, **params):
        logging.debug("sleeping %d seconds" % self.request_sleep)
        time.sleep(self.request_sleep)
        logging.debug("opening %s" % url)
        logging.debug(f"{params=}")
        response = session.get(
            url, headers={"User-Agent": self.__get_random_user_agent()}, params=params, timeout=self.request_timeout
        )
        response.raise_for_status()
        logging.debug("Response URL: %s" % response.url)
        return BeautifulSoup(response.text, features="html.parser")

    def __get_product_url(self, parser, product):
        logging.debug(f"{product['name']=}")
        for tag in parser.select("a.c-product__link"):
            if product["name"] in tag.contents[0] and self.valid_product_url(tag["href"], self.search_url):
                return tag["href"]

    def valid_product_url(self, product_url, search_url):
        return self.__url_validator(product_url) and "%s/exit" % search_url not in product_url

    @staticmethod
    def __get_product_identification(product):
        return "%s (product ID: %s)" % (product["name"], product["product_id"])

    def __get_min_accepted_price(self, product):
        return self.__get_mrp_price(product) * (1 + self.vat) * (1 + self.minimum_discount)

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
            session.cookies.set("bothunter", self.bot_hunter_cookie, domain=self.cookies_domain)

    def __update_price(self, product, new_price, session, token):
        logging.info(
            "%s price changing from %.2f € to %.2f €"
            % (self.__get_product_identification(product), self.__get_product_price(product), new_price)
        )
        if self.price_update_enabled == "1":
            product_update_response = session.post(
                self.api_url + self.product_update_page,
                headers={"User-Agent": self.__get_random_user_agent()},
                params={"token": token},
                data={"product_id": product["product_id"], "price": new_price},
                timeout=self.request_timeout,
            )
            product_update_response.raise_for_status()
            if "success" in json.loads(product_update_response.text):
                logging.info("%s price update has been successful" % self.__get_product_identification(product))
            else:
                logging.error("%s price update has been unsuccessful" % self.__get_product_identification(product))
        else:
            logging.warning("%s price update is disabled" % self.__get_product_identification(product))

    @staticmethod
    def __get_shop_offers(parser):
        offers = parser.select("section.c-offer")
        shop_offers = []
        for offer in offers:
            offer_price_span = offer.select("span.c-offer__price")
            if len(offer_price_span) > 0:
                price_array = offer_price_span[0].contents[0].rsplit("\xa0", 1)
                price = float(price_array[0].replace(",", "."))
                shop_offers.append((price, price_array[1], offer.select("img.c-offer__shop-logo")[0]["alt"]))
        shop_offers.sort(key=lambda tup: tup[0])
        return shop_offers

    @staticmethod
    def __get_product_name(parser):
        return parser.select("h1.c-product-info__name")[0].contents[0]

    def __is_my_offer_exist(self, shop_offers):
        return self.my_shop_name in [shop[2] for shop in shop_offers]

    def __get_under_best_price_amount(self, product):
        if product["limit"] is not None and float(product["limit"]) >= 0:
            return float(product["limit"])
        else:
            return self.under_best_price_amount

    def __get_new_price(
        self,
        product,
        best_price,
        best_shop_name,
        second_best_price,
        second_best_price_currency,
        under_best_price_amount,
    ):
        if best_shop_name == self.my_shop_name:
            if second_best_price is not None:
                logging.info(
                    "The second best price for %s is %.2f %s"
                    % (self.__get_product_identification(product), second_best_price, second_best_price_currency)
                )
                return round(second_best_price - under_best_price_amount, 2)
        else:
            return round(best_price - under_best_price_amount, 2)

    @staticmethod
    def __get_mrp_price(product):
        try:
            return float(product["mrp_price"])
        except ValueError:
            return 0

    def __get_random_user_agent(self):
        return self.user_agents[random.randint(0, len(self.user_agents) - 1)]

    def __process_product(self, product, parser, session, token):
        product_url = self.__get_product_url(parser, product)
        if product_url is None:
            logging.error("URL for product %s has been not found" % product["name"])
            return

        parser = self.__open_url_and_parse(session, product_url)

        shop_offers = self.__get_shop_offers(parser)
        if len(shop_offers) == 0:
            logging.error("Error parsing product prices")
            return

        best_price = shop_offers[0][0]
        best_price_currency = shop_offers[0][1]
        best_shop_name = shop_offers[0][2]

        second_best_price, second_best_price_currency = (
            [shop_offers[0][0], shop_offers[0][1]] if len(shop_offers) > 1 else [None, None]
        )

        product_name = self.__get_product_name(parser)
        my_offer_exist = self.__is_my_offer_exist(shop_offers)
        min_accepted_price = self.__get_min_accepted_price(product)
        under_best_price_amount = self.__get_under_best_price_amount(product)

        logging.debug("Heureka product's name is %s" % product_name)
        logging.info(
            "The best price for %s is %.2f %s from %s (accepted minimum price: %.2f €, limit: %.2f €)"
            % (
                self.__get_product_identification(product),
                best_price,
                best_price_currency,
                best_shop_name,
                min_accepted_price,
                under_best_price_amount,
            )
        )
        if not my_offer_exist:
            logging.info("My offer does not exist for product %s" % product["name"])
            return

        if self.__get_mrp_price(product) <= 0:
            logging.info("MRP price is not set (%s)" % product["mrp_price"])
            return

        new_price = self.__get_new_price(
            product, best_price, best_shop_name, second_best_price, second_best_price_currency, under_best_price_amount
        )

        logging.debug(f"New price should be: {new_price}")

        if new_price is not None and new_price != self.__get_product_price(product) and new_price >= min_accepted_price:
            self.__update_price(product, new_price, session, token)
        else:
            logging.info("New price has not been updated")

    def process(self):
        logging.info("starting")

        try:
            with requests.Session() as session:
                self.__set_bot_hunter_cookie(session)

                token = self.__get_token(session)
                products = self.__get_products(session, token)
                logging.debug(f"{products=}")

                for index, product in enumerate(products):
                    if DEVELOPMENT and index > 0:
                        break
                    try:
                        parser = self.__open_url_and_parse(
                            session, self.search_url, **{self.search_var_name: product["name"]}
                        )
                        if self.__bot_hunter_page(parser):
                            logging.warning("Bot Hunter page has been occurred")
                            logging.debug(parser.contents)
                            break
                        self.__process_product(product, parser, session, token)

                    except Exception as error:
                        logging.error("error: %s\n%s" % (error, traceback.format_exc()))
        except Exception as error:
            logging.error("error: %s\n%s" % (error, traceback.format_exc()))

        logging.info("end")

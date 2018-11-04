#!/usr/bin/python
# -*- coding: utf-8 -*-

import optparse, requests, logging, signal, sys, urllib, traceback, json,  re
from bs4 import BeautifulSoup
from ConfigParser import SafeConfigParser

VERSION = "1.0.0"
AUTHOR = "Balogh Peter <bercob@gmail.com>"

def signal_handler(signal, frame):
	sys.exit(0)

def help(parser):
	parser.print_help()

def set_logging(ini_parser):
	logging.basicConfig(filename = ini_parser.get("logging", "log_file_path"), level = logging.INFO, format = "%(asctime)s %(message)s")
	sh = logging.StreamHandler(sys.stdout)
	sh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
	logging.getLogger().addHandler(sh)

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
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
        r'localhost|' #localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
        r'(?::\d+)?' # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return re.match(regex, url) is not None
        
def main(m_args=None):
    reload(sys)
    sys.setdefaultencoding("utf8")

    (options, args) = parse_arguments(m_args)
    ini_parser = SafeConfigParser()
    ini_parser.read(args[0])
    
    set_logging(ini_parser)
    
    logging.info("starting")
    
    credentials_ini_parser = SafeConfigParser()
    credentials_ini_parser.read(ini_parser.get("credentials", "ini_file_path"))
    
    try:
        with requests.Session() as session:
            login_response = session.post(ini_parser.get("urls", "api_url") + ini_parser.get("pages", "login_page"), data = { "username": credentials_ini_parser.get("authentication", "user_name"), "password": credentials_ini_parser.get("authentication", "password") })
            token = json.loads(login_response.text)["token"]
            product_list_response = session.get(ini_parser.get("urls", "api_url") + ini_parser.get("pages", "product_list_page"),  params = { "token": token })
            products = json.loads(product_list_response.text)["products"]
            
            for product in products:
#                TODO: remove restrictions
                if float(product["price"]) < 1000:
                    continue
#                if product["product_id"] != "560":
#                    continue
                
                try:
                    url = "%s/?%s" % (ini_parser.get("urls", "search_url"), urllib.urlencode({ ini_parser.get("urls", "search_var_name"): product["name"] }))
                    logging.debug("opening %s" % url)
                    search_response = session.get(url)
                    bs = BeautifulSoup(search_response.text, features = "html.parser")
                    
                    if not bs.select(ini_parser.get("selectors", "product_found_selector")):
                        logging.warning("product %s has not found" % product["name"])
                        continue
                        
                    product_url = bs.select(ini_parser.get("selectors", "product_link_selector"))[0]["href"]
                    if not url_validator(product_url):
                        product_url = bs.select(ini_parser.get("selectors", "second_product_link_selector"))[0]["href"]
                        if not url_validator(product_url):
                            logging.warning("%s is not valid url for product %s" % (product_url,  product["name"]))
                            continue
                    logging.debug("opening %s" % product_url)
                    product_response = session.get(product_url)
                    bs = BeautifulSoup(product_response.text, features = "html.parser")
                    
                    best_price_array = bs.select(ini_parser.get("selectors", "product_price_selector"))[0].contents[0].rsplit(" ", 1)
                    best_price = float(best_price_array[0].replace(" ", "").replace(",","."))
                    best_price_currency = best_price_array[1]
                    best_shop_name = bs.select(ini_parser.get("selectors", "shop_name_selector"))[0].contents[0].strip()
                    product_name = bs.select(ini_parser.get("selectors", "product_name_selector"))[0].contents[0]
                    my_offer_exist = any(ini_parser.get("general", "my_shop_name") in shop_name for shop_name in [tag.contents[0] for tag in bs.select(ini_parser.get("selectors", "shop_name_selector"))])
                    
                    logging.info("best price for %s (%s) is %.2f %s from %s" % (product["name"], product_name, best_price, best_price_currency, best_shop_name))
                    
                    new_price = best_price -  float(ini_parser.get("price", "under_best_price_amount"))
                    if (my_offer_exist and 
                        best_shop_name != ini_parser.get("general", "my_shop_name") and 
                        best_price < float(product["price"]) and 
                        float(product["mrp_price"]) > 0 and 
                        new_price >= float(product["mrp_price"]) * (1 + float(ini_parser.get("general", "vat"))) * (1 + float(ini_parser.get("price", "minimum_discount")))
                    ):
                        logging.info("price changing from %.2f to %.2f" % (float(product["price"]),  new_price))
                        if ini_parser.get("general", "price_update_enabled") == "1":
                            product_update_response = session.post(ini_parser.get("urls", "api_url") + ini_parser.get("pages", "product_update_page"), params = { "token": token },  data = { "product_id": product["product_id"], "price":  new_price})
                            if "success" in json.loads(product_update_response.text):
                                logging.info("price update has been successful")
                            else:
                                logging.error("price update has been unsuccessful")
                        else:
                            logging.warning("price update is disabled")
                        
                except:
                    logging.error("error: %s" % traceback.format_exc(sys.exc_info()[2]))
                    continue
    except:
        logging.error("error: %s" % traceback.format_exc(sys.exc_info()[2]))
    
    logging.info("end")

#-------------------------------    
if __name__ == "__main__":
	signal.signal(signal.SIGINT, signal_handler)
	main()


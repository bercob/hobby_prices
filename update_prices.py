#!/usr/bin/python
# -*- coding: utf-8 -*-

import optparse, requests, logging, signal, sys, urllib, urllib3, urlparse, traceback
from bs4 import BeautifulSoup
from ConfigParser import SafeConfigParser

VERSION = "1.0.0"
AUTHOR = "Balogh Peter <bercob@gmail.com>"

SEARCH_URL = "https://www.heureka.sk"
SEARCH_VAR = "h[fraze]"
MY_SHOP_NAME = "HOBBY-Németh"
PRODUCT_LINK_SELECTOR = "div.product a"
PRODUCT_PRICE_SELECTOR = "div.shopspr.bottom a.pricen"
SHOP_NAME_SELECTOR = "div.shopspr.bottom a.shop-name__link"
PRODUCT_NAME_SELECTOR = "div.main-info h1"
PRODUCT_FOUND_SELECTOR = "div#search > div.product"

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
	parser = optparse.OptionParser(usage = "%s <product name>\n\nupdate price\n\nauthor: %s" % (__file__, AUTHOR))
	parser.add_option("-v", "--version", action="store_true", help = "get version", default = False)
	(options, args) = parser.parse_args()
	
	if m_args is not None:
		args = m_args

	if options.version:
		print VERSION
		sys.exit(0)
	
	if len(args) == 0:
		parser.error('ini file path is required')

	return options, args

def main(m_args=None):
	reload(sys)
	sys.setdefaultencoding("utf8")

	urllib3.disable_warnings()

	(options, args) = parse_arguments(m_args)

	ini_parser = SafeConfigParser()
	ini_parser.read(args[0])

	set_logging(ini_parser)

	logging.info("starting")

	credentials_ini_parser = SafeConfigParser()
	credentials_ini_parser.read(ini_parser.get("credentials", "ini_file_path"))

	http = urllib3.PoolManager()

	try:

		with requests.Session() as s:
		    login_response = s.post(ini_parser.get("urls", "api_url") + ini_parser.get("pages", "login_page"), data = { "username": credentials_ini_parser.get("authentication", "user_name"), "password": credentials_ini_parser.get("authentication", "password") })
		    token = urlparse.parse_qs(urlparse.urlparse(login_response.url).query)["token"][0]
		    
		    product_list_response = s.get(ini_parser.get("urls", "api_url") + ini_parser.get("pages", "product_list_page"), params = { "token": token })

		    print product_list_response

	# for product in args:
	# 	try:
	# 		url = "%s/?%s" % (SEARCH_URL, urllib.urlencode({ SEARCH_VAR: product }))

	# 		logging.info("opening %s" % url)

	# 		r = http.request("GET", url)

	# 		bs = BeautifulSoup(r.data, features = "html.parser")

	# 		if not bs.select(PRODUCT_FOUND_SELECTOR):
	# 			logging.info("product %s has not found" % product)
	# 			continue

	# 		product_url = bs.select(PRODUCT_LINK_SELECTOR)[0]["href"]

	# 		logging.info("opening %s" % product_url)

	# 		r = http.request("GET", product_url)		
		
	# 		bs = BeautifulSoup(r.data, features = "html.parser")
			
	# 		best_price_array = bs.select(PRODUCT_PRICE_SELECTOR)[0].contents[0].rsplit(" ", 1)
	# 		best_price = float(best_price_array[0].replace(" ", "").replace(",","."))
	# 		best_price_currency = best_price_array[1]
	# 		best_shop_name = bs.select(SHOP_NAME_SELECTOR)[0].contents[0].strip()
	# 		product_name = bs.select(PRODUCT_NAME_SELECTOR)[0].contents[0]
	# 		my_offer_exist = any(MY_SHOP_NAME in shop_name for shop_name in [tag.contents[0] for tag in bs.select(SHOP_NAME_SELECTOR)])
			
	# 		logging.info("best price for %s (%s) is %.2f %s from %s" % (product, product_name, best_price, best_price_currency, best_shop_name))

	# 		if my_offer_exist and best_shop_name != MY_SHOP_NAME:
	# 			logging.info("price changing")

	except:
		logging.error("error: %s" % traceback.format_exc(sys.exc_info()[2]))

	logging.info("end")

#-------------------------------    
if __name__ == "__main__":
	signal.signal(signal.SIGINT, signal_handler)
	main()

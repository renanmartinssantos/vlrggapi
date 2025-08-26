import requests
from bs4 import BeautifulSoup
import logging
from utils.utils import headers
import traceback

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scraper_debug.log", mode="w"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('matchDetails_test')

def test_match_details():
    try:
        match_id = '246550'
        url = f"https://www.vlr.gg/{match_id}"
        logger.info(f"Making request to: {url}")
        resp = requests.get(url, headers=headers)
        logger.info(f"Response status code: {resp.status_code}")
        if resp.status_code != 200:
            logger.error(f"Failed to fetch match details. Status code: {resp.status_code}")
            return {"error": f"Failed to fetch match details. Status code: {resp.status_code}"}
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        logger.info("Successfully parsed HTML")
        
        # Test basic extraction
        tournament_element = soup.select_one(".match-header-event div[style='font-weight: 700;']")
        tournament_name = tournament_element.get_text(strip=True) if tournament_element else None
        logger.info(f"Tournament Name: {tournament_name}")
        
        # Return success
        return {"success": True, "tournament_name": tournament_name}
    except Exception as e:
        logger.error(f"Exception: {str(e)}")
        logger.error(traceback.format_exc())
        return {"error": str(e), "traceback": traceback.format_exc()}

if __name__ == "__main__":
    result = test_match_details()
    print(result)

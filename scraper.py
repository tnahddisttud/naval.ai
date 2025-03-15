import argparse
import csv
import random
import time
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


class TwitterSeleniumScraper:
    def __init__(self, headless=True):
        print("Initializing the scraper...")
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--lang=en")

        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")

        try:
            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        except Exception as e:
            print(f"Error setting up Chrome driver: {e}")
            print("Trying alternative setup method...")
            self.driver = webdriver.Chrome(options=chrome_options)

        self.wait = WebDriverWait(self.driver, 10)

    def handle_login_popup(self):
        """Handle the login popup that might appear"""
        try:
            time.sleep(2)

            possible_selectors = [
                "//span[contains(text(), 'Not now')]",
                "//span[contains(text(), 'Close')]",
                "//div[@role='button' and @aria-label='Close']",
                "//div[@data-testid='mask']"
            ]

            for selector in possible_selectors:
                try:
                    popup_element = self.driver.find_element(By.XPATH, selector)
                    popup_element.click()
                    print("Closed a popup")
                    time.sleep(1)
                    return True
                except:
                    continue

            return False
        except Exception as e:
            print(f"Error handling popups: {e}")
            return False

    def scroll_page(self, pause_time=1.0):
        """Scroll down the page to load more tweets"""
        last_height = self.driver.execute_script("return document.body.scrollHeight")

        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause_time)

        new_height = self.driver.execute_script("return document.body.scrollHeight")
        return new_height != last_height

    def scrape_tweets(self, username, max_tweets=100, include_replies=False, include_retweets=False):
        """Scrape tweets from a user's timeline"""
        tweets = []
        url = f"https://twitter.com/{username}"

        try:
            print(f"Navigating to {url}...")
            self.driver.get(url)
            time.sleep(3)

            self.handle_login_popup()

            # Check if the account exists
            if "This account doesn't exist" in self.driver.page_source:
                print(f"Account @{username} doesn't exist.")
                return tweets

            print("Scrolling to load tweets...")
            scroll_attempts = 0
            max_scroll_attempts = max(10, max_tweets // 5)

            while len(tweets) < max_tweets and scroll_attempts < max_scroll_attempts:
                try:
                    tweet_elements = self.driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
                    new_tweets_found = False

                    for tweet_elem in tweet_elements:
                        tweet_id = None
                        try:
                            # Extract tweet ID from an element with a link
                            link_elem = tweet_elem.find_element(By.CSS_SELECTOR, 'a[href*="/status/"]')
                            href = link_elem.get_attribute('href')
                            if '/status/' in href:
                                tweet_id = href.split('/status/')[1].split('?')[0]
                        except:
                            pass

                        # Skip if we've already processed this tweet
                        if tweet_id and any(t.get('tweet_id') == tweet_id for t in tweets):
                            continue

                        try:
                            # Check if it's a retweet
                            is_retweet = False
                            try:
                                retweet_indicator = tweet_elem.find_element(By.XPATH,
                                                                            './/span[contains(text(), "Retweeted")]')
                                is_retweet = True
                            except NoSuchElementException:
                                pass

                            if is_retweet and not include_retweets:
                                continue

                            # Check if it's a reply
                            is_reply = False
                            try:
                                reply_indicator = tweet_elem.find_element(By.XPATH,
                                                                          './/span[contains(text(), "Replying to")]')
                                is_reply = True
                            except NoSuchElementException:
                                pass

                            if is_reply and not include_replies:
                                continue

                            tweet_text = ""
                            try:
                                text_elem = tweet_elem.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
                                tweet_text = text_elem.text
                            except NoSuchElementException:
                                # Some tweets might not have text (just images/videos)
                                pass

                            timestamp = None
                            try:
                                time_elem = tweet_elem.find_element(By.TAG_NAME, 'time')
                                timestamp = time_elem.get_attribute('datetime')
                            except:
                                pass

                            # Get tweet stats (likes, retweets, replies)
                            stats = {}
                            for stat_type in ['reply', 'retweet', 'like']:
                                try:
                                    stat_elem = tweet_elem.find_element(By.CSS_SELECTOR,
                                                                        f'div[data-testid="{stat_type}"]')
                                    count_text = stat_elem.text.strip()
                                    # Convert "1,234" to "1234"
                                    count = count_text.replace(',', '') if count_text else "0"
                                    stats[stat_type] = count
                                except:
                                    stats[stat_type] = "0"

                            # Add the tweet to our collection
                            tweets.append({
                                'tweet_id': tweet_id,
                                'username': username,
                                'text': tweet_text,
                                'timestamp': timestamp,
                                'is_retweet': is_retweet,
                                'is_reply': is_reply,
                                'replies': stats.get('reply', '0'),
                                'retweets': stats.get('retweet', '0'),
                                'likes': stats.get('like', '0')
                            })

                            new_tweets_found = True
                            print(f"Scraped tweet: {tweet_text[:50]}..." if len(
                                tweet_text) > 50 else f"Scraped tweet: {tweet_text}")

                            if len(tweets) >= max_tweets:
                                break

                        except Exception as e:
                            print(f"Error parsing tweet: {str(e)}")
                            continue

                    more_content_available = self.scroll_page(
                        random.uniform(1.5, 3.0))  # Random delay to look more human

                    if not new_tweets_found and not more_content_available:
                        scroll_attempts += 1
                    else:
                        scroll_attempts = 0  # Reset counter if we found new content

                except Exception as e:
                    print(f"Error during scrolling/scraping: {str(e)}")
                    scroll_attempts += 1
                    time.sleep(2)

            print(f"Finished scraping. Found {len(tweets)} tweets.")
            return tweets

        except Exception as e:
            print(f"Scraping error: {str(e)}")
            return tweets
        finally:
            # Don't close the driver here so we can use it for multiple usernames if needed
            pass

    def close(self):
        """Close the browser"""
        if hasattr(self, 'driver'):
            self.driver.quit()

    def save_to_csv(self, tweets, filename=None):
        """Save tweets to a CSV file"""
        if not filename:
            filename = f"tweets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        try:
            with open(filename, 'w', newline='', encoding='utf-8') as file:
                if not tweets:
                    print("No tweets to save.")
                    return

                fieldnames = tweets[0].keys()
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()

                for tweet in tweets:
                    writer.writerow(tweet)

            print(f"Saved {len(tweets)} tweets to {filename}")
            return filename
        except Exception as e:
            print(f"Error saving to CSV: {e}")
            return None


def main():
    parser = argparse.ArgumentParser(description='Scrape tweets from a Twitter account using Selenium')
    parser.add_argument('username', type=str, help='Twitter username to scrape (without @)')
    parser.add_argument('--max', type=int, default=50, help='Maximum number of tweets to scrape')
    parser.add_argument('--include-replies', action='store_true', help='Include replies in the scraped tweets')
    parser.add_argument('--include-retweets', action='store_true', help='Include retweets in the scraped tweets')
    parser.add_argument('--output', type=str, help='Output CSV filename')
    parser.add_argument('--headless', action='store_true', default=True, help='Run browser in headless mode')

    args = parser.parse_args()

    try:
        scraper = TwitterSeleniumScraper(headless=args.headless)
        print(f"Scraping tweets from @{args.username}...")

        tweets = scraper.scrape_tweets(
            username=args.username,
            max_tweets=args.max,
            include_replies=args.include_replies,
            include_retweets=args.include_retweets
        )

        if tweets:
            output_file = args.output if args.output else f"{args.username}_tweets.csv"
            scraper.save_to_csv(tweets, output_file)

        scraper.close()

    except Exception as e:
        print(f"An error occurred: {str(e)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Xiaohongshu (RedNote) Content Scraper with Enhanced Debugging
Scrapes posts and comments based on Chinese keywords
"""

import json
import time
import random
from typing import List, Dict, Any
from dataclasses import dataclass, asdict
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)
from selenium.webdriver.common.keys import Keys
import logging
from bs4 import BeautifulSoup
import re
from urllib.parse import quote

# Configure logging with DEBUG level
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class Comment:
    """Represents a comment on a post"""

    comment: str
    likes: int


@dataclass
class Post:
    """Represents a Xiaohongshu post"""

    post_url: str
    post_content: str
    author: str
    author_profile_page: str
    comments: List[Dict[str, Any]]


class XiaohongshuScraper:
    """Main scraper class for Xiaohongshu content with enhanced debugging"""

    def __init__(self, headless: bool = False, debug: bool = True):
        """
        Initialize the scraper with Chrome WebDriver

        Args:
            headless: Run browser in headless mode (may not work well with XHS)
            debug: Enable debug output
        """
        self.debug = debug
        self.setup_driver(headless)
        self.base_url = "https://www.xiaohongshu.com"
        self.search_url = f"{self.base_url}/search_result"
        logger.info(f"Scraper initialized. Base URL: {self.base_url}")

    def setup_driver(self, headless: bool):
        """Setup Chrome WebDriver with anti-detection measures"""
        logger.debug("Setting up Chrome WebDriver...")
        chrome_options = Options()

        # Anti-detection measures
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        # User agent
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        chrome_options.add_argument(f"user-agent={user_agent}")

        # Additional options for better compatibility
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--allow-running-insecure-content")
        chrome_options.add_argument("--window-size=1920,1080")

        if headless:
            chrome_options.add_argument("--headless=new")  # Use new headless mode
            logger.warning(
                "Running in headless mode - this may not work well with Xiaohongshu"
            )

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            # Execute CDP commands to mask webdriver
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": """
                    Object.defineProperty(navigator, "webdriver", {get: () => undefined});
                    Object.defineProperty(navigator, "plugins", {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, "languages", {get: () => ["zh-CN", "zh", "en"]});
                """
                },
            )
            logger.info("Chrome driver initialized successfully")

            # Test if we can access the site
            logger.debug("Testing access to Xiaohongshu...")
            self.driver.get(self.base_url)
            time.sleep(3)
            logger.debug(f"Current URL: {self.driver.current_url}")
            logger.debug(f"Page title: {self.driver.title}")

        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            raise

    def search_posts(
        self, keyword: str, min_likes: int = 100, max_posts: int = 20
    ) -> List[str]:
        """
        Search for posts based on keyword and filter by minimum likes

        Args:
            keyword: Chinese keyword to search
            min_likes: Minimum number of likes required
            max_posts: Maximum number of posts to collect

        Returns:
            List of post URLs that meet criteria
        """
        post_urls = []

        try:
            # Method 1: Try direct search URL
            encoded_keyword = quote(keyword)
            search_query = f"{self.base_url}/search_result?keyword={encoded_keyword}&source=web_search_result_notes"
            logger.info(f"Navigating to search URL: {search_query}")

            self.driver.get(search_query)
            time.sleep(random.uniform(5, 7))

            # Debug: Save screenshot
            self.driver.save_screenshot("debug_search_page.png")
            logger.debug("Screenshot saved as debug_search_page.png")

            # Debug: Print page source snippet
            page_source = self.driver.page_source
            logger.debug(f"Page source length: {len(page_source)}")

            # Check if we need to handle any popups or login prompts
            self.handle_popups()

            # Multiple selector strategies for finding posts
            post_selectors = [
                "section.note-item",  # Common selector for note items
                'div[class*="note-item"]',
                'a[href*="/explore/"]',
                "div.cover.ld.mask",
                'div[class*="feeds-container"] a',
                ".note-list .note",
                'article[class*="note"]',
                'div[data-v-][class*="note"]',
            ]

            posts_found = False
            for selector in post_selectors:
                logger.debug(f"Trying selector: {selector}")
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    logger.info(
                        f"Found {len(elements)} elements with selector: {selector}"
                    )
                    posts_found = True
                    break

            if not posts_found:
                # Try scrolling to trigger lazy loading
                logger.warning("No posts found with CSS selectors, trying to scroll...")
                for i in range(3):
                    self.driver.execute_script(
                        "window.scrollTo(0, document.body.scrollHeight);"
                    )
                    time.sleep(2)

                # Try again after scrolling
                for selector in post_selectors:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        logger.info(
                            f"Found {len(elements)} elements after scrolling with selector: {selector}"
                        )
                        break

            # If still no elements, try XPath
            if not elements:
                xpath_selectors = [
                    '//a[contains(@href, "/explore/")]',
                    '//section[contains(@class, "note")]//a',
                    '//div[@class="feeds-container"]//a',
                ]

                for xpath in xpath_selectors:
                    logger.debug(f"Trying XPath: {xpath}")
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    if elements:
                        logger.info(
                            f"Found {len(elements)} elements with XPath: {xpath}"
                        )
                        break

            # Process found elements
            for element in elements:
                if len(post_urls) >= max_posts:
                    break

                try:
                    # Get the href attribute
                    href = element.get_attribute("href")
                    if not href or "/explore/" not in href:
                        continue

                    logger.debug(f"Found potential post URL: {href}")

                    # Try to find likes count - multiple strategies
                    likes_count = 0

                    # Strategy 1: Look for likes in parent element
                    parent = element.find_element(By.XPATH, "..")
                    likes_text = self.extract_likes_from_element(parent)
                    if likes_text:
                        likes_count = self.parse_likes(likes_text)

                    # Strategy 2: Look for specific likes element
                    if likes_count == 0:
                        try:
                            likes_elem = parent.find_element(
                                By.CSS_SELECTOR,
                                'span[class*="like"], span[class*="count"]',
                            )
                            likes_count = self.parse_likes(likes_elem.text)
                        except:
                            pass

                    # For debugging, accept all posts if we can't find likes
                    if self.debug and likes_count == 0:
                        logger.warning(
                            f"Could not find likes for {href}, including it anyway in debug mode"
                        )
                        post_urls.append(href)
                    elif likes_count >= min_likes:
                        post_urls.append(href)
                        logger.info(f"Added post with {likes_count} likes: {href}")
                    else:
                        logger.debug(
                            f"Skipped post with {likes_count} likes (min: {min_likes})"
                        )

                except Exception as e:
                    logger.debug(f"Error processing element: {e}")
                    continue

            # If no posts found, try alternative search method
            if not post_urls:
                logger.warning(
                    "No posts found with method 1, trying alternative search..."
                )
                post_urls = self.alternative_search(keyword, min_likes, max_posts)

        except Exception as e:
            logger.error(f"Error in search_posts: {e}")
            import traceback

            logger.error(traceback.format_exc())

        logger.info(f"Total posts found: {len(post_urls)}")
        return post_urls

    def handle_popups(self):
        """Handle any popups or modals that might appear"""
        try:
            # Close cookie consent, login prompts, etc.
            close_buttons = [
                "div.close-btn",
                'button[class*="close"]',
                'span[class*="close"]',
                'div[class*="modal-close"]',
            ]

            for selector in close_buttons:
                try:
                    close_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    close_btn.click()
                    logger.debug(f"Closed popup with selector: {selector}")
                    time.sleep(1)
                except:
                    pass
        except:
            pass

    def extract_likes_from_element(self, element):
        """Extract likes text from an element"""
        try:
            # Look for text containing numbers
            text = element.text
            # Look for patterns like "100", "1.2万", "1.2k"
            patterns = [r"\d+\.?\d*[万wkK]?", r"赞\s*\d+", r"likes?\s*\d+"]
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group()
        except:
            pass
        return None

    def alternative_search(
        self, keyword: str, min_likes: int, max_posts: int
    ) -> List[str]:
        """Alternative search method using different approach"""
        logger.info("Trying alternative search method...")
        post_urls = []

        try:
            # Go to home page first
            self.driver.get(self.base_url)
            time.sleep(3)

            # Look for search box and enter keyword
            search_selectors = [
                'input[placeholder*="搜索"]',
                'input[type="search"]',
                'input[class*="search"]',
                "#search-input",
            ]

            search_box = None
            for selector in search_selectors:
                try:
                    search_box = self.driver.find_element(By.CSS_SELECTOR, selector)
                    logger.debug(f"Found search box with selector: {selector}")
                    break
                except:
                    continue

            if search_box:
                search_box.clear()
                search_box.send_keys(keyword)
                search_box.send_keys(Keys.RETURN)
                time.sleep(5)

                # Now look for posts again
                elements = self.driver.find_elements(
                    By.CSS_SELECTOR, 'a[href*="/explore/"]'
                )
                for element in elements[:max_posts]:
                    href = element.get_attribute("href")
                    if href:
                        post_urls.append(href)

        except Exception as e:
            logger.error(f"Alternative search failed: {e}")

        return post_urls

    def parse_likes(self, likes_text: str) -> int:
        """Parse likes count from text (handles 万 for 10k)"""
        if not likes_text:
            return 0

        likes_text = likes_text.strip()

        if "万" in likes_text:
            num = float(likes_text.replace("万", ""))
            return int(num * 10000)
        elif "w" in likes_text.lower():
            num = float(likes_text.lower().replace("w", ""))
            return int(num * 10000)
        else:
            # Extract numbers from string
            numbers = re.findall(r"\d+", likes_text)
            if numbers:
                return int(numbers[0])
        return 0

    def scrape_post_details(self, post_url: str) -> Dict[str, Any]:
        """
        Scrape detailed information from a single post

        Args:
            post_url: URL of the post to scrape

        Returns:
            Dictionary containing post details
        """
        post_data = {
            "post_url": post_url,
            "post_content": "",
            "author": "",
            "author_profile_page": "",
            "comments": [],
        }

        try:
            logger.info(f"Scraping post: {post_url}")
            self.driver.get(post_url)
            time.sleep(random.uniform(4, 6))

            # Handle any popups
            self.handle_popups()

            # Debug: Save screenshot
            if self.debug:
                self.driver.save_screenshot(f"debug_post_{post_url.split('/')[-1]}.png")

            # Wait for content to load
            wait = WebDriverWait(self.driver, 10)

            # Get post content - try multiple selectors
            content_selectors = [
                'div[class*="note-text"]',
                'div[class*="content"]',
                "div.note-scroller",
                'span[class*="note-text"]',
                "#detail-desc",
                'div[data-v-][class*="desc"]',
                'meta[name="description"]',  # Sometimes in meta tags
            ]

            for selector in content_selectors:
                try:
                    if selector.startswith("meta"):
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)
                        post_data["post_content"] = element.get_attribute("content")
                    else:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)
                        post_data["post_content"] = element.text

                    if post_data["post_content"]:
                        logger.debug(f"Found content with selector: {selector}")
                        break
                except:
                    continue

            # If still no content, try JavaScript extraction
            if not post_data["post_content"]:
                try:
                    content = self.driver.execute_script(
                        """
                        var desc = document.querySelector('[class*="desc"]');
                        if (desc) return desc.innerText;
                        var note = document.querySelector('[class*="note-text"]');
                        if (note) return note.innerText;
                        return '';
                    """
                    )
                    if content:
                        post_data["post_content"] = content
                        logger.debug("Found content with JavaScript extraction")
                except:
                    pass

            # Get author information - try multiple selectors
            author_selectors = [
                'a[class*="author"]',
                'span[class*="username"]',
                'div[class*="user-name"]',
                'a[href*="/user/profile/"]',
                "div.author-wrapper a",
                "span.name",
            ]

            for selector in author_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    post_data["author"] = (
                        element.text
                        or element.get_attribute("title")
                        or element.get_attribute("alt")
                    )

                    # Try to get profile link
                    if element.tag_name == "a":
                        post_data["author_profile_page"] = element.get_attribute("href")
                    else:
                        # Look for parent link
                        parent_link = element.find_element(By.XPATH, "./ancestor::a")
                        post_data["author_profile_page"] = parent_link.get_attribute(
                            "href"
                        )

                    if post_data["author"]:
                        logger.debug(f"Found author with selector: {selector}")
                        break
                except:
                    continue

            # Get comments
            logger.debug("Scraping comments...")
            post_data["comments"] = self.scrape_comments()

            logger.info(
                f"Successfully scraped post. Content length: {len(post_data['post_content'])}, Comments: {len(post_data['comments'])}"
            )

        except Exception as e:
            logger.error(f"Error scraping post {post_url}: {e}")
            import traceback

            logger.error(traceback.format_exc())

        return post_data

    def scrape_comments(
        self, min_likes: int = 2, max_comments: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Scrape comments from the current post page

        Args:
            min_likes: Minimum likes for a comment to be included
            max_comments: Maximum number of comments to return

        Returns:
            List of comment dictionaries
        """
        comments = []

        try:
            # Scroll to load comments section
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            time.sleep(random.uniform(2, 3))

            # Try to click "show more comments" if exists
            try:
                more_comments = self.driver.find_element(
                    By.CSS_SELECTOR, '[class*="show-more"], [class*="load-more"]'
                )
                more_comments.click()
                time.sleep(2)
                logger.debug("Clicked 'show more comments'")
            except:
                pass

            # Find comment elements - try multiple selectors
            comment_selectors = [
                'div[class*="comment-item"]',
                'div[class*="comment-content"]',
                'div[class*="comments-list"] > div',
                'ul[class*="comments"] li',
                "div.comment",
            ]

            comment_elements = []
            for selector in comment_selectors:
                comment_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if comment_elements:
                    logger.debug(
                        f"Found {len(comment_elements)} comments with selector: {selector}"
                    )
                    break

            for element in comment_elements:
                try:
                    # Get comment text - try multiple selectors
                    comment_text = ""
                    text_selectors = [
                        '[class*="content"]',
                        '[class*="text"]',
                        "span",
                        "p",
                    ]

                    for selector in text_selectors:
                        try:
                            text_elem = element.find_element(By.CSS_SELECTOR, selector)
                            comment_text = text_elem.text
                            if comment_text:
                                break
                        except:
                            continue

                    if not comment_text:
                        continue

                    # Get likes count
                    likes_count = 0
                    likes_selectors = [
                        '[class*="like"]',
                        '[class*="count"]',
                        'span[class*="num"]',
                    ]

                    for selector in likes_selectors:
                        try:
                            likes_elem = element.find_element(By.CSS_SELECTOR, selector)
                            likes_count = self.parse_likes(likes_elem.text)
                            if likes_count > 0:
                                break
                        except:
                            continue

                    # Check if comment has replies
                    has_replies = False
                    try:
                        replies = element.find_elements(
                            By.CSS_SELECTOR, '[class*="reply"], [class*="sub-comment"]'
                        )
                        if len(replies) >= 2:
                            has_replies = True
                            logger.debug(f"Comment has {len(replies)} replies")
                    except:
                        pass

                    # Include comment if it meets criteria
                    if (
                        likes_count >= min_likes
                        or has_replies
                        or (self.debug and len(comments) < 3)
                    ):
                        comments.append(
                            {
                                "comment": comment_text[:500],  # Limit length
                                "likes": likes_count,
                            }
                        )
                        logger.debug(f"Added comment with {likes_count} likes")

                except Exception as e:
                    logger.debug(f"Error processing comment: {e}")
                    continue

            # Sort by likes and limit to max_comments
            comments.sort(key=lambda x: x["likes"], reverse=True)
            comments = comments[:max_comments]

            logger.info(f"Scraped {len(comments)} comments meeting criteria")

        except Exception as e:
            logger.error(f"Error scraping comments: {e}")
            import traceback

            logger.error(traceback.format_exc())

        return comments

    def scrape_keyword(
        self, keyword: str, output_file: str = None, max_posts: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Main method to scrape posts for a given keyword

        Args:
            keyword: Chinese keyword to search
            output_file: Optional JSON file to save results
            max_posts: Maximum number of posts to scrape

        Returns:
            List of post dictionaries
        """
        logger.info(f"Starting scrape for keyword: {keyword}")

        # Search for posts
        post_urls = self.search_posts(keyword, min_likes=100, max_posts=max_posts)
        logger.info(f"Found {len(post_urls)} posts meeting criteria")

        # If no posts found in normal mode but debug is on, try to get any posts
        if not post_urls and self.debug:
            logger.warning(
                "No posts found with likes criteria, trying without likes filter in debug mode..."
            )
            post_urls = self.search_posts(keyword, min_likes=0, max_posts=max_posts)

        # Scrape each post
        results = []
        for i, url in enumerate(post_urls, 1):
            logger.info(f"Scraping post {i}/{len(post_urls)}: {url}")
            post_data = self.scrape_post_details(url)
            results.append(post_data)

            # Random delay between requests
            time.sleep(random.uniform(3, 6))

        # Save to file if specified
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"Results saved to {output_file}")

        return results

    def close(self):
        """Close the browser driver"""
        if hasattr(self, "driver"):
            self.driver.quit()


def main():
    """Main function to run the scraper with enhanced debugging"""
    print("=" * 60)
    print("Xiaohongshu Scraper - Debug Mode")
    print("=" * 60)

    # Get user input
    keyword = input(
        "Enter Chinese keyword to search (e.g., '美食', '旅游', '护肤'): "
    ).strip()
    if not keyword:
        keyword = "美食"  # Default keyword for testing
        print(f"Using default keyword: {keyword}")

    debug_mode = input("Enable debug mode? (y/n, default=y): ").strip().lower()
    debug = debug_mode != "n"

    headless_mode = input("Run in headless mode? (y/n, default=n): ").strip().lower()
    headless = headless_mode == "y"

    test_mode = (
        input("Run in test mode (only 3 posts)? (y/n, default=n): ").strip().lower()
    )
    max_posts = 3 if test_mode == "y" else 20

    print("\n" + "=" * 60)
    print(f"Configuration:")
    print(f"  Keyword: {keyword}")
    print(f"  Debug Mode: {debug}")
    print(f"  Headless: {headless}")
    print(f"  Max Posts: {max_posts}")
    print("=" * 60 + "\n")

    # Initialize scraper
    scraper = XiaohongshuScraper(headless=headless, debug=debug)

    try:
        # Test basic connectivity
        print("Testing basic connectivity...")
        scraper.driver.get("https://www.xiaohongshu.com")
        print(f"✓ Connected to Xiaohongshu")
        print(f"  Page title: {scraper.driver.title}")
        print(f"  Current URL: {scraper.driver.current_url}\n")

        # Scrape posts
        print(f"Starting search for keyword: '{keyword}'...")
        results = scraper.scrape_keyword(
            keyword=keyword,
            output_file=f"xiaohongshu_{keyword}_results.json",
            max_posts=max_posts,
        )

        # Print summary
        print("\n" + "=" * 60)
        print("SCRAPING COMPLETED")
        print("=" * 60)
        print(f"Total posts scraped: {len(results)}")

        # Print details of results
        if results:
            print("\nPosts found:")
            for i, post in enumerate(results, 1):
                print(f"\n{i}. Post URL: {post['post_url']}")
                print(f"   Author: {post['author'] or 'Unknown'}")
                print(
                    f"   Content: {post['post_content'][:100]}..."
                    if post["post_content"]
                    else "   Content: No content found"
                )
                print(f"   Comments: {len(post['comments'])}")
        else:
            print("\nNo posts were scraped. Possible issues:")
            print("1. The website structure may have changed")
            print("2. Anti-scraping measures may be blocking access")
            print("3. The keyword may not have results with 100+ likes")
            print("4. You may need to manually complete a CAPTCHA")
            print("\nTry running without headless mode to see what's happening")

    except Exception as e:
        print(f"\n❌ Error occurred: {e}")
        import traceback

        print("\nFull traceback:")
        print(traceback.format_exc())
    finally:
        input("\nPress Enter to close the browser...")
        scraper.close()


if __name__ == "__main__":
    main()

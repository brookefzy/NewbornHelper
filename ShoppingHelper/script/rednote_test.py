#!/usr/bin/env python3
"""
Diagnostic test script for Xiaohongshu scraping
This will help identify where the scraping is failing
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import json


def test_basic_access():
    """Test basic access to Xiaohongshu"""
    print("\n" + "=" * 60)
    print("TEST 1: Basic Access Test")
    print("=" * 60)

    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)

    try:
        # Test 1: Can we access the main page?
        print("\n1. Testing main page access...")
        driver.get("https://www.xiaohongshu.com")
        time.sleep(5)

        print(f"   ✓ Page Title: {driver.title}")
        print(f"   ✓ Current URL: {driver.current_url}")

        # Save screenshot
        driver.save_screenshot("test_main_page.png")
        print("   ✓ Screenshot saved as test_main_page.png")

        # Test 2: Can we find any elements?
        print("\n2. Looking for page elements...")

        # Check for common elements
        elements_to_check = [
            ("Posts/Notes", 'a[href*="/explore/"]'),
            ("Search box", 'input[placeholder*="搜索"]'),
            ("User links", 'a[href*="/user/"]'),
            ("Images", "img"),
            ("Divs with class", "div[class]"),
        ]

        for name, selector in elements_to_check:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            print(f"   - {name}: Found {len(elements)} elements")

        # Test 3: Check page source
        print("\n3. Checking page source...")
        page_source = driver.page_source
        print(f"   - Page source length: {len(page_source)} characters")

        # Look for signs of content
        if "explore" in page_source.lower():
            print("   ✓ Found 'explore' in page source")
        if "笔记" in page_source or "note" in page_source.lower():
            print("   ✓ Found note-related content")
        if "登录" in page_source or "login" in page_source.lower():
            print("   ⚠ Login prompt detected")

        # Save a snippet of the page source
        with open("page_source_snippet.html", "w", encoding="utf-8") as f:
            f.write(page_source[:5000])
        print("   ✓ Page source snippet saved to page_source_snippet.html")

        return True

    except Exception as e:
        print(f"\n❌ Error in basic access test: {e}")
        return False
    finally:
        driver.quit()


def test_search_functionality(keyword="美食"):
    """Test search functionality"""
    print("\n" + "=" * 60)
    print(f"TEST 2: Search Functionality Test (keyword: {keyword})")
    print("=" * 60)

    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(options=options)

    try:
        # Try direct search URL
        print(f"\n1. Testing direct search URL...")
        search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"
        driver.get(search_url)
        time.sleep(5)

        print(f"   - Current URL: {driver.current_url}")
        driver.save_screenshot("test_search_page.png")
        print("   ✓ Screenshot saved as test_search_page.png")

        # Look for posts
        print("\n2. Looking for post elements...")

        post_selectors = [
            'a[href*="/explore/"]',
            'section[class*="note"]',
            'div[class*="note-item"]',
            'div[class*="feeds"]',
        ]

        found_posts = []
        for selector in post_selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                print(f"   ✓ Found {len(elements)} elements with selector: {selector}")

                # Try to extract URLs
                for elem in elements[:3]:  # Just check first 3
                    href = elem.get_attribute("href")
                    if href and "/explore/" in href:
                        found_posts.append(href)
                        print(f"     - Post URL: {href}")

        if not found_posts:
            print("   ⚠ No post URLs found")

            # Try to understand what's on the page
            print("\n3. Analyzing page content...")
            all_links = driver.find_elements(By.TAG_NAME, "a")
            print(f"   - Total links on page: {len(all_links)}")

            # Sample some links
            for link in all_links[:5]:
                href = link.get_attribute("href")
                text = link.text[:50] if link.text else ""
                if href:
                    print(f"     Sample link: {href} | Text: {text}")

        return found_posts

    except Exception as e:
        print(f"\n❌ Error in search test: {e}")
        return []
    finally:
        driver.quit()


def test_post_detail(url=None):
    """Test accessing a specific post"""
    print("\n" + "=" * 60)
    print("TEST 3: Post Detail Test")
    print("=" * 60)

    if not url:
        # Use a sample URL (may need to be updated)
        url = "https://www.xiaohongshu.com/explore/6747eb5d000000001e00f4e5"
        print(f"Using sample URL: {url}")

    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)

    try:
        print(f"\n1. Accessing post...")
        driver.get(url)
        time.sleep(5)

        driver.save_screenshot("test_post_detail.png")
        print("   ✓ Screenshot saved as test_post_detail.png")

        print("\n2. Looking for content elements...")

        content_selectors = [
            ("Note text", 'div[class*="note-text"]'),
            ("Content", 'div[class*="content"]'),
            ("Description", 'div[class*="desc"]'),
            ("Author", 'a[class*="author"]'),
            ("Comments", 'div[class*="comment"]'),
        ]

        for name, selector in content_selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                print(f"   ✓ {name}: Found {len(elements)} elements")
                # Try to get text from first element
                try:
                    text = elements[0].text[:100] if elements[0].text else "No text"
                    print(f"     Sample: {text}...")
                except:
                    pass

        return True

    except Exception as e:
        print(f"\n❌ Error in post detail test: {e}")
        return False
    finally:
        driver.quit()


def main():
    """Run all diagnostic tests"""
    print("=" * 60)
    print("XIAOHONGSHU SCRAPER DIAGNOSTIC")
    print("=" * 60)
    print("\nThis will run several tests to identify issues with scraping.")
    print("Please make sure Chrome and ChromeDriver are installed.\n")

    input("Press Enter to start tests...")

    # Test 1: Basic Access
    if test_basic_access():
        print("\n✅ Basic access test passed")
    else:
        print("\n❌ Basic access test failed")
        print("   The site may be blocking automated access.")
        print("   Try:")
        print("   1. Using a VPN")
        print("   2. Adding more anti-detection measures")
        print("   3. Using a different user agent")

    # Test 2: Search
    posts = test_search_functionality()
    if posts:
        print(f"\n✅ Search test passed - found {len(posts)} posts")

        # Test 3: Post Detail (using first found post)
        if test_post_detail(posts[0] if posts else None):
            print("\n✅ Post detail test passed")
        else:
            print("\n❌ Post detail test failed")
    else:
        print("\n❌ Search test failed")
        print("   Possible issues:")
        print("   1. Site structure has changed")
        print("   2. JavaScript is required but not loading")
        print("   3. Login is required")
        print("   4. Geographic restrictions")

    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)
    print("\nCheck the generated screenshots and HTML files for more details.")
    print("If all tests fail, the site may be actively blocking scrapers.")
    print("\nAlternative approaches to try:")
    print("1. Use a proxy or VPN")
    print("2. Add delays and randomization")
    print("3. Use browser automation tools like Playwright")
    print("4. Consider using the mobile app API")
    print("5. Try accessing from a different geographic location")


if __name__ == "__main__":
    main()

import httpx
from bs4 import BeautifulSoup
import asyncio

async def main():
    sitemap_url = "https://valvrareteam.net/sitemap.xml"
    async with httpx.AsyncClient() as client:
        resp = await client.get(sitemap_url)
        soup = BeautifulSoup(resp.content, "lxml-xml")
        count = 0
        for loc in soup.find_all("loc"):
            url = loc.text
            if "toan-chuc-phap-su" in url:
                print(f"Found: {url}")
                count += 1
        print(f"Total matches: {count}")

if __name__ == "__main__":
    asyncio.run(main())

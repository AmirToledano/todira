import time
import random
import httpx
import os
from typing import Dict, Any, List

class StealthHTTPClient:
    def __init__(self, proxy_list: List[str] = None):
        # טעינת פרוקסים: מרשימה או ממשתנה סביבה במערכת
        env_proxy = os.getenv("ROTATING_PROXY_URL")
        self.proxies = proxy_list or ([env_proxy] if env_proxy else [])
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        ]

    def _get_random_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="130", "Google Chrome";v="130"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

    def fetch(self, url: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        # 1. חיקוי התנהגות אנושית - השהיה אקראית של משתמש אמיתי
        time.sleep(random.uniform(3.0, 7.0))
        
        # 2. בחירת פרוקסי מתחלף מהמאגר הקיים
        current_proxy = random.choice(self.proxies) if self.proxies else None
        mounts = {"http://": httpx.HTTPTransport(proxy=current_proxy), "https://": httpx.HTTPTransport(proxy=current_proxy)} if current_proxy else None

        # 3. יצירת קליינט עם תמיכה מלאה ב-HTTP/2 וחתימות דפדפן
        with httpx.Client(http2=True, mounts=mounts, headers=self._get_random_headers(), timeout=15.0) as client:
            for attempt in range(3):
                try:
                    response = client.get(url, params=params)
                    
                    # אם נתקלנו בחסימת קצב או סירוב, נחליף פרוקסי מייד ונמתין
                    if response.status_code in:
                        if self.proxies and len(self.proxies) > 1:
                            current_proxy = random.choice([p for p in self.proxies if p != current_proxy])
                            client.mounts = {"http://": httpx.HTTPTransport(proxy=current_proxy), "https://": httpx.HTTPTransport(proxy=current_proxy)}
                        time.sleep(5 * (attempt + 1))
                        continue
                        
                    return response.json()
                except Exception as e:
                    if attempt == 2:
                        raise e
                    time.sleep(2)
            return {}

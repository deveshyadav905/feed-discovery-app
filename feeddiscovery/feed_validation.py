import os
import sys
import requests
import pandas as pd
import pytz
from lxml import etree
from datetime import datetime
from dateutil import parser
from concurrent.futures import ThreadPoolExecutor
from requests.exceptions import RequestException



class FeedValidator:
    def __init__(self):
        self.report_data = []
        self.tz_ist = pytz.timezone("Asia/Kolkata")
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }

    def fetch_urls_by_domain_names(self, domain_names: list):
        """
        Queries the source URLs by joining the domain and source tables.
        Filters by a list of domain names.
        """
        if not domain_names:
            return []

        conn, cursor = get_msq_conn()
        feed_urls = []
        try:
            # JOIN logic: Match source.domain_id with domain.id
            # We use the 'IN' clause for efficiency instead of looping
            format_strings = ','.join(['%s'] * len(domain_names))
            query = f"""
                SELECT s.url 
                FROM source s
                INNER JOIN domain d ON s.domain_id = d.id 
                WHERE d.name IN ({format_strings}) 
                AND s.is_deleted = 0
            """
            cursor.execute(query, tuple(domain_names))
            feed_urls = [row[0] for row in cursor.fetchall()]
            print(f"Fetched {len(feed_urls)} URLs for {len(domain_names)} domains.")
        except Exception as e:
            print(f"Database error: {e}")
        finally:
            close_mysql_conn(db=conn, cursor=cursor)
        
        return feed_urls
    
    def parse_date_to_ist(self, date_str):
        """Parse string and convert to IST."""
        if not date_str:
            return None
        try:
            dt = parser.parse(str(date_str).strip())
            if dt.tzinfo is None:
                dt = pytz.UTC.localize(dt)
            return dt.astimezone(self.tz_ist)
        except Exception:
            return None

    def get_age_metrics(self, pub_date):
        """Calculate time differences from now."""
        if not pub_date:
            return {"days": "N/A", "hours": "N/A", "status_msg": "No Date Found"}
        
        now = datetime.now(self.tz_ist)
        diff = now - pub_date
        hours = int(diff.total_seconds() // 3600)
        days = diff.days
        
        return {
            "days": days,
            "hours": hours,
            "status_msg": "Active" if days < 2 else "Stale" if days < 30 else "Inactive"
        }

    def extract_feed_data(self, xml_content):
        """Extracts the latest item info using namespace-agnostic XPaths."""
        try:
            tree = etree.fromstring(xml_content, parser=etree.XMLParser(recover=True, no_network=True))
            
            # Common RSS/Atom paths for the 'latest' entry/item
            # We use local-name() to bypass namespace issues (like 'content:', 'atom:', etc.)
            items = tree.xpath("//*[local-name()='item'] | //*[local-name()='entry']")
            if not items:
                items = tree.xpath("//*[local-name()='url']") 
                
            
            if not items:
                return None, None, "Feed is empty (no items/entries)"

            latest_item = items[0]

            # Find Link
            link = latest_item.xpath(".//*[local-name()='link']/text() | .//*[local-name()='loc']/text()")
            if not link: # Try href attribute (common in Atom)
                link = latest_item.xpath(".//*[local-name()='link']/@href | .//*[local-name()='loc']/@href")
            link = link[0] if link else "N/A"

            # Find Date (Order of preference)
            date_queries = [
                ".//*[local-name()='pubDate']/text()",
                ".//*[local-name()='updated']/text()",
                ".//*[local-name()='published']/text()",
                ".//*[local-name()='date']/text()",
                ".//*[local-name()='lastmod']/text()",
                ".//*[local-name()='publication_date']/text()"
                
            ]
            
            pub_date_str = None
            for query in date_queries:
                found = latest_item.xpath(query)
                if found:
                    pub_date_str = found[0]
                    break
            
            return link, pub_date_str, "Success"

        except Exception as e:
            return None, None, f"Parsing Error: {str(e)}"
        
    def start_check(self, domain_names: list = None, excel_file: str = None, max_workers=10):
        """
        Starts the validation process. Can take a list of domain names OR an excel file.
        """
        feed_urls = []

        # 1. Fetch from Database if domain names are provided
        if domain_names:
            feed_urls.extend(self.fetch_urls_by_domain_names(domain_names))

        # 2. Fetch from Excel if file provided
        if excel_file and os.path.exists(excel_file):
            data = pd.read_excel(excel_file)
            if 'url' in data.columns:
                feed_urls.extend(data['url'].dropna().tolist())

        if not feed_urls:
            print("No URLs found to check.")
            return

        # Process feeds in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            executor.map(self.check_url, list(set(feed_urls))) # use set() to avoid duplicates

        self.generate_report("feed_report_final.xlsx")


    def check_url(self, feed_url):
        """Worker function to fetch and process a single URL."""
        result = {
            "feed_url": feed_url,
            "link": "N/A",
            "pub_date": "N/A",
            "days_old": "N/A",
            "hours_old": "N/A",
            "status": "Failure",
            "message": ""
        }

        try:
            response = self.session.get(feed_url, headers=self.headers, timeout=15, verify=True)
            
            if response.status_code == 200:
                link, date_str, msg = self.extract_feed_data(response.content)
                result["status"] = "Success"
                result["link"] = link
                result["message"] = msg
                if date_str:

                    dt_obj = self.parse_date_to_ist(date_str)
                    age = self.get_age_metrics(dt_obj)
                    
                    result.update({
                        "link": link,
                        "pub_date": dt_obj.strftime('%Y-%m-%d %H:%M:%S') if dt_obj else date_str,
                        "days_old": age['days'],
                        "hours_old": age['hours'],
                        "status": "Success",
                        "message": age['status_msg'] if msg == "Success" else msg
                    })
                else:
                    result["message"] = msg or "No date found in XML"
            else:
                result["message"] = f"HTTP {response.status_code}"

        except RequestException as e:
            result["message"] = f"Network Error: {type(e).__name__}"
        except Exception as e:
            result["message"] = f"Unexpected Error: {str(e)}"

        self.report_data.append(result)

    def start_check(self, domain_names: list = None, excel_file: str = None, max_workers=10):
        """
        Starts the validation process. Can take a list of domain names OR an excel file.
        """
        feed_urls = []

        # 1. Fetch from Database if domain names are provided
        if domain_names:
            feed_urls.extend(self.fetch_urls_by_domain_names(domain_names))

        # 2. Fetch from Excel if file provided
        if excel_file and os.path.exists(excel_file):
            data = pd.read_excel(excel_file)
            if 'url' in data.columns:
                feed_urls.extend(data['url'].dropna().tolist())

        if not feed_urls:
            print("No URLs found to check.")
            return

        # Process feeds in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            executor.map(self.check_url, list(set(feed_urls))) # use set() to avoid duplicates        

    def export_to_excel(self, filename="feed_validation_report.xlsx"):
        df = pd.DataFrame(self.report_data)
        # Reorder columns for readability
        cols = ["status", "feed_url", "days_old", "hours_old", "pub_date", "link", "message"]
        df = df[cols]
        df.to_excel(filename, index=False)
        print(f"Report saved to {filename}")
        
    def update_master_report(self, filename="all_feeds_history",api_info=None):
        # 1. Convert current run data to DataFrame
        new_df = pd.DataFrame(self.report_data)
        cols = ["status", "feed_url", "days_old", "hours_old", "pub_date", "link", "message"]
        new_df = new_df[cols]

        # 2. Check if the master file already exists
        if os.path.exists(filename):
            # Read the existing data
            existing_df = pd.read_excel(filename)

            # Combine existing and new data
            # We put new_df second so that 'keep="last"' preserves the newest check
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = new_df

        # 3. Remove duplicates
        # Use 'link' as the unique key. If 'link' is the same, it's a duplicate.
        # keep='last' ensures that if a feed was checked twice, we keep the most recent result.

        combined_df.drop_duplicates(subset=["feed_url"], keep="last", inplace=True)

        # 4. Save back to Excel
        api_df = pd.DataFrame([api_info])
        combined_df = pd.concat([combined_df,api_df],ignore_index=True)
        combined_df.to_excel(filename, index=False)
        print(f"Master report updated (duplicates removed). Total records: {len(combined_df)}")
    
    def check_with_newsdataApi(self,domain_name):
        
        API_URL = "https://local.newsdata.io/api/1/latest?apikey=pub_488929ce5c57c541ee39441739fe9caf28094&domain={}"
        
        response = requests.get(API_URL.format(domain_name))
        if response.status_code == 200:
            results = response.json().get('results') 
            if len(results)>0:
                data = { 
                'latest_count':response.json().get('totalResults'),
                'last_pubdate':results[0].get('pubDate')}
                return data
        
        return {'status':response.status_code}
    
    # --- Execution Logic ---
    def main(self,domains_name):
        domains_name = [domains_name]
        
        self.start_check(domain_names=domains_name)
        # Save the report for JUST this run
        self.export_to_excel(f"feedsdata/feed_report_of_{domains_name[0]}.xlsx")

        # Update the master history file (appends and cleans)
        data = self.check_with_newsdataApi(domain_name=domains_name[0])
        print(data)
        self.update_master_report("feedsdata/all_feeds_history.xlsx",api_info=data)

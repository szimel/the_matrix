import os
import json
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
import datetime
import re
import html

# Environment Variables
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
VIKUNJA_URL = os.getenv("VIKUNJA_URL", "https://tasks.bigdaddyz.com").rstrip('/')
MEALIE_URL = os.getenv("MEALIE_URL", "https://mealie.bigdaddyz.com").rstrip('/') 

def clean_html(raw_html):
    """Safely converts HTML to Discord-friendly text."""
    if not raw_html:
        return ""
    text = re.sub(r'<(br|p|h[1-6]|li|div)[^>]*>', '\n', raw_html, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

class WebhookHandler(BaseHTTPRequestHandler):
    # Keep standard HTTP logs so you can see EVERY connection
    def log_message(self, format, *args):
        print(f"[{datetime.datetime.now().isoformat()}] HTTP Connection: {self.client_address[0]} - {format % args}", flush=True)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            payload = json.loads(post_data.decode('utf-8'))
            
            # Application Routing
            if self.path.startswith('/vikunja') or self.path == '/webhook':
                self.process_vikunja(payload)
            elif self.path.startswith('/mealie'):
                self.process_mealie(payload)
            else:
                self.send_response(404)
                self.end_headers()
                return
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"success"}')
            
        except Exception as e:
            print(f"[{datetime.datetime.now().isoformat()}] Error processing POST: {e}", flush=True)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"status":"error"}')

    def send_to_discord(self, payload_dict):
        """Helper function to execute the Discord POST request."""
        if not DISCORD_WEBHOOK_URL:
            print("ERROR: DISCORD_WEBHOOK_URL is missing!", flush=True)
            return
            
        req = urllib.request.Request(DISCORD_WEBHOOK_URL, method="POST")
        req.add_header('Content-Type', 'application/json')
        req.add_header('User-Agent', 'Homelab-Discord-Relay')
        
        try:
            payload_data = json.dumps(payload_dict).encode('utf-8')
            urllib.request.urlopen(req, data=payload_data, timeout=5)
            print(f"[{datetime.datetime.now().isoformat()}] Successfully pushed to Discord!", flush=True)
        except Exception as e:
            print(f"Failed to push to Discord: {e}", flush=True)

    def process_vikunja(self, payload):
        event_name = payload.get("event_name", "Unknown Event")
        print(f"[{datetime.datetime.now().isoformat()}] Vikunja Event triggered: {event_name}", flush=True)
        
        data = payload.get("data", {})
        task = data.get("task", {})
        tasks = data.get("tasks", []) 
        doer = data.get("doer", {})
        project = data.get("project", {})
        comment = data.get("comment", {})
        
        readable_event = event_name.replace('.', ' ').title()
        
        task_url = VIKUNJA_URL
        if tasks: 
            task_title = f"{len(tasks)} tasks are overdue!"
            task_desc = "\n".join([f"• {clean_html(t.get('title', ''))}" for t in tasks])
        else:
            task_title = clean_html(task.get("title", "Unknown Task"))
            task_desc = clean_html(task.get("description", ""))
            task_id = task.get("id")
            if task_id:
                task_url = f"{VIKUNJA_URL}/tasks/{task_id}"
                
        color = 3447003 
        if "created" in event_name: color = 3066993 
        elif "deleted" in event_name: color = 15158332 
        elif "updated" in event_name or "edited" in event_name: color = 15844367 
        elif "overdue" in event_name: color = 15105570 
        elif "reminder" in event_name: color = 10181046 
        elif "done" in event_name: color = 3066993 
            
        doer_name = doer.get("name") or doer.get("username") or "Vikunja System"
        
        embed = {
            "title": task_title,
            "url": task_url,
            "color": color,
            "author": {
                "name": f"{doer_name}  •  {readable_event}",
            },
            "fields": [],
            "footer": {"text": "Vikunja Task Automation"}
        }
        
        if task_desc:
            embed["description"] = task_desc[:800] + "..." if len(task_desc) > 800 else task_desc
            
        if project and project.get("title"):
            embed["fields"].append({"name": "📁 Project", "value": clean_html(project.get("title")), "inline": True})
            
        priority = task.get("priority")
        if priority:
            p_map = {1: "🟢 Low", 2: "🔵 Normal", 3: "🟡 High", 4: "🟠 Urgent", 5: "🔴 DO NOW"}
            p_text = p_map.get(priority, str(priority))
            embed["fields"].append({"name": "🚨 Priority", "value": p_text, "inline": True})
            
        due_date = task.get("due_date")
        if due_date and not due_date.startswith("0001"):
            embed["fields"].append({"name": "📅 Due Date", "value": due_date[:10], "inline": True})
            
        if comment and comment.get("text"):
            embed["fields"].append({"name": "💬 Comment", "value": clean_html(comment.get("text")), "inline": False})
            
        self.send_to_discord({"embeds": [embed]})

    def process_mealie(self, payload):
        print(f"[{datetime.datetime.now().isoformat()}] Mealie Event triggered", flush=True)
        
        # Recursive search to find specific keys regardless of how deeply Mealie nests them
        def find_key(d, key):
            if isinstance(d, dict):
                if key in d: return d[key]
                for v in d.values():
                    res = find_key(v, key)
                    if res is not None: return res
            elif isinstance(d, list):
                for item in d:
                    res = find_key(item, key)
                    if res is not None: return res
            return None

        # 1. Safely extract recipe data
        recipe = find_key(payload, "recipe")
        if not recipe or not isinstance(recipe, dict):
            recipe = payload

        recipe_name = recipe.get("name", "Unknown Meal")
        
        # 2. Extract tags (handle edge cases where tags are at root instead of inside recipe)
        tags = recipe.get("tags")
        if tags is None:
            tags = find_key(payload, "tags") or []
            
        tag_names = [str(t.get("name", "")).lower() if isinstance(t, dict) else str(t).lower() for t in tags]
        
        # 3. Filter for BigPappa
        if not any("bigpappa" in t for t in tag_names):
            print(f"[{datetime.datetime.now().isoformat()}] Skipping Mealie notification. '{recipe_name}' isn't tagged for BigPappa", flush=True)
            return

        # 4. URLs and Routing
        recipe_slug = recipe.get("slug", "")
        mealie_local_url = f"{MEALIE_URL}/recipe/{recipe_slug}" if recipe_slug else MEALIE_URL
        
        # Extract orgURL (Mealie's native key for original URL) or sourceUrl
        original_url = recipe.get("orgURL") or recipe.get("sourceUrl") or mealie_local_url
        
        embed = {
            "title": f"👨‍🍳 Time to Cook: {recipe_name}",
            "description": f"You are scheduled to cook **{recipe_name}** tonight!\n\n[View Recipe in Mealie]({mealie_local_url})",
            "url": original_url, # Now points to Budget Bytes!
            "color": 15258703,
            "footer": {"text": "Mealie Meal Planner"}
        }

        # 5. Image Extraction
        recipe_id = recipe.get("id")
        if recipe_id:
            image_url = f"{MEALIE_URL}/api/media/recipes/{recipe_id}/images/original.webp"
            embed["image"] = {"url": image_url}

        self.send_to_discord({"embeds": [embed]})

def run(server_class=HTTPServer, handler_class=WebhookHandler, port=8001):
    server_address = ('0.0.0.0', port)
    print(f'Starting Ultra-Lightweight Discord Relay on port {port}...', flush=True)
    print('Routing map -> /vikunja (or /webhook) | /mealie', flush=True)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()

if __name__ == "__main__":
    run()

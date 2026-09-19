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
    # Replace block tags with newlines to preserve structural spacing
    text = re.sub(r'<(br|p|h[1-6]|li|div)[^>]*>', '\n', raw_html, flags=re.IGNORECASE)
    # Strip all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Convert HTML entities (e.g., &amp; to &)
    text = html.unescape(text)
    # Clean up excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

class WebhookHandler(BaseHTTPRequestHandler):
    # Un-suppress standard HTTP logs so you can see EVERY connection
    def log_message(self, format, *args):
        print(f"[{datetime.datetime.now().isoformat()}] HTTP Connection: {self.client_address[0]} - {format % args}", flush=True)

    def do_POST(self):
        print(f"[{datetime.datetime.now().isoformat()}] Received POST request on path: {self.path}", flush=True)
        
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            payload = json.loads(post_data.decode('utf-8'))
            
            # Application Routing
            if self.path.startswith('/vikunja'):
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
        print("========== RAW MEALIE PAYLOAD ==========", flush=True)
        print(json.dumps(payload, indent=2), flush=True)
        print("========================================", flush=True)
        
        # Depending on the Mealie event, recipe data might be nested or flat.
        recipe = payload.get("recipe", payload)
        recipe_name = recipe.get("name", "Unknown Meal")
        tags = recipe.get("tags", [])
        
        # Flatten and lower-case tags to easily check for "BigPappa"
        tag_names = [str(t.get("name", "")).lower() if isinstance(t, dict) else str(t).lower() for t in tags]
        
        # If the tag logic determines your wife is cooking, skip sending it to Discord
        # (Converted "BigPappa" to lower here to safely match tag_names which were just lowered)
        if not any("bigpappa" in t for t in tag_names):
            print(f"Skipping Mealie Discord notification. '{recipe_name}' isn't tagged for BigPappa", flush=True)
            return

        recipe_slug = recipe.get("slug", "")
        recipe_url = f"{MEALIE_URL}/recipe/{recipe_slug}" if recipe_slug else MEALIE_URL
        
        embed = {
            "title": f"👨‍🍳 Time to Cook: {recipe_name}",
            "description": f"You are scheduled to cook **{recipe_name}** tonight!",
            "url": recipe_url,
            "color": 15258703, # A nice culinary orange color
            "footer": {"text": "Mealie Meal Planner"}
        }

        # Try to append the image. Discord handles image fetching externally, 
        # so this assumes your Mealie instance is accessible via your domain!
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

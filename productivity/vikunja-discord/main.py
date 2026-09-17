import os
import json
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
import datetime

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
# Allows the Discord Title to be a clickable link straight to the task
VIKUNJA_URL = os.getenv("VIKUNJA_URL", "https://your-vikunja-url.com").rstrip('/')

class WebhookHandler(BaseHTTPRequestHandler):
    # Suppress standard HTTP logs to keep Docker logs clean
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        if self.path != '/webhook':
            self.send_response(404)
            self.end_headers()
            return
            
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            payload = json.loads(post_data.decode('utf-8'))
            self.process_payload(payload)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"success"}')
            print(f"[{datetime.datetime.now().isoformat()}] Processed: {payload.get('event_name')}")
        except Exception as e:
            print(f"[{datetime.datetime.now().isoformat()}] Error: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"status":"error"}')
            
    def process_payload(self, payload):
        if not DISCORD_WEBHOOK_URL:
            print("ERROR: DISCORD_WEBHOOK_URL is missing!")
            return

        event_name = payload.get("event_name", "Unknown Event")
        data = payload.get("data", {})
        
        task = data.get("task", {})
        tasks = data.get("tasks", []) 
        doer = data.get("doer", {})
        project = data.get("project", {})
        comment = data.get("comment", {})
        
        # 1. Format Event Subtitle (e.g., "task.reminder.fired" -> "Task Reminder Fired")
        readable_event = event_name.replace('.', ' ').title()
        
        # 2. Extract Titles & Task URL for Clickability
        task_url = VIKUNJA_URL
        if tasks: # Handles multiple tasks going overdue at once
            task_title = f"{len(tasks)} tasks are overdue!"
            task_desc = "\n".join([f"• {t.get('title', '')}" for t in tasks])
        else:
            task_title = task.get("title", "Unknown Task")
            task_desc = task.get("description", "")
            task_id = task.get("id")
            if task_id:
                task_url = f"{VIKUNJA_URL}/tasks/{task_id}"
                
        # 3. Dynamic Discord Colors (Hex converted to Int)
        color = 3447003 # Default Blue
        if "created" in event_name: color = 3066993 # Green
        elif "deleted" in event_name: color = 15158332 # Red
        elif "updated" in event_name or "edited" in event_name: color = 15844367 # Yellow
        elif "overdue" in event_name: color = 15105570 # Orange
        elif "reminder" in event_name: color = 10181046 # Purple
        elif "done" in event_name: color = 3066993 # Green
            
        # 4. Determine User
        doer_name = doer.get("name") or doer.get("username") or "Vikunja System"
        
        # 5. Build Discord Embed Structure
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
        
        # Main Description (Cut off if it's a massive wall of text)
        if task_desc:
            embed["description"] = task_desc[:800] + "..." if len(task_desc) > 800 else task_desc
            
        # Optional Context Fields (These display side-by-side in Discord)
        if project and project.get("title"):
            embed["fields"].append({"name": "📁 Project", "value": project.get("title"), "inline": True})
            
        priority = task.get("priority")
        if priority:
            p_map = {1: "🟢 Low", 2: "🔵 Normal", 3: "🟡 High", 4: "🟠 Urgent", 5: "🔴 DO NOW"}
            p_text = p_map.get(priority, str(priority))
            embed["fields"].append({"name": "🚨 Priority", "value": p_text, "inline": True})
            
        due_date = task.get("due_date")
        if due_date and not due_date.startswith("0001"):
            # Truncates '2026-10-17T19:39:32Z' into '2026-10-17'
            embed["fields"].append({"name": "📅 Due Date", "value": due_date[:10], "inline": True})
            
        if comment and comment.get("text"):
            embed["fields"].append({"name": "💬 Comment", "value": comment.get("text"), "inline": False})
            
        # 6. Send payload to Discord using native urllib
        req = urllib.request.Request(DISCORD_WEBHOOK_URL, method="POST")
        req.add_header('Content-Type', 'application/json')
        req.add_header('User-Agent', 'Vikunja-Discord-Relay')
        
        try:
            payload_data = json.dumps({"embeds": [embed]}).encode('utf-8')
            urllib.request.urlopen(req, data=payload_data, timeout=5)
        except Exception as e:
            print(f"Failed to push to Discord: {e}")

def run(server_class=HTTPServer, handler_class=WebhookHandler, port=8001):
    server_address = ('0.0.0.0', port)
    print(f'Starting Ultra-Lightweight Vikunja Relay on port {port}...')
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()

if __name__ == "__main__":
    run()
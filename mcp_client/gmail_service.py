# mcp_client/gmail_service.py

import base64
import json
from email.message import EmailMessage
import httpx
from .google_auth import get_gmail_credentials


def _get_headers():
    creds = get_gmail_credentials()
    return {"Authorization": f"Bearer {creds.token}"}


async def execute_gmail_fallback(tool_name: str, args: dict) -> str:
    """Executes Gmail API calls directly when remote MCP server returns permission errors."""
    headers = _get_headers()
    base_url = "https://gmail.googleapis.com/gmail/v1/users/me"

    async with httpx.AsyncClient() as client:
        if tool_name == "list_labels":
            res = await client.get(f"{base_url}/labels", headers=headers)
            if res.status_code == 200:
                labels = res.json().get("labels", [])
                formatted = [
                    f"- {l.get('name')} (ID: {l.get('id')}, Type: {l.get('type')})"
                    for l in labels
                ]
                return "Gmail Labels:\n" + "\n".join(formatted)
            return f"Error listing labels: {res.status_code} - {res.text}"

        elif tool_name == "search_threads":
            query = args.get("query", "in:inbox")
            max_results = args.get("maxResults", 10)
            res = await client.get(
                f"{base_url}/threads",
                headers=headers,
                params={"q": query, "maxResults": max_results},
            )
            if res.status_code == 200:
                threads = res.json().get("threads", [])
                if not threads:
                    return f"No threads found matching query: '{query}'"
                
                details = []
                for t in threads[:max_results]:
                    t_res = await client.get(
                        f"{base_url}/threads/{t['id']}",
                        headers=headers,
                        params={"format": "metadata"},
                    )
                    if t_res.status_code == 200:
                        t_data = t_res.json()
                        messages = t_data.get("messages", [])
                        snippet = messages[0].get("snippet", "") if messages else ""
                        headers_list = messages[0].get("payload", {}).get("headers", []) if messages else []
                        subject = next((h["value"] for h in headers_list if h["name"].lower() == "subject"), "No Subject")
                        from_hdr = next((h["value"] for h in headers_list if h["name"].lower() == "from"), "Unknown Sender")
                        details.append(
                            f"Thread ID: {t['id']}\n  From: {from_hdr}\n  Subject: {subject}\n  Snippet: {snippet}\n"
                        )
                return "\n".join(details)
            return f"Error searching threads: {res.status_code} - {res.text}"

        elif tool_name == "get_thread":
            thread_id = args.get("threadId") or args.get("thread_id")
            if not thread_id:
                return "Error: threadId is required."
            res = await client.get(f"{base_url}/threads/{thread_id}", headers=headers)
            if res.status_code == 200:
                data = res.json()
                messages_summary = []
                for msg in data.get("messages", []):
                    hdr_list = msg.get("payload", {}).get("headers", [])
                    subject = next((h["value"] for h in hdr_list if h["name"].lower() == "subject"), "No Subject")
                    from_hdr = next((h["value"] for h in hdr_list if h["name"].lower() == "from"), "Unknown")
                    date_hdr = next((h["value"] for h in hdr_list if h["name"].lower() == "date"), "")
                    messages_summary.append(
                        f"Message ID: {msg.get('id')}\nDate: {date_hdr}\nFrom: {from_hdr}\nSubject: {subject}\nSnippet: {msg.get('snippet')}\n"
                    )
                return f"Thread ID: {thread_id}\nMessages ({len(messages_summary)}):\n" + "\n---\n".join(messages_summary)
            return f"Error getting thread: {res.status_code} - {res.text}"

        elif tool_name == "get_message":
            message_id = args.get("messageId") or args.get("message_id")
            if not message_id:
                return "Error: messageId is required."
            res = await client.get(f"{base_url}/messages/{message_id}", headers=headers)
            if res.status_code == 200:
                data = res.json()
                hdr_list = data.get("payload", {}).get("headers", [])
                subject = next((h["value"] for h in hdr_list if h["name"].lower() == "subject"), "No Subject")
                from_hdr = next((h["value"] for h in hdr_list if h["name"].lower() == "from"), "Unknown")
                to_hdr = next((h["value"] for h in hdr_list if h["name"].lower() == "to"), "Unknown")
                snippet = data.get("snippet", "")
                return f"Message ID: {message_id}\nFrom: {from_hdr}\nTo: {to_hdr}\nSubject: {subject}\nSnippet: {snippet}"
            return f"Error getting message: {res.status_code} - {res.text}"

        elif tool_name == "list_drafts":
            res = await client.get(f"{base_url}/drafts", headers=headers)
            if res.status_code == 200:
                drafts = res.json().get("drafts", [])
                if not drafts:
                    return "No drafts found."
                items = [f"- Draft ID: {d['id']} (Message ID: {d.get('message', {}).get('id')})" for d in drafts]
                return "Drafts:\n" + "\n".join(items)
            return f"Error listing drafts: {res.status_code} - {res.text}"

        elif tool_name == "create_draft":
            to = args.get("to", "")
            subject = args.get("subject", "")
            body = args.get("body", "") or args.get("content", "")
            
            message = EmailMessage()
            message.set_content(body)
            if to:
                message["To"] = to
            if subject:
                message["Subject"] = subject

            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            payload = {"message": {"raw": encoded_message}}
            
            res = await client.post(f"{base_url}/drafts", headers=headers, json=payload)
            if res.status_code == 200:
                d = res.json()
                return f"Draft created successfully. Draft ID: {d.get('id')}"
            return f"Error creating draft: {res.status_code} - {res.text}"

        elif tool_name == "create_label":
            display_name = args.get("displayName") or args.get("name")
            if not display_name:
                return "Error: displayName is required."
            res = await client.post(f"{base_url}/labels", headers=headers, json={"name": display_name})
            if res.status_code == 200:
                l = res.json()
                return f"Label '{display_name}' created successfully. Label ID: {l.get('id')}"
            return f"Error creating label: {res.status_code} - {res.text}"

        elif tool_name in ("label_thread", "unlabel_thread"):
            thread_id = args.get("threadId")
            label_ids = args.get("labelIds", [])
            if not thread_id:
                return "Error: threadId is required."
            body = {"addLabelIds": label_ids} if tool_name == "label_thread" else {"removeLabelIds": label_ids}
            res = await client.post(f"{base_url}/threads/{thread_id}/modify", headers=headers, json=body)
            if res.status_code == 200:
                return f"Thread {thread_id} updated successfully."
            return f"Error modifying thread labels: {res.status_code} - {res.text}"

        elif tool_name in ("label_message", "unlabel_message"):
            message_id = args.get("messageId")
            label_ids = args.get("labelIds", [])
            if not message_id:
                return "Error: messageId is required."
            body = {"addLabelIds": label_ids} if tool_name == "label_message" else {"removeLabelIds": label_ids}
            res = await client.post(f"{base_url}/messages/{message_id}/modify", headers=headers, json=body)
            if res.status_code == 200:
                return f"Message {message_id} updated successfully."
            return f"Error modifying message labels: {res.status_code} - {res.text}"

        elif tool_name in ("apply_sensitive_thread_label", "apply_sensitive_message_label"):
            target_id = args.get("threadId") or args.get("messageId")
            label_option = args.get("labelOption", "")
            if not target_id:
                return "Error: threadId or messageId is required."
            label_id = "TRASH" if "TRASH" in label_option else ("SPAM" if "SPAM" in label_option else "")
            if not label_id:
                return f"Unsupported sensitive label option: {label_option}"
            
            endpoint = "threads" if "thread" in tool_name else "messages"
            res = await client.post(f"{base_url}/{endpoint}/{target_id}/modify", headers=headers, json={"addLabelIds": [label_id]})
            if res.status_code == 200:
                return f"Applied {label_id} to {endpoint[:-1]} {target_id} successfully."
            return f"Error applying label option: {res.status_code} - {res.text}"

        return f"Unknown Gmail tool action: {tool_name}"

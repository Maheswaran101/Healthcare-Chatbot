#!/usr/bin/env python3
"""
Bedrock Agent runtime helper.

The model is configured on the Bedrock Agent itself, so keep Terraform pointed
at amazon.nova-lite-v1:0 and call the runtime agent normally.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
import requests # Added import
from typing import Any

import boto3


FALLBACK_MARKERS = ("ask for", "i can help", "i can help summarize")


def is_fallback(text: str) -> bool:
    normalized = " ".join((text or "").lower().split())
    return any(marker in normalized for marker in FALLBACK_MARKERS)


def invoke_agent(
    user_message: str,
    session_id: str,
    agent_id: str,
    agent_alias_id: str,
    region: str = "us-east-1",
    response_override: dict | None = None,
) -> dict[str, Any]:
    bedrock_agent = boto3.client("bedrock-agent-runtime", region_name=region)
    
    params = {
        "agentId": agent_id,
        "agentAliasId": agent_alias_id,
        "sessionId": session_id,
    }
    
    session_state = {}
    if response_override:
        session_state["invocationId"] = response_override["invocationId"]
        session_state["returnControlInvocationResults"] = response_override["results"]
    else:
        params["inputText"] = user_message

    params["sessionState"] = session_state

    response = bedrock_agent.invoke_agent(**params)

    raw_parts: list[str] = []
    for event in response.get("completion", []):
        chunk = event.get("chunk", {})
        if "bytes" in chunk:
            raw_parts.append(chunk["bytes"].decode("utf-8"))
        elif "returnControl" in event:
            print(f"DEBUG: Agent returned control: {json.dumps(event['returnControl'], indent=2)}")
            return {"returnControl": event["returnControl"]}
        elif "trace" in event:
            pass

    raw = "".join(raw_parts).strip()
    return {
        "text": raw,
        "intent": "fallback" if is_fallback(raw) else "bedrock",
        "raw": raw,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--message", "--query", dest="message", default="Who are the top 10 expensive patients?")
    parser.add_argument("--session-id", default=str(uuid.uuid4()))
    parser.add_argument("--agent-id", default=os.getenv("BEDROCK_AGENT_ID", "Q3IT7IQOEX"))
    parser.add_argument("--alias-id", default=os.getenv("BEDROCK_AGENT_ALIAS_ID", "OLQQYHBDML"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    args = parser.parse_args()

    current_message = args.message
    session_id = args.session_id
    response_override = None

    while True:
        result = invoke_agent(
            current_message,
            session_id=session_id,
            agent_id=args.agent_id,
            agent_alias_id=args.alias_id,
            region=args.region,
            response_override=response_override,
        )

        if "returnControl" in result:
            rc = result["returnControl"]
            invocation_id = rc["invocationId"]
            action_group_request = rc["agentTool"]["toolInput"]["actionGroupRequest"]
            api_path = action_group_request["apiPath"]
            action_group = action_group_request.get("actionGroup", "HealthcareActionGroup")
            http_method = action_group_request.get("httpMethod", "POST")
            parameters_list = action_group_request.get("parameters", [])
            parameters = {p["name"]: p["value"] for p in parameters_list}

            print(f"Agent requested action: {api_path} with params: {parameters}")

            operation_id = api_path.lstrip('/')
            server_url = f"http://localhost:5000/api/action/{operation_id}"
            
            try:
                server_response = requests.post(server_url, json=parameters)
                server_response.raise_for_status()
                api_result = server_response.json()
                print(f"Local server responded with: {json.dumps(api_result, indent=2)}")
            except requests.exceptions.RequestException as e:
                print(f"Error calling local server {server_url}: {e}")
                api_result = {"error": str(e)}
                server_response_status = 500
            else:
                server_response_status = server_response.status_code

            api_res_payload = {
                "apiResult": {
                    "actionGroup": action_group,
                    "apiPath": api_path,
                    "httpMethod": http_method,
                    "httpStatusCode": server_response_status,
                    "responseBody": {
                        "application/json": {
                            "body": json.dumps(api_result)
                        }
                    }
                }
            }

            response_override = {
                "invocationId": invocation_id,
                "results": [api_res_payload]
            }
            # For subsequent control returns, inputText is omitted
            current_message = ""
        else:
            # If no returnControl, it's the final response from the agent
            print(json.dumps(result, indent=2))
            break # Exit loop if final text is received


if __name__ == "__main__":
    main()

import asyncio
import json
import os
import sys
import logging
import re
from typing import Dict, List, Any, Optional, Type
 
import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, create_model
 
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
 
# MODERN LANGCHAIN IMPORTS
from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langchain_core.callbacks import BaseCallbackHandler
 
 
from gen_ai_hub.proxy.langchain.openai import ChatOpenAI
from file_ops import write_json,  save_clean_json, save_to_pdf, save_to_pdf_with_TAD, save_clean_pdf
 
 
# --------------------------------------------------
# WINDOWS UTF FIX
# --------------------------------------------------
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
 
# --------------------------------------------------
# LOGGING
# --------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("multi_mcp.log", encoding="utf-8"),
        # logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)
 
# --------------------------------------------------
# ENV
# --------------------------------------------------
load_dotenv()
 
# --------------------------------------------------
# MCP SERVERS
# --------------------------------------------------
MCP_SERVERS = {
    "integration_suite": "https://sap-integration-suite-mcp-lean-capybara-mb.cfapps.us10-001.hana.ondemand.com/mcp",
    "mcp_testing": "https://iflow-test-mcp-py-wise-fox-ay.cfapps.us10-001.hana.ondemand.com/mcp",
    "documentation_mcp": "https://Documentation-Agent-py-reflective-armadillo-kx.cfapps.us10-001.hana.ondemand.com/mcp",
}
 
TRANSPORT_OPTIONS = {
    "integration_suite": {"verify": True, "timeout": 60.0},
    "mcp_testing": {"verify": False, "timeout": 60.0},
    "documentation_mcp": {"verify": False, "timeout": 60.0},
}
 
MAX_RETRIES = 3
MEMORY_LIMIT = 12
 
SERVER_ROUTING_GUIDE = {
    "documentation_mcp": "Use for SAP-standard documentation/specification/template generation.",
    "integration_suite": "Use for iFlow and SAP Integration Suite design/creation/deployment tasks.",
    "mcp_testing": "Use for validation, test execution, and test-report related tasks.",
}
 
SAP_DOC_TEMPLATE = """
Documentation output contract (must follow exactly for documentation requests):
- Title line: "<Adapter Name> Guide"
- Subtitle line: "For SAP Integration Suite and SAP Cloud Integration"
- Version line: "Version <x.y.z> - <Month YYYY>"
- Add "Table of Contents"
- Use numbered sections and subsection numbering in this sequence:
  1. Introduction
  1.1 Coding Samples
  1.2 Internet Hyperlinks
  2. <Provider/Domain> Integration
  2.1 Introduction
  2.2 <Adapter Name> Adapter
  2.2.1 Features
  2.3 Architectural Overview
  3. Supported Operations
  4. Authentication & Authorization
  4.1 Creating Secure Parameter in Security Material
  4.2 Usage of the Secure Parameter
  5. <Provider/Domain> Configuration3
  6. Receiver Adapter Configuration
  6.1 Connection
  6.2 Processing Configuration
  7. Payload and Dynamic Configuration
  7.1 Message Payloads
  7.2 Dynamic Configuration
  8. Troubleshooting
  9. Sample Scenarios Explained
  10. References
  11. API Deprecation Notice
- Content requirements:
  - Write in SAP help-guide style: precise, neutral, implementation-focused.
  - Include concrete fields/parameters, supported operations, and example scenario bullets.
  - Mention limitations, auth handling, and troubleshooting error mappings (401/400/404 at minimum).
  - Do not skip any section; if unknown, write "Not applicable for current adapter scope."
""".strip()
 
 
# --------------------------------------------------
# LLM
# --------------------------------------------------
def create_llm():
    dep = os.getenv("LLM_DEPLOYMENT_ID")
    if not dep:
        raise RuntimeError("LLM_DEPLOYMENT_ID missing in .env")
    return ChatOpenAI(deployment_id=dep, temperature=0)
 
# --------------------------------------------------
# JSON SCHEMA → PYDANTIC MODEL
# --------------------------------------------------
def build_model(name: str, schema: Dict, root=None):
    if root is None:
        root = schema
 
    if "type" not in schema and "schema" in schema:
        schema = schema["schema"]
 
    if "$ref" in schema:
        ref = schema["$ref"][2:].split("/")
        obj = root
        for r in ref:
            obj = obj.get(r, {})
        return build_model(name, obj, root)
 
    if "enum" in schema:
        from typing import Literal
        return Literal[tuple(schema["enum"])]
 
    if schema.get("type") == "object":
        props = schema.get("properties", {})
        required = schema.get("required", [])
        fields = {}
        for k, v in props.items():
            t = build_model(name + "_" + k, v, root)
            default = ... if k in required else None
            fields[k] = (t, default)
        safe = re.sub(r"\W", "_", name)
        return create_model(safe, **fields)
 
    if schema.get("type") == "array":
        t = build_model(name + "_item", schema.get("items", {}), root)
        return List[t]
 
    return {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }.get(schema.get("type"), Any)
 
 
# --------------------------------------------------
# MCP TOOL WRAPPER
# --------------------------------------------------
class MCPTool(BaseTool):
    name: str
    description: str
    args_schema: Type[BaseModel]
    server: str
    mcp_tool_name: str
    manager: "MultiMCP"
 
    def _run(self, *a, **kw):
        raise NotImplementedError()
 
    async def _arun(self, **kwargs):
        return await self.manager.execute(self.server, self.mcp_tool_name, kwargs)
 
 
# --------------------------------------------------
# STEP LOGGER
# --------------------------------------------------
class StepLogger(BaseCallbackHandler):
    def __init__(self):
        self.steps = []
 
    def on_tool_start(self, serialized, input_str, **kw):
        self.steps.append({"tool": serialized["name"], "input": input_str})
 
    def on_tool_end(self, output, **kw):
        if self.steps:
            self.steps[-1]["output"] = str(output)
 
 
# --------------------------------------------------
# MULTI MCP MANAGER
# --------------------------------------------------
class MultiMCP:
    def __init__(self):
        self.clients: Dict[str, Client] = {}
        self.tools: List[MCPTool] = []
        self.llm = create_llm()
        self.agent = None
        self.memory: List[Dict[str, str]] = []
 
    def _safe_tool_name(self, server: str, tool_name: str) -> str:
        safe = re.sub(r"\W+", "_", f"{server}__{tool_name}").strip("_").lower()
        return safe[:64] if safe else f"{server}_tool"
 
    def _routing_hint_for_query(self, query: str) -> Optional[str]:
        q = query.lower()
        if any(k in q for k in ["document", "documentation", "spec", "template", "sap standard"]):
            return "documentation_mcp"
        if any(k in q for k in ["iflow", "integration flow", "integration suite", "deploy flow"]):
            return "integration_suite"
        if any(k in q for k in ["test", "testing", "validate", "verification", "assertion"]):
            return "mcp_testing"
        return None
 
    def _is_documentation_query(self, query: str) -> bool:
        q = query.lower()
        return any(
            k in q
            for k in [
                "document",
                "documentation",
                "guide",
                "spec",
                "template",
                "sap standard",
                "adapter guide",
            ]
        )
 
    # -----------------------------
    async def connect(self):
        for name, url in MCP_SERVERS.items():
            try:
                opts = TRANSPORT_OPTIONS.get(name, {})
 
                def factory(**kw):
                    kw["verify"] = opts.get("verify", True)
                    kw["timeout"] = opts.get("timeout", 30)
                    return httpx.AsyncClient(**kw)
 
                transport = StreamableHttpTransport(url, httpx_client_factory=factory)
                self.clients[name] = Client(transport=transport)
 
                logger.info(f"[OK] Connected → {name}")
 
            except Exception as e:
                logger.error(f"[FAIL] {name} → {e}")
 
    # -----------------------------
    async def discover_tools(self):
        self.tools.clear()
        used_names = set()
 
        async def load(server, client):
            async with client:
                raw = await client.list_tools()
                for t in raw:
                    schema = t.inputSchema or {}
                    Model = build_model(t.name + "_Input", schema)
                    agent_tool_name = self._safe_tool_name(server, t.name)
                    suffix = 2
                    while agent_tool_name in used_names:
                        agent_tool_name = f"{agent_tool_name}_{suffix}"
                        suffix += 1
                    used_names.add(agent_tool_name)
 
                    desc_prefix = f"[server={server}] {SERVER_ROUTING_GUIDE.get(server, '')}".strip()
                    full_desc = f"{desc_prefix} Original tool: {t.name}. {t.description or ''}".strip()
 
                    tool = MCPTool(
                        name=agent_tool_name,
                        description=full_desc,
                        args_schema=Model,
                        server=server,
                        mcp_tool_name=t.name,
                        manager=self,
                    )
                    self.tools.append(tool)
 
        await asyncio.gather(*(load(n, c) for n, c in self.clients.items()))
        logger.info("Loaded %d tools", len(self.tools))
 
    # -----------------------------
    async def execute(self, server, tool, args):
        client = self.clients[server]
 
        for attempt in range(MAX_RETRIES):
            try:
                async with client:
                    res = await client.call_tool(tool, args)
 
                out = []
                for c in res.content:
                    if getattr(c, "text", None):
                        out.append(c.text)
                    elif getattr(c, "json", None):
                        out.append(json.dumps(c.json, indent=2))
                    else:
                        out.append(str(c))
 
                return "\n".join(out)
 
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    return f"ERROR: {e}"
                await asyncio.sleep(1)
 
    # -----------------------------
    async def build_agent(self):
        if not self.tools:
            raise RuntimeError("No MCP tools were discovered. Cannot build agent.")
 
        routing_text = "\n".join(
            f"- {name}: {guide}" for name, guide in SERVER_ROUTING_GUIDE.items()
        )
 
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=(
                "You are an SAP MCP automation agent.\n"
                "Select tools strictly by server responsibility.\n"
                "Server routing rules:\n"
                f"{routing_text}\n"
                "If the user asks for SAP-standard documentation, prioritize documentation_mcp tools first.\n"
                "If the task is iFlow creation, prioritize integration_suite tools.\n"
                "If the task is testing or validation, prioritize mcp_testing tools.\n"
                "Do not mix servers unless explicitly required."
            ),
        )
    def update_memory(self, user, assistant):
 
        self.memory.append({"role":"user","content":user})
        self.memory.append({"role":"assistant","content":assistant})
 
        if len(self.memory) > MEMORY_LIMIT:
            self.memory = self.memory[-MEMORY_LIMIT:]
 
    # -----------------------------
    async def ask(self, query: str):
        logger_cb = StepLogger()
        route_server = self._routing_hint_for_query(query)
        guidance = ""
        if route_server:
            guidance = (
                f"\n\nRouting hint: This request best matches `{route_server}`. "
                f"{SERVER_ROUTING_GUIDE.get(route_server, '')}"
            )
        if self._is_documentation_query(query):
            guidance += f"\n\n{SAP_DOC_TEMPLATE}"
 
        messages = list(self.memory)
        messages.append({"role": "user", "content": query + guidance})
 
        result = await self.agent.ainvoke(
            {"messages": messages},
            config={"callbacks": [logger_cb]},
        )
        
        write_json(json_value = str(result), json_file_name = "pipo_client_code_response.json")
        # print(type(response))
        
        agent_messages = result["messages"]

        structured_messages = []

        for idx, msg in enumerate(agent_messages):
            message_dict = {
                "index": idx,
                "type": msg.__class__.__name__,
                "content": msg.content,
            }

            # Tool calls (only AIMessage usually)
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                message_dict["tool_calls"] = msg.tool_calls

            # Tool name (only ToolMessage)
            if hasattr(msg, "name") and msg.name:
                message_dict["tool_name"] = msg.name

            # Response metadata if exists
            if hasattr(msg, "response_metadata") and msg.response_metadata:
                message_dict["response_metadata"] = msg.response_metadata

            structured_messages.append(message_dict)
        
        write_json(json_value = structured_messages, json_file_name = "pipo_client_code_parsed.json")
        
        save_to_pdf(str(structured_messages))
        
        # result_text = (
        #     result.content if hasattr(result, "content") else
        #     result["output"] if isinstance(result, dict) and "output" in result else
        #     str(result)
        # )
        # save_to_pdf_with_TAD(result_text)


        # result_str = str(result)                                         #single pdf file save
        # save_to_pdf(result_str, filename="agent_result.pdf")
        
        # save_clean_json(data = str(result), filename = "result2.json")    # for json file save    
 
        final_msg = result["messages"][-1]
        answer_text = final_msg.content if hasattr(final_msg, "content") else str(final_msg)
        self.update_memory(query, answer_text)
        
        result_str = str(answer_text)                                         #single pdf file save
        save_to_pdf(result_str, filename="final_message.pdf")    

        
          
 
        return {
            "answer": answer_text,
            "steps": logger_cb.steps,
        }
 
 
 
# --------------------------------------------------
# CLI LOOP
# --------------------------------------------------
async def cli():
    mcp = MultiMCP()
 
    print("\nConnecting servers...")
    await mcp.connect()
 
    print("Discovering tools...")
    await mcp.discover_tools()
 
    print("Building agent...")
    await mcp.build_agent()
 
    print("\nREADY. Type 'exit' to quit.\n")
 
    while True:
        q = input(">> ").strip()
        if q.lower() in {"exit", "quit"}:
            break
 
        res = await mcp.ask(q)
 
        print("\n--- RESULT ---")
        print(res["answer"])
 
        print("\n--- STEPS ---")
        for s in res["steps"]:
            print(s)
        print()
 
 
# --------------------------------------------------
# MAIN
# --------------------------------------------------
if __name__ == "__main__":
    asyncio.run(cli())
 
 
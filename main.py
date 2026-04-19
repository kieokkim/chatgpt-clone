import dotenv
dotenv.load_dotenv()

from openai import OpenAI
import asyncio
import base64
import copy
import streamlit as st
from agents import Agent, Runner, SQLiteSession, WebSearchTool, FileSearchTool, ImageGenerationTool, CodeInterpreterTool, HostedMCPTool
from agents.mcp.server import MCPServerStdio

client = OpenAI()

VECTOR_STORE_ID = "vs_69ddedc766288191826480d2b1c4a6c0"


class FilteredSQLiteSession(SQLiteSession):
    
    def _remove_action_recursive(self, obj):
        """재귀적으로 action 필드 제거"""
        if isinstance(obj, dict):
            cleaned = {k: v for k, v in obj.items() if k != "action"}
            return {k: self._remove_action_recursive(v) for k, v in cleaned.items()}
        elif isinstance(obj, list):
            return [self._remove_action_recursive(item) for item in obj]
        else:
            return obj

    async def get_items(self):
        items = await super().get_items()
        return [
            self._remove_action_recursive(copy.deepcopy(item)) for item in items
        ]

### 처음 로드할 때만 Agent 객체 생성(안해주면 rerun할때마다 새로 생성)


### 처음 로드할 때만 세션 생성(안해주면 rerun할때마다 새로 생성)
if "session" not in st.session_state:
    st.session_state["session"] = FilteredSQLiteSession(
        "chat-history",
        "chat-gpt-clone-memory.db",
    )
session = st.session_state["session"]


async def paint_history():
    messages = await session.get_items()

    for message in messages:
        if "role" in message:
            with st.chat_message(message["role"]):
                if message["role"] == "user":
                    content = message["content"]
                    if isinstance(content, str):
                        st.write(content)
                    elif isinstance(content, list):
                        for part in content:
                            if "image_url" in part:
                                st.image(part["image_url"])

                else:
                    if message["type"] == "message":
                        st.write(message["content"][0]["text"])
        if "type" in message:
            message_type = message["type"]
            if message_type == "web_search_call":
                with st.chat_message("ai"):
                    st.write("Searched the web...")
            elif message_type == "file_search_call":
                with st.chat_message("ai"):
                    st.write("Searched your file...")
            elif message_type == "image_generation_call":
                image = base64.b64decode(message["result"])
                with st.chat_message("ai"):
                    st.image(image)
            elif message_type == "code_interpreter_call":
                with st.chat_message("ai"):
                    st.code(message["code"])
            elif message_type == "mcp_list_tools":
                with st.chat_message("ai"):
                    st.write(f"Listed '{message["server_label"]}'s tools")
            elif message_type == "mcp_call":
                with st.chat_message("ai"):
                    st.write(f"Called {message["server_label"]}'s [{message["name"]}] with args:[{message["arguments"]}]")

asyncio.run(paint_history())

def update_status(status_container, event):
    status_messages = {
        'response.web_search_call.completed': ("✅ Web Search Completed", "complete"),
        'response.web_search_call.in_progress': ("🔎 Starting Web Search", "running"),
        'response.web_search_call.searching': ("🔎 Web Search in progress", "running"),
        'response.file_search_call.completed': ("✅ File Search Completed", "complete"),
        'response.file_search_call.in_progress': ("📁 Starting File Search", "running"),
        'response.file_search_call.searching': ("📁 File Search in progress", "running"),
        'response.image_generation_call.generating': ("🎨 Drawing image...", "running"),
        'response.image_generation_call.in_progress': ("🎨 Drawing image...", "running"),
        'response.code_interpreter_call_code.done': ("🤖 Ran Code.","complete"),
        'response.code_interpreter_call.completed': ("🤖 Ran Code.","complete"),
        'response.code_interpreter_call.in_progress': ("🤖 Running Code.","running"),
        'response.code_interpreter_call.interpreting': ("🤖 Running Code.","running"),
        'response.mcp_call.completed': ("⚒️ Called MCP Tool","complete"),
        'response.mcp_call.failed': ("⚒️ Error calling MCP Tool","complete"),
        'response.mcp_call.in_progress': ("⚒️ Calling MCP Tool","running"),
        'response.mcp_list_tools.completed': ("⚒️ Listed MCP Tool","complete"),
        'response.mcp_list_tools.failed': ("⚒️ Error listing MCP Tool","complete"),
        'response.mcp_list_tools.in_progress: ("⚒️ Listing MCP Tool","running")'
        'response.completed': ("✅", "complete")
    }

    if event in status_messages:
        label, state = status_messages[event]
        status_container.update(label=label, state=state)

async def run_agent(message):
    yfinance_server = MCPServerStdio(
        params={
            "command": "uvx",
            "args": ["mcp-yahoo-finance"],
        },
        cache_tools_list=True,
        client_session_timeout_seconds=60
    )

    timezone_server = MCPServerStdio(
        params={
            "command":"uvx",
            "args": ["mcp-server-time","--local-timezone=America/New_York"]
        }
    )

    async with yfinance_server, timezone_server: 
        agent = Agent(
            mcp_servers=[yfinance_server, timezone_server],
            name="chatGPT Clone",
            instructions="""
            You are helpful assistant.

            You have access to the following tools:
                - Web Search Tool : Use this when the user asks a questions that isn't in your training data. Use this to learn about current events.
                - File Search Tool : Use this tool when the user asked a question about facts related to themselves. Or when they ask questions about specific files.
                - Code Interpreter Tool : Use this tool when you need to write and run code to answer the user's question.
            """,
            tools=[
                WebSearchTool(),
                FileSearchTool(
                    vector_store_ids=[VECTOR_STORE_ID],
                    max_num_results=3,),
                ImageGenerationTool(
                    tool_config={
                        "type": "image_generation",
                        "quality":"high",
                        "output_format": "jpeg",
                        "moderation": "low",
                        "partial_images": 1,

                    }),
                CodeInterpreterTool(
                    tool_config={
                        "type":"code_interpreter",
                        "container": {
                            "type":"auto",},
                    }
                ),
                HostedMCPTool(
                    tool_config={
                        "server_url":"https://mcp.context7.com/mcp",
                        "type":"mcp",
                        "server_label":"Context7",
                        "server_description": "Use this to get the docs from software projects.",
                        "require_approval": "never",

                        
                    }
                )
            ]
        )

        with st.chat_message("ai"):
            status_container = st.status("⏳", expanded=False)
            code_placeholder = st.empty()
            image_placeholder = st.empty()
            search_placeholder = st.empty()
            text_placeholder = st.empty()
            response = ""
            code_response = ""

            st.session_state["code_placeholder"] = code_placeholder
            st.session_state["image_placeholder"] = image_placeholder
            st.session_state["search_placeholder"] = search_placeholder
            st.session_state["text_placeholder"] = text_placeholder

            stream = Runner.run_streamed(agent, message, session=session,)

            async for event in stream.stream_events():
                if event.type == "raw_response_event":
                    update_status(status_container, event.data.type)

                    if event.data.type == "response.output_text.delta":
                        response += event.data.delta
                        text_placeholder.write(response)

                    elif event.data.type == "response.code_interpreter_call_code.delta":
                        code_response += event.data.delta
                        code_placeholder.code(code_response)

                    elif event.data.type == "response.image_generation_call.partial_image":
                        image = base64.b64decode(event.data.partial_image_b64)
                        image_placeholder.image(image)



prompt = st.chat_input(
    "Write a message for your assistant.",
    accept_file=True,
    file_type=["txt", "jpg", "jpeg", "png"],
)

if prompt:

    if "code_placeholder" in st.session_state: 
        st.session_state["code_placeholder"].empty()
    if "image_placeholder" in st.session_state:
        st.session_state["image_placeholder"].empty()
    if "text_placeholder" in st.session_state:
        st.session_state["text_placeholder"].empty()

    file_uploaded=False
    for file in prompt.files:
        if file.type.startswith("text/"):
            with st.chat_message("ai"):
                with st.status("⏳ Uploadng file...") as status:
                    uploaded_file = client.files.create(
                        file=(file.name, file.getvalue()),
                        purpose="user_data",
                    )
                    status.update(label="⏳ Attaching file...")
                    client.vector_stores.files.create_and_poll(
                        vector_store_id=VECTOR_STORE_ID,
                        file_id=uploaded_file.id,
                    )
                    status.update(label="✅ File Uploaded", state="complete")
                    file_uploaded=True

        elif file.type.startswith("image/"):
            with st.status("⏳ Uploadng image...") as status:
                file_bytes = file.getvalue()
                base64_data = base64.b64encode(file_bytes).decode("utf-8")
                data_uri = f"data:{file.type};base64, {base64_data}"
                asyncio.run(
                    session.add_items(
                        [
                            {
                                "role":"user",
                                "content":[
                                    {
                                        "type":"input_image",
                                        "detail": "auto",
                                        "image_url": data_uri,
                                    }
                                ],
                            }
                        ]
                    )
                )
                status.update(label="✅ Image Uploaded", state="complete")
                
            with st.chat_message("human"):
                st.image(data_uri)


    if prompt.text:
        with st.chat_message("human"):
            st.write(prompt.text)

        asyncio.run(run_agent(prompt.text))


with st.sidebar:
    reset = st.button("reset memory")
    if reset:
        asyncio.run(session.clear_session())
    st.write(asyncio.run(session.get_items()))



## 메모리 저장하기
## 이전 대화 표현하기
## 실시간 타이핑 효과 내주기
import dotenv
dotenv.load_dotenv()
import asyncio
import streamlit as st
from agents import Agent, Runner, SQLiteSession, WebSearchTool

### 처음 로드할 때만 Agent 객체 생성(안해주면 rerun할때마다 새로 생성)
if "agent" not in st.session_state:
    st.session_state["agent"] = Agent(
        name="chatGPT Clone",
        instructions="""
        You are helpful assistant.

        You have access to the following tools:
            - Web Search Tool : Use this when the user asks a questions that isn't in your training data. Use this to learn about current events.
        """,
        tools=[WebSearchTool(
            
        ),]
    )
agent = st.session_state["agent"]

### 처음 로드할 때만 세션 생성(안해주면 rerun할때마다 새로 생성)
if "session" not in st.session_state:
    st.session_state["session"] = SQLiteSession(
        "chat-history",
        "chat-gpt-clone-memory.db",
    )
session = st.session_state["session"]


async def paint_history():
    messages = await session.get_items()

    for message in messages:
        if "role" in messages:
            with st.chat_message(message["role"]):
                if message["role"] == "user":
                    st.write(message["content"])
                else:
                    if message["type"] == "message":
                        st.write(message["content"][0]["text"])
        if "type" in message and message["type"] == "web_search_call":
            with st.chat_message("ai"):
                st.write("Searched the web...")

def update_status(status_container, event):
    status_messages = {
        'response.web_search_call.completed': ("✅ Web Search Completed", "complete"),
        'response.web_search_call.in_progress': ("🔎 Starting Web Search", "running"),
        'response.web_search_call.searching': ("🔎 Web Search in progress", "running"),
        'response.completed': ("✅", "complete")
    }

    if event in status_messages:
        label, state = status_messages[event]
        status_container.update(label=label, state=state)

asyncio.run(paint_history())

async def run_agent(message):
    with st.chat_message("ai"):
        text_placeholder = st.empty()
        response = ""

        status_container = st.status("⏳", expanded=False)
        stream = Runner.run_streamed(agent,message, session = session,)

        async for event in stream.stream_events():
            if event.type == "raw_response_event":

                update_status(status_container, event.data.type)
                if event.data.type == "response.output_text.delta":
                        response += event.data.delta
                        text_placeholder.write(response)




prompt = st.chat_input("Write a message for your assistant.")

if prompt:
    with st.chat_message("human"):
        st.write(prompt)
    asyncio.run(run_agent(prompt))


with st.sidebar:
    reset = st.button("reset memory")
    if reset:
        asyncio.run(session.clear_session())
    st.write(asyncio.run(session.get_items()))



## 메모리 저장하기
## 이전 대화 표현하기
## 실시간 타이핑 효과 내주기
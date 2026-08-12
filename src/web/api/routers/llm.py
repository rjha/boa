import os 
from fastapi import Response, status, APIRouter
from fastapi import Request
from openai import OpenAI

"""
To forward the port on SSL for testing using VPC bound model key,
(1) add an entry in /etc/hosts to route inference.do-ai.run to 127.0.0.1 

# Do inference testing
# 127.0.0.1 inference.do-ai.run

(2) open a port to remote machine,
sudo ssh -i ~/.ssh/id_rsa -L 443:inference.do-ai.run:443 user@remote-ip

"""

client = OpenAI(
    base_url="https://inference.do-ai.run/v1/",
    api_key=os.getenv("QWEN3_32B_KEY")
)


# do not include a final slash in the prefix
llm_router = APIRouter(prefix="/llm", tags=["LLM"], responses={404: {"description": "LLM router not found"}})

# noinspection SpellCheckingInspection
@llm_router.post("/qwen3/chat", status_code=200)
def process_qwen3_chat(prompt: str = "Explain the CAP theorem."):
    
    completion = client.chat.completions.create(
        model="alibaba-qwen3-32b",
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract the string content from the response object
    reply_content = completion.choices[0].message.content

    return {
        "status": "success",
        "model": "alibaba-qwen3-32b",
        "response": reply_content,
    }
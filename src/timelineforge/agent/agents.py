import asyncio
import os
from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from timelineforge.core import SyslogParser, WebLogParser, CSVParser, Exporter
from .tools import (
    grep, read_file, list_files, read_file, read_file_head
)

load_dotenv()

openrouter_provider = OpenAIProvider(
    base_url='https://openrouter.ai/api/v1',
    api_key=os.getenv('OPENROUTER_API_KEY'),
)

# Pass the provider and model name to OpenAIChatModel
model1 = OpenAIChatModel(
    'z-ai/glm-5.2',
    provider=openrouter_provider,
)

model2 = model1 = OpenAIChatModel(
    'nvidia/nemotron-3.5-lightning:free',
    provider=openrouter_provider,
)

log_exporter = Agent(
    model=model2,
    tools=[list_files, read_file],
    model_settings={'max_tokens': 2000},  # Set max tokens globally for the agent
    instructions=(
        "Search notes with list_files, grep, read_file. Cite files."
        "If evidence is missing, say so."
    ),
)

log_time_aggregator = Agent(
    model=model1,
    tools=[grep, list_files, read_file],
    model_settings={'max_tokens': 2000},  # Set max tokens globally for the agent
    instructions=(
        "Search notes with list_files, grep, read_file. Cite files."
        "If evidence is missing, say so."
    ),
)
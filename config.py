import os
import time
import functools
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables
load_dotenv()

# Initialize client
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# Model ID
PRO_MODEL_ID = "gemini-3-pro-image-preview"

# Output directory
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============ Timer Wrapper ============
class TimerStats:
    """Track generation timing statistics."""
    
    def __init__(self):
        self.calls = []
    
    def record(self, duration: float, model: str):
        self.calls.append({"duration": duration, "model": model, "timestamp": time.time()})
        
    def summary(self):
        if not self.calls:
            return "No calls recorded."
        total = sum(c["duration"] for c in self.calls)
        avg = total / len(self.calls)
        return f"Calls: {len(self.calls)} | Total: {total:.2f}s | Avg: {avg:.2f}s"


# Global stats instance
stats = TimerStats()


def _wrap_generate_content(original_method):
    """Wrap generate_content to add timing."""
    
    @functools.wraps(original_method)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = original_method(*args, **kwargs)
        duration = time.time() - start
        
        model = kwargs.get("model", "chat")
        stats.record(duration, model)
        print(f"⏱️  Generation took {duration:.2f}s")
        
        return result
    
    return wrapper


# Apply wrapper
client.models.generate_content = _wrap_generate_content(client.models.generate_content)


# Wrap chat.send_message as well
_original_chats_create = client.chats.create

def _wrap_chats_create(*args, **kwargs):
    chat = _original_chats_create(*args, **kwargs)
    chat.send_message = _wrap_generate_content(chat.send_message)
    return chat

client.chats.create = _wrap_chats_create